# Test Design — profile failure diagnostics

## Purpose

Retain the cause of a failed child operation in both human and JSON profile
invocations. A failed certification receipt must not discard the diagnostic
needed to reproduce its smallest failing operation.

## Description and authority

`toolchain.json` continues to own operations, profile membership and commands.
The certification schema and existing serializer own deterministic evidence;
diagnostic streams are supplemental observations, not certification authority.
The existing failure renderer owns bounded console output and hash-identified
full-stream preservation. JSON mode must use that same policy without adding
non-JSON text to stdout or changing the artifact, result, exit code or status.

## Scope

In scope are failed/unavailable/incomplete child stdout and stderr, large
Unicode streams, destination guards, write failures, GitHub annotations and
successful-result silence. Existing human-mode routing remains compatible.
Out of scope are profile execution, authenticated performance acquisition,
baseline refresh, retries, altered failure classification and trust promotion.
All new fixtures use temporary outputs and stubbed profile execution only.

## Categories of Tests

-   Positive: a JSON CLI failure emits exactly one parseable artifact on stdout
    and both child diagnostic streams on stderr. The retained artifact equals
    the emitted artifact; status, reason, exit code and evidence stay unchanged.
-   Retention: long child streams are preserved byte-for-byte before bounded
    console truncation, with their actual SHA256, length and path reported on
    stderr. Early decisive findings remain available in the preserved files.
-   Isolation: JSON GitHub annotations also use stderr. Successful operations
    emit no failure diagnostics or diagnostic files; human routing is unchanged.
-   Fail-closed: an output destination guard or preservation error cannot
    overwrite a protected path, mask the observed failure or classify it green.
    Its warning and bounded child output remain visible on the selected stream.

## Completion Criteria

-   The existing JSON CLI regression demonstrates discarded child diagnostics
    before implementation and passes after the narrow correction.
-   Focused routing, retention, guard, annotation and failure-classification
    regressions pass repeatedly on native Python and WSL.
-   Direct quality/certification/artifact regressions and relevant static checks
    pass without a profile or authenticated performance sample being produced.
-   Historical failed receipts remain unchanged; this correction does not claim
    to identify the original underlying test failure until atomic evidence does.
