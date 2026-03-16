#!/bin/env python

from setuptools import setup

setup(
    name="throwable-firefox",
    version="0.1",
    description="A throwable Firefox to browse anonymously! ",
    url="https://github.com/radium226/throwable-firefox",
    license="GPL",
    zip_safe=True,
    install_requires=[],
    scripts=[
        "scripts/throwable-firefox",
        "scripts/stream-torrent"
    ],
    packages=[
        "throwablefirefox",
        "throwablefirefox.firefox",
        "throwablefirefox.ipchecker",
        "throwablefirefox.networknamespace",
        "throwablefirefox.openvpn",
        "throwablefirefox.shell",
        "throwablefirefox.waitfor",
        "throwablefirefox.tools"
    ]
)
