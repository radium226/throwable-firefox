from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Self

from loguru import logger

from .profile import Profile


class Browser:
    process: asyncio.subprocess.Process

    def __init__(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        self.process = process

    @classmethod
    @asynccontextmanager
    async def launch(
        cls,
        profile: Profile,
        headless: bool = False,
        private: bool = True,
        url: str | None = None,
        remote_control: bool = False,
    ) -> AsyncIterator[Self]:
        headless_args = ["--headless"] if headless else []
        private_args = ["--private-window"] if private else []
        remote_control_args = ["--marionette"] if remote_control else []
        url_args = [url] if url else []
        command = [
            "firefox",
            "-no-remote",
            "--new-instance",
            "--profile",
            str(profile.path),
            *headless_args,
            *private_args,
            *remote_control_args,
            *url_args,
        ]
        logger.debug("Launching Firefox: {command}", command=command)

        process = await asyncio.create_subprocess_exec(
            *command,
            start_new_session=True,
        )

        self = cls(process=process)
        try:
            yield self
        finally:
            await self.terminate()

    async def terminate(self) -> None:
        try:
            logger.debug("Terminating Firefox process group")
            pgid = os.getpgid(self.process.pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await asyncio.shield(self.process.wait())

    async def wait(self) -> None:
        await self.process.wait()


# async def _connect_selenium(profile: Profile) -> object:
#     from selenium.webdriver import Firefox, FirefoxOptions
#     from selenium.webdriver.firefox.service import Service

#     # Wait a moment for Firefox to start its Marionette socket
#     await asyncio.sleep(3)

#     loop = asyncio.get_event_loop()

#     def _connect() -> Firefox:
#         marionette_port = _read_marionette_port(profile)
#         service = Service(
#             service_args=[
#                 "--marionette-port", str(marionette_port),
#                 "--connect-existing",
#             ],
#         )
#         options = FirefoxOptions()
#         return Firefox(service=service, options=options)

#     return await loop.run_in_executor(None, _connect)


# def _read_marionette_port(profile: Profile) -> int:
#     user_js = profile.path / "user.js"
#     if user_js.exists():
#         for line in user_js.read_text().splitlines():
#             if "marionette.port" in line:
#                 # user_pref("marionette.port", 2828);
#                 port_str = line.split(",")[-1].strip().rstrip(");")
#                 return int(port_str)
#     return 2828  # Firefox default
