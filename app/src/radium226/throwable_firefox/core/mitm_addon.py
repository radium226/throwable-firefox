# type: ignore
# Standalone mitmproxy addon — no imports from this package.
# Runs inside mitmdump's process.

import json
import os

from mitmproxy import ctx, exceptions


class WriteHTTPFlowToFD:
    def load(self, loader):
        loader.add_option(
            name="fd",
            typespec=int | None,
            default=None,
            help="File descriptor to write HTTP flows to",
        )

    def configure(self, updates):
        if "fd" in updates:
            if ctx.options.fd is None:
                raise exceptions.OptionsError("fd option must be set to a valid file descriptor")

    def response(self, flow):
        fd = ctx.options.fd
        if fd is None:
            return

        data = {
            "id": str(flow.id),
            "request": {
                "method": flow.request.method,
                "url": flow.request.url,
                "headers": dict(flow.request.headers),
                "content": flow.request.get_text(strict=False),
            },
            "response": {
                "status_code": flow.response.status_code,
                "reason": flow.response.reason,
                "headers": dict(flow.response.headers),
                "content": flow.response.get_text(strict=False),
            },
        }
        line = json.dumps(data) + "\n"
        os.write(fd, line.encode("utf-8"))


addons = [WriteHTTPFlowToFD()]
