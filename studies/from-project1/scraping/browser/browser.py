from typing import Self, Generator, overload
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp
from subprocess import Popen, run
from signal import SIGTERM
from loguru import logger
from textwrap import dedent

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver import FirefoxOptions, Firefox

from ..proxy import Proxy
from .types import Port, HostAndPort



@contextmanager
def create_temp_folder_path() -> Generator[Path, None, None]:
    folder_path = Path(mkdtemp())
    try:
        yield folder_path
    finally:
        pass
        # shutil.rmtree(folder_path)



class Browser():

    driver: WebDriver

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver


    @overload
    @classmethod
    @contextmanager
    def start(
        cls,
        *,
        marionette_port: Port | None = None,
        proxy_location: HostAndPort | None = None,
        cert_file_path: Path | None = None,
    ) -> Generator[Self, None, None]:
        ...


    @overload
    @classmethod
    @contextmanager
    def start(
        cls,
        *,
        marionette_port: Port | None = None,
        proxy: Proxy | None = None,
    ) -> Generator[Self, None, None]:
        ...


    @classmethod
    @contextmanager
    def start(
        cls,
        *, 
        marionette_port: Port | None = None,
        proxy: Proxy | None = None,
        proxy_location: HostAndPort | None = None,
        cert_file_path: Path | None = None,
    ) -> Generator[Self, None, None]:
        if proxy is not None:
            proxy_location = proxy.location
            cert_file_path = proxy.cert_file_path

        with create_temp_folder_path() as temp_folder_path:
            profile_folder_path = temp_folder_path / "profile"
            profile_folder_path.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "Firefox profile folder created (profile_folder_path={profile_folder_path})", 
                profile_folder_path=profile_folder_path,
            )

            with ( profile_folder_path / "user.js" ).open("w") as user_js_file:
                if marionette_port is not None:
                    user_js_file.write(f"user_pref(\"marionette.port\", {marionette_port});\n")

                if cert_file_path is not None:
                    cls._generate_cert9_db(
                        profile_folder_path=profile_folder_path,
                        cert_file_path=cert_file_path,
                    )

                if proxy_location is not None:
                    user_js_file.write(dedent(f"""\
                        user_pref("network.proxy.type", 1);

                        user_pref("network.proxy.http", "{proxy_location.host}");
                        user_pref("network.proxy.http_port", {proxy_location.port});

                        user_pref("network.proxy.ssl", "{proxy_location.host}");
                        user_pref("network.proxy.ssl_port", {proxy_location.port});

                        user_pref("network.proxy.share_proxy_settings", true);

                        // Bypass proxy for local addresses (optional)
                        user_pref("network.proxy.no_proxies_on", "localhost, 127.0.0.1");
                    """))
                    
            command = [
                "firefox", 
                *( ["--marionette"] if marionette_port is not None else [] ),
                "--new-instance",
                "--profile", str(profile_folder_path),
            ]
            process = Popen(command)

            service = Service(
                service_args=[
                    "--marionette-port", f"{marionette_port}",
                    "--connect-existing",
                ],
            )

            options = FirefoxOptions()
            
            driver = Firefox(
                service=service, 
                options=options,
            )

            instance = cls(driver=driver)
            try:
                yield instance
            finally:
                process.send_signal(SIGTERM)
                process.wait()


    @classmethod
    def _generate_cert9_db(
        cls,
        profile_folder_path: Path,
        cert_file_path: Path,
    ) -> None:
        command = [
            "certutil",
            "-A",
            "-n", "Thunes Proxy CA",
            "-t", "CT,C,C",
            "-i", str(cert_file_path),
            "-d", f"sql:{str(profile_folder_path)}",
        ]
        run(command, check=True)