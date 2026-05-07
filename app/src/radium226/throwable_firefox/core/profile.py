import asyncio
import secrets
import shutil
import tempfile
import time
import urllib.request
from base64 import urlsafe_b64encode
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Self

import aiosqlite
from loguru import logger

from ._shell import run_and_wait
from .bookmark import BookmarkFolder, BookmarkItem
from .extension import Extension
from .proxy import Proxy

ARKENFOX_USER_JS_URL = "https://raw.githubusercontent.com/arkenfox/user.js/master/user.js"


def _generate_guid() -> str:
    return urlsafe_b64encode(secrets.token_bytes(9)).decode("ascii")


def _hash_url(url: str) -> int:
    # Mirrors Firefox's hash() SQL function (toolkit/components/places): the low 32 bits
    # are HashString(url), the next 16 bits are HashString(scheme) & 0xFFFF.
    golden = 0x9E3779B9
    mask = 0xFFFFFFFF

    def hash_bytes(data: bytes) -> int:
        h = 0
        for b in data:
            h = (golden * ((((h << 5) | (h >> 27)) & mask) ^ b)) & mask
        return h

    encoded = url.encode("utf-8")
    full_hash = hash_bytes(encoded)
    colon = encoded.find(b":")
    if colon > 0:
        prefix_hash = hash_bytes(encoded[:colon]) & 0xFFFF
        return (prefix_hash << 32) | full_hash
    return full_hash


