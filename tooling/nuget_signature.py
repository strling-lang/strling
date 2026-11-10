"""Verify the sole registered NuGet repository-signature transformation.

This metadata-only verifier has no publisher or credential acquisition path.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from tooling.release_supply_chain import ReleaseSupplyChainError


def verify_nuget_registry_payload(payload: bytes, sbom: dict, *, fetch) -> dict:
    """Check exact certified content plus NuGet.org's mandatory repository seal.

    This is a registry transformation check, not build normalization. No archive
    content other than the verified repository signature may be added or changed.
    """
    from tooling.release_payload import archive_files

    files = archive_files(io.BytesIO(payload))
    expected = {}
    for row in sbom["files"]:
        _, name = row["fileName"].split("!/", 1)
        checksums = {
            item["algorithm"]: item["checksumValue"] for item in row["checksums"]
        }
        if name in expected or "SHA256" not in checksums:
            raise ReleaseSupplyChainError(
                "publication-companion", "invalid certified NuGet file graph"
            )
        expected[name] = checksums["SHA256"]
    observed = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
        if name != ".signature.p7s"
    }
    if ".signature.p7s" not in files or observed != expected:
        raise ReleaseSupplyChainError(
            "publication-companion",
            "public NuGet content differs from the certified package",
        )
    index_bytes = fetch(
        "https://api.nuget.org/v3-index/repository-signatures/5.0.0/index.json"
    )
    index = json.loads(index_bytes)
    fingerprints = [
        row["fingerprints"]["2.16.840.1.101.3.4.2.1"]
        for row in index.get("signingCertificates", [])
    ]
    if (
        index.get("allRepositorySigned") is not True
        or not fingerprints
        or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in fingerprints)
    ):
        raise ReleaseSupplyChainError(
            "publication-companion",
            "NuGet.org repository signing identities are unavailable",
        )
    with tempfile.TemporaryDirectory(prefix="strling-public-nuget-") as temporary:
        package = Path(temporary) / "package.nupkg"
        package.write_bytes(payload)
        command = ["dotnet", "nuget", "verify", str(package), "--all"]
        for fingerprint in fingerprints:
            command.extend(["--certificate-fingerprint", fingerprint])
        environment = {
            name: value
            for name, value in os.environ.items()
            if name.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "COMSPEC",
                "PATHEXT",
                "PROGRAMDATA",
                "DOTNET_ROOT",
                "TEMP",
                "TMP",
                "ALLUSERSPROFILE",
                "PROGRAMFILES",
                "PROGRAMFILES(X86)",
                "PROGRAMW6432",
                "COMMONPROGRAMFILES",
                "COMMONPROGRAMFILES(X86)",
                "COMMONPROGRAMW6432",
                "SYSTEMDRIVE",
            }
        }
        environment.update(
            DOTNET_CLI_HOME=temporary,
            HOME=temporary,
            USERPROFILE=temporary,
            APPDATA=str(Path(temporary) / "appdata"),
            LOCALAPPDATA=str(Path(temporary) / "localappdata"),
            NUGET_PLUGIN_PATHS="",
            DOTNET_CLI_TELEMETRY_OPTOUT="1",
            DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
            DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        )
        subprocess.run(
            command,
            cwd=temporary,
            env=environment,
            check=True,
            capture_output=True,
            timeout=120,
        )
    return {
        "file_sha256": observed,
        "repository_signature_sha256": hashlib.sha256(
            files[".signature.p7s"]
        ).hexdigest(),
        "signing_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
    }
