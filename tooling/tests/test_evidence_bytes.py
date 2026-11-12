"""Qualify the retained lossless metadata format and its bounded decoder."""

import base64
import copy
import gzip
import json
import unittest

from tooling.evidence_bytes import MAX_ENCODED, MAX_RAW, decode, encode


class EvidenceByteTests(unittest.TestCase):
    def test_exact_roundtrip_and_adversarial_bounds(self):
        source = "a" * 40
        raw = b"First\r\nsecond\nno-final-newline"
        document = json.loads(encode(raw, "preparation.log", source))
        self.assertEqual(raw, decode(document, source))
        mutations = {
            "source": lambda row: row.update(source="b" * 40),
            "schema": lambda row: row.update(schema_version="wrong"),
            "kind": lambda row: row.update(document_kind="wrong"),
            "encoding": lambda row: row.update(encoding="wrong"),
            "name-traversal": lambda row: row.update(original_name="../secret"),
            "name-empty": lambda row: row.update(original_name=""),
            "missing": lambda row: row.pop("sha256"),
            "extra": lambda row: row.update(unrecognized=True),
            "negative-size": lambda row: row.update(bytes=-1),
            "boolean-size": lambda row: row.update(bytes=True),
            "oversize": lambda row: row.update(bytes=MAX_RAW + 1),
            "wrong-size": lambda row: row.update(bytes=row["bytes"] + 1),
            "hash": lambda row: row.update(sha256="0" * 64),
            "corruption": lambda row: row.update(payload="!"),
            "truncation": lambda row: row.update(
                payload=base64.b64encode(base64.b64decode(row["payload"])[:-4]).decode()
            ),
            "trailing-stream": lambda row: row.update(
                payload=base64.b64encode(
                    base64.b64decode(row["payload"]) + gzip.compress(b"extra")
                ).decode()
            ),
            "encoded-bound": lambda row: row.update(payload="a" * (MAX_ENCODED + 1)),
            "decompression-bound": lambda row: row.update(
                bytes=1,
                payload=base64.b64encode(gzip.compress(b"x" * 1000000)).decode(),
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                changed = copy.deepcopy(document)
                mutate(changed)
                with self.assertRaises(ValueError):
                    decode(changed, source)
