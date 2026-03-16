#!/usr/bin/env python

from time import sleep
from throwablefirefox.shell import execute

def local_port_opened(port, network_namespace=None):
    def closure():
        try:
            execute(["bash", "-c", f"netstat -tulpn | grep 'LISTEN' | grep {port}"], network_namespace=network_namespace, sudo=True)
            print("Local port is opened")
            return True
        except:
            print("Local port is closed")
            return False
    return closure


def wait_for(condition, timeout=None):
    while True:
        try:
            result = condition()
            if result is None or result:
                break
        except:
            pass
        sleep(1)