class Profile:
    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        marionette_port: int | None = None,
        proxy: Proxy | None = None,
        extensions: list[Extension] | None = None,
        bookmarks: list[BookmarkItem] | None = None,
    ) -> AsyncIterator[Self]:
        extensions = extensions or []
        bookmarks = bookmarks or []

        base = Path(tempfile.gettempdir()) / "throwable-firefox" / "profiles"
        base.mkdir(parents=True, exist_ok=True)
        profile_folder_path = Path(tempfile.mkdtemp(dir=base))

        try:
            await cls._setup(
                profile_folder_path,
                proxy=proxy,
                extensions=extensions,
                bookmarks=bookmarks,
                marionette_port=marionette_port,
            )
            yield cls(path=profile_folder_path)
        finally:
            shutil.rmtree(profile_folder_path, ignore_errors=True)

    @classmethod
    async def _setup(
        cls,
        profile_folder_path: Path,
        proxy: Proxy | None,
        extensions: list[Extension],
        bookmarks: list[BookmarkItem],
        marionette_port: int | None,
    ) -> None:
        # await cls._setup_arkenfox_base(profile_folder_path)
        # await cls._setup_privacy(profile_folder_path)
        # await cls._setup_ai_and_telemetry(profile_folder_path)
        # await cls._setup_search_engine(profile_folder_path)
        await cls._setup_marionette(profile_folder_path, marionette_port)
        await cls._setup_proxy(profile_folder_path, proxy)
        await cls._setup_bookmarks_toolbar(profile_folder_path)
        await cls._setup_extensions(profile_folder_path, extensions)
        await cls._setup_proxy_cert(profile_folder_path, proxy)
        await cls._prestart_firefox(profile_folder_path, extensions, bookmarks)
        await cls._setup_bookmarks(profile_folder_path, bookmarks)

    @classmethod
    async def _setup_arkenfox_base(cls, profile_folder_path: Path) -> None:
        logger.debug("Downloading arkenfox user.js from {url}...", url=ARKENFOX_USER_JS_URL)
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, cls._fetch_arkenfox_user_js)
        user_js = profile_folder_path / "user.js"
        await loop.run_in_executor(None, lambda: user_js.write_bytes(content))
        logger.debug("Wrote arkenfox base user.js ({size} bytes)", size=len(content))

    @staticmethod
    def _fetch_arkenfox_user_js() -> bytes:
        with urllib.request.urlopen(ARKENFOX_USER_JS_URL, timeout=30) as response:
            return response.read()

    @classmethod
    async def _setup_privacy(cls, profile_folder_path: Path) -> None:
        logger.debug("Setting up privacy preferences...")
        lines = [
            'user_pref("browser.startup.page", 0);',
            'user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);',
            'user_pref("datareporting.policy.firstRunURL", "");',
            'user_pref("browser.aboutwelcome.enabled", false);',
            'user_pref("startup.homepage_welcome_url", "");',
            'user_pref("startup.homepage_welcome_url.additional", "");',
            'user_pref("startup.homepage_override.mstone", "ignore");',
            # Show bookmarks toolbar and suppress import prompt
            'user_pref("browser.toolbars.bookmarks.visibility", "always");',
            'user_pref("browser.bookmarks.addedImportButton", true);',
            'user_pref("browser.bookmarks.restore_default_bookmarks", false);',
        ]
        await cls._append_user_js(profile_folder_path, lines)

    @classmethod
    async def _setup_ai_and_telemetry(cls, profile_folder_path: Path) -> None:
        logger.debug("Disabling AI and telemetry...")
        lines = [
            # Telemetry
            'user_pref("toolkit.telemetry.enabled", false);',
            'user_pref("toolkit.telemetry.unified", false);',
            'user_pref("toolkit.telemetry.archive.enabled", false);',
            'user_pref("toolkit.telemetry.updatePing.enabled", false);',
            'user_pref("toolkit.telemetry.bhrPing.enabled", false);',
            'user_pref("toolkit.telemetry.firstShutdownPing.enabled", false);',
            'user_pref("toolkit.telemetry.newProfilePing.enabled", false);',
            'user_pref("toolkit.telemetry.shutdownPingSender.enabled", false);',
            'user_pref("toolkit.telemetry.server", "");',
            # Data reporting
            'user_pref("datareporting.healthreport.uploadEnabled", false);',
            'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
            # Crash reporting
            'user_pref("breakpad.reportURL", "");',
            'user_pref("browser.tabs.crashReporting.sendReport", false);',
            'user_pref("browser.crashReports.unsubmittedCheck.autoSubmit2", false);',
            # Studies and experiments
            'user_pref("app.shield.optoutstudies.enabled", false);',
            'user_pref("app.normandy.enabled", false);',
            'user_pref("messaging-system.rsexperimentloader.enabled", false);',
            # AI features
            'user_pref("browser.ml.chat.enabled", false);',
            'user_pref("browser.ml.chat.sidebar", false);',
            'user_pref("browser.ml.enable", false);',
            # Firefox Suggest / sponsored content
            'user_pref("browser.urlbar.suggest.quicksuggest.sponsored", false);',
            'user_pref("browser.urlbar.suggest.quicksuggest.nonsponsored", false);',
            'user_pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);',
            'user_pref("browser.newtabpage.activity-stream.showSponsored", false);',
            # Connectivity / captive portal checks
            'user_pref("network.captive-portal-service.enabled", false);',
            'user_pref("network.connectivity-service.enabled", false);',
        ]
        await cls._append_user_js(profile_folder_path, lines)

    @classmethod
    async def _setup_search_engine(cls, profile_folder_path: Path) -> None:
        logger.debug("Setting DuckDuckGo as default search engine...")
        await cls._append_user_js(profile_folder_path, [
            'user_pref("browser.search.defaultenginename", "DuckDuckGo");',
            'user_pref("browser.search.selectedEngine", "DuckDuckGo");'
        ])

    @classmethod
    async def _setup_marionette(cls, profile_folder_path: Path, marionette_port: int | None) -> None:
        if marionette_port is None:
            return
        logger.debug("Setting up marionette on port {port}...", port=marionette_port)
        await cls._append_user_js(profile_folder_path, [
            f'user_pref("marionette.port", {marionette_port});',
        ])

    @classmethod
    async def _setup_proxy(cls, profile_folder_path: Path, proxy: Proxy | None) -> None:
        if proxy is None:
            return
        logger.debug("Setting up proxy {proxy_host}:{proxy_port}...", proxy_host=proxy.host, proxy_port=proxy.port)
        await cls._append_user_js(profile_folder_path, [
            'user_pref("network.proxy.type", 1);',
            f'user_pref("network.proxy.http", "{proxy.host}");',
            f'user_pref("network.proxy.http_port", {proxy.port});',
            f'user_pref("network.proxy.ssl", "{proxy.host}");',
            f'user_pref("network.proxy.ssl_port", {proxy.port});',
            'user_pref("network.proxy.share_proxy_settings", true);',
            'user_pref("network.proxy.no_proxies_on", "localhost, 127.0.0.1");',
        ])

    @classmethod
    async def _setup_bookmarks_toolbar(cls, profile_folder_path: Path) -> None:
        logger.debug("Setting bookmarks toolbar to always visible...")
        await cls._append_user_js(profile_folder_path, [
            'user_pref("browser.toolbars.bookmarks.visibility", "always");',
        ])

    @classmethod
    async def _setup_extensions(cls, profile_folder_path: Path, extensions: list[Extension]) -> None:
        if not extensions:
            return
        logger.debug("Setting up {count} extension(s)...", count=len(extensions))
        await cls._append_user_js(profile_folder_path, ['user_pref("extensions.autoDisableScopes", 0);'])
        ext_dir = profile_folder_path / "extensions"
        ext_dir.mkdir(exist_ok=True)
        for ext in extensions:
            addon_id = ext.addon_id()
            shutil.copy2(str(ext.path), str(ext_dir / f"{addon_id}.xpi"))
            logger.debug("Installed extension {addon_id}", addon_id=addon_id)

    @classmethod
    async def _setup_proxy_cert(cls, profile_folder_path: Path, proxy: Proxy | None) -> None:
        if proxy is None:
            return
        logger.debug("Installing proxy CA certificate...")
        await run_and_wait(
            [
                "certutil",
                "-A",
                "-n",
                "Throwable Firefox MITM CA",
                "-t",
                "CT,C,C",
                "-i",
                str(proxy.ca_cert_path),
                "-d",
                f"sql:{profile_folder_path}",
            ]
        )

    @classmethod
    async def _setup_bookmarks(cls, profile_folder_path: Path, bookmarks: list[BookmarkItem]) -> None:
        if not bookmarks:
            return
        logger.debug("Setting up {count} top-level bookmark item(s)...", count=len(bookmarks))
        places_path = profile_folder_path / "places.sqlite"
        # parent=3 is the Bookmarks Toolbar folder in Firefox
        toolbar_parent_id = 3
        now = time.time_ns() // 1000

        async def next_id(db: aiosqlite.Connection, table: str) -> int:
            row = await db.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}")
            fetched = await row.fetchone()
            assert fetched is not None
            (n,) = fetched
            return n

        async def delete_subtree(db: aiosqlite.Connection, parent_id: int) -> None:
            cursor = await db.execute("SELECT id FROM moz_bookmarks WHERE parent = ?", (parent_id,))
            children = [row[0] for row in await cursor.fetchall()]
            for child_id in children:
                await delete_subtree(db, child_id)
            await db.execute("DELETE FROM moz_bookmarks WHERE parent = ?", (parent_id,))

        async def insert_items(
            db: aiosqlite.Connection, items: list[BookmarkItem], parent_id: int
        ) -> None:
            for position, item in enumerate(items):
                if isinstance(item, BookmarkFolder):
                    folder_id = await next_id(db, "moz_bookmarks")
                    await db.execute(
                        "INSERT INTO moz_bookmarks(id, type, parent, position, title, "
                        "dateAdded, lastModified, guid) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (folder_id, 2, parent_id, position, item.title, now, now, _generate_guid()),
                    )
                    await insert_items(db, item.children, folder_id)
                else:
                    place_id = await next_id(db, "moz_places")
                    await db.execute(
                        "INSERT INTO moz_places(id, url, title, url_hash, guid, foreign_count) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (place_id, item.url, item.title, _hash_url(item.url), _generate_guid(), 1),
                    )
                    bookmark_id = await next_id(db, "moz_bookmarks")
                    await db.execute(
                        "INSERT INTO moz_bookmarks(id, type, fk, parent, position, title, "
                        "dateAdded, lastModified, guid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            bookmark_id, 1, place_id, parent_id, position, item.title,
                            now, now, _generate_guid(),
                        ),
                    )

        async with aiosqlite.connect(str(places_path)) as db:
            await delete_subtree(db, toolbar_parent_id)
            await insert_items(db, bookmarks, toolbar_parent_id)
            await db.commit()

    @classmethod
    async def _prestart_firefox(
        cls, profile_folder_path: Path, extensions: list[Extension], bookmarks: list[BookmarkItem]
    ) -> None:
        if not extensions and not bookmarks:
            return
        logger.debug("Pre-starting Firefox to initialize profile...")
        pre_process = await asyncio.create_subprocess_exec(
            "librewolf",
            "--headless",
            "--first-startup",
            "--profile",
            str(profile_folder_path),
            start_new_session=True,
        )
        wait_for_files = []
        if extensions:
            wait_for_files.append(profile_folder_path / "extensions.json")
        if bookmarks:
            wait_for_files.append(profile_folder_path / "places.sqlite")
        await cls._wait_for_files(wait_for_files)
        pre_process.terminate()
        await pre_process.wait()
        # Firefox creates search.json.mozlz4 during prestart, which takes precedence over
        # browser.search.defaultenginename. Deleting it forces Firefox to rebuild from prefs
        # on the real launch.
        search_json = profile_folder_path / "search.json.mozlz4"
        if search_json.exists():
            search_json.unlink()
        logger.debug("Extension pre-start complete")

    @classmethod
    async def _wait_for_files(cls, files: list[Path], timeout: float = 10.0) -> None:
        for _ in range(int(timeout / 0.1)):
            if all(f.exists() for f in files):
                return
            await asyncio.sleep(0.1)

    @classmethod
    async def _append_user_js(cls, profile_folder_path: Path, lines: list[str]) -> None:
        user_js = profile_folder_path / "user.js"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: user_js.open("a").write("\n".join(lines) + "\n"))
