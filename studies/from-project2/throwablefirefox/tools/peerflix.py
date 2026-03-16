#!/usr/bin/env python

from throwablefirefox.shell import execute, kill
from pathlib import Path
import os
from throwablefirefox.waitfor import wait_for, local_port_opened
import socket
from colorama import Fore, Back, Style

def first(l):
    return next((i for i in l if i is not None), None)


def port_opened(ip, port):
    def closure():
        print(f" --> Checking port {port} on {ip}")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            print(":)")
            return True
        except:
            print(":(")
            return False

    return closure

def list_files(folder_path, recursive=True, absolute=False, sort_by=None):
    file_paths = []
    if recursive:
        for sub_folder_path, _, file_paths_in_sub_folder in os.walk(str(folder_path)):
            for file_path in file_paths_in_sub_folder:
                file_paths.append(Path(sub_folder_path).relative_to(folder_path) / Path(file_path))
    else:
        file_paths = [file_or_folder_path for file_or_folder_path in map( # We retreive Path instead of string
                Path,
                os.listdir(str(folder_path))
            ) if (folder_path / file_or_folder_path).is_file()]
    return sorted([(folder_path / file_path) if absolute else file_path for file_path in file_paths], key=sort_by)


class Peerflix:

    def __init__(self, magnet=None, network_namespace=None):
        self.magnet = magnet
        self.video_folder_path = None
        self.process = None
        self.network_namespace = network_namespace

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.stop()

    def start(self):
        print(Fore.RED + "Starting Peerflix... " + Style.RESET_ALL)
        self.process = execute(["peerflix", "-f", ".", "-q", ".", self.magnet], network_namespace=self.network_namespace, background=True)
        wait_for(local_port_opened(8888, network_namespace=self.network_namespace))
        print("Here we go! ")

    @property
    def url(self):
        return "http://localhost:8888/"

    @property
    def video_file_path(self):
        wait_for(lambda: first(list_files(Path("."))) is not None)
        return first(list_files(Path("."), sort_by=lambda file_path: -file_path.stat().st_size))

    def stop(self):
        print(Fore.RED + "Stopping Peerflix... " + Style.RESET_ALL)
        kill(self.process, sudo=True)
