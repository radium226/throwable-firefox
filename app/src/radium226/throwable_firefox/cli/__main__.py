import asyncio
import signal
import tempfile
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
    encrypt_preset_bytes,
    find_default_preset,
    get_preset_password,
    list_presets,
    load_preset_from_path,
    preset_path,
    resolve_preset,
)


class _DefaultRunGroup(click.Group):
    """Click group that falls through to the 'run' subcommand when no command is given."""

    ignore_unknown_options = True

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            args = ["run"]
        return super().parse_args(ctx, args)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            ctx.meta["_default_arg0"] = cmd_name
            return super().get_command(ctx, "run")
        return cmd

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name, cmd, remaining = super().resolve_command(ctx, args)
        if "_default_arg0" in ctx.meta:
            remaining = [ctx.meta["_default_arg0"], *remaining]
        return cmd_name, cmd, remaining


@click.group(cls=_DefaultRunGroup)
def main() -> None:
    pass


@main.command("run")
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
def run(
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


_PRESET_TEMPLATE = """\
# name: {name}
default: false
# private: true
# marionette: false
# bookmarks:
#   - title: "Example"
#     url: "https://example.com"
# dns_overrides:
#   internal.example.com:
#     - "10.0.0.1"
# extra_routes:
#   - "10.0.0.0/8"
"""


@main.command("create-preset")
@click.argument("name")
@click.option("--encrypted/--no-encrypted", default=False, help="Encrypt the preset with a password")
def create_preset(name: str, encrypted: bool) -> None:
    dest = preset_path(name, encrypted)
    if dest.exists():
        raise click.ClickException(f"Preset already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    password: str | None = None
    if encrypted:
        password = get_preset_password(confirm=True)

    template = _PRESET_TEMPLATE.format(name=name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(template)
        tmp_path = Path(tmp.name)

    try:
        click.edit(filename=str(tmp_path))
        content = tmp_path.read_bytes()
        if encrypted and password is not None:
            dest.write_bytes(encrypt_preset_bytes(content, password))
        else:
            dest.write_bytes(content)
    finally:
        tmp_path.unlink(missing_ok=True)

    click.echo(f"Preset saved: {dest}")


@main.command("edit-preset")
@click.argument("name")
def edit_preset(name: str) -> None:
    plain = preset_path(name, encrypted=False)
    encrypted_path = preset_path(name, encrypted=True)

    if plain.is_file():
        click.edit(filename=str(plain))
        return

    if not encrypted_path.is_file():
        raise click.ClickException(f"Preset {name!r} not found (looked for {plain} and {encrypted_path})")

    password = get_preset_password()
    preset = load_preset_from_path(encrypted_path, password)  # validates password before opening editor

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        import yaml
        tmp.write(yaml.dump(preset.model_dump(exclude_none=False), allow_unicode=True))
        tmp_path = Path(tmp.name)

    try:
        click.edit(filename=str(tmp_path))
        content = tmp_path.read_bytes()
        encrypted_path.write_bytes(encrypt_preset_bytes(content, password))
    finally:
        tmp_path.unlink(missing_ok=True)

    click.echo(f"Preset saved: {encrypted_path}")


@main.command("list-presets")
def list_presets_cmd() -> None:
    presets = list_presets()
    if not presets:
        click.echo("No presets found.")
        return
    for name, is_encrypted, is_default in presets:
        tags: list[str] = []
        if is_encrypted:
            tags.append("encrypted")
        if is_default:
            tags.append("default")
        suffix = f"  ({', '.join(tags)})" if tags else ""
        click.echo(f"{name}{suffix}")
