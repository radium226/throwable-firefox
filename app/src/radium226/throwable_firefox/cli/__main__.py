import asyncio
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import click
from loguru import logger

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
            host, port_str = value.rsplit(":", 1)
            return HostAndPort(host=host, port=int(port_str))
        except ValueError:
            self.fail(f"'{value}' is not a valid host:port", param, ctx)


HOST_AND_PORT = HostAndPortParamType()


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extension_locations", multiple=True, type=str, help="Path or URL of a .xpi extension")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add")
@click.option("--private/--no-private", is_flag=True, help="Enable or disable private browsing mode")
@click.option("--marionette-address", default=None, type=HOST_AND_PORT, help="Marionette address (host:port)")
def main(
    url: str | None,
    headless: bool,
    extension_locations: tuple[str, ...],
    bookmarks: tuple[tuple[str, str], ...],
    private: bool,
    marionette_address: HostAndPort | None,
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
