"""Authenticated file encryption for ENVY Vault.

The on-disk envelope is byte-compatible with ENVY BLACK VEIL's Vault:

    MAGIC(11) | salt(16) | nonce(12) | AES-256-GCM(ciphertext + tag)

The key is derived from the passphrase with scrypt (n=2**15, r=8, p=1), and the
MAGIC header is the AEAD associated data, so a truncated or altered file fails to
decrypt. Files written here open in the original Vault and vice versa.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"ENVYVAULT2\x00"
SALT_BYTES = 16
NONCE_BYTES = 12
MIN_PASSPHRASE_BYTES = 12
# AES-GCM appends a 16-byte tag; the smallest envelope has empty plaintext.
_MIN_ENVELOPE = len(MAGIC) + SALT_BYTES + NONCE_BYTES + 16
MAX_FILE_BYTES = 64 * 1024 * 1024


class VaultError(Exception):
    """A user-facing error: a bad passphrase, a missing file, a refused path."""


def _derive_key(secret: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(secret)


def encrypt_bytes(data: bytes, secret: bytes) -> bytes:
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    sealed = AESGCM(_derive_key(secret, salt)).encrypt(nonce, data, MAGIC)
    return MAGIC + salt + nonce + sealed


def decrypt_bytes(data: bytes, secret: bytes) -> bytes:
    if not data.startswith(MAGIC) or len(data) < _MIN_ENVELOPE:
        raise VaultError("Not an ENVY encrypted file.")
    body = data[len(MAGIC):]
    salt = body[:SALT_BYTES]
    nonce = body[SALT_BYTES:SALT_BYTES + NONCE_BYTES]
    sealed = body[SALT_BYTES + NONCE_BYTES:]
    try:
        return AESGCM(_derive_key(secret, salt)).decrypt(nonce, sealed, MAGIC)
    except InvalidTag:
        raise VaultError("Incorrect passphrase, or the file was modified.") from None


def check_passphrase(secret: bytes) -> bytes:
    if len(secret) < MIN_PASSPHRASE_BYTES:
        raise VaultError(f"Use a passphrase of at least {MIN_PASSPHRASE_BYTES} characters.")
    return secret


def read_regular(path: str | Path, limit: int = MAX_FILE_BYTES) -> bytes:
    """Read a regular file, refusing symlinks and anything over the size limit."""
    path = Path(path).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        raise VaultError(f"File not found: {path}") from None
    except OSError as exc:
        raise VaultError(f"Cannot open {path}: {exc.strerror or exc}") from None
    with os.fdopen(descriptor, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode):
            raise VaultError("Expected a regular file.")
        if meta.st_size > limit:
            raise VaultError(f"File is larger than the {limit // (1024 * 1024)} MiB limit.")
        return stream.read(limit + 1)[:limit + 1]


def write_new_file(path: str | Path, data: bytes) -> Path:
    """Write to a new file only; never overwrite. Owner-only where the OS allows."""
    path = Path(path).expanduser()
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        raise VaultError(f"Output already exists; choose a new name: {path}") from None
    except OSError as exc:
        raise VaultError(f"Cannot write {path}: {exc.strerror or exc}") from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def transform_file(action: str, source: str | Path, destination: str | Path, secret: bytes) -> dict:
    """Encrypt or decrypt ``source`` into a brand-new ``destination``.

    The source is always left untouched. ``secret`` is the passphrase bytes;
    validate it with :func:`check_passphrase` before calling for encryption.
    """
    if action not in ("encrypt", "decrypt"):
        raise VaultError("Action must be 'encrypt' or 'decrypt'.")
    data = read_regular(source)
    output = encrypt_bytes(data, secret) if action == "encrypt" else decrypt_bytes(data, secret)
    write_new_file(destination, output)
    return {"output": str(Path(destination).expanduser()), "bytes": len(output), "source_preserved": True}
