# type: ignore

from mitmproxy import ctx
from mitmproxy import exceptions
import json
import os
from loguru import logger

from radium226.thunes.tools.scraping import proxy


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
                raise exceptions.OptionsError("fd must be set to a valid file descriptor")

    def response(self, flow):
        if ( fd := ctx.options.fd ) is not None:
            http_flow_for_proxy = proxy.HTTPFlow(
                id=str(flow.id),
                request=proxy.HTTPRequest(
                    method=flow.request.method,
                    url=flow.request.url,
                    headers=dict(flow.request.headers),
                    content=flow.request.get_text(),
                ),
                response=proxy.HTTPResponse(
                    status_code=flow.response.status_code,
                    reason=flow.response.reason,
                    headers=dict(flow.response.headers),
                    content=flow.response.get_text(),
                ),
            )

            http_flow_obj_for_proxy = http_flow_for_proxy.model_dump()
            buffer = json.dumps(http_flow_obj_for_proxy) + "\n"
            logger.trace(f"{buffer=}")

            os.write(fd, buffer.encode("utf-8"))


addons = [WriteHTTPFlowToFD()]

