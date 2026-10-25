"""Data-only capsule/archive attacks; these do not create native observations."""

import base64
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from tooling import workstation_attestation as audit
from tooling import workstation_evidence as reader


class CapsuleTransportTests(unittest.TestCase):
    def setUp(self):
        self.payload = dict(
            contract="shared-workstation-profile-evidence-v2",
            files={"stdout.bin": base64.b64encode(bytes(range(256))).decode()},
            observations=[dict(samples=[2**63, 1], label="\u03bb")],
        )
        self.packet = reader.pack_profile_payload(self.payload)

    def repack(self, raw, compressed=None):
        packet = copy.deepcopy(self.packet)
        compressed = zlib.compress(raw) if compressed is None else compressed
        packet.update(
            raw_bytes=len(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            compressed_bytes=len(compressed),
            compressed_sha256=hashlib.sha256(compressed).hexdigest(),
            data_base64=base64.b64encode(compressed).decode(),
        )
        return packet

    def test_every_raw_byte_and_exact_integer_survives_transport(self):
        self.assertEqual(reader.unpack_profile_payload(self.packet), self.payload)
        self.assertEqual(reader.pack_profile_payload(self.payload), self.packet)

    def test_closed_fields_exact_sizes_and_both_pins_are_required(self):
        attacks = [
            lambda p: p.pop("raw_bytes"),
            lambda p: p.update(extra=True),
            lambda p: p.update(raw_bytes=True),
            lambda p: p.update(compressed_bytes=True),
            lambda p: p.update(raw_sha256="0" * 64),
            lambda p: p.update(compressed_sha256="0" * 64),
            lambda p: p.update(compressed_bytes=p["compressed_bytes"] + 1),
            lambda p: p.update(compression="gzip"),
            lambda p: p.update(data_base64="!"),
        ]
        for mutate in attacks:
            packet = copy.deepcopy(self.packet)
            mutate(packet)
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                reader.unpack_profile_payload(packet)

    def test_rehashed_trailing_truncated_and_expanding_streams_fail(self):
        raw = json.dumps(self.payload).encode()
        compressed = zlib.compress(raw)
        for content in (
            compressed + b"trailing",
            compressed + zlib.compress(raw),
            compressed[:-1],
            b"invalid",
        ):
            with self.subTest(content=content[:12]), self.assertRaises(ValueError):
                reader.unpack_profile_payload(self.repack(raw, content))
        packet = self.repack(raw)
        packet["raw_bytes"] = len(raw) - 1
        with self.assertRaises(ValueError):
            reader.unpack_profile_payload(packet)

    def test_declared_expansion_limit_is_checked_before_decompression(self):
        packet = copy.deepcopy(self.packet)
        packet["raw_bytes"] = 256 * 1024 * 1024 + 1
        with patch.object(reader.zlib, "decompressobj") as decompress:
            with self.assertRaises(ValueError):
                reader.unpack_profile_payload(packet)
        decompress.assert_not_called()

    def test_rehashed_duplicate_nonfinite_and_foreign_documents_fail(self):
        for raw in (
            b'{"contract":"shared-workstation-profile-evidence-v2","x":1,"x":2}',
            b'{"contract":"shared-workstation-profile-evidence-v2","x":NaN}',
            b'{"contract":"shared-workstation-cohort-v2"}',
            b"[]",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reader.unpack_profile_payload(self.repack(raw))


class ArchiveDataBoundaryTests(unittest.TestCase):
    def archive(self, entries):
        stream = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(stream, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name, content in entries:
                if isinstance(name, str):
                    info = zipfile.ZipInfo(name)
                    info.filename = name  # Preserve adversarial Windows separators.
                    name = info
                archive.writestr(name, content)
        return stream.getvalue()

    def test_regular_source_is_data_and_preserves_exact_bytes(self):
        raw = b"import candidate_code\r\n\x00"
        self.assertEqual(
            audit.archive_catalog(self.archive([("tooling/x.py", raw)])),
            {"tooling/x.py": raw},
        )

    def test_paths_duplicates_and_links_are_rejected(self):
        for name in ("../outside", "/absolute", "C:/drive", "a\\b", "a/../../outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.archive_catalog(self.archive([(name, b"x")]))
        with self.assertRaises(ValueError):
            audit.archive_catalog(self.archive([("a", b"x"), ("a", b"y")]))
        link = zipfile.ZipInfo("linked")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        with self.assertRaises(ValueError):
            audit.archive_catalog(self.archive([(link, b"../outside")]))

    def test_archive_member_and_expansion_denominators_are_bounded(self):
        fake = unittest.mock.MagicMock()
        fake.__enter__.return_value = fake
        for entries in (
            [unittest.mock.Mock(file_size=0)] * 10001,
            [unittest.mock.Mock(file_size=64 * 1024 * 1024 + 1)],
        ):
            fake.infolist.return_value = entries
            with (
                patch.object(audit.zipfile, "ZipFile", return_value=fake),
                self.assertRaises(ValueError),
            ):
                audit.archive_catalog(b"synthetic")


if __name__ == "__main__":
    unittest.main()
