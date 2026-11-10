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


_ARCHIVE_MAGIC = b"ENVYDIR1\x00"
MAX_FOLDER_FILES = 100_000


def _pack_folder(folder) -> tuple[bytes, list[str]]:
    """Pack a folder's regular files into one deterministic archive blob. Symlinks and
    special files are skipped; empty directories are not preserved."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise VaultError("Expected a folder to encrypt.")
    files = [p for p in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix())
             if p.is_file() and not p.is_symlink()]
    if len(files) > MAX_FOLDER_FILES:
        raise VaultError("Folder has too many files to archive.")
    out = bytearray(_ARCHIVE_MAGIC)
    out += len(files).to_bytes(4, "big")
    names = []
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = read_regular(path)
        out += len(rel).to_bytes(2, "big") + rel
        out += len(data).to_bytes(8, "big") + data
        names.append(path.relative_to(root).as_posix())
    return bytes(out), names


def _unpack_folder(blob: bytes, destination) -> tuple[Path, list[str]]:
    """Restore files from an archive blob into ``destination``, refusing any path that
    would escape it and never overwriting an existing file."""
    if not blob.startswith(_ARCHIVE_MAGIC):
        raise VaultError("This is not an ENVY encrypted folder.")
    dest = Path(destination).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    droot = os.path.realpath(dest)
    view = memoryview(blob)
    i = len(_ARCHIVE_MAGIC)
    count = int.from_bytes(view[i:i + 4], "big"); i += 4
    written = []
    for _ in range(count):
        nlen = int.from_bytes(view[i:i + 2], "big"); i += 2
        rel = bytes(view[i:i + nlen]).decode("utf-8"); i += nlen
        dlen = int.from_bytes(view[i:i + 8], "big"); i += 8
        data = bytes(view[i:i + dlen]); i += dlen
        target = os.path.realpath(os.path.join(dest, rel))
        try:
            inside = target == droot or os.path.commonpath([target, droot]) == droot
        except ValueError:                       # different drive on Windows
            inside = False
        if not inside:
            raise VaultError("Refusing an unsafe path inside the archive.")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        write_new_file(target, data)
        written.append(rel)
    return dest, written


def encrypt_folder(folder, destination, secret: bytes) -> dict:
    """Archive a folder's files and encrypt them into a single new vault file."""
    blob, names = _pack_folder(folder)
    output = encrypt_bytes(blob, secret)
    write_new_file(destination, output)
    return {"output": str(Path(destination).expanduser()), "files": len(names),
            "bytes": len(output), "source_preserved": True}


def decrypt_folder(source, destination, secret: bytes) -> dict:
    """Decrypt a folder vault and restore its files under ``destination``."""
    blob = decrypt_bytes(read_regular(source), secret)
    dest, written = _unpack_folder(blob, destination)
    return {"output": str(dest), "files": len(written), "source_preserved": True}


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
