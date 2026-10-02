# JVM dependency alignment regression charter

## Authority and scope

The shared bridge manifest, `bindings/jvm/pom.xml`, owns its exact Jackson
maintenance version. The registered JVM release-graph generator and Gradle
lockfile must project that same dependency identity without changing public
language semantics or the adapter boundary.

## Regression proof

`tooling/tests/test_jvm_adapter_package.py` compares the manifest's Jackson
version with all three Jackson coordinates in the generator's external package
inventory, every host release graph, and the Kotlin lockfile. Any missing,
additional, or stale Jackson coordinate fails the comparison.

Live vulnerability eligibility remains the responsibility of the unchanged
security scanners; this consistency test does not replace advisory validation.

The Gradle license disposition admits the exact JUnit BOM 5.10.1 only through
the two test classpaths and test implementation dependency metadata. Its focused
policy regression must reject any added production or distributed configuration.

## Validation

Run `python3 -m unittest tooling.tests.test_jvm_adapter_package`, the registered
release-graph check, dependency integrity and risk checks, then the affected
JVM host tests. No publication or performance sampling is required.
