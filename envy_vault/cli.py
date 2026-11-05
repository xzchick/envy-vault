"""Command-line entry point. The GUI is the default; subcommands are explicit."""

from __future__ import annotations

import argparse
import getpass
import sys

from . import __version__
from .core import VaultError, check_passphrase, transform_file


def _passphrase(confirm: bool) -> bytes:
    if not sys.stdin.isatty():
        raise VaultError("Run this in a terminal, or use the app window, to enter a passphrase.")
    secret = getpass.getpass("Passphrase: ").encode()
    if confirm and secret != getpass.getpass("Repeat passphrase: ").encode():
        raise VaultError("Passphrases do not match.")
    return check_passphrase(secret) if confirm else secret


def _run_transform(args: argparse.Namespace) -> int:
    secret = _passphrase(confirm=args.command == "encrypt")
    result = transform_file(args.command, args.source, args.destination, secret)
    print(f"Wrote {result['bytes']} bytes to {result['output']} (original left in place).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="envy-vault",
        description="Encrypt and decrypt files locally with AES-256-GCM. Run with no "
                    "arguments to open the app window.")
    root.add_argument("--version", action="version", version=f"envy-vault {__version__}")
    commands = root.add_subparsers(dest="command")
    commands.add_parser("gui", help="open the ENVY Vault window (default)")
    for name, verb in (("encrypt", "Encrypt"), ("decrypt", "Decrypt")):
        sub = commands.add_parser(name, help=f"{verb.lower()} a file")
        sub.add_argument("source")
        sub.add_argument("destination", help="a new file; it is never overwritten")
    return root


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in (None, "gui"):
        from .gui import run_app
        return run_app()
    try:
        return _run_transform(args)
    except VaultError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
