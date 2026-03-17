from dataclasses import dataclass


@dataclass(frozen=True, eq=True)
class HostAndPort:
    host: str | None
    port: int | None

    def merge_with(self, other: "HostAndPort") -> "HostAndPort":
        return HostAndPort(
            host=self.host if self.host is not None else other.host,
            port=self.port if self.port is not None else other.port,
        )
    
    @staticmethod
    def parse(text: str) -> "HostAndPort":
        if ":" not in text:
            raise ValueError(f"Invalid host:port format: '{text}'")
        host, port_str = text.rsplit(":", 1)
        if len(host) == 0:
            host = None
        if len(port_str) == 0:
            port = None
        else:
            port = int(port_str)

        return HostAndPort(host=host, port=port)
    
    @staticmethod
    def none() -> "HostAndPort":
        return HostAndPort(host=None, port=None)
