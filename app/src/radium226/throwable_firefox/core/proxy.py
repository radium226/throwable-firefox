import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Self

from loguru import logger

from ._shell import run_and_wait
from .http import HTTPFlow


type HTTPFlowMatcher = Callable[[HTTPFlow], bool]


def having_url_that_starts_with(prefix: str) -> HTTPFlowMatcher:
    def matcher(flow: HTTPFlow) -> bool:
        return flow.request.url.startswith(prefix)
    return matcher


class Proxy:

    ca_cert_path: Path
    host: str
    port: int
    flows: list[HTTPFlow]
    _process: asyncio.subprocess.Process | None

    def __init__(self, ca_cert_path: Path, host: str, port: int, flows: list[HTTPFlow]) -> None:
        self.ca_cert_path = ca_cert_path
        self.host = host
        self.port = port
        self.flows = flows
        self._process = None

    def stop(self) -> None:
        """Terminate mitmdump immediately. Safe to call multiple times."""
        if self._process is not None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass

    @classmethod
    async def _generate_certs(cls, folder: Path) -> Path:
        key_path = folder / "mitmproxy-ca.key"
        cert_path = folder / "mitmproxy-ca-cert.pem"
        combined_path = folder / "mitmproxy-ca.pem"

        await run_and_wait([
            "openssl", "genrsa",
            "-out", str(key_path),
            "2048",
        ])
        await run_and_wait([
            "openssl", "req", "-x509", "-new", "-nodes",
            "-key", str(key_path),
            "-sha256",
            "-out", str(cert_path),
            "-addext", "keyUsage=critical,keyCertSign",
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-subj", "/CN=Throwable Firefox MITM CA",
        ])
        combined_path.write_text(cert_path.read_text() + key_path.read_text())
        return cert_path

    @classmethod
    @asynccontextmanager
    async def start(cls, host: str = "127.0.0.1", port: int = 8080) -> AsyncIterator[Self]:
        with tempfile.TemporaryDirectory(prefix="throwable-firefox-proxy-") as tmp:
            tmp_path = Path(tmp)

            cert_path = await cls._generate_certs(tmp_path)

            addon_path = tmp_path / "mitm_addon.py"
            shutil.copy(Path(__file__).parent / "mitm_addon.py", addon_path)

            http_flow_read_fd, http_flow_write_fd = os.pipe()

            command = [
                "mitmdump",
                "--listen-host", host,
                "--listen-port", str(port),
                "--set", f"fd={http_flow_write_fd}",
                "--set", f"confdir={tmp_path}",
                "--script", str(addon_path),
            ]
            logger.debug("Starting mitmdump: {command}", command=command)
            process = await asyncio.create_subprocess_exec(
                *command,
                pass_fds=(http_flow_write_fd,),
            )
            os.close(http_flow_write_fd)

            flows: list[HTTPFlow] = []

            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            read_pipe = os.fdopen(http_flow_read_fd, "rb", buffering=0)
            transport, _ = await loop.connect_read_pipe(lambda: protocol, read_pipe)

            async def _read_flows() -> None:
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        flows.append(HTTPFlow.model_validate(json.loads(line)))
                    except Exception as exc:
                        logger.error("Failed to parse HTTP flow: {exc}", exc=exc)

            read_task = asyncio.create_task(_read_flows())

            # Give mitmdump time to start
            await asyncio.sleep(2.5)

            instance = cls(ca_cert_path=cert_path, host=host, port=port, flows=flows)
            instance._process = process
            try:
                yield instance
            finally:
                instance._process = None

                # Terminate mitmdump (may already be stopped via proxy.stop())
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass

                # Closing the transport sends EOF to the StreamReader so the read
                # task exits naturally; cancel it if it doesn't finish in time.
                transport.close()
                try:
                    await asyncio.wait_for(read_task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    read_task.cancel()
                    try:
                        await read_task
                    except asyncio.CancelledError:
                        pass

                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    async def wait_for_flow(self, matcher: HTTPFlowMatcher, timeout: float = 30.0) -> HTTPFlow:
        async def _poll() -> HTTPFlow:
            while True:
                for flow in self.flows:
                    if matcher(flow):
                        return flow
                await asyncio.sleep(0.5)

        return await asyncio.wait_for(_poll(), timeout=timeout)
