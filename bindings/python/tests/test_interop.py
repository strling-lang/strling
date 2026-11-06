from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import importlib.metadata
import json
from types import SimpleNamespace

import pytest
import STRling.interop as interop

from STRling.interop import (
    INTEROP_PROTOCOL_VERSION,
    MAX_INTEROP_REQUEST_BYTES,
    InteropProtocolError,
    NativeAdapterError,
    NativeClient,
    NativeLoadError,
    load_native,
)


@pytest.mark.parametrize(
    "failure", ["missing", "version", "checksum", "protocol", "abi"]
)
def test_installed_wheel_rejects_mismatched_kernel_before_loading(
    tmp_path, monkeypatch, failure
):
    package = tmp_path / "STRling"
    native = package / "_native"
    native.mkdir(parents=True)
    library = tmp_path / "selected-library"
    library.write_bytes(b"fixture native payload")
    identity = dict(
        product_version="4.0.0",
        native_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        protocol_version="1.0.0",
        abi_major=1,
    )
    field = {
        "version": "product_version",
        "checksum": "native_sha256",
        "protocol": "protocol_version",
        "abi": "abi_major",
    }
    if failure != "missing":
        identity[field[failure]] = "wrong"
        (native / "kernel-identity.json").write_text(json.dumps(identity))
    monkeypatch.setattr(interop, "__file__", str(package / "interop.py"))
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda _: SimpleNamespace(
            version="4.0.0", files=["STRling-4.0.0.dist-info/RECORD"]
        ),
    )
    monkeypatch.setattr(
        interop.ctypes,
        "CDLL",
        lambda _: pytest.fail("mismatched native payload was loaded"),
    )
    with pytest.raises(NativeLoadError, match="identity"):
        NativeClient(library)


def test_explicit_native_library_describes_exact_abi(native_library: Path) -> None:
    client = load_native(native_library)
    description = client.describe()
    assert description["protocol_version"] == INTEROP_PROTOCOL_VERSION
    assert description["native_abi"]["id"] == "strling.c-abi"
    assert description["native_abi"]["major"] == 1


def test_stable_protocol_errors_remain_values(native_library: Path) -> None:
    client = NativeClient(native_library)
    response = client.execute(
        {
            "interop_protocol_version": INTEROP_PROTOCOL_VERSION,
            "operation": "not-supported",
            "payload": {},
        }
    )
    assert response["status"] == "error"
    assert response["error"] == {
        "code": "STRL-INTEROP-0005",
        "path": "$.operation",
    }


def test_invalid_utf8_and_host_bounds_are_distinct(native_library: Path) -> None:
    client = NativeClient(native_library)
    response = client.execute_bytes(b"\xff")
    assert response["error"] == {"code": "STRL-INTEROP-0001", "path": "$"}
    with pytest.raises(NativeAdapterError):
        client.execute_bytes(b"0" * (MAX_INTEROP_REQUEST_BYTES + 1))


def test_non_finite_request_values_fail_before_native_execution(
    native_library: Path,
) -> None:
    with pytest.raises(NativeAdapterError, match="not strict JSON"):
        NativeClient(native_library).execute({"value": float("nan")})


def test_high_level_invalid_payload_raises_typed_interop_error(
    native_library: Path,
) -> None:
    client = NativeClient(native_library)
    with pytest.raises(InteropProtocolError) as captured:
        client.compile({})
    assert captured.value.code == "STRL-INTEROP-0007"
    assert captured.value.path == "$.payload.compile_request"


def test_repeated_owned_response_cycles(native_library: Path) -> None:
    client = NativeClient(native_library)
    for _ in range(128):
        assert client.describe()["protocol_version"] == INTEROP_PROTOCOL_VERSION


def test_native_calls_are_reentrant_and_deterministic(native_library: Path) -> None:
    client = NativeClient(native_library)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: client.describe(), range(64)))
    assert all(result == results[0] for result in results)


def test_missing_library_has_no_implicit_fallback(tmp_path: Path) -> None:
    with pytest.raises(NativeLoadError):
        load_native(tmp_path / "missing-native-library")


@pytest.mark.parametrize(
    "payload",
    [
        b"old kernel",
        b"\0STRLING-PRODUCT-VERSION:3.0.0\0",
        b"\0STRLING-PRODUCT-VERSION:4.0.0\0\0STRLING-PRODUCT-VERSION:4.0.0\0",
    ],
)
def test_native_product_mismatch_rejected_before_loading(
    tmp_path, monkeypatch, payload
):
    import ctypes

    path = tmp_path / "wrong-kernel.so"
    path.write_bytes(payload)

    def forbidden_load(*args):
        raise AssertionError("mismatched kernel must never reach CDLL")

    monkeypatch.setattr(ctypes, "CDLL", forbidden_load)
    with pytest.raises(NativeLoadError, match="product identity mismatch"):
        NativeClient(path)
