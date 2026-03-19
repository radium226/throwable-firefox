# Throwable Firefox

> [!IMPORTANT]
> If you're watching this page from [the repo in GitHub](https://github.com/radium226/throwable-firefox), please note it's only a read-only mirror from [the repo in SourceHut](https://git.sr.ht/~radium226/throwable-firefox).

A CLI tool to launch disposable Firefox instances with ephemeral profiles, pre-configured with privacy-hardened settings, custom bookmarks, extensions, an optional MITM proxy, and optional VPN passthrough.

## Features

- **Ephemeral profiles**: each launch creates a temporary Firefox profile that is cleaned up on exit
- **Privacy-hardened**: disables telemetry, AI features, sponsored content, crash reporting, studies, and connectivity checks out of the box
- **Extensions**: install `.xpi` extensions from local files or URLs
- **Bookmarks**: pre-populate the bookmarks toolbar
- **MITM proxy**: optional `mitmdump`-based proxy with auto-generated CA certificate and HTTP flow capture
- **VPN passthrough**: optionally route Firefox traffic through a VPN tunnel via [`vpn-passthrough`](https://git.sr.ht/~radium226/vpn-passthrough)
- **Marionette support**: enable Firefox's remote automation protocol on a configurable port

## Usage

```
throwable-firefox [OPTIONS]
```

| Option | Description |
|---|---|
| `--url URL` | URL to open on launch |
| `--headless` | Run Firefox in headless mode |
| `--extension PATH_OR_URL` | Path or URL of a `.xpi` extension (repeatable) |
| `--bookmark TITLE URL` | Bookmark to add to the toolbar (repeatable) |
| `--private / --no-private` | Enable or disable private browsing mode |
| `--marionette / --no-marionette` | Enable Marionette remote protocol |
| `--marionette-port PORT` | Marionette port (default: 2828) |
| `--with-vpn / --without-vpn` | Route traffic through vpn-passthrough (default: on) |

## Dependencies

- Python >= 3.14, managed with [uv](https://docs.astral.sh/uv/)
- Firefox
- `mitmproxy` / `mitmdump` (for the proxy feature)
- `certutil` from NSS tools (for proxy CA cert installation)
- [`vpn-passthrough`](https://git.sr.ht/~radium226/vpn-passthrough) (optional, for VPN routing)
