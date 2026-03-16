#!/usr/bin/env python

from throwablefirefox.shell import execute, kill
from throwablefirefox.waitfor import wait_for

from pathlib import Path
from colorama import Back, Fore, Style


class OpenVPN:

    CONFIG_FOLDER_PATH = Path("/etc/openvpn/client")
    TUNNEL_NAME = "tunvpn"

    def __init__(self, network_namespace, country):
        self.network_namespace = network_namespace
        self.country = country

    def __enter__(self):
        self.start()

    def start(self):
        print(Fore.RED + "Starting OpenVPN... " + Style.RESET_ALL)
        config_file_path = OpenVPN.CONFIG_FOLDER_PATH / f"{self.country}.conf"
        command = [
            "openvpn",
                "--cd", str(OpenVPN.CONFIG_FOLDER_PATH),
                "--config", str(config_file_path),
                "--dev", OpenVPN.TUNNEL_NAME,
                "--errors-to-stderr"
        ]
        self.process = execute(command, sudo=True, network_namespace=self.network_namespace, background=True)

        wait_for(lambda: execute(["ip", "link", "show", OpenVPN.TUNNEL_NAME], sudo=True, network_namespace=self.network_namespace))

    def __exit__(self, type, value, traceback):
        self.stop()

    def stop(self):
        print(Fore.RED + "Stopping OpenVPN... " + Style.RESET_ALL)
        kill(self.process, sudo=True, group=True)

    def wait(self):
        self.process.wait()
