# Test Design — concurrent owned prerequisite builds

## Purpose and authority

Schedule the existing three independent Release prerequisites concurrently on
Windows without changing their command lines, target directories, environment,
1800-second command bounds or required artifacts. The controller remains the
authority for command membership. This executor does not acquire performance
samples or qualify conditioning, ancestor-job limits or independent ownership.
Other platforms retain their existing serial implementation.

## Contract and cases

-   Launch each worker into a new unnamed kill-on-close job before authorizing any
    build. Never change an inherited job, token, service or host power policy.
    Preserve the existing process-local HighQoS control.
-   Retain immutable per-invocation raw logs, exact commands, worker and child
    birth identities, timings, outputs and cleanup receipts. Completion order
    never changes command identity or the ordered three-command denominator.
-   A successful command must immediately produce every nonempty regular output.
    Keep the controller's final complete artifact check and bundle generation.
-   On the first observed failure, missing output, timeout or supervision error,
    cancel remaining owned jobs and reap all workers. No retries or measurement
    placement after failure. Unstarted and cancelled commands remain explicit.
-   Success requires complete fresh job queries and unchanged output bytes across
    retirement. The only allowed survivor is the reviewed MSVC vctip.exe image
    with the exact predeclared SHA-256; paths alone never authorize cleanup.
    Unknown survivors fail, then undergo owned failure cleanup.
-   Retain every cleanup error and never report success without proven empty
    jobs. Kill-on-close is a last-resort containment guard, not a quiescence proof.
-   Pure scheduling tests inject reordered completion, failure at each position,
    timeout, launch/poll/cleanup errors and an interrupted owner.
    Native subprocess tests exercise handshake, successful completion, failing
    child, missing output, timeout and unknown surviving descendant using tiny
    local fixtures.

## Completion criteria

Pure tests and direct dependents pass on Windows and WSL; native integration
passes on Windows with no product samples. Original serial artifact regression
coverage remains. Production commands and roles have explicit integration
assertions. The existing complete, fresh build comparison is diagnostic support,
not a new production wall-time or performance-admission result. No measurement
threshold, sample denominator, independent Release or trust control changes.
