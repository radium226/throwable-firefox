import asyncio
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import click
from click.core import ParameterSource
from loguru import logger
from radium226.vpn_passthrough.client import Client, ClientConfig

from radium226.throwable_firefox.core import (
    Bookmark,
    CreateProcess,
    Extension,
    Firefox,
    Preset,
    Profile,
    create_process_through_vpn,
    find_default_preset,
    resolve_preset,
)


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extension_locations", multiple=True, type=str, help="Path or URL of a .xpi extension")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add")
@click.option("--preset", "preset_value", default=None, type=str, help="Preset name or path to a YAML preset file")
@click.option("--private/--no-private", is_flag=True, default=True, help="Enable or disable private browsing mode")
@click.option("--marionette/--no-marionette", is_flag=True, default=False, help="Enable Marionette")
@click.option("--marionette-port", default=2828, type=int, help="Marionette port")
@click.option("--with-vpn/--without-vpn", is_flag=True, default=True, help="Run Firefox via the vpn-passthrough daemon")
@click.pass_context
def main(
    ctx: click.Context,
    url: str | None,
    headless: bool,
    extension_locations: tuple[str, ...],
    bookmarks: tuple[tuple[str, str], ...],
    preset_value: str | None,
    private: bool,
    marionette: bool,
    marionette_port: int,
    with_vpn: bool,
) -> None:
    async def coro() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_event.set)

        try:
            async with AsyncExitStack() as exit_stack:
                preset: Preset | None = (
                    resolve_preset(preset_value) if preset_value is not None else find_default_preset()
                )
                if preset is not None:
                    logger.debug("Applying preset {name}", name=preset.name)
                    if (
                        ctx.get_parameter_source("private") != ParameterSource.COMMANDLINE
                        and preset.private is not None
                    ):
                        private = preset.private
                    if (
                        ctx.get_parameter_source("marionette") != ParameterSource.COMMANDLINE
                        and preset.marionette is not None
                    ):
                        marionette = preset.marionette

                preset_bookmarks = preset.bookmarks if preset else []
                final_bookmarks = preset_bookmarks + [Bookmark(title=t, url=u) for t, u in bookmarks]

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
                if with_vpn:
                    vpn_passthrough_client = await exit_stack.enter_async_context(Client.connect(ClientConfig.load()))

                    regions = await vpn_passthrough_client.list_regions()
                    region_id = regions[0].region_id
                    logger.debug("Selected VPN region: {region_id}", region_id=region_id)
                    ports = [marionette_port] if marionette else []
                    tunnel_created = await vpn_passthrough_client.create_tunnel(
                        "throwable-firefox",
                        ports_to_forward_from_vpeer_to_loopback=ports,
                        dns_overrides=preset.dns_overrides if preset else {},
                        extra_routes=preset.extra_routes if preset else [],
                    )

                    exit_stack.push_async_callback(vpn_passthrough_client.destroy_tunnel, tunnel_created.name)

                    create_process = create_process_through_vpn(vpn_passthrough_client, tunnel_created.name)

                profile = await exit_stack.enter_async_context(
                    Profile.create(
                        proxy=None,
                        extensions=extensions,
                        bookmarks=final_bookmarks,
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

                async def _wait() -> int:
                    return await browser.wait()

                wait_task = asyncio.create_task(_wait())
                shutdown_task = asyncio.create_task(shutdown_event.wait())
                try:
                    await asyncio.wait(
                        {wait_task, shutdown_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    for t in (wait_task, shutdown_task):
                        if not t.done():
                            t.cancel()
        except asyncio.CancelledError:
            pass

    asyncio.run(coro())
