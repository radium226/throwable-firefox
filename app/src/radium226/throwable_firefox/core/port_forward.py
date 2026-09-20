import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from loguru import logger


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


@asynccontextmanager
async def forward_tcp_port(
    local_host: str,
    local_port: int,
    remote_host: str,
    remote_port: int,
) -> AsyncIterator[None]:
    """Relay TCP connections made to (local_host, local_port) to (remote_host, remote_port).

    Used so a service that is only reachable from the host through a non-loopback address
    (e.g. Marionette bound inside a vpn-passthrough network namespace) can still be reached
    at its usual 127.0.0.1 address.
    """

    async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        try:
            remote_reader, remote_writer = await asyncio.open_connection(remote_host, remote_port)
        except OSError as error:
            logger.warning(
                "Port forward: failed to connect to {host}:{port}: {error}",
                host=remote_host,
                port=remote_port,
                error=error,
            )
            client_writer.close()
            return

        await asyncio.gather(
            _pump(client_reader, remote_writer),
            _pump(remote_reader, client_writer),
        )

    server = await asyncio.start_server(handle_client, local_host, local_port)
    logger.debug(
        "Forwarding {local_host}:{local_port} to {remote_host}:{remote_port}",
        local_host=local_host,
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
    )
    try:
        yield
    finally:
        server.close()
        await server.wait_closed()
