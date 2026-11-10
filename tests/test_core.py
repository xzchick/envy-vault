"""Core encryption tests, including a golden vector from the original Vault."""

import base64
import os
from pathlib import Path
import tempfile
import unittest

from envy_vault import core

# Produced by ENVY BLACK VEIL's original Vault (envy/vault.py) for the payload
# and passphrase below. It locks in byte-compatibility: envy-vault must read
# files the original wrote.
ORIGINAL_SECRET = b"correct horse battery staple"
ORIGINAL_PLAINTEXT = b"ENVY interop test payload"
ORIGINAL_ENVELOPE = base64.b64decode(
    "RU5WWVZBVUxUMgDFp2D6LUT9nxlgYG3iMKkY336J0E6FNwNcZEYpVJrJXvo5xLBniY7g"
    "CU76BwRfXPRX6NZ1ukj+v1tcoLte85/NNyiwPM0="
)


class EnvelopeTest(unittest.TestCase):
    def test_round_trip(self):
        secret = b"a strong enough secret"
        for payload in (b"", b"x", os.urandom(4096)):
            blob = core.encrypt_bytes(payload, secret)
            self.assertTrue(blob.startswith(core.MAGIC))
            self.assertEqual(core.decrypt_bytes(blob, secret), payload)

    def test_reads_original_vault_file(self):
        self.assertEqual(core.decrypt_bytes(ORIGINAL_ENVELOPE, ORIGINAL_SECRET), ORIGINAL_PLAINTEXT)

    def test_wrong_passphrase_fails(self):
        blob = core.encrypt_bytes(b"secret data", b"the right passphrase")
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(blob, b"the wrong passphrase")

    def test_tampered_envelope_fails(self):
        blob = bytearray(core.encrypt_bytes(b"secret data", b"passphrase here"))
        blob[-1] ^= 0x01
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(bytes(blob), b"passphrase here")

    def test_non_envelope_is_rejected(self):
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(b"just some plain bytes", b"passphrase here")

    def test_unique_salt_and_nonce_per_call(self):
        a = core.encrypt_bytes(b"same", b"same passphrase here")
        b = core.encrypt_bytes(b"same", b"same passphrase here")
        self.assertNotEqual(a, b)

    def test_short_passphrase_rejected(self):
        with self.assertRaises(core.VaultError):
            core.check_passphrase(b"short")
        self.assertEqual(core.check_passphrase(b"a dozen bytes!"), b"a dozen bytes!")


class FileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="envy-vault-"))
        self.addCleanup(__import__("shutil").rmtree, self.dir)

    def test_encrypt_then_decrypt_file_preserves_source(self):
        plain = self.dir / "note.txt"
        plain.write_bytes(b"hello vault")
        enc, dec = self.dir / "note.enc", self.dir / "note.out"
        core.transform_file("encrypt", plain, enc, b"a good passphrase")
        self.assertTrue(plain.exists())
        core.transform_file("decrypt", enc, dec, b"a good passphrase")
        self.assertEqual(dec.read_bytes(), b"hello vault")

    def test_folder_round_trip(self):
        src = self.dir / "proj"
        (src / "sub").mkdir(parents=True)
        (src / "a.txt").write_bytes(b"alpha")
        (src / "sub" / "b.bin").write_bytes(b"\x00\x01\x02beta")
        (src / "sub" / "deep").mkdir()
        (src / "sub" / "deep" / "c.md").write_text("# gamma\n")
        vault = self.dir / "proj.vault"
        res = core.encrypt_folder(src, vault, b"a good passphrase")
        self.assertEqual(res["files"], 3)
        self.assertTrue(src.exists(), "source folder preserved")
        out = self.dir / "restored"
        dres = core.decrypt_folder(vault, out, b"a good passphrase")
        self.assertEqual(dres["files"], 3)
        self.assertEqual((out / "a.txt").read_bytes(), b"alpha")
        self.assertEqual((out / "sub" / "b.bin").read_bytes(), b"\x00\x01\x02beta")
        self.assertEqual((out / "sub" / "deep" / "c.md").read_text(), "# gamma\n")

    def test_folder_skips_symlinks(self):
        src = self.dir / "proj"
        src.mkdir()
        (src / "real.txt").write_bytes(b"real")
        try:
            (src / "link.txt").symlink_to(src / "real.txt")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        res = core.encrypt_folder(src, self.dir / "p.vault", b"a good passphrase")
        self.assertEqual(res["files"], 1)       # only the regular file

    def test_decrypt_folder_rejects_path_traversal(self):
        blob = core._ARCHIVE_MAGIC + (1).to_bytes(4, "big")
        rel = b"../escape.txt"
        blob += len(rel).to_bytes(2, "big") + rel
        payload = b"pwned"
        blob += len(payload).to_bytes(8, "big") + payload
        forged = self.dir / "evil.vault"
        forged.write_bytes(core.encrypt_bytes(blob, b"a good passphrase"))
        with self.assertRaises(core.VaultError):
            core.decrypt_folder(forged, self.dir / "out", b"a good passphrase")
        self.assertFalse((self.dir / "escape.txt").exists())

    def test_decrypt_folder_rejects_non_folder_vault(self):
        plain = self.dir / "f.txt"; plain.write_bytes(b"just a file")
        enc = self.dir / "f.enc"
        core.transform_file("encrypt", plain, enc, b"a good passphrase")
        with self.assertRaises(core.VaultError):
            core.decrypt_folder(enc, self.dir / "out", b"a good passphrase")

    def test_never_overwrites_destination(self):
        plain = self.dir / "a.txt"
        plain.write_bytes(b"data")
        dest = self.dir / "exists.enc"
        dest.write_bytes(b"do not clobber")
        with self.assertRaises(core.VaultError):
            core.transform_file("encrypt", plain, dest, b"a good passphrase")
        self.assertEqual(dest.read_bytes(), b"do not clobber")

    def test_missing_source_is_clear(self):
        with self.assertRaises(core.VaultError):
            core.transform_file("encrypt", self.dir / "nope", self.dir / "out.enc", b"a good passphrase")

    def test_size_limit_enforced(self):
        big = self.dir / "big.bin"
        big.write_bytes(b"\x00" * 128)
        with self.assertRaises(core.VaultError):
            core.read_regular(big, limit=64)


if __name__ == "__main__":
    unittest.main()
