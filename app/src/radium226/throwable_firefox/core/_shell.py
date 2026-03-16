import asyncio
from typing import IO


async def run(
    command: list[str],
    stdin: int | IO | None = None,
    stdout: int | IO | None = None,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *command,
        stdin=stdin,
        stdout=stdout,
    )


async def run_and_wait(
    command: list[str],
    stdin: int | IO | None = None,
    stdout: int | IO | None = None,
) -> None:
    process = await run(command, stdin=stdin, stdout=stdout)
    returncode = await process.wait()
    if returncode != 0:
        raise RuntimeError(f"Command {command!r} exited with code {returncode}")
