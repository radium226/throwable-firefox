from contextlib import contextmanager
import os
from typing import Self, Generator, Callable
from subprocess import Popen, run
from pathlib import Path
import json
from threading import Thread
from signal import SIGTERM
from loguru import logger
from select import select
from time import sleep, time
from fcntl import fcntl, F_SETFL
import shutil
from tempfile import mkdtemp

from .types import Host, Port, HTTPFlow, HostAndPort



type HTTPFlowMatcher = Callable[[HTTPFlow], bool]


def having_url_that_starts_with(prefix: str) -> HTTPFlowMatcher:
    def matcher(http_flow: HTTPFlow) -> bool:
        return http_flow.request.url.startswith(prefix)
    return matcher


@contextmanager
def create_temp_folder() -> Generator[Path, None, None]:
    folder_path = Path(mkdtemp())
    folder_path.mkdir(parents=True, exist_ok=True)
    try:
        yield folder_path
    finally:
        pass
        # shutil.rmtree(folder_path)


class Proxy():

    host: Host
    port: Port

    http_flows: list[HTTPFlow]
    cert_file_path: Path

    def __init__(self, host: Host, port: Port, http_flows: list[HTTPFlow], cert_file_path: Path) -> None:
        self.http_flows = http_flows
        self.host = host
        self.port = port
        self.cert_file_path = cert_file_path

    
    @property
    def location(self) -> HostAndPort:
        return HostAndPort(
            host=self.host,
            port=self.port,
        )
    

    @classmethod
    def _generate_certs(cls, folder_path: Path) -> Path:
        # openssl genrsa -out ca.key 2048
        run(["openssl", "genrsa", "-out", str(folder_path / "mitmproxy-ca.key"), "2048"], check=True)

        # openssl req -x509 -new -nodes -key ca.key -sha256 -out ca.crt -addext keyUsage=critical,keyCertSign -addext basicConstraints=critical,CA:TRUE,pathlen:0 -subj "/CN=My Mitm Proxy CA"
        run([
            "openssl", "req", "-x509", "-new", "-nodes",
            "-key", str(folder_path / "mitmproxy-ca.key"),
            "-sha256",
            "-out", str(folder_path / "mitmproxy-ca-cert.pem"),
            "-addext", "keyUsage=critical,keyCertSign",
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-subj", "/CN=My Mitm Proxy CA",
        ], check=True)

        (folder_path / "mitmproxy-ca.pem").write_text(
            (folder_path / "mitmproxy-ca-cert.pem").read_text() +
            (folder_path / "mitmproxy-ca.key").read_text()
        )

        return folder_path / "mitmproxy-ca-cert.pem"



    @classmethod
    @contextmanager
    def start(cls, host: Host, port: Port) -> Generator[Self, None, None]:
        with create_temp_folder() as temp_folder_path:

            cert_file_path = cls._generate_certs(temp_folder_path)
            addon_file_path = temp_folder_path / "mitm_addon.py"
            shutil.copy(
                ( Path(__file__).parent / "mitm_addon.py" ),
                addon_file_path,
            )

            http_flow_read_fd, http_flow_write_fd = os.pipe()
            stop_read_thread_read_fd, stop_read_thread_write_fd = os.pipe()

            fcntl(http_flow_read_fd, F_SETFL, os.O_NONBLOCK)
            fcntl(stop_read_thread_read_fd, F_SETFL, os.O_NONBLOCK)

            command = [
                "mitmdump",
                "--listen-host", host,
                "--listen-port", str(port),
                "--set", f"fd={http_flow_write_fd}",
                "--set", f"confdir={temp_folder_path}",
                "--script", str(addon_file_path),
            ]
            logger.debug("Starting mitmdump (command={command})", command=command)
            process = Popen(
                command,
                pass_fds=[
                    http_flow_write_fd,
                ],
            )

            http_flows: list[HTTPFlow] = []

            def read_thread_target(http_flow_read_fd: int, stop_read_thread_read_fd: int) -> None:
                logger.debug("Starting thread that reads...")
                should_stop = False
                while not should_stop:
                    logger.debug("Waiting for something to happen on the fds...")
                    fds_to_read, _, _ = select([http_flow_read_fd, stop_read_thread_read_fd], [], [])
                    logger.debug(f"select returned fds_to_read={fds_to_read}")
                    if stop_read_thread_read_fd in fds_to_read:
                        logger.debug("Stop signal received for the tread that reads! ")
                        should_stop = True
                        continue

                    if http_flow_read_fd not in fds_to_read:
                        logger.error("Unexpected behavior: http_flow_read_fd not in fds_to_read")
                        should_stop = True
                        continue


                    logger.debug("Reading buffer...")
                    buffer = b""
                    while True:
                        try:
                            logger.trace("Reading chunk... ")
                            chunk = os.read(http_flow_read_fd, 4096 * 1024)
                            buffer += chunk
                            logger.trace("Chunk has been read! ")
                        except BlockingIOError:
                            logger.trace("No more data available to read from http_flow_read_fd at the moment (would block).")
                            break
                    logger.trace("Buffer has been read! ")

                    lines = buffer.split(b"\n")
                    for line in lines:
                        if line.strip() == b"":
                            continue

                        try:
                            obj = json.loads(line)
                            logger.trace(f"{obj=}")
                            http_flow = HTTPFlow.model_validate(obj)
                            http_flows.append(http_flow)
                            logger.trace("Appended new HTTP flow read from http_flow_read_fd (http_flow={http_flow})", http_flow=http_flow)
                        except Exception as e:
                            logger.error(f"Failed to parse HTTP flow from line: {line!r}, error: {e}")
                            continue

                logger.debug("Thread that reads is done! ")

            instance = cls(
                host=host,
                port=port,
                http_flows=http_flows,
                cert_file_path=cert_file_path,
            )

            read_thread = Thread(
                target=read_thread_target,
                args=(
                    http_flow_read_fd, 
                    stop_read_thread_read_fd,
                ),
            )

            read_thread.start()
            try:
                sleep(2.5)  # FIXME: Replace with something like wait_for_port_to_be_open()
                yield instance
            finally:
                os.write(stop_read_thread_write_fd, b"STOP")
                read_thread.join()
                os.close(stop_read_thread_write_fd)
                os.close(stop_read_thread_read_fd)

                process.send_signal(SIGTERM)
                process.wait()

                os.close(http_flow_read_fd)
                os.close(http_flow_write_fd)


    def wait_for_http_flow(self, http_flow_matcher: HTTPFlowMatcher, timeout: float = 10.0) -> HTTPFlow:
        start_time = time()
        while True:
            for http_flow in self.http_flows:
                if http_flow_matcher(http_flow):
                    return http_flow
            if time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for HTTP flow matching criteria")
            sleep(0.5)