from pydantic import BaseModel

from radium226.thunes.models import Host, Port, HostAndPort



class HTTPRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    content: str


class HTTPResponse(BaseModel):
    status_code: int
    reason: str
    headers: dict[str, str]
    content: str


class HTTPFlow(BaseModel):
    id: str
    request: HTTPRequest
    response: HTTPResponse



__all__ = [
    "HTTPRequest",
    "HTTPResponse",
    "HTTPFlow",
    "Host",
    "Port",
    "HostAndPort",
]