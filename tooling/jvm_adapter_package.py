"""Certify JVM adapter release graphs, licenses, advisory state, and consumers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PRODUCT_VERSION = json.loads(
    (ROOT / "governance/release-policy.json").read_text(encoding="utf-8")
)["product"]["version"]
GRAPH_PATH = ROOT / "tests/adapters/3.0/release-graph.json"
OSV_ENDPOINT = "https://api.osv.dev/v1/querybatch"
EXTERNAL_PACKAGES = (
    ("com.fasterxml.jackson.core:jackson-annotations", "2.18.11", "Apache-2.0"),
    ("com.fasterxml.jackson.core:jackson-core", "2.18.11", "Apache-2.0"),
    ("com.fasterxml.jackson.core:jackson-databind", "2.18.11", "Apache-2.0"),
    ("net.java.dev.jna:jna", "5.19.1", "LGPL-2.1-or-later OR Apache-2.0"),
    ("org.jetbrains:annotations", "13.0", "Apache-2.0"),
    ("org.jetbrains.kotlin:kotlin-stdlib", "2.0.20", "Apache-2.0"),
)
INTERNAL_PACKAGES = (
    ("com.strling:strling", PRODUCT_VERSION),
    ("com.strling:strling-jvm", PRODUCT_VERSION),
    ("com.strling:strling-kotlin", PRODUCT_VERSION),
)
ROOT_GRAPHS = {
    "java": (
        f"com.strling:strling:{PRODUCT_VERSION}",
        f"com.strling:strling-jvm:{PRODUCT_VERSION}",
        "net.java.dev.jna:jna:5.19.1",
        "com.fasterxml.jackson.core:jackson-databind:2.18.11",
        "com.fasterxml.jackson.core:jackson-annotations:2.18.11",
        "com.fasterxml.jackson.core:jackson-core:2.18.11",
    ),
    "jvm": (
        f"com.strling:strling-jvm:{PRODUCT_VERSION}",
        "net.java.dev.jna:jna:5.19.1",
        "com.fasterxml.jackson.core:jackson-databind:2.18.11",
        "com.fasterxml.jackson.core:jackson-annotations:2.18.11",
        "com.fasterxml.jackson.core:jackson-core:2.18.11",
    ),
    "kotlin": (
        f"com.strling:strling-kotlin:{PRODUCT_VERSION}",
        "org.jetbrains.kotlin:kotlin-stdlib:2.0.20",
        "org.jetbrains:annotations:13.0",
        f"com.strling:strling-jvm:{PRODUCT_VERSION}",
        "net.java.dev.jna:jna:5.19.1",
        "com.fasterxml.jackson.core:jackson-databind:2.18.11",
        "com.fasterxml.jackson.core:jackson-annotations:2.18.11",
        "com.fasterxml.jackson.core:jackson-core:2.18.11",
    ),
}


class JvmPackageCertificationError(RuntimeError):
    """The JVM release graph or clean-consumer proof failed."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _fingerprint(value: Mapping[str, Any]) -> str:
    normalized = {key: item for key, item in value.items() if key != "fingerprint"}
    return f"sha256:{hashlib.sha256(_canonical(normalized)).hexdigest()}"


def _require_manifest_markers() -> None:
    files = {
        "bindings/jvm/pom.xml": (
            "<artifactId>strling-jvm</artifactId>",
            "<artifactId>jna</artifactId>",
            "<jna.version>5.19.1</jna.version>",
            "<artifactId>jackson-databind</artifactId>",
            "<jackson.version>2.18.11</jackson.version>",
            "<artifactId>maven-jar-plugin</artifactId>",
            "<addMavenDescriptor>false</addMavenDescriptor>",
        ),
        "bindings/java/pom.xml": (
            "<artifactId>strling</artifactId>",
            "<artifactId>strling-jvm</artifactId>",
            f"<version>{PRODUCT_VERSION}</version>",
        ),
        "bindings/kotlin/build.gradle.kts": (
            f'api("com.strling:strling-jvm:{PRODUCT_VERSION}")',
            'kotlin("jvm") version "2.0.20"',
        ),
    }
    for relative, markers in files.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise JvmPackageCertificationError(
                f"{relative} does not match the locked release graph: {missing!r}"
            )
    java = (ROOT / "bindings/java/pom.xml").read_text(encoding="utf-8")
    kotlin = (ROOT / "bindings/kotlin/build.gradle.kts").read_text(encoding="utf-8")
    if "net.java.dev.jna" in java or "net.java.dev.jna" in kotlin:
        raise JvmPackageCertificationError("a host package bypasses strling-jvm")


