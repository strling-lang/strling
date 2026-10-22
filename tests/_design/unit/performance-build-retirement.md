# Test Design — owned compiler background retirement

## Purpose and authority

Diagnostic build orchestration must distinguish successful command completion
from owned-job quiescence. Windows permits compiler helpers to outlive the
command that created them. This implementation contract does not admit performance
samples, relax conditioning or qualify an inherited job for certification.

The native caller must own the newly created job, obtain fresh process identities
from that exact job, preserve receipts and retain its existing bounded failure
cleanup. No unrelated process, job, service or host setting is in scope.

## Cases

-   An already empty job closes without termination; required artifacts retain
    their exact hashes and sizes.
-   A successful build may retire only live, birth-identified members of the
    exact owned job whose absolute image is the explicitly pinned `vctip.exe`.
-   Unknown image, path, hash, membership, identity, duplicate PID, truncated
    list, inconsistent accounting or malformed data fails without success cleanup.
-   A failed build, missing/empty required artifact, or invalid approval pin
    cannot reach successful retirement.
-   Record the complete initial snapshot and every bounded drain snapshot.
    Never reinterpret a query failure, timeout or surviving child as quiescence.
-   Required artifact changes during cleanup fail after preserving both hashes.
-   Terminate the owned job at most once; close only after verified empty state.
-   Native integration must reproduce a tiny Cargo helper survivor, verify its
    exact image and membership, preserve output bytes through cleanup, and prove
    an unknown live Python survivor is rejected. It must not repeat product
    builds or consume performance samples.

## Completion criteria

Pure policy tests pass on Windows and WSL. The real native regression uses small
disposable fixtures, records every process observation and preserves failed
attempts. Existing artifact, scheduling, process-observation and retained-owner
guards remain unchanged. Timing results are diagnostic, not certification gains.
