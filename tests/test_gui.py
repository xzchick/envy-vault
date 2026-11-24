"""Offscreen GUI tests: drive the real ENVY Vault window without a display."""
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PyQt6.QtGui import QDropEvent
    HAVE_QT = True
except Exception:  # pragma: no cover - PyQt6 missing
    HAVE_QT = False

PASS = "correct horse battery staple"


@unittest.skipUnless(HAVE_QT, "PyQt6 is not installed")
class VaultWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from envy_vault.gui import _build
        app_cls, cls.Window = _build()
        cls.app = app_cls.instance() or app_cls([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = self.Window()

    def tearDown(self):
        if self.w.worker:
            self.w.worker.wait(30000)
        self.w.timer.stop()
        self.w.close()
        self.tmp.cleanup()

    def run_job(self):
        self.w.go()
        self.assertIsNotNone(self.w.worker, self.w.status.text())
        deadline = time.monotonic() + 60
        while self.w.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(self.w.worker, "worker did not finish")

    def make_folder(self):
        folder = self.root / "case"
        (folder / "notes").mkdir(parents=True)
        (folder / "a.txt").write_text("alpha")
        (folder / "b.txt").write_text("bravo")
        (folder / "notes" / "c.txt").write_text("charlie")
        return folder

    def test_folder_source_switches_labels_and_destination(self):
        folder = self.make_folder()
        self.w.set_source(str(folder))
        self.assertIn("folder", self.w.go_btn.text().lower())
        self.assertEqual(self.w.dst.text(), str(folder) + ".envy")

    def test_dropping_an_envy_file_switches_to_decrypt(self):
        vault = self.root / "x.envy"; vault.write_bytes(b"ENVY")
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(vault))])
        event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.w.dropEvent(event)
        self.assertEqual(self.w.mode, "decrypt")
        self.assertEqual(self.w.src.text(), str(vault))
        self.assertEqual(self.w.dst.text(), str(self.root / "x"))

    def test_drop_without_local_file_is_ignored(self):
        mime = QMimeData(); mime.setText("not a file")
        self.assertIsNone(self.w._dropped_path(mime))

    def test_folder_round_trip_with_progress(self):
        folder = self.make_folder()
        self.w.set_source(str(folder)); self.w.pw.setText(PASS)
        self.run_job()
        self.assertIn("3 file(s)", self.w.status.text())
        self.assertEqual((self.w.bar.value(), self.w.bar.maximum()), (3, 3))

        self.w.set_mode("decrypt")
        self.w.set_source(str(folder) + ".envy")
        self.w.dst.setText(str(self.root / "restored"))
        self.run_job()
        self.assertIn("Decrypted", self.w.status.text())
        self.assertEqual((self.root / "restored" / "notes" / "c.txt").read_text(), "charlie")

    def test_file_round_trip_with_keyfile(self):
        src = self.root / "memo.txt"; src.write_text("top secret")
        key = self.root / "key.bin"; key.write_bytes(os.urandom(64))
        self.w.set_source(str(src)); self.w.pw.setText(PASS); self.w.kf.setText(str(key))
        self.run_job()
        self.assertTrue((self.root / "memo.txt.envy").exists())

        # Without the key file, decryption must fail and write nothing.
        self.w.kf.clear()
        self.w.set_source(str(self.root / "memo.txt.envy"))
        self.run_job()
        self.assertIn("Incorrect passphrase or key-file", self.w.status.text())
        self.assertEqual(src.read_text(), "top secret")  # original untouched

        self.w.kf.setText(str(key)); self.w.dst.setText(str(self.root / "memo.out"))
        self.run_job()
        self.assertEqual((self.root / "memo.out").read_text(), "top secret")

    def test_empty_keyfile_is_refused(self):
        src = self.root / "memo.txt"; src.write_text("x")
        empty = self.root / "empty.key"; empty.write_bytes(b"")
        self.w.set_source(str(src)); self.w.pw.setText(PASS); self.w.kf.setText(str(empty))
        self.w.go()
        self.assertIsNone(self.w.worker)
        self.assertIn("Key file", self.w.status.text())


if __name__ == "__main__":
    unittest.main()
