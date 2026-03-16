#!/bin/env python

from .profile import *
from .bookmark import *
from .extension import *
from throwablefirefox.shell import kill

from pathlib import Path
from tempfile import mkdtemp
from configparser import ConfigParser
import shutil
from time import sleep
from urllib.request import urlretrieve
from urllib.parse import urlparse
import os
import subprocess as sp
import sqlite3
from colorama import Fore, Back, Style
from signal import *

import json

from zipfile import ZipFile

from pyasn1.codec.der import decoder as der_decoder
from pyasn1_modules import rfc5652, rfc2315, rfc5280
import json
from pathlib import Path

IP_ADDON_URL = "https://addons.mozilla.org/firefox/downloads/file/776591/show_external_ip-1.0.6-an+fx.xpi"
ADBLOCK_ADDON_URL = "https://addons.mozilla.org/firefox/downloads/file/957947/adblock_plus-3.1-an+fx.xpi?src=dp-btn-primary"


class Firefox:

    APPLICATION_ID = "{ec8030f7-c20a-464f-9b0e-13a3a9e97384}"

    def __init__(self, profile, process):
        self.profile = profile
        self.process = process

    def wait(self):
        self.process.wait()

    @classmethod
    def configure(cls, profile, bookmarks=False, extensions=False):
        config_file_path = Path.home() / ".config" / "throwable-firefox.conf"
        if config_file_path.exists():
            firefox = cls.start(profile, private=False, headless=True)
            sleep(5)
            firefox.stop()

            with config_file_path.open("r") as config_file:
                config = json.loads(config_file.read())
                print(config)
                if bookmarks:
                    for bookmark in config["bookmarks"]:
                        profile.add_bookmark(Bookmark(bookmark["url"], bookmark["title"]))

                if extensions:
                    for extension_url in config["extensions"]:
                        extension = Extension.download(extension_url)
                        profile.install_extension(extension)

                firefox = cls.start(profile, private=False, headless=True)
                sleep(5)
                firefox.stop()
                sleep(5)

    @classmethod
    def start(cls, profile, headless=False, private=False, url=None):
        print(Fore.RED + "Starting Firefox... " + Style.RESET_ALL)
        command=([
            "firefox",
            "-P", profile.name,
            "-no-remote",
            "-new-instance"
        ]) + (["-headless"] if headless else []) + (["-private"] if private else []) + (["-url", url] if url else [])
        process = execute(command, background=True, network_namespace=profile.network_namespace)
        return cls(profile, process)

    def stop(self):
        print(Fore.RED + "Stopping Firefox... " + Style.RESET_ALL)
        kill(self.process, sudo=True, group=True)
