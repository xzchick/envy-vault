"""CLI tests that need no terminal and no display."""

import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from envy_vault import cli, core


class CLITest(unittest.TestCase):
    def invoke(self, *args, stdin_tty=False):
        out, err = io.StringIO(), io.StringIO()
        fake_stdin = type("S", (), {"isatty": lambda self: stdin_tty})()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.object(sys, "stdin", fake_stdin):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("envy-vault", out.getvalue())

    def test_encrypt_without_tty_is_a_clear_error(self):
        code, _, err = self.invoke("encrypt", "a", "b", stdin_tty=False)
        self.assertEqual(code, 2)
        self.assertIn("terminal", err.lower())

    def test_encrypt_then_decrypt_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "note.txt"
            src.write_bytes(b"cli round trip")
            enc, dec = Path(tmp) / "note.envy", Path(tmp) / "note.out"
            with patch("envy_vault.cli.getpass.getpass", return_value="a strong passphrase"):
                self.assertEqual(self.invoke("encrypt", src, enc, stdin_tty=True)[0], 0)
                self.assertEqual(self.invoke("decrypt", enc, dec, stdin_tty=True)[0], 0)
            self.assertEqual(dec.read_bytes(), b"cli round trip")
            self.assertTrue(src.exists())

    def test_parser_rejects_unknown_command(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["frobnicate"])

    def test_completions_bash(self):
        code, out, _ = self.invoke("completions", "--shell", "bash")
        self.assertEqual(code, 0)
        self.assertIn("complete -F _envy_vault envy-vault", out)
        for name in ("gui", "encrypt", "decrypt", "completions"):
            self.assertIn(name, out)

    def test_completions_zsh(self):
        code, out, _ = self.invoke("completions", "--shell", "zsh")
        self.assertEqual(code, 0)
        self.assertIn("#compdef envy-vault", out)
        self.assertIn("encrypt", out)

    def test_completions_default_is_bash_and_stays_in_sync(self):
        code, out, _ = self.invoke("completions")
        self.assertEqual(code, 0)
        self.assertIn("complete -F _envy_vault", out)
        # The subcommand list is derived from the parser, so a new command appears here too.
        self.assertEqual(set(cli._subcommand_names(cli.build_parser())),
                         {"gui", "encrypt", "decrypt", "encrypt-folder", "decrypt-folder", "completions"})


if __name__ == "__main__":
    unittest.main()
