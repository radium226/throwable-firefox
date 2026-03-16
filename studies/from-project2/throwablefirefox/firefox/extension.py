#!/usr/bin/env python

from colorama import Fore, Back, Style
import os
from urllib.parse import urlparse
from urllib.request import urlretrieve
from tempfile import mkdtemp
from zipfile import ZipFile
import subprocess as sp

from throwablefirefox.shell import execute


class Extension:

    def __init__(self, xpi_file_path):
        self.xpi_file_path = xpi_file_path

    @classmethod
    def download(cls, xpi_url):
        print(Fore.RED + "Downloading extension... " + Style.RESET_ALL)

        xpi_file_name = os.path.basename(urlparse(xpi_url).path)
        xpi_folder_path = mkdtemp()
        xpi_file_path = os.path.join(xpi_folder_path, xpi_file_name)
        urlretrieve(xpi_url, xpi_file_path)
        print(xpi_file_path)
        return Extension(xpi_file_path)

    @property
    def id(self):
        with ZipFile(str(self.xpi_file_path)) as zip_file:
            mozilla_rsa = zip_file.read("META-INF/mozilla.rsa")
            sh_process = execute(["sh", "-c", "openssl asn1parse -inform DER -in -  | grep -A 1 'commonName' | grep -E '{|@' | cut -d ':' -f 4"], stdin=sp.PIPE, stdout=sp.PIPE, background=True)
            sh_process.stdin.write(mozilla_rsa)
            sh_process.stdin.close()

            id = "".join(filter(lambda l: len(l) > 0, map(lambda b: b.decode("utf-8").strip(), iter(sh_process.stdout.readline, b""))))
            return id
