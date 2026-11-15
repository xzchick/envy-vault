"""Property/fuzz hardening tests for the AES-256-GCM + scrypt envelope.

These complement the hand-picked cases in test_core.py with systematic coverage:
round-trip over many sizes, detection of a flip at *every* byte position, rejection
of *every* truncation length, randomized wrong secrets, salt/nonce uniqueness at
scale, MAGIC/AAD binding, and key-file mismatch. Standard library only.
"""
import os
import random
import unittest

from envy_vault import core

SECRET = b"correct horse battery staple"


class EnvelopeRoundTrip(unittest.TestCase):
    def test_round_trip_many_sizes(self):
        rng = random.Random(0xA11CE)
        edge = [0, 1, 15, 16, 17, 31, 32, 63, 64, 65, 255, 256, 257, 4095, 4096]
        for i in range(80):
            n = edge[i] if i < len(edge) else rng.randint(0, 6000)
            data = os.urandom(n)
            blob = core.encrypt_bytes(data, SECRET)
            self.assertTrue(blob.startswith(core.MAGIC))
            self.assertEqual(core.decrypt_bytes(blob, SECRET), data)

    def test_empty_plaintext_round_trips(self):
        blob = core.encrypt_bytes(b"", SECRET)
        self.assertEqual(core.decrypt_bytes(blob, SECRET), b"")


class EnvelopeTamper(unittest.TestCase):
    def test_single_byte_flip_at_every_position_detected(self):
        blob = core.encrypt_bytes(b"sensitive payload for tamper testing", SECRET)
        for i in range(len(blob)):
            bad = bytearray(blob)
            bad[i] ^= 0x01
            with self.assertRaises(core.VaultError, msg=f"flip at byte {i} not detected"):
                core.decrypt_bytes(bytes(bad), SECRET)

    def test_every_truncation_length_rejected(self):
        blob = core.encrypt_bytes(b"payload to be truncated", SECRET)
        for length in range(len(blob)):  # 0 .. len-1 (full length is the only valid one)
            with self.assertRaises(core.VaultError):
                core.decrypt_bytes(blob[:length], SECRET)

    def test_appended_bytes_rejected(self):
        blob = core.encrypt_bytes(b"payload", SECRET)
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(blob + b"\x00", SECRET)

    def test_magic_binding(self):
        blob = bytearray(core.encrypt_bytes(b"bound to the header", SECRET))
        blob[0] ^= 0x01  # corrupt the MAGIC header (the AEAD associated data)
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(bytes(blob), SECRET)

    def test_non_envelope_rejected(self):
        for junk in (b"", b"not an envelope", os.urandom(10), os.urandom(200)):
            with self.assertRaises(core.VaultError):
                core.decrypt_bytes(junk, SECRET)


class EnvelopeKeys(unittest.TestCase):
    def test_randomized_wrong_secret_fails(self):
        rng = random.Random(7)
        blob = core.encrypt_bytes(b"the real data", SECRET)
        for _ in range(50):
            wrong = bytes(rng.randrange(256) for _ in range(rng.randint(8, 48)))
            if wrong == SECRET:
                continue
            with self.assertRaises(core.VaultError):
                core.decrypt_bytes(blob, wrong)

    def test_keyfile_mismatch_fails_but_match_succeeds(self):
        blob = core.encrypt_bytes(b"data", SECRET, keyfile=b"key-file-material")
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(blob, SECRET)                      # no key-file
        with self.assertRaises(core.VaultError):
            core.decrypt_bytes(blob, SECRET, keyfile=b"wrong")   # wrong key-file
        self.assertEqual(
            core.decrypt_bytes(blob, SECRET, keyfile=b"key-file-material"), b"data")

    def test_salt_and_nonce_unique_at_scale(self):
        seen = set()
        h = len(core.MAGIC)
        span = core.SALT_BYTES + core.NONCE_BYTES
        for _ in range(150):
            hdr = core.encrypt_bytes(b"same plaintext", SECRET)[h:h + span]
            self.assertNotIn(hdr, seen)
            seen.add(hdr)


if __name__ == "__main__":
    unittest.main()
