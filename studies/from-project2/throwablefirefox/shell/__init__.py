#!/usr/bin/env python

import subprocess as sp
import getpass
from pathlib import Path
import os
from signal import *

def mkdir(folder_path, sudo=False):
    execute(["mkdir", "-p", str(folder_path)], sudo=sudo)


def tee(content, file_path, append=False, sudo=False):
    tee_process = execute(["tee"] + (["-a"] if append else []) + [str(file_path)], sudo=sudo, background=True, stdin=sp.PIPE)
    tee_process.stdin.write(content)
    tee_process.stdin.close()
    tee_process.wait()


def kill(process, signal=SIGTERM, sudo=False, group=True):
    pid = process.pid
    if group:
        pgid = os.getpgid(process.pid)
        execute(["kill", f"-{signal}", f"-{str(pgid)}"], sudo=sudo)
    else:
        execute(["kill", f"-{signal}", str(pid)], sudo=sudo)


def execute(command, success_exit_codes=[0], sudo=False, network_namespace=None, background=False, stdin=None, stdout=None, in_folder=None):
    before_command = []
    if network_namespace:
        user = getpass.getuser()
        before_command = ["sudo", "-E", "ip", "netns", "exec", network_namespace, "sudo", "-E", "-u", user]

    if sudo:
        before_command = before_command + ["sudo", "-E"]

    process = sp.Popen(before_command + command, stdin=stdin, stdout=stdout, start_new_session=True, cwd=str(in_folder) if in_folder else None)
    if background:
        return process
    else:
        process.wait()
        exit_code = process.returncode
        if exit_code not in success_exit_codes:
            raise Exception(f"The {before_command + command} process failed! ")
