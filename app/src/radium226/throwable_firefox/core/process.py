import asyncio
import os
import signal
import sys
from asyncio import shield
from asyncio.subprocess import Process, create_subprocess_exec
from dataclasses import dataclass
from typing import Awaitable, Callable, overload

from loguru import logger
from radium226.vpn_passthrough.client import Client

type Command = list[str]

type ExitCode = int

type KillProcess = Callable[[], Awaitable[None]]

type WaitForProcess = Callable[[], Awaitable[ExitCode]]


@dataclass
class CreateProcessResult:
    kill_process: KillProcess
    wait_for_process: WaitForProcess


type CreateProcess = Callable[[Command], Awaitable[CreateProcessResult]]



@overload
def create_process() -> CreateProcess: ...


@overload
def create_process(client: Client, tunnel_name: str) -> CreateProcess: ...


def create_process(client: Client | None = None, tunnel_name: str | None = None) -> CreateProcess:
    if client and tunnel_name:
        return create_process_through_vpn(client, tunnel_name)
    else:
        return create_local_process()



def create_local_process() -> CreateProcess:
    async def create_process(command: Command) -> CreateProcessResult:
        logger.debug("Creating process locally: {command}", command=command)
        process: Process = await create_subprocess_exec(
            *command,
            start_new_session=True,
        )

        async def kill_process() -> None:
            if process.returncode is not None:
                logger.debug("Process {pid} already exited, skipping kill", pid=process.pid)
                return
            logger.debug("Killing process locally with PID {pid}", pid=process.pid)
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            await shield(process.wait())

        async def wait_for_process() -> ExitCode:
            logger.debug("Waiting for process with PID {pid} to exit", pid=process.pid)
            return await process.wait()

        return CreateProcessResult(kill_process=kill_process, wait_for_process=wait_for_process)
    return create_process


def create_process_through_vpn(client: Client, tunnel_name: str) -> CreateProcess:
    async def create_process(command: Command) -> CreateProcessResult:
        logger.debug("Creating process via VPN passthrough: {command}", command=command)
        logger.debug("Tunnel name: {tunnel_name}", tunnel_name=tunnel_name)

        loop = asyncio.get_running_loop()
        pid_future: asyncio.Future[int] = loop.create_future()

        async def on_pid_received(pid: int) -> None:
            if not pid_future.done():
                pid_future.set_result(pid)

        task = asyncio.create_task(
            client.run_process(
                command[0],
                args=command[1:],
                tunnel_name=tunnel_name,
                fds=[sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()],
                on_pid_received=on_pid_received,
                ambient_capabilities=[],
            )
        )

        pid = await pid_future

        async def kill_process() -> None:
            if task.done() and not task.cancelled():
                logger.debug("Process {pid} already exited, skipping kill", pid=pid)
                return
            logger.debug("Killing process via VPN passthrough with PID {pid}", pid=pid)
            await client.kill_process(pid, signal.SIGTERM)

        async def wait_for_process() -> ExitCode:
            logger.debug("Waiting for process with PID {pid} to exit via VPN passthrough", pid=pid)
            return await task

        return CreateProcessResult(kill_process=kill_process, wait_for_process=wait_for_process)
    return create_process