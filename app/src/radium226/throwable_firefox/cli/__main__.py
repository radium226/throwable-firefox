import asyncio
import signal
from contextlib import AsyncExitStack
from pathlib import Path

import click

from radium226.throwable_firefox.core import (
    Bookmark,
    Browser,
    Extension,
    Profile,
)


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extensions", multiple=True, type=Path, help="Path to a .xpi extension file")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add")
@click.option("--private/--no-private", is_flag=True, help="Enable or disable private browsing mode")
def main(
    url: str | None,
    headless: bool,
    extensions: tuple[Path, ...],
    bookmarks: tuple[tuple[str, str], ...],
    private: bool,
) -> None:
    async def coro() -> None:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        assert task is not None

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)

        try:
            async with AsyncExitStack() as exit_stack:
                profile = await exit_stack.enter_async_context(
                    Profile.create(
                        proxy=None,
                        extensions=[Extension(p) for p in extensions],
                        bookmarks=[Bookmark(title=t, url=u) for t, u in bookmarks],
                        marionette_port=None,
                    )
                )

                browser = await exit_stack.enter_async_context(
                    Browser.launch(
                        profile,
                        headless=headless,
                        private=private,
                        url=url,
                    )
                )

                await browser.wait()
        except asyncio.CancelledError:
            pass

    asyncio.run(coro())
