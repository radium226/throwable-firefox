import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from textwrap import dedent
from typing import Self

import aiosqlite
from loguru import logger

from ._shell import run_and_wait
from .bookmark import Bookmark
from .extension import Extension
from .proxy import Proxy


class Profile:

    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        proxy: Proxy | None = None,
        extensions: list[Extension] | None = None,
        bookmarks: list[Bookmark] | None = None,
        marionette_port: int | None = None,
    ) -> AsyncIterator[Self]:
        extensions = extensions or []
        bookmarks = bookmarks or []

        base = Path(tempfile.gettempdir()) / "throwable-firefox" / "profiles"
        base.mkdir(parents=True, exist_ok=True)
        profile_path = Path(tempfile.mkdtemp(dir=base))

        try:
            await cls._initialize(
                profile_path,
                proxy=proxy,
                extensions=extensions,
                bookmarks=bookmarks,
                marionette_port=marionette_port,
            )
            yield cls(path=profile_path)
        finally:
            shutil.rmtree(profile_path, ignore_errors=True)

    @classmethod
    async def _initialize(
        cls,
        profile_path: Path,
        proxy: Proxy | None,
        extensions: list[Extension],
        bookmarks: list[Bookmark],
        marionette_port: int | None,
    ) -> None:
        logger.debug("Creating Firefox profile at {path}", path=profile_path)

        # 1. Let Firefox create the profile skeleton
        await run_and_wait([
            "firefox",
            "-no-remote",
            "-CreateProfile", f"Throwable {profile_path}",
        ])

        # 2. Write user.js
        user_js_lines: list[str] = [
            'user_pref("extensions.autoDisableScopes", 0);',
            'user_pref("browser.startup.page", 0);',
        ]
        if marionette_port is not None:
            user_js_lines.append(f'user_pref("marionette.port", {marionette_port});')
        if proxy is not None:
            user_js_lines += [
                'user_pref("network.proxy.type", 1);',
                f'user_pref("network.proxy.http", "{proxy.host}");',
                f'user_pref("network.proxy.http_port", {proxy.port});',
                f'user_pref("network.proxy.ssl", "{proxy.host}");',
                f'user_pref("network.proxy.ssl_port", {proxy.port});',
                'user_pref("network.proxy.share_proxy_settings", true);',
                'user_pref("network.proxy.no_proxies_on", "localhost, 127.0.0.1");',
            ]
        (profile_path / "user.js").write_text("\n".join(user_js_lines) + "\n")

        # 3. Write xulstore.json (show bookmarks toolbar)
        (profile_path / "xulstore.json").write_text(
            '{"chrome://browser/content/browser.xul":{"PersonalToolbar":{"collapsed":"false"}}}'
        )

        # 4. Install extensions
        if extensions:
            ext_dir = profile_path / "extensions"
            ext_dir.mkdir(exist_ok=True)
            for ext in extensions:
                addon_id = ext.addon_id()
                shutil.copy2(str(ext.path), str(ext_dir / f"{addon_id}.xpi"))
                logger.debug("Installed extension {addon_id}", addon_id=addon_id)

        # 5. Install MITM CA certificate via certutil
        if proxy is not None:
            await run_and_wait([
                "certutil",
                "-A",
                "-n", "Throwable Firefox MITM CA",
                "-t", "CT,C,C",
                "-i", str(proxy.ca_cert_path),
                "-d", f"sql:{profile_path}",
            ])

        # 6. Insert bookmarks via aiosqlite
        if bookmarks:
            places_path = profile_path / "places.sqlite"
            async with aiosqlite.connect(str(places_path)) as db:
                for bookmark in bookmarks:
                    row = await db.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM moz_places")
                    (place_id,) = await row.fetchone()
                    await db.execute(
                        "INSERT INTO moz_places(id, url, title) VALUES (?, ?, ?)",
                        (place_id, bookmark.url, bookmark.title),
                    )
                    row = await db.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM moz_bookmarks")
                    (bookmark_id,) = await row.fetchone()
                    await db.execute(
                        "INSERT INTO moz_bookmarks(id, type, fk, parent, title) VALUES (?, ?, ?, ?, ?)",
                        (bookmark_id, 1, place_id, 3, bookmark.title),
                    )
                await db.commit()

        # 7. Pre-start Firefox to register extensions
        if extensions:
            logger.debug("Pre-starting Firefox to register extensions...")
            pre_process = await asyncio.create_subprocess_exec(
                "firefox",
                "-no-remote",
                "--headless",
                "--profile", str(profile_path),
                start_new_session=True,
            )
            await asyncio.sleep(5)
            pre_process.terminate()
            await pre_process.wait()
            logger.debug("Extension pre-start complete")
