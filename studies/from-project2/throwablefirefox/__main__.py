#!/usr/bin/env python

from throwablefirefox.firefox import Firefox, Profile, Bookmark
from throwablefirefox.networknamespace import NetworkNamespace
from throwablefirefox.openvpn import OpenVPN
from throwablefirefox.ipchecker import IPChecker
from throwablefirefox.pia import PIA
from time import sleep

if __name__ == "__main__":
    real_ip_checker = IPChecker.for_http(network_namespace=None)
    with NetworkNamespace(name="throwable-firefox") as network_namespace:
        with PIA.random(network_namespace=network_namespace):
            with Profile.throwable(network_namespace=network_namespace) as profile:
                hidden_ip_checker = IPChecker.for_http(network_namespace=network_namespace)
                if real_ip_checker.ip == hidden_ip_checker.ip:
                    raise Error("IP is not hidden")
                else:
                    print(f" ==> country={hidden_ip_checker.country}")

                Firefox.configure(profile, bookmarks=True, extensions=True)

                firefox = Firefox.start(profile, private=True, url="https://duckduckgo.com")
                firefox.wait()
