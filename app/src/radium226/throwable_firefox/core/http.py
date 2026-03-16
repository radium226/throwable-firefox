from pydantic import BaseModel


class HTTPRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str]
    content: str | None = None


class HTTPResponse(BaseModel):
    status_code: int
    reason: str
    headers: dict[str, str]
    content: str | None = None


class HTTPFlow(BaseModel):
    id: str
    request: HTTPRequest
    response: HTTPResponse | None = None
