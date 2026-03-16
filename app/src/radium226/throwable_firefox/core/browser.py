from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Self

from loguru import logger

from .profile import Profile

if TYPE_CHECKING:
    from .proxy import Proxy


class Browser:

    _process: asyncio.subprocess.Process
    _proxy: Proxy | None
    driver: object | None  # selenium WebDriver or None

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        proxy: Proxy | None = None,
        driver: object | None = None,
    ) -> None:
        self._process = process
        self._proxy = proxy
        self.driver = driver

    @classmethod
    @asynccontextmanager
    async def launch(
        cls,
        profile: Profile,
        proxy: Proxy | None = None,
        headless: bool = False,
        private: bool = True,
        url: str | None = None,
        selenium: bool = False,
    ) -> AsyncIterator[Self]:
        command = [
            "firefox",
            "-no-remote",
            "--new-instance",
            "--profile", str(profile.path),
        ]
        if headless:
            command.append("--headless")
        if private:
            command.append("--private-window")
        if selenium:
            command.append("--marionette")
        if url is not None:
            command.append(url)

        logger.debug("Launching Firefox: {command}", command=command)
        process = await asyncio.create_subprocess_exec(
            *command,
            start_new_session=True,
        )

        driver = None
        if selenium:
            driver = await _connect_selenium(profile)

        instance = cls(process=process, proxy=proxy, driver=driver)
        try:
            yield instance
        finally:
            if driver is not None:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, driver.quit)
                except Exception as exc:
                    logger.warning("Error quitting Selenium driver: {exc}", exc=exc)
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            await process.wait()

    async def wait(self) -> None:
        loop = asyncio.get_event_loop()
        signal_event = asyncio.Event()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_event.set)

        process_task = asyncio.create_task(self._process.wait())
        signal_task = asyncio.create_task(signal_event.wait())

        try:
            done, pending = await asyncio.wait(
                [process_task, signal_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Kill mitmdump now so Firefox can drain its proxy connections and exit.
            # This must happen before we wait for the Firefox process in __aexit__.
            if self._proxy is not None:
                self._proxy.stop()

        # Propagate signal to Firefox's process group
        if signal_task in done:
            try:
                pgid = os.getpgid(self._process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass


async def _connect_selenium(profile: Profile) -> object:
    from selenium.webdriver import Firefox, FirefoxOptions
    from selenium.webdriver.firefox.service import Service

    # Wait a moment for Firefox to start its Marionette socket
    await asyncio.sleep(3)

    loop = asyncio.get_event_loop()

    def _connect() -> Firefox:
        marionette_port = _read_marionette_port(profile)
        service = Service(
            service_args=[
                "--marionette-port", str(marionette_port),
                "--connect-existing",
            ],
        )
        options = FirefoxOptions()
        return Firefox(service=service, options=options)

    return await loop.run_in_executor(None, _connect)


def _read_marionette_port(profile: Profile) -> int:
    user_js = profile.path / "user.js"
    if user_js.exists():
        for line in user_js.read_text().splitlines():
            if "marionette.port" in line:
                # user_pref("marionette.port", 2828);
                port_str = line.split(",")[-1].strip().rstrip(");")
                return int(port_str)
    return 2828  # Firefox default
