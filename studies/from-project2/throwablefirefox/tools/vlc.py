#!/usr/bin/env python

from throwablefirefox.shell import execute, kill
from colorama import Fore, Back, Style

class VLC:

    def __init__(self, url, subtitles_file_path=None, network_namespace=None):
        self.subtitles_file_path = subtitles_file_path
        self.url = url
        self.process = None
        self.network_namespace = network_namespace

    def start(self):
        print(Fore.RED + "Starting VLC... " + Style.RESET_ALL)
        self.process = execute(["vlc", self.url] + (["--sub-file", str(self.subtitles_file_path)] if self.subtitles_file_path else []), background=True, network_namespace=self.network_namespace)

    def __enter__(self):
        self.start()
        return self

    def stop(self):
        print(Fore.RED + "Stopping VLC... " + Style.RESET_ALL)
        kill(self.process)

    def __exit__(self, type, value, traceback):
        self.stop()

    def wait(self):
        self.process.wait()
