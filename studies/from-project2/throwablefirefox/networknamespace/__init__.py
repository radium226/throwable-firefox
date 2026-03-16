#!/bin/env python

from throwablefirefox.shell import execute, mkdir, tee
from colorama import Fore, Back, Style
from pathlib import Path

class NetworkNamespace:

    VETH_VPN = "veth_vpn"
    VETH_DEFAULT="veth_default"

    def __init__(self, name=None):
        self.name = name

    @property
    def folder_path(self):
         return Path(f"/etc/netns/{self.name}")

    @classmethod
    def random(cls):
        return NetworkNamespace("random")

    def create(self):
        print(Fore.RED + "Creating Network Namespace... " + Style.RESET_ALL)
        execute(["ip", "netns", "add", self.name], sudo=True)
        mkdir(self.folder_path, sudo=True)

        # Loopback
        execute(["ip", "address", "add", "127.0.0.1/8", "dev", "lo"], sudo=True, network_namespace=self.name)
        execute(["ip", "address", "add", "::1/128", "dev", "lo"], sudo=True, network_namespace=self.name)
        execute(["ip", "link", "set", "lo", "up"], sudo=True, network_namespace=self.name)

        # Tunnel
        execute(["ip", "link", "add", NetworkNamespace.VETH_VPN, "type", "veth", "peer", "name", NetworkNamespace.VETH_DEFAULT], sudo=True)
        execute(["ip", "link", "set", NetworkNamespace.VETH_VPN, "netns", self.name], sudo=True)

        execute(["ip", "link", "set", NetworkNamespace.VETH_DEFAULT, "up"], sudo=True)
        execute(["ip", "link", "set", NetworkNamespace.VETH_VPN, "up"], sudo=True, network_namespace=self.name)

        execute(["ip", "address", "add", "10.10.10.10/31", "dev", NetworkNamespace.VETH_DEFAULT], sudo=True)
        execute(["ip", "address", "add", "10.10.10.11/31", "dev", NetworkNamespace.VETH_VPN], sudo=True, network_namespace=self.name)

        execute(["ip", "route", "add", "default", "via", "10.10.10.10", "dev", NetworkNamespace.VETH_VPN], sudo=True, network_namespace=self.name)

        execute(["sysctl", "--quiet", "net.ipv4.ip_forward=1"], sudo=True)
        execute(["iptables", "--table", "nat", "--append", "POSTROUTING", "--jump", "MASQUERADE", "--source", "10.10.10.10/31"], sudo=True)

        content = f"""nameserver 108.62.19.131
    nameserver 104.238.194
"""
        tee(content.encode("utf-8"), self.folder_path / "resolv.conf", sudo=True)


    def delete(self):
        print(Fore.RED + "Deleting Network Namespace... " + Style.RESET_ALL)
        execute(["ip", "link", "del", NetworkNamespace.VETH_DEFAULT], sudo=True)
        execute(["ip", "netns", "del", self.name], sudo=True)

    def __enter__(self):
        self.create()
        return self.name

    def __exit__(self, type, value, traceback):
        self.delete()
