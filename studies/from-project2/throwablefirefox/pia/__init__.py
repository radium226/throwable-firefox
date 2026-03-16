#!/usr/bin/env python

from throwablefirefox.shell import execute
from throwablefirefox.openvpn import OpenVPN
from throwablefirefox.networknamespace import NetworkNamespace
import subprocess as sp
import re
import random
from time import sleep
from throwablefirefox.ipchecker import IPChecker

class PIA:

    @classmethod
    def random(cls, network_namespace=None):
        return random.choice(cls.list(network_namespace=network_namespace))

    @classmethod
    def list(cls, network_namespace=None):
        process = execute(["pia", "-l"], stdout=sp.PIPE, background=True)
        openvpns = []
        for line in filter(lambda line: line, map(lambda line: line.strip(), map(lambda line_in_bytes: line_in_bytes.decode("utf-8"), iter(process.stdout.readline, b"")))):
            groups = re.search("^(.*) \[nm\]$", line)
            country = None
            if groups:
                country = groups.group(1)
                openvpn = OpenVPN(network_namespace=network_namespace, country=country.replace(" ", "_"))
                openvpns.append(openvpn)
        return openvpns

if __name__ == "__main__":
    with NetworkNamespace(name="toto") as network_namespace:
        with PIA.random(network_namespace=network_namespace):
            ip_checker = IPChecker.for_http(network_namespace)
            print(ip_checker.ip)
            print(ip_checker.country)
