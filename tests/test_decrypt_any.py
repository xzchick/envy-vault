import tempfile
import unittest
from pathlib import Path

from envy_vault import core

SECRET = b"correct horse battery staple"


class DecryptAnyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_vault_restores_a_file(self):
        src = self.root / "note.txt"; src.write_bytes(b"hello vault")
        core.transform_file("encrypt", src, self.root / "note.txt.envy", SECRET)
        result = core.decrypt_any(self.root / "note.txt.envy", self.root / "out.txt", SECRET)
        self.assertEqual(result["kind"], "file")
        self.assertEqual((self.root / "out.txt").read_bytes(), b"hello vault")

    def test_folder_vault_restores_the_tree_with_progress(self):
        folder = self.root / "case"; (folder / "sub").mkdir(parents=True)
        (folder / "a.txt").write_bytes(b"A"); (folder / "sub" / "b.bin").write_bytes(b"\x00\x01")
        core.encrypt_folder(folder, self.root / "case.envy", SECRET)
        seen = []
        result = core.decrypt_any(self.root / "case.envy", self.root / "restored", SECRET,
                                  progress=lambda d, t, n: seen.append((d, t, n)))
        self.assertEqual(result["kind"], "folder")
        self.assertEqual(result["files"], 2)
        self.assertEqual((self.root / "restored" / "sub" / "b.bin").read_bytes(), b"\x00\x01")
        self.assertEqual([(d, t) for d, t, _ in seen], [(1, 2), (2, 2)])

    def test_keyfile_is_required_when_used(self):
        src = self.root / "s.txt"; src.write_bytes(b"secret")
        core.transform_file("encrypt", src, self.root / "s.envy", SECRET, b"keyfile-bytes")
        with self.assertRaises(core.VaultError):
            core.decrypt_any(self.root / "s.envy", self.root / "x", SECRET)
        core.decrypt_any(self.root / "s.envy", self.root / "y", SECRET, b"keyfile-bytes")
        self.assertEqual((self.root / "y").read_bytes(), b"secret")

    def test_wrong_passphrase_writes_nothing(self):
        src = self.root / "s.txt"; src.write_bytes(b"secret")
        core.transform_file("encrypt", src, self.root / "s.envy", SECRET)
        with self.assertRaises(core.VaultError):
            core.decrypt_any(self.root / "s.envy", self.root / "nope", b"wrong passphrase!!")
        self.assertFalse((self.root / "nope").exists())


if __name__ == "__main__":
    unittest.main()
