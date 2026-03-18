import asyncio
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import click
from loguru import logger
from radium226.vpn_passthrough.client import Client, ClientConfig

from radium226.throwable_firefox.core import (
    Bookmark,
    CreateProcess,
    Extension,
    Firefox,
    Profile,
    create_process_through_vpn,
)


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extension_locations", multiple=True, type=str, help="Path or URL of a .xpi extension")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add")
@click.option("--private/--no-private", is_flag=True, help="Enable or disable private browsing mode")
@click.option("--marionette/--no-marionette", is_flag=True, default=False, help="Enable Marionette")
@click.option("--marionette-port", default=2828, type=int, help="Marionette port")
@click.option("--behind-vpn", is_flag=True, default=False, help="Run Firefox via the vpn-passthrough daemon")
def main(
    url: str | None,
    headless: bool,
    extension_locations: tuple[str, ...],
    bookmarks: tuple[tuple[str, str], ...],
    private: bool,
    marionette: bool,
    marionette_port: int,
    behind_vpn: bool,
) -> None:
    async def coro() -> None:
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
                if behind_vpn:
                    vpn_passthrough_client = await exit_stack.enter_async_context(Client.connect(ClientConfig.load()))

                    regions = await vpn_passthrough_client.list_regions()
                    region_id = regions[0].region_id
                    logger.debug("Selected VPN region: {region_id}", region_id=region_id)
                    ports = [marionette_port] if marionette else []
                    tunnel_created = await vpn_passthrough_client.create_tunnel(
                        "throwable-firefox",
                        ports_to_forward_from_vpeer_to_loopback=ports,
                    )

                    create_process = create_process_through_vpn(vpn_passthrough_client, tunnel_created.name)

                profile = await exit_stack.enter_async_context(
                    Profile.create(
                        proxy=None,
                        extensions=extensions,
                        bookmarks=[Bookmark(title=t, url=u) for t, u in bookmarks],
                        marionette_port=marionette_port if marionette else None,
                    )
                )

                logger.info("Marionette port: {marionette_port}", marionette_port=marionette_port)
                browser = await exit_stack.enter_async_context(
                    Firefox.launch(
                        profile,
                        headless=headless,
                        private=private,
                        url=url,
                        with_marionette=marionette,
                        create_process=create_process,
                    )
                )

                await browser.wait()
        except asyncio.CancelledError:
            pass

    asyncio.run(coro())
