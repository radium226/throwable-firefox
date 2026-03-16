#!/bin/env python

import subprocess as sp
from time import sleep
import signal
import os
import re
from geolite2 import geolite2
from throwablefirefox.shell import execute, kill

CHECK_IP_MAGNET = "magnet:?xt=urn:btih:24dcde05861586954f32e871a754fcc06fbb36a6&dn=checkmyiptorrent&tr=http%3A%2F%2F34.204.227.31%2Fcheckmytorrentipaddress.php"

CHECK_IP_REGEX = r"([0-9]{0,3}\.[0-9]{0,3}\.[0-9]{0,3}\.[0-9]{0,3})$"

class IPChecker:

    def __init__(self, ip):
        self.ip = ip

    @property
    def country(self):
        reader = geolite2.reader()
        t = reader.get(self.ip)
        geolite2.close()
        return t["country"]["iso_code"]

    @classmethod
    def for_http(cls, network_namespace=None):
        process = execute(["curl", "-s", "https://api.ipify.org?format=text"], stdout=sp.PIPE, network_namespace=network_namespace, background=True)
        ip = "".join(filter(lambda line: line, map(lambda line: line.strip(), map(lambda line_in_bytes: line_in_bytes.decode("utf-8"), iter(process.stdout.readline, b"")))))
        return cls(ip)

    @classmethod
    def for_torrent(cls, network_namespace=None):
        print(" --> for_torrent")
        process = execute(["aria2c", CHECK_IP_MAGNET], stdout=sp.PIPE, network_namespace=network_namespace, background=True)
        for line in filter(lambda line: line, map(lambda line: line.strip(), map(lambda line_in_bytes: line_in_bytes.decode("utf-8"), iter(process.stdout.readline, b"")))):
            print(" --> line=" + line)
            groups = re.search(CHECK_IP_REGEX, line)
            ip = None
            if groups:
                ip = groups.group(0)
                break
            #else:
            #    print(line)
        kill(process, sudo=True, signal = signal.SIGKILL)
        return cls(ip)

if __name__ == "__main__":
    ip = IPChecker.for_torrent()
    country = IPChecker.country_by_ip(ip)
    print(country)
