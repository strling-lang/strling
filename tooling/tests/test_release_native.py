import struct

import pytest

from tooling.release_native import EXPORTS, inspect_native


def elf_fixture(*, search_path=None, dependency="libc.so.6"):
    data = bytearray(4096)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<HH", data, 16, 3, 62)
    struct.pack_into("<Q", data, 40, 64)
    struct.pack_into("<HH", data, 58, 64, 4)
    strings = bytearray(b"\0")

    def add(text):
        offset = len(strings)
        strings.extend(text.encode() + b"\0")
        return offset

    symbols = [add(name) for name in sorted(EXPORTS)]
    library = add(dependency)
    path = add(search_path) if search_path else None
    data[512 : 512 + len(strings)] = strings
    struct.pack_into(
        "<IIQQQQIIQQ", data, 128, 0, 3, 0, 0, 512, len(strings), 0, 0, 1, 0
    )
    struct.pack_into(
        "<IIQQQQIIQQ", data, 192, 0, 11, 0, 0, 1024, 24 * len(symbols), 1, 0, 8, 24
    )
    for i, symbol in enumerate(symbols):
        struct.pack_into("<IBBHQQ", data, 1024 + i * 24, symbol, 0x12, 0, 1, 0, 0)
    struct.pack_into("<IIQQQQIIQQ", data, 256, 0, 6, 0, 0, 2048, 48, 1, 0, 8, 16)
    struct.pack_into("<qQ", data, 2048, 1, library)
    if path:
        struct.pack_into("<qQ", data, 2064, 29, path)
    return bytes(data)


def test_elf_exact_exports_and_system_dependencies():
    assert inspect_native(elf_fixture()) == dict(
        platform="linux-x86_64",
        exports=sorted(EXPORTS),
        dependencies=["libc.so.6"],
        search_paths=[],
    )


@pytest.mark.parametrize(
    "path", ["/developer/workspace", "$ORIGIN/../private", "/usr/lib"]
)
def test_elf_rejects_unregistered_library_search_paths(path):
    with pytest.raises(ValueError, match="search path"):
        inspect_native(elf_fixture(search_path=path))


def test_elf_rejects_unregistered_dependency():
    with pytest.raises(ValueError, match="dependency"):
        inspect_native(elf_fixture(dependency="libdeveloper.so"))


def pe_fixture(*, exports=EXPORTS, dependency="KERNEL32.dll"):
    data = bytearray(4608)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HH", data, 132, 0x8664, 1)
    struct.pack_into("<H", data, 148, 240)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<IIII", data, 264, 0x1000, 256, 0x1500, 40)
    struct.pack_into(
        "<8sIIIIIIHHI", data, 392, b".rdata", 4096, 0x1000, 4096, 512, 0, 0, 0, 0, 0
    )
    struct.pack_into("<I", data, 536, len(exports))
    struct.pack_into("<I", data, 544, 0x1100)
    for i, name in enumerate(sorted(exports)):
        offset = 1024 + i * 100
        struct.pack_into("<I", data, 768 + i * 4, offset - 512 + 0x1000)
        data[offset : offset + len(name)] = name.encode()
    struct.pack_into("<IIIII", data, 1792, 0, 0, 0, 0x1600, 0)
    data[2048 : 2048 + len(dependency)] = dependency.encode()
    return bytes(data)


def test_pe_exact_exports_and_system_dependencies():
    assert inspect_native(pe_fixture()) == dict(
        platform="windows-x86_64",
        exports=sorted(EXPORTS),
        dependencies=["kernel32.dll"],
        search_paths=[],
    )


@pytest.mark.parametrize(
    "exports",
    [set(), EXPORTS - {next(iter(EXPORTS))}, EXPORTS | {"unregistered_export"}],
)
def test_pe_missing_extra_exports_fail(exports):
    with pytest.raises(ValueError, match="exported ABI"):
        inspect_native(pe_fixture(exports=exports))


@pytest.mark.parametrize(
    "dependency",
    [
        "developer.dll",
        "C:/workspace/kernel.dll",
        "../KERNEL32.dll",
        "api-ms-win-crt-../evil.dll",
    ],
)
def test_unregistered_or_path_dependencies_fail(dependency):
    with pytest.raises(ValueError):
        inspect_native(pe_fixture(dependency=dependency))


@pytest.mark.parametrize("length", [0, 63, 128, 392, 600, 2048])
def test_truncated_native_metadata_fails(length):
    with pytest.raises((ValueError, UnicodeError)):
        inspect_native(pe_fixture()[:length])


def test_unbounded_export_count_fails():
    data = bytearray(pe_fixture())
    struct.pack_into("<I", data, 536, 0xFFFFFFFF)
    with pytest.raises(ValueError, match="export count"):
        inspect_native(bytes(data))
