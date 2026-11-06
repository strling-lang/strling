"""Bounded, non-executing export and dependency inspection of release kernels."""

from __future__ import annotations

import struct

EXPORTS = {
    "strling_interop_abi_version_v1",
    "strling_interop_execute_v1",
    "strling_interop_owned_bytes_free_v1",
}


def inspect_native(data: bytes) -> dict:
    if len(data) > 128 * 1024 * 1024:
        raise ValueError("native payload exceeds inspection limit")

    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data):
            raise ValueError("truncated native metadata")
        return struct.unpack_from(fmt, data, offset)

    def string(offset, end=None):
        end = min(len(data), end if end is not None else offset + 4096)
        stop = data.find(b"\0", offset, end)
        if offset < 0 or stop < offset:
            raise ValueError("unterminated native metadata")
        return data[offset:stop].decode("ascii")

    exports, dependencies, search_paths = set(), set(), []
    if data.startswith(b"\x7fELF\x02\x01"):
        if unpack("<HH", 16) != (3, 62):
            raise ValueError("native ELF must be an x86_64 shared object")
        table = unpack("<Q", 40)[0]
        size, count = unpack("<HH", 58)
        if size != 64 or count == 0 or count > 4096:
            raise ValueError("invalid ELF section table")
        sections = [unpack("<IIQQQQIIQQ", table + i * size) for i in range(count)]

        def strings(section):
            if section[6] >= count:
                raise ValueError("ELF string table link is invalid")
            linked = sections[section[6]]
            start, length = linked[4:6]
            if start + length > len(data):
                raise ValueError("ELF string table is truncated")
            return start, start + length

        for section in sections:
            kind, start, length = section[1], section[4], section[5]
            if kind not in {6, 11}:
                continue
            stride = 16 if kind == 6 else 24
            if (
                section[9] != stride
                or length % stride
                or length // stride > 100000
                or start + length > len(data)
            ):
                raise ValueError("invalid ELF dynamic metadata")
            strings_start, strings_end = strings(section)
            for offset in range(start, start + length, stride):
                if kind == 11:
                    name, info, other, index, _, _ = unpack("<IBBHQQ", offset)
                    if index and info >> 4 in {1, 2} and other & 3 == 0:
                        exports.add(string(strings_start + name, strings_end))
                else:
                    tag, value = unpack("<qQ", offset)
                    if tag in {1, 15, 29}:
                        text = string(strings_start + value, strings_end)
                        (
                            dependencies.add(text)
                            if tag == 1
                            else search_paths.append(text)
                        )
        allowed = {
            "libgcc_s.so.1",
            "libc.so.6",
            "libm.so.6",
            "libdl.so.2",
            "libpthread.so.0",
            "ld-linux-x86-64.so.2",
        }
        platform = "linux-x86_64"
    elif data.startswith(b"MZ"):
        pe = unpack("<I", 60)[0]
        if data[pe : pe + 4] != b"PE\0\0" or unpack("<H", pe + 4)[0] != 0x8664:
            raise ValueError("native PE must be x86_64")
        count = unpack("<H", pe + 6)[0]
        optional_size = unpack("<H", pe + 20)[0]
        optional = pe + 24
        if (
            unpack("<H", optional)[0] != 0x20B
            or count == 0
            or count > 96
            or optional_size < 128
        ):
            raise ValueError("invalid PE metadata")
        sections = [
            unpack("<8sIIIIIIHHI", optional + optional_size + i * 40)
            for i in range(count)
        ]

        def address(rva, length=1):
            for section in sections:
                virtual_size, virtual, raw_size, raw = section[1:5]
                if virtual <= rva and rva + length <= virtual + min(
                    virtual_size, raw_size
                ):
                    result = raw + rva - virtual
                    if result + length <= len(data):
                        return result
            raise ValueError("PE metadata address is outside file-backed sections")

        export_rva, export_size, import_rva, import_size = unpack(
            "<IIII", optional + 112
        )
        directory = address(export_rva, 40)
        number = unpack("<I", directory + 24)[0]
        names = unpack("<I", directory + 32)[0]
        if number > 4096 or export_size < 40:
            raise ValueError("invalid PE export count")
        for i in range(number):
            rva = unpack("<I", address(names + i * 4, 4))[0]
            exports.add(string(address(rva)))
        if import_rva:
            if import_size > 20000 or import_size < 20:
                raise ValueError("invalid PE import table")
            terminated = False
            for i in range(import_size // 20):
                row = unpack("<IIIII", address(import_rva + i * 20, 20))
                if not any(row):
                    terminated = True
                    break
                dependencies.add(string(address(row[3])).lower())
            if not terminated:
                raise ValueError("unterminated PE import table")
        allowed = {
            "kernel32.dll",
            "advapi32.dll",
            "bcrypt.dll",
            "userenv.dll",
            "ws2_32.dll",
            "ntdll.dll",
            "ucrtbase.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "msvcrt.dll",
        }
        allowed.update(
            name
            for name in dependencies
            if name.startswith("api-ms-win-crt-")
            and name.endswith(".dll")
            and "/" not in name
            and "\\" not in name
        )
        platform = "windows-x86_64"
    else:
        raise ValueError("unregistered native object format")
    if exports != EXPORTS:
        raise ValueError(
            "native exported ABI differs from the exact three-function contract"
        )
    if not dependencies or dependencies - allowed or search_paths:
        raise ValueError(
            "native payload has an unregistered dependency or library search path"
        )
    return {
        "platform": platform,
        "exports": sorted(exports),
        "dependencies": sorted(dependencies),
        "search_paths": search_paths,
    }
