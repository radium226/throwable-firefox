import asyncio
from pathlib import Path

import click

from radium226.throwable_firefox.core import (
    Bookmark,
    Browser,
    Extension,
    Profile,
    Proxy,
)


@click.command()
@click.option("--url", default=None, help="URL to open on launch")
@click.option("--headless", is_flag=True, help="Run Firefox in headless mode")
@click.option("--extension", "extensions", multiple=True, type=Path, help="Path to a .xpi extension file")
@click.option("--bookmark", "bookmarks", multiple=True, type=(str, str), metavar="TITLE URL", help="Bookmark to add (title url)")
@click.option("--no-proxy", is_flag=True, help="Launch without MITM proxy")
@click.option("--no-private", is_flag=True, help="Disable private browsing mode")
@click.option("--selenium/--no-selenium", default=False, help="Enable or disable Marionette/Selenium WebDriver")
def main(
    url: str | None,
    headless: bool,
    extensions: tuple[Path, ...],
    bookmarks: tuple[tuple[str, str], ...],
    no_proxy: bool,
    no_private: bool,
    selenium: bool,
) -> None:
    asyncio.run(_run(
        url=url,
        headless=headless,
        extensions=list(extensions),
        bookmarks=list(bookmarks),
        with_proxy=not no_proxy,
        private=not no_private,
        selenium=selenium,
    ))


async def _run(
    url: str | None,
    headless: bool,
    extensions: list[Path],
    bookmarks: list[tuple[str, str]],
    with_proxy: bool,
    private: bool,
    selenium: bool,
) -> None:
    ext_objects = [Extension(p) for p in extensions]
    bm_objects = [Bookmark(title=t, url=u) for t, u in bookmarks]
    marionette_port = 2828 if selenium else None

    if with_proxy:
        async with Proxy.start() as proxy:
            async with Profile.create(
                proxy=proxy,
                extensions=ext_objects,
                bookmarks=bm_objects,
                marionette_port=marionette_port,
            ) as profile:
                async with Browser.launch(
                    profile,
                    proxy=proxy,
                    headless=headless,
                    private=private,
                    url=url,
                    selenium=selenium,
                ) as browser:
                    await browser.wait()
    else:
        async with Profile.create(
            extensions=ext_objects,
            bookmarks=bm_objects,
            marionette_port=marionette_port,
        ) as profile:
            async with Browser.launch(
                profile,
                headless=headless,
                private=private,
                url=url,
                selenium=selenium,
            ) as browser:
                await browser.wait()


if __name__ == "__main__":
    main()
