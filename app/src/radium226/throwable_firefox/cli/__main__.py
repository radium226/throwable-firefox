import asyncio
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import click
from loguru import logger
from radium226.vpn_passthrough.client import Client

from radium226.throwable_firefox.core import CreateProcess, CreateProcessResult, Firefox, Command

from radium226.throwable_firefox.core import (
    Bookmark,
    Extension,
    Firefox,
    HostAndPort,
    Profile,
)


class HostAndPortParamType(click.ParamType):
    name = "host:port"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> HostAndPort:
        try:
            return HostAndPort.parse(value)
        except ValueError:
            self.fail(f"'{value}' is not a valid host:port", param, ctx)


HOST_AND_PORT = HostAndPortParamType()


DEFAULT_VPN_PASSTHROUGH_SOCKET = Path("/run/vpn-passthrough/ipc.socket")


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extension_locations", multiple=True, type=str, help="Path or URL of a .xpi extension")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add")
@click.option("--private/--no-private", is_flag=True, help="Enable or disable private browsing mode")
@click.option("--marionette-address", default=None, type=HOST_AND_PORT, help="Marionette address (host:port)")
@click.option("--with-vpn-passthrough", is_flag=True, default=False, help="Run Firefox via the vpn-passthrough daemon")
def main(
    url: str | None,
    headless: bool,
    extension_locations: tuple[str, ...],
    bookmarks: tuple[tuple[str, str], ...],
    private: bool,
    marionette_address: HostAndPort | None,
    with_vpn_passthrough: bool,
) -> None:
    async def coro() -> None:
        nonlocal marionette_address
        marionette_address = marionette_address or HostAndPort.none()

        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        assert task is not None

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)

        try:
            async with AsyncExitStack() as exit_stack:
                def create_extension(location: str) -> Extension:
                    if location.startswith(("http://", "https://")):
                        logger.debug("Loading extension from URL: {url}", url=location)
                        return Extension.from_url(location)
                    else:
                        file_path = Path(location)
                        if not file_path.is_file():
                            raise ValueError(f"Extension file not found: {location}")
                        return Extension(file_path)

                extensions = [
                    create_extension(location)
                    for location in extension_locations
                ]

                create_process: CreateProcess | None = None
                if with_vpn_passthrough:
                    vpn_passthrough_client = await exit_stack.enter_async_context(
                        Client.connect(Path("/run/vpn-passthrough/ipc.socket"))
                    )

                    tunnel_created = await vpn_passthrough_client.create_tunnel(name="my_tunnel")
                    vpeer_ip = tunnel_created.vpeer_ip
                    marionette_address = marionette_address.merge_with(HostAndPort(host=vpeer_ip, port=None))

                    async def create_process(command: Command) -> CreateProcessResult:
                        logger.debug("Creating process via vpn-passthrough with command: {command}", command=command)
                        process_id = await vpn_passthrough_client.run_process(command)
                        logger.debug("Process created with PID {pid}", pid=process_id)

                        async def kill_process() -> None:
                            logger.debug("Killing process via vpn-passthrough with PID {pid}", pid=process_id)
                            await vpn_passthrough_client.kill_process(process_id)

                        async def wait_for_process() -> int:
                            exit_code = await vpn_passthrough_client.wait_for_process(process_id)
                            logger.debug("Process with PID {pid} exited with code {code}", pid=process_id, code=exit_code)
                            return exit_code

                        return CreateProcessResult(kill_process=kill_process, wait_for_process=wait_for_process)

                profile = await exit_stack.enter_async_context(
                    Profile.create(
                        proxy=None,
                        extensions=extensions,
                        bookmarks=[Bookmark(title=t, url=u) for t, u in bookmarks],
                        marionette_address=marionette_address,
                    )
                )

                browser = await exit_stack.enter_async_context(
                    Firefox.launch(
                        profile,
                        headless=headless,
                        private=private,
                        url=url,
                        with_marionette=marionette_address is not None,
                    )
                )

                await browser.wait()
        except asyncio.CancelledError:
            pass

    asyncio.run(coro())
