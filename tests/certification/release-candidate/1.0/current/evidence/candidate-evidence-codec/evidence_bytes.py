"""Bounded, lossless transport of explicitly selected supplemental evidence."""

import base64
import gzip
import hashlib
import json
import re
import zlib

MAX_RAW = 16 * 1024 * 1024
MAX_ENCODED = 900000
KEYS = {
    "schema_version",
    "document_kind",
    "source",
    "original_name",
    "bytes",
    "sha256",
    "encoding",
    "payload",
}


def need(value, message):
    if not value:
        raise ValueError(message)


def encode(data, name, source):
    need(isinstance(data, bytes) and len(data) <= MAX_RAW, "metadata size bound")
    need(re.fullmatch("[A-Za-z0-9._+-]+", name) is not None, "metadata name")
    payload = base64.b64encode(gzip.compress(data, mtime=0)).decode("ascii")
    need(len(payload) <= MAX_ENCODED, "encoded size bound")
    result = dict(
        schema_version="strling-evidence-byte-archive-v1",
        document_kind="supplemental-evidence-bytes",
        source=source,
        original_name=name,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        encoding="gzip+base64",
        payload=payload,
    )
    need(decode(result, source) == data, "round trip")
    return (json.dumps(result, indent=2) + "\n").encode()


def decode(document, source):
    need(isinstance(document, dict) and set(document) == KEYS, "archive fields")
    need(
        document["schema_version"] == "strling-evidence-byte-archive-v1"
        and document["document_kind"] == "supplemental-evidence-bytes",
        "archive identity",
    )
    need(
        document["source"] == source
        and re.fullmatch("[a-f0-9]{40}", source) is not None,
        "archive source",
    )
    need(
        isinstance(document["original_name"], str)
        and re.fullmatch("[A-Za-z0-9._+-]+", document["original_name"]) is not None
        and document["original_name"] not in (".", ".."),
        "archive name",
    )
    size = document["bytes"]
    need(type(size) is int and 0 <= size <= MAX_RAW, "archive byte bound")
    need(
        isinstance(document["sha256"], str)
        and re.fullmatch("[a-f0-9]{64}", document["sha256"]) is not None,
        "archive checksum",
    )
    need(
        document["encoding"] == "gzip+base64"
        and isinstance(document["payload"], str)
        and len(document["payload"]) <= MAX_ENCODED,
        "archive encoding",
    )
    try:
        packed = base64.b64decode(document["payload"], validate=True)
        stream = zlib.decompressobj(31)
        raw = stream.decompress(packed, size + 1)
        need(
            len(raw) == size
            and not stream.unconsumed_tail
            and not stream.unused_data
            and stream.eof,
            "archive size, tail or completeness",
        )
    except (ValueError, zlib.error) as error:
        raise ValueError("invalid bounded archive") from error
    need(
        hashlib.sha256(raw).hexdigest() == document["sha256"],
        "archive content checksum",
    )
    return raw
