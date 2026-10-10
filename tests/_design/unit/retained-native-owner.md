# Retained native owner lifecycle

## Scope and authority

Repository orchestration must distinguish the tool-session lifecycle from an
explicitly authorized long-running native owner. A manager job configured to
terminate children when closed cannot own such work across manager restarts.
This is a launch-lifecycle correction, not a performance contract, isolation,
security policy, privilege, sample-count, acceptance-budget or retry change.

Only an explicitly approved native launch may use an already permitted Windows
job detach flag. Never configure a job, change a token, request administrator
rights, modify security settings, or detach from a job that disallows it. The
worker must independently confirm its ordinary token and absence of inherited
job ownership before acquiring evidence. Existing source, one-use, host
conditioning, CPU placement and resource guards remain mandatory.

## Unit cases

-   Reject non-Windows, non-boolean or missing approval, administrator tokens,
    ambiguous context fields and jobs lacking the explicit existing detach flag.
-   Reject unknown/job resource-limit flags rather than removing constraints.
-   Reject inconsistent job membership/flags and a worker still in any job.
-   Bind a launch to one exact Python executable, pinned reviewed script bytes,
    canonical checkout and an output prefix confined to target/codex-tools.
-   Reject symlink/path escapes, wrong digest, foreign Python, consumed output
    prefix and overwritten receipts. No arbitrary command or shell evaluation.
-   Preserve failed launch diagnostics exclusively; do not fabricate a process
    exit or completed producer evidence.
-   Pure tests cannot acquire performance samples, interrupt retained work or
    infer certification from launch success.

## Native atomic proof

Launch a sample-free pinned worker in the existing approved launch context. It
records its own token/job facts and writes an exclusive receipt after the
foreground launcher has returned. Prove this twice at distinct output paths.
Neither a service restart nor an essential application closure is part of this
test. Do not claim that this proves host failure immunity.

## Completion criteria

Focused tests pass repeatedly, native proofs reconstruct the ordinary-token,
no-inherited-job claim, all affected generated families are synchronized, and
direct tooling dependents and cheap prerequisites pass before a clean new
candidate is frozen. Interrupted attempts remain incomplete and source-consumed;
fresh launch permission cannot authorize replay of a sampled source.
