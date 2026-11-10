"""Command-line entry point. The GUI is the default; subcommands are explicit."""

from __future__ import annotations

import argparse
import getpass
import sys

from . import __version__
from .core import VaultError, check_passphrase, decrypt_folder, encrypt_folder, transform_file


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


def _run_folder(args: argparse.Namespace) -> int:
    secret = _passphrase(confirm=args.command == "encrypt-folder")
    if args.command == "encrypt-folder":
        result = encrypt_folder(args.source, args.destination, secret)
        print(f"Encrypted {result['files']} file(s) → {result['output']} "
              f"({result['bytes']} bytes). The folder was left in place.")
    else:
        result = decrypt_folder(args.source, args.destination, secret)
        print(f"Restored {result['files']} file(s) under {result['output']}.")
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
    ef = commands.add_parser("encrypt-folder", help="archive and encrypt a whole folder into one vault file")
    ef.add_argument("source", help="the folder to encrypt (its files, minus symlinks)")
    ef.add_argument("destination", help="a new vault file; it is never overwritten")
    df = commands.add_parser("decrypt-folder", help="decrypt a folder vault and restore its files")
    df.add_argument("source", help="the folder vault file")
    df.add_argument("destination", help="a directory to restore the files under")
    comp = commands.add_parser("completions", help="print a shell completion script (bash or zsh)")
    comp.add_argument("--shell", choices=("bash", "zsh"), default="bash")
    return root


def _subcommand_names(parser: argparse.ArgumentParser) -> list[str]:
    """The subcommand names, read back from the parser so completions stay in sync."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices.keys())
    return []


_BASH_COMPLETION = r"""_envy_vault() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local subcommands="__SUBS__"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$subcommands --version --help" -- "$cur") )
        return
    fi
    case "${COMP_WORDS[1]}" in
        encrypt|decrypt) COMPREPLY=( $(compgen -f -- "$cur") ) ;;
        completions) COMPREPLY=( $(compgen -W "--shell bash zsh" -- "$cur") ) ;;
    esac
}
complete -F _envy_vault envy-vault
"""

_ZSH_COMPLETION = r"""#compdef envy-vault
_envy_vault() {
    local -a subcommands
    subcommands=(__SUBS__)
    if (( CURRENT == 2 )); then
        _describe 'command' subcommands
        return
    fi
    case ${words[2]} in
        encrypt|decrypt) _files ;;
        completions) _values 'shell' bash zsh ;;
    esac
}
_envy_vault "$@"
"""


def completion_script(shell: str, parser: argparse.ArgumentParser) -> str:
    subs = " ".join(_subcommand_names(parser))
    template = _ZSH_COMPLETION if shell == "zsh" else _BASH_COMPLETION
    return template.replace("__SUBS__", subs)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in (None, "gui"):
        from .gui import run_app
        return run_app()
    if args.command == "completions":
        print(completion_script(args.shell, parser))
        return 0
    try:
        if args.command in ("encrypt-folder", "decrypt-folder"):
            return _run_folder(args)
        return _run_transform(args)
    except VaultError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
