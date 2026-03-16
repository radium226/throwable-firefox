#!/usr/bin/env python

from pathlib import Path
from tempfile import mkdtemp, gettempdir
from configparser import ConfigParser
import shutil
from time import sleep
from urllib.request import urlretrieve
from urllib.parse import urlparse
import os
import subprocess as sp
import sqlite3
from colorama import Fore, Back, Style
import tempfile

from throwablefirefox.shell import execute

import json

from zipfile import ZipFile

from pyasn1.codec.der import decoder as der_decoder
from pyasn1_modules import rfc5652, rfc2315, rfc5280

class Profile:

    INI_PATH = Path.home() / ".mozilla" / "firefox" / "profiles.ini"

    @classmethod
    def throwable(cls, network_namespace=None):
        return ThrowableProfile(network_namespace)


class ThrowableProfile:

    BASE_FOLDER_PATH = Path(gettempdir()) / "throwable-firefox" / "profiles"

    NAME = "Private"

    @classmethod
    def random_folder_path(cls):
        ThrowableProfile.BASE_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
        folder_path = Path(mkdtemp(dir=str(ThrowableProfile.BASE_FOLDER_PATH)))
        return folder_path

    def __init__(self, network_namespace=None):
        self.folder_path = ThrowableProfile.random_folder_path()
        self.name = ThrowableProfile.NAME
        self.network_namespace = network_namespace

    def __enter__(self):
        self.create()
        return self

    @property
    def prefs_file_path(self):
        return self.folder_path / "prefs.js"

    @property
    def xulstore_file_path(self):
        return self.folder_path / "xulstore.json"

    @property
    def places_file_path(self):
        return self.folder_path / "places.sqlite"

    def create(self):
        print(Fore.RED + "Creating profile... " + Style.RESET_ALL)
        command = [
            "firefox",
            "-no-remote",
            "-CreateProfile", f"{ThrowableProfile.NAME} {self.folder_path.resolve()}"
        ]
        execute(command)

        with self.prefs_file_path.open("w") as f:
            f.write('user_pref("extensions.autoDisableScopes", 0);' + "\n")

        with self.xulstore_file_path.open("w") as f:
            f.write('{"chrome://browser/content/browser.xul":{"PersonalToolbar":{"collapsed":"false"}}}')


        #with (self.folder_path / "extensions.json").open("w") as f:
        #    f.write('{"addons":[{"active":true,"seen":true,"userDisabled":false,"id":"@showextip"}]}');


        return self

    def delete(self):
        print(Fore.RED + "Deleting profile... " + Style.RESET_ALL)
        # Removing profile from profile.ini
        ini = ConfigParser()
        ini.optionxform = str
        ini.read(str(Profile.INI_PATH))
        for section_name in ini.sections():
            if "Name" in ini[section_name]:
                name = ini[section_name]["Name"]
                if name == self.name:
                    ini.remove_section(section_name)

        with Profile.INI_PATH.open("w") as ini_file:
            ini.write(ini_file, space_around_delimiters=False)

        # Deleting profile folder
        #shutil.rmtree(str(self.folder_path))

    def __exit__(self, type, value, traceback):
        self.delete()
        pass

    def add_bookmark(self, bookmark):
        connection = sqlite3.connect(str(self.places_file_path))
        cursor = connection.cursor()

        #for a in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        #    print(a)

        place_id, = cursor.execute("SELECT MAX(id) + 1 AS id FROM moz_places").fetchone()
        cursor.execute("INSERT INTO moz_places(id, url, title) VALUES (?, ?, ?)", (place_id, bookmark.url, bookmark.title))

        bookmark_id, = cursor.execute("SELECT MAX(id) + 1 AS id FROM moz_bookmarks").fetchone()
        cursor.execute("INSERT INTO moz_bookmarks(id, type, fk, parent, title) VALUES (?, ?, ?, ?, ?)", (bookmark_id, 1, place_id, 3, bookmark.title))

        connection.commit()
        connection.close()


    def install_extension(self, extension, pre_start=False):
        print(Fore.RED + "Installing extension... " + Style.RESET_ALL)

        extensions_folder_path = self.folder_path / "extensions"
        extensions_folder_path.mkdir(exist_ok=True)
        shutil.copy2(str(extension.xpi_file_path), str(extensions_folder_path) + f"/{extension.id}.xpi")

        if pre_start:
            firefox = Firefox.start(self, headless=True)
            sleep(5)
            firefox.stop()
            sleep(1)

        with (self.folder_path / "extensions.json").open("r") as extensions_file:
            extensions = json.load(extensions_file)
            for addon in extensions["addons"]:
                print(addon)
                addon["seen"] = True
                addon["userDisabled"] = False
                addon["active"] = True


            #with (self.folder_path / "extensions.json").open("w") as extensions_file:
            #    json.dump(extensions, extensions_file, separators=(',', ':'))
