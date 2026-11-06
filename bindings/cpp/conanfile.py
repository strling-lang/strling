"""Conan 2 distribution of the canonical C++/C/native adapter stack."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMake, CMakeToolchain
from conan.tools.files import copy
from conan.tools.env import Environment


class StrlingConan(ConanFile):
    name = "strling"
    license = "Apache-2.0"
    url = "https://github.com/strling-lang/strling"
    description = "Canonical STRling compiler with C++17 and C adapters"
    package_type = "static-library"
    settings = "os", "arch", "compiler", "build_type"

    def set_version(self):
        policy = Path(self.recipe_folder).parents[1] / "governance/release-policy.json"
        if policy.is_file():
            version = json.loads(policy.read_text(encoding="utf-8"))["product"][
                "version"
            ]
            if self.version and str(self.version) != version:
                raise ConanInvalidConfiguration(
                    "Conan version override contradicts product policy"
                )
            self.version = version
        elif not self.version:
            raise ConanInvalidConfiguration("A governed release coordinate is required")

    def validate(self):
        if (
            str(self.settings.os) not in {"Windows", "Linux"}
            or str(self.settings.arch) != "x86_64"
        ):
            raise ConanInvalidConfiguration("Only Windows/Linux x86_64 is Supported")

    def export_sources(self):
        root = Path(self.recipe_folder).parents[1]
        paths = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--",
                "bindings/c",
                "bindings/cpp",
                "bindings/interop",
                "core",
                "spec",
                "tests/conformance",
                "governance/release-policy.json",
                "tooling/release_notices.py",
                "tooling/native_release_build.py",
                "LICENSE",
            ]
        ).split(b"\0")
        for raw in paths:
            if not raw:
                continue
            relative = Path(raw.decode("utf-8"))
            source = root / relative
            if source.is_symlink():
                raise ConanInvalidConfiguration(
                    "Release sources cannot contain symlinks"
                )
            target = Path(self.export_sources_folder) / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def layout(self):
        self.folders.source = "source"
        self.folders.build = "build"
        self.folders.generators = "build/generators"

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.variables["BUILD_TESTING"] = False
        toolchain.variables["Python3_EXECUTABLE"] = Path(sys.executable).as_posix()
        toolchain.generate()

    def build(self):
        cmake = CMake(self)
        environment = Environment()
        if str(self.settings.os) == "Linux":
            environment.define(
                "CFLAGS", "-ffile-prefix-map=" + self.source_folder + "=/strling"
            )
            environment.define(
                "CXXFLAGS", "-ffile-prefix-map=" + self.source_folder + "=/strling"
            )
        with environment.vars(self).apply():
            cmake.configure(build_script_folder="bindings/cpp")
            cmake.build()

    def package(self):
        CMake(self).install()
        copy(
            self,
            "LICENSE",
            src=self.source_folder,
            dst=str(Path(self.package_folder) / "licenses"),
        )
        subprocess.run(
            [
                sys.executable,
                str(Path(self.source_folder) / "tooling/release_notices.py"),
                "--output",
                str(Path(self.package_folder) / "licenses/THIRD_PARTY_NOTICES.txt"),
            ],
            check=True,
        )

    def package_info(self):
        archive_name = (
            "strling_interop.lib" if str(self.settings.os) == "Windows"
            else "libstrling_interop.a"
        )
        archive = Path(self.package_folder) / "lib" / archive_name
        if archive.stat().st_size > 128 * 1024 * 1024:
            raise ConanInvalidConfiguration("Native package exceeds the registered size limit")
        data = archive.read_bytes()
        prefix = b"\0STRLING-PRODUCT-VERSION:"
        expected = prefix + str(self.version).encode("ascii") + b"\0"
        if data.count(prefix) != 1 or data.count(expected) != 1:
            raise ConanInvalidConfiguration("Native package product identity mismatch")
        self.cpp_info.libs = ["strling_cpp", "strling", "strling_interop"]
        self.cpp_info.system_libs = (
            ["advapi32", "bcrypt", "ntdll", "userenv", "ws2_32"]
            if str(self.settings.os) == "Windows"
            else ["pthread", "dl", "m"]
        )
        self.cpp_info.set_property("cmake_file_name", "strling-cpp")
        self.cpp_info.set_property("cmake_target_name", "STRling::cpp")
