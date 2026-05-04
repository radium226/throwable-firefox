from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Self

from loguru import logger

from .process import CreateProcess, ExitCode, create_local_process
from .profile import Profile


@dataclass
class Firefox:
    
    terminate: Callable[[], Awaitable[None]]
    wait: Callable[[], Awaitable[ExitCode]]

    @classmethod
    @asynccontextmanager
    async def launch(
        cls,
        profile: Profile,
        headless: bool = False,
        private: bool = True,
        url: str | None = None,
        with_marionette: bool = False,
        create_process: CreateProcess | None = None,
    ) -> AsyncIterator[Self]:
        create_process = create_process or create_local_process()
        
        headless_args = ["--headless"] if headless else []
        private_args = ["--private-window"] if private else []
        with_marionette_args = ["--marionette"] if with_marionette else []
        url_args = [url] if url else []
        profile_args = ["--profile", str(profile.path)]
        command = [
            "librewolf",
            "--new-instance",
            *profile_args,
            *headless_args,
            *private_args,
            *with_marionette_args,
            *url_args,
        ]
        logger.debug("Launching Firefox: {command}", command=command)

        create_process = create_process or create_local_process()
        result = await create_process(command)

        self = cls(terminate=result.kill_process, wait=result.wait_for_process)
        try:
            yield self
        finally:
            await self.terminate()


# @asynccontextmanager
# async def _launch_locally(cls: type[Firefox], command: list[str]) -> AsyncIterator[Firefox]:
#     process: Process = await create_subprocess_exec(
#         *command,
#         start_new_session=True,
#     )

#     async def terminate() -> None:
#         try:
#             pgid = os.getpgid(process.pid)
#             os.killpg(pgid, signal.SIGTERM)
#         except ProcessLookupError:
#             pass
#         await asyncio.shield(process.wait())

#     async def wait() -> None:
#         await process.wait()

#     self = cls(_terminate=terminate, _wait=wait)
#     try:
#         yield self
#     finally:
#         await self.terminate()


# @asynccontextmanager
# async def _launch_via_vpn_passthrough(
#     cls: type[Firefox], command: list[str], socket_file_path: Path
# ) -> AsyncIterator[Firefox]:
#     from radium226.vpn_passthrough.client import Client

#     async with Client.connect(socket_file_path) as vpn_client:
#         vpn_pid: int | None = None
#         pid_received = asyncio.Event()

#         async def on_pid_received(pid: int) -> None:
#             nonlocal vpn_pid
#             vpn_pid = pid
#             pid_received.set()

#         run_task: asyncio.Task[int] = asyncio.create_task(
#             vpn_client.run_process(
#                 command[0],
#                 args=command[1:],
#                 on_pid_received=on_pid_received,
#             )
#         )

#         await pid_received.wait()

#         async def terminate() -> None:
#             if vpn_pid is not None:
#                 await vpn_client.kill_process(vpn_pid, signal.SIGTERM)
#             await asyncio.shield(run_task)

#         async def wait() -> None:
#             await run_task

#         self = cls(_terminate=terminate, _wait=wait)
#         try:
#             yield self
#         finally:
#             await self.terminate()