def build_graph() -> dict[str, Any]:
    _require_manifest_markers()
    packages = [
        {
            "coordinate": f"{name}:{version}",
            "ecosystem": "Maven",
            "internal": True,
            "license": "Apache-2.0",
        }
        for name, version in INTERNAL_PACKAGES
    ]
    packages.extend(
        {
            "coordinate": f"{name}:{version}",
            "ecosystem": "Maven",
            "internal": False,
            "license": license_expression,
            "license_disposition": (
                "Apache-2.0 branch selected"
                if name == "net.java.dev.jna:jna"
                else "permitted"
            ),
        }
        for name, version, license_expression in EXTERNAL_PACKAGES
    )
    value: dict[str, Any] = {
        "schema_version": "jvm-release-graph-v1",
        "roots": {key: list(value) for key, value in sorted(ROOT_GRAPHS.items())},
        "packages": sorted(packages, key=lambda item: item["coordinate"]),
        "native_payload": {
            "packaged": False,
            "load_mode": "caller-supplied absolute path",
            "reason": "P17-T04 certifies only the locally executed Windows x86_64 native row; no unexecuted classifier is advertised.",
        },
    }
    value["fingerprint"] = _fingerprint(value)
    return value


def synchronize(*, write: bool) -> dict[str, Any]:
    expected = build_graph()
    actual = None
    if GRAPH_PATH.is_file():
        try:
            actual = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            actual = None
    matches = actual == expected
    if write and not matches:
        GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRAPH_PATH.write_text(
            json.dumps(expected, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        matches = True
    return {
        "status": "passed" if matches else "failed",
        "graph_fingerprint": expected["fingerprint"],
        "package_count": len(expected["packages"]),
        "root_counts": {key: len(value) for key, value in ROOT_GRAPHS.items()},
    }


def _osv_query(packages: Sequence[tuple[str, str, str]]) -> list[Mapping[str, Any]]:
    request_body = {
        "queries": [
            {
                "package": {"ecosystem": "Maven", "name": name},
                "version": version,
            }
            for name, version, _ in packages
        ]
    }
    request = urllib.request.Request(
        OSV_ENDPOINT,
        data=_canonical(request_body),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "strling-certifier/1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise JvmPackageCertificationError(
            f"OSV advisory retrieval failed: {error}"
        ) from error
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or len(results) != len(packages):
        raise JvmPackageCertificationError("OSV advisory response is incomplete")
    if any(not isinstance(item, dict) for item in results):
        raise JvmPackageCertificationError("OSV advisory result is malformed")
    return results


def certify_risk() -> dict[str, Any]:
    graph = synchronize(write=False)
    if graph["status"] != "passed":
        raise JvmPackageCertificationError("release graph does not reproduce")
    results = _osv_query(EXTERNAL_PACKAGES)
    affected = []
    for package, result in zip(EXTERNAL_PACKAGES, results, strict=True):
        vulnerabilities = result.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            raise JvmPackageCertificationError(
                "OSV vulnerability inventory is malformed"
            )
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict) or not isinstance(
                vulnerability.get("id"), str
            ):
                raise JvmPackageCertificationError(
                    "OSV vulnerability identity is missing"
                )
            affected.append(
                {
                    "coordinate": f"{package[0]}:{package[1]}",
                    "advisory": vulnerability["id"],
                }
            )
    return {
        "status": "failed" if affected else "passed",
        "source": "OSV",
        "retrieval": "completed",
        "packages_queried": len(EXTERNAL_PACKAGES),
        "affected": affected,
        "license_dispositions": {
            "permitted": len(EXTERNAL_PACKAGES),
            "jna": "Apache-2.0 branch selected from LGPL-2.1-or-later OR Apache-2.0",
        },
        "graph_fingerprint": graph["graph_fingerprint"],
    }


def _tool(name: str, candidates: Sequence[str]) -> str:
    configured = os.environ.get(name)
    if configured and Path(configured).is_file():
        return configured
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise JvmPackageCertificationError(f"{name} is unavailable")


def _gradle_tool() -> str:
    wrapper = (
        ROOT / "bindings/kotlin" / ("gradlew.bat" if os.name == "nt" else "gradlew")
    )
    if wrapper.is_file():
        return str(wrapper)
    return _tool("STRLING_GRADLE", ("gradle", "gradle.bat"))


def _run(arguments: Sequence[str], cwd: Path, environment: Mapping[str, str]) -> str:
    completed = subprocess.run(
        list(arguments),
        cwd=cwd,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr.strip() or completed.stdout.strip())[-5000:]
        raise JvmPackageCertificationError(
            f"{' '.join(arguments)} failed with {completed.returncode}: {detail}"
        )
    return completed.stdout + completed.stderr


def _safe_reset(directory: Path) -> None:
    resolved = directory.resolve()
    target = (ROOT / "target").resolve()
    if resolved.parent != target or not resolved.name.startswith("jvm-adapter-package"):
        raise JvmPackageCertificationError(
            f"unsafe certification directory: {resolved}"
        )
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def _jar_has_forbidden_payload(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    forbidden_suffixes = (".dll", ".so", ".dylib")
    forbidden_markers = ("/core/Parser", "/core/Compiler", "/emitters/")
    return any(name.endswith(forbidden_suffixes) for name in names) or any(
        marker in name for marker in forbidden_markers for name in names
    )


def certify_packages(native_library: Path) -> dict[str, Any]:
    graph = synchronize(write=False)
    if graph["status"] != "passed":
        raise JvmPackageCertificationError("release graph does not reproduce")
    native = native_library.resolve()
    if not native.is_file():
        raise JvmPackageCertificationError(f"native library is unavailable: {native}")
    maven = _tool("STRLING_MAVEN", ("mvn", "mvn.cmd"))
    gradle = _gradle_tool()
    java = _tool("STRLING_JAVA", ("java", "java.exe"))
    javac = _tool("STRLING_JAVAC", ("javac", "javac.exe"))
    repository_text = os.environ.get("STRLING_MAVEN_REPOSITORY")
    if not repository_text or not Path(repository_text).is_dir():
        raise JvmPackageCertificationError("STRLING_MAVEN_REPOSITORY is unavailable")
    repository = Path(repository_text).resolve()
    work = ROOT / "target/jvm-adapter-package-certification"
    _safe_reset(work)
    local_install = work / "repository"
    local_install.mkdir()
    environment = os.environ.copy()
    environment["STRLING_NATIVE_LIBRARY"] = str(native)
    environment["STRLING_LOCAL_MAVEN_REPOSITORY"] = str(local_install)
    _run(
        [maven, "-o", "-B", "-q", "clean", "install"],
        ROOT / "bindings/jvm",
        environment,
    )
    _install_canonical_jar(maven, "jvm", environment)
    _run(
        [maven, "-o", "-B", "-q", "clean", "install"],
        ROOT / "bindings/java",
        environment,
    )
    _install_canonical_jar(maven, "java", environment)
    _run(
        [
            gradle,
            "--offline",
            "--no-daemon",
            "clean",
            "test",
            "publishMavenPublicationToLocalInstallRepository",
        ],
        ROOT / "bindings/kotlin",
        environment,
    )

    coordinates = [
        (
            f"com/strling/strling/{PRODUCT_VERSION}/strling-{PRODUCT_VERSION}.jar",
            repository,
        ),
        (
            f"com/strling/strling-jvm/{PRODUCT_VERSION}/strling-jvm-{PRODUCT_VERSION}.jar",
            repository,
        ),
        (
            f"com/strling/strling-kotlin/{PRODUCT_VERSION}/strling-kotlin-{PRODUCT_VERSION}.jar",
            local_install,
        ),
    ]
    product_jars = [root / relative for relative, root in coordinates]
    if any(not path.is_file() for path in product_jars):
        raise JvmPackageCertificationError(
            "one or more product jars were not installed"
        )
    if any(_jar_has_forbidden_payload(path) for path in product_jars):
        raise JvmPackageCertificationError(
            "a product jar contains native or semantic-copy payload"
        )

    external_jars = []
    for name, version, _ in EXTERNAL_PACKAGES:
        if name in {"org.jetbrains.kotlin:kotlin-stdlib", "org.jetbrains:annotations"}:
            continue
        group, artifact = name.split(":", 1)
        external_jars.append(
            repository
            / Path(*group.split("."))
            / artifact
            / version
            / f"{artifact}-{version}.jar"
        )
    if any(not path.is_file() for path in external_jars):
        raise JvmPackageCertificationError("the Java consumer graph is incomplete")
    classpath = os.pathsep.join(
        str(path) for path in [*product_jars[:2], *external_jars]
    )
    java_root = work / "java-consumer"
    java_root.mkdir()
    source = java_root / "Consumer.java"
    source.write_text(
        """import com.strling.Compiler;
import com.strling.jvm.NativeClient;
import java.nio.file.Paths;
public final class Consumer {
  public static void main(String[] args) {
    try (NativeClient client = NativeClient.load(Paths.get(args[0]).toAbsolutePath())) {
      Object result = new Compiler(client).parse("abc", com.strling.SourceCompileOptions.builder()
          .frontendId("strling.regex-compat").frontendVersion("1.0.0").mediaType("text/strling-regex").build());
      if (!(result instanceof java.util.Map)) throw new IllegalStateException("not canonical data");
      java.util.Map<?, ?> data = (java.util.Map<?, ?>) result;
      if (!"succeeded".equals(data.get("outcome"))) throw new IllegalStateException("compile failed");
      java.util.Map<?, ?> semantic = (java.util.Map<?, ?>) data.get("semantic_result");
      java.util.Map<?, ?> program = (java.util.Map<?, ?>) semantic.get("program");
      java.util.Map<?, ?> literal = (java.util.Map<?, ?>) program.get("root");
      if (!"abc".equals(literal.get("text"))) throw new IllegalStateException("semantic payload changed");
      System.out.println("JAVA_CONSUMER_PASS");
    }
  }
}
""",
        encoding="utf-8",
        newline="\n",
    )
    _run(
        [javac, "--release", "11", "-cp", classpath, str(source)],
        java_root,
        environment,
    )
    java_output = _run(
        [
            java,
            "-cp",
            os.pathsep.join((str(java_root), classpath)),
            "Consumer",
            str(native),
        ],
        java_root,
        environment,
    )
    if "JAVA_CONSUMER_PASS" not in java_output:
        raise JvmPackageCertificationError("Java clean consumer did not complete")

    kotlin_root = work / "kotlin-consumer"
    (kotlin_root / "src/main/kotlin").mkdir(parents=True)
    (kotlin_root / "settings.gradle.kts").write_text(
        'rootProject.name = "strling-kotlin-consumer"\n', encoding="utf-8", newline="\n"
    )
    local_uri = local_install.as_posix()
    base_uri = repository.as_posix()
    (kotlin_root / "build.gradle.kts").write_text(
        f'''plugins {{ kotlin("jvm") version "2.0.20"; application }}
repositories {{ maven {{ url = uri("{local_uri}") }}; maven {{ url = uri("{base_uri}") }}; mavenCentral() }}
dependencies {{ implementation("com.strling:strling-kotlin:{PRODUCT_VERSION}") }}
application {{ mainClass.set("ConsumerKt") }}
''',
        encoding="utf-8",
        newline="\n",
    )
    (kotlin_root / "src/main/kotlin/Consumer.kt").write_text(
        """import com.strling.jvm.NativeClient
import java.nio.file.Paths
import strling.Compiler
fun main(args: Array<String>) {
    NativeClient.load(Paths.get(args[0]).toAbsolutePath()).use { client ->
        val result = Compiler(client).parse("abc", strling.SourceCompileOptions(
            frontendId = "strling.regex-compat", frontendVersion = "1.0.0", mediaType = "text/strling-regex")) as Map<*, *>
        check(result["outcome"] == "succeeded")
        val semantic = result["semantic_result"] as Map<*, *>
        val program = semantic["program"] as Map<*, *>
        check((program["root"] as Map<*, *>)["text"] == "abc")
        println("KOTLIN_CONSUMER_PASS")
    }
}
""",
        encoding="utf-8",
        newline="\n",
    )
    kotlin_output = _run(
        [gradle, "--offline", "--no-daemon", "run", "--args", str(native)],
        kotlin_root,
        environment,
    )
    if "KOTLIN_CONSUMER_PASS" not in kotlin_output:
        raise JvmPackageCertificationError("Kotlin clean consumer did not complete")
    return {
        "status": "passed",
        "graph_fingerprint": graph["graph_fingerprint"],
        "product_jars": len(product_jars),
        "native_payloads": 0,
        "semantic_copy_payloads": 0,
        "clean_consumers": 2,
        "native_library": str(native),
    }


def product_verification_projection(
    text: str, version: str, jar_sha256: str, pom_sha256: str
) -> str:
    if any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (jar_sha256, pom_sha256)
    ):
        raise JvmPackageCertificationError("invalid product verification digest")
    pattern = r'(?ms)^      <component group="com\.strling" name="strling-jvm" version="[^"]+">.*?^      </component>'
    if len(list(re.finditer(pattern, text))) != 1:
        raise JvmPackageCertificationError(
            "expected exactly one local JVM product verification entry"
        )
    component = f'''      <component group="com.strling" name="strling-jvm" version="{version}">
         <artifact name="strling-jvm-{version}.jar">
            <sha256 value="{jar_sha256}" origin="Canonical STRling JVM package"/>
         </artifact>
         <artifact name="strling-jvm-{version}.pom">
            <sha256 value="{pom_sha256}" origin="Canonical STRling JVM package"/>
         </artifact>
      </component>'''
    return re.sub(pattern, lambda match: component, text)


def _install_canonical_jar(
    maven: str, slug: str, environment: Mapping[str, str]
) -> Path:
    from tooling.maven_release import canonical_binary_jar

    binding = ROOT / "bindings" / slug
    name = "strling-jvm" if slug == "jvm" else "strling"
    jar = binding / "target" / f"{name}-{PRODUCT_VERSION}.jar"
    canonical_binary_jar(jar)
    repository_options = (
        ["-Dmaven.repo.local=" + environment["STRLING_MAVEN_REPOSITORY"]]
        if environment.get("STRLING_MAVEN_REPOSITORY")
        else []
    )
    _run(
        [
            maven,
            "-o",
            "-B",
            "-q",
            *repository_options,
            "org.apache.maven.plugins:maven-install-plugin:3.1.2:install-file",
            "-Dfile=" + str(jar),
            "-DpomFile=" + str(binding / "pom.xml"),
        ],
        binding,
        environment,
    )
    return jar


def synchronize_product_verification(*, write: bool) -> dict[str, Any]:
    """Refresh only local product hashes; preserve all reviewed third-party entries."""
    _require_manifest_markers()
    maven = _tool("STRLING_MAVEN", ("mvn", "mvn.cmd"))
    _run(
        [maven, "-o", "-B", "-q", "-DskipTests", "clean", "install"],
        ROOT / "bindings/jvm",
        os.environ.copy(),
    )
    jar = _install_canonical_jar(maven, "jvm", os.environ.copy())
    if _jar_has_forbidden_payload(jar):
        raise JvmPackageCertificationError(
            "local bridge contains forbidden semantic/native payload"
        )
    pom = ROOT / "bindings/jvm/pom.xml"
    path = ROOT / "bindings/kotlin/gradle/verification-metadata.xml"
    text = path.read_text(encoding="utf-8")
    expected = product_verification_projection(
        text,
        PRODUCT_VERSION,
        hashlib.sha256(jar.read_bytes()).hexdigest(),
        hashlib.sha256(pom.read_bytes()).hexdigest(),
    )
    if expected != text and not write:
        raise JvmPackageCertificationError(
            "local JVM product verification hashes are stale"
        )
    if write and expected != text:
        try:
            from tooling.sync_versions import write_projection
        except ModuleNotFoundError:
            from sync_versions import write_projection
        write_projection({path: expected})
    return {
        "status": "passed",
        "product_version": PRODUCT_VERSION,
        "third_party_entries_changed": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install-product", action="store_true")
    mode.add_argument("--write-product-verification", action="store_true")
    mode.add_argument("--check-product-verification", action="store_true")
    mode.add_argument("--write-graph", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--risk", action="store_true")
    mode.add_argument("--certify", action="store_true")
    parser.add_argument("--native-library", type=Path)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--maven-repository", type=Path)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.install_product:
            environment = os.environ.copy()
            if arguments.maven_repository:
                environment["STRLING_MAVEN_REPOSITORY"] = str(
                    arguments.maven_repository.resolve()
                )
            maven = _tool("STRLING_MAVEN", ("mvn", "mvn.cmd"))
            repository_options = (
                ["-Dmaven.repo.local=" + environment["STRLING_MAVEN_REPOSITORY"]]
                if environment.get("STRLING_MAVEN_REPOSITORY")
                else []
            )
            _run(
                [
                    maven,
                    "-o",
                    "-B",
                    "-q",
                    *repository_options,
                    *(["-DskipTests"] if arguments.skip_tests else []),
                    "clean",
                    "install",
                ],
                ROOT / "bindings/jvm",
                environment,
            )
            _install_canonical_jar(maven, "jvm", environment)
            result = {
                "status": "passed",
                "product_version": PRODUCT_VERSION,
                "canonical_product_installed": True,
            }
        elif (
            arguments.write_product_verification or arguments.check_product_verification
        ):
            result = synchronize_product_verification(
                write=arguments.write_product_verification
            )
        elif arguments.write_graph:
            result = synchronize(write=True)
        elif arguments.risk:
            result = certify_risk()
        elif arguments.certify:
            native = arguments.native_library or Path(
                os.environ.get("STRLING_NATIVE_LIBRARY", "")
            )
            result = certify_packages(native)
        else:
            result = synchronize(write=False)
    except (JvmPackageCertificationError, OSError, ValueError) as error:
        result = {"status": "failed", "error": str(error)}
    print(json.dumps(result, sort_keys=True) if arguments.json else result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
