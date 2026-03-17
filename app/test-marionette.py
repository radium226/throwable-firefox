# /// script
# requires-python = ">=3.12"
# dependencies = ["selenium"]
# ///

import sys

from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.firefox.service import Service


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} host:port", file=sys.stderr)
        sys.exit(1)

    host, port_str = sys.argv[1].rsplit(":", 1)
    port = int(port_str)

    service = Service(
        service_args=[
            "--marionette-port", str(port),
            "--marionette-host", host,
            "--connect-existing",
        ],
    )
    options = FirefoxOptions()
    driver = Firefox(service=service, options=options)

    try:
        driver.get("https://www.google.com")
        print(f"Page title: {driver.title}")
        input("Press Enter to quit...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
