# CLAUDE.md

## Project overview

Throwable Firefox is a Python CLI tool (`throwable-firefox`) that launches disposable Firefox instances with ephemeral profiles. It features privacy-hardened defaults, extension/bookmark injection, MITM proxy support, and optional VPN passthrough.

## Tech stack

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/) for project/dependency management
- Click for CLI
- Pydantic for HTTP flow models
- mitmproxy/mitmdump for MITM proxy
- loguru for logging
- aiosqlite for bookmark injection into Firefox's places.sqlite
- Depends on [`vpn-passthrough`](https://git.sr.ht/~radium226/vpn-passthrough) client library

## Repository layout

```
app/                              # Main uv project
  pyproject.toml                  # Project metadata & dependencies
  src/radium226/throwable_firefox/
    cli/
      __main__.py                 # Click CLI entrypoint
    core/
      firefox.py                  # Firefox process launcher
      profile.py                  # Ephemeral profile creation (user.js, extensions, bookmarks, proxy cert)
      proxy.py                    # MITM proxy wrapper around mitmdump
      extension.py                # .xpi extension handling (local files or URLs)
      bookmark.py                 # Bookmark dataclass
      process.py                  # Process abstraction (local or via VPN passthrough)
      http.py                     # Pydantic models for HTTP request/response/flow
      host_and_port.py            # HostAndPort utility
      mitm_addon.py               # Standalone mitmproxy addon (streams flows over a pipe)
      _shell.py                   # Async subprocess helpers
studies/                          # Prior art / reference code from earlier projects
```

## Development

```bash
cd app
uv sync           # Install dependencies
uv run throwable-firefox --help
```

## Linting & type checking

- **ruff** for linting (`E`, `F`, `I` rules), line length 120
- **ty** for type checking (Python 3.14 target, excludes `mitm_addon.py`)

```bash
cd app
uv run ruff check src/
uv run ty check
```

## Key patterns

- Heavy use of `asynccontextmanager` for resource lifecycle (profile, proxy, firefox process)
- `CreateProcess` is a callable type alias allowing process creation to be swapped between local and VPN-routed execution
- The MITM addon (`mitm_addon.py`) runs inside mitmdump's process and communicates flows back via a file descriptor pipe
- Firefox profiles are pre-started headlessly to initialize `extensions.json` and `places.sqlite` before the real launch
