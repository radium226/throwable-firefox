import os
from pathlib import Path

import click
import yaml
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel, Field

from .bookmark import BookmarkItem

_MAGIC = b"TFEN"
_VERSION = b"\x01"
_KDF_ITERATIONS = 600_000
_SALT_LEN = 32
_NONCE_LEN = 12
_KEY_LEN = 32


class Preset(BaseModel):
    name: str
    default: bool = False
    private: bool | None = None
    marionette: bool | None = None
    bookmarks: list[BookmarkItem] = Field(default_factory=list)
    dns_overrides: dict[str, list[str]] = Field(default_factory=dict)
    extra_routes: list[str] = Field(default_factory=list)


def _presets_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "throwable-firefox" / "presets"


def preset_path(name: str, encrypted: bool) -> Path:
    suffix = ".yaml.enc" if encrypted else ".yaml"
    return _presets_dir() / f"{name}{suffix}"


def get_preset_password(confirm: bool = False) -> str:
    env_password = os.environ.get("THROWABLE_FIREFOX_PRESET_PASSWORD")
    if env_password:
        return env_password
    return click.prompt("Preset password", hide_input=True, confirmation_prompt=confirm)


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=SHA256(), length=_KEY_LEN, salt=salt, iterations=_KDF_ITERATIONS)
    return kdf.derive(password.encode())


def encrypt_preset_bytes(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return _MAGIC + _VERSION + salt + nonce + ciphertext


def decrypt_preset_bytes(data: bytes, password: str) -> bytes:
    if not data.startswith(_MAGIC):
        raise ValueError("Not a valid encrypted preset (bad magic bytes)")
    offset = len(_MAGIC) + len(_VERSION)
    salt = data[offset : offset + _SALT_LEN]
    offset += _SALT_LEN
    nonce = data[offset : offset + _NONCE_LEN]
    offset += _NONCE_LEN
    ciphertext = data[offset:]
    key = _derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Wrong password or corrupted preset file")


def load_preset_from_path(path: Path, password: str | None = None) -> Preset:
    if path.suffix == ".enc":
        return load_preset_from_encrypted_path(path, password or get_preset_password())
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Preset file {path} must contain a YAML mapping")
    raw.setdefault("name", path.stem)
    return Preset.model_validate(raw)


def load_preset_from_encrypted_path(path: Path, password: str) -> Preset:
    plaintext = decrypt_preset_bytes(path.read_bytes(), password)
    raw = yaml.safe_load(plaintext.decode()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Preset file {path} must contain a YAML mapping")
    # stem of "foo.yaml.enc" → "foo.yaml", so strip one more suffix
    raw.setdefault("name", Path(path.stem).stem)
    return Preset.model_validate(raw)


def resolve_preset(value: str, password: str | None = None) -> Preset:
    candidate = Path(value)
    if candidate.is_file():
        return load_preset_from_path(candidate, password)
    for suffix in (".yaml", ".yaml.enc"):
        named = _presets_dir() / f"{value}{suffix}"
        if named.is_file():
            return load_preset_from_path(named, password)
    raise FileNotFoundError(f"Preset {value!r} not found (looked in {_presets_dir()})")


def list_presets() -> list[tuple[str, bool, bool | None]]:
    """Return (name, is_encrypted, is_default) for each preset; is_default is None for encrypted files."""
    directory = _presets_dir()
    if not directory.is_dir():
        return []
    results: list[tuple[str, bool, bool | None]] = []
    for p in sorted(directory.iterdir()):
        if p.name.endswith(".yaml.enc"):
            name = Path(p.stem).stem
            results.append((name, True, None))
        elif p.name.endswith(".yaml"):
            try:
                preset = load_preset_from_path(p)
                results.append((preset.name, False, preset.default))
            except Exception:
                results.append((p.stem, False, None))
    return results


def find_default_preset(password: str | None = None) -> "Preset | None":
    directory = _presets_dir()
    if not directory.is_dir():
        return None
    defaults: list[Preset] = []
    for p in sorted(directory.iterdir()):
        if p.name.endswith(".yaml.enc"):
            if password is None:
                continue
            preset = load_preset_from_path(p, password)
        elif p.name.endswith(".yaml"):
            preset = load_preset_from_path(p)
        else:
            continue
        if preset.default:
            defaults.append(preset)
    if len(defaults) > 1:
        names = ", ".join(p.name for p in defaults)
        raise ValueError(f"Multiple default presets found: {names}")
    return defaults[0] if defaults else None
