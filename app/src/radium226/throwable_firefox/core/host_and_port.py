from dataclasses import dataclass


@dataclass
class HostAndPort:
    host: str
    port: int
