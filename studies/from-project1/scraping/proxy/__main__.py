from .proxy import Proxy
from time import sleep


if __name__ == "__main__":
    with Proxy.start(
        host="127.0.0.1",
        port=9999,
    ) as proxy:
        sleep(1000)