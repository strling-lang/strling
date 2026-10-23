# Test Design — diagnostic campaign journal

## Purpose and authority

Permit a prospectively fixed, sample-free diagnostic experiment to yield between
completed work units without relying on a detached owner. This is an execution
journal, not a scheduler, process supervisor, performance admission policy or
certification evidence store. It never launches or detaches a process.

The caller must retain the existing source lease, bounded child lifetime,
owned-job cleanup and raw evidence verification for each complete unit. A unit
cannot yield while its children remain live. The retained-native-owner guard is
unchanged and remains mandatory for independent long-running ownership.

## Contract

-   Before work, fix the source SHA/tree, recipe, implementation, environment,
    ordered distinct unit IDs and positive per-unit wall-time bounds. Pin the
    resulting plan hash outside the journal. Diagnostic results are never
    eligible for certification, performance admission or reference qualification.
-   A caller requests an explicit unit index, supplies the externally retained
    previous checkpoint hash and revalidates every pin before claiming it.
    An exclusive claim is flushed before any work starts. A second claimant
    cannot launch duplicate work or silently advance to another unit.
-   Close a claim once, only with the same owner identity and unchanged pins.
    Bind the independently checked raw result by SHA-256. Preserve failure and
    unfavorable timing; enforce the prospective wall-time bound. Successful
    closing additionally requires an explicit true owned-child-quiescence proof.
-   A claimed unit without a terminal is incomplete, not pending/retryable. No
    later unit may start after missing, malformed, failed or incomplete evidence.
    There is no stale-claim reclamation, resume-inside-unit or retry API.
-   A completed prefix can continue only at its next predeclared unit with the
    same plan and last checkpoint. All units, in order, are required for a
    complete diagnostic. A complete diagnostic is not a passing certification.
-   Reject symlinks/reparse points, hard-linked receipt files, path escapes,
    duplicate JSON fields, noncanonical bytes, unexpected fields, invalid exact
    integers, hash/owner/order drift and overwritten receipts. Partial writes
    remain unusable evidence; no repair-in-place operation is offered.

## Test categories

Pure tests exercise each contract above, including duplicate claim/close,
interrupted writes, failed/unfavorable results, checkpoint transplantation and
source changes between claim and close. A real multiprocess test proves that
two claimants race for exactly one unit and that a process exit between units
does not prevent the next fixed unit from being claimed. An interrupted owner
must leave its claim consumed and prevent subsequent work.

## Completion criteria

Focused and direct-dependent tests pass; a sample-free subprocess proof retains
all receipts and reconstructs the fixed denominator. No live conditioner,
baseline, threshold, sample count, trusted verifier or authoritative producer is
changed. Real build/reference integration remains separately required: journal
tests alone do not qualify inherited-job constraints or claim a runtime gain.
