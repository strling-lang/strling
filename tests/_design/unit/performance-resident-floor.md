# Test Design — Prospective resident-floor diagnostic

## Purpose and authority

The observed owned-process hard maximum can suppress peak RSS while allocated
work and private commit remain high. Investigate the opposite, conservative
control: an enforced minimum working set above the unchanged memory ceiling,
installed only on a newly owned suspended process after all job assignments.
This is an experiment, not live admission or proof of unrestricted ancestors.

The [Windows working-set API contract](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-setprocessworkingsetsizeex)
distinguishes enforced minima from soft defaults. An API success alone is
insufficient: record exact effective readback before resume and in the child.
Do not enable privileges, change inherited jobs or workstation settings, escape
jobs, or normalize the measured resident bytes. Failed acquisition stays failed.

## Prospectively fixed first experiment

-   Use two fresh owned synthetic processes, one with an unrestricted owned
    immediate job and one with an additional owned CPU-limited ancestor at
    flags5/rate100. Inherited jobs remain untouched and unknown.
-   After every assignment, request a 64MiB hard minimum and soft maximum with
    flags9, read back exactly, then resume. Record default and requested controls.
-   Retain the previous fixed synthetic workload: 8MiB allocation, 8192 page
    touches, 1000000 CPU iterations, deterministic checksums, raw peak/current
    RSS, commit, faults and whole process interval. These are not product samples.
-   Each mode runs at most once. If setup fails, preserve its terminal receipt
    and do not execute that workload or retry the unchanged setup. The next mode
    is not consumed. Every owned tree retires, including pre-resume failures.
-   Observe whether the floor itself forces residency, is ignored or cleared,
    needs unavailable privilege, or survives the complete child interval.

## Required later challenges and completion boundary

The initial equal minimum/maximum request returned error87 before execution,
with defaults unchanged. Preserve that attempt. A distinct setup experiment
keeps the same 64MiB hard minimum but provides 128MiB maximum headroom; it does
not reduce the resident floor or repeat a consumed workload. Equality is allowed
by the documented parameter description, so success with headroom would be an
observed native API constraint, not evidence that the first attempt executed.

The headroom setup succeeded in both modes and did not force RSS up to 64MiB.
A distinct single-child negative challenge now keeps two simultaneous 4MiB
allocations but explicitly requests `K32EmptyWorkingSet` between them. Retain
snapshots before allocation, after the first allocation, after trimming, and
after the second allocation; record trim success/error without assuming either
outcome. A successful trim below the floor would disprove treating flag readback
alone as continuous residency protection. This child owns all affected memory;
no other application, process, job or system control is changed.

## Locked-page alternative, separate experiment

The explicit trim succeeded while flags9 remained unchanged: minimum readback
is not sufficient protection. Test the distinct
[VirtualLock contract](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtuallock):
success guarantees that the specified committed pages remain resident until
unlock or process termination. Do not infer this property for other pages.

A standalone Rust1.75 native fixture (not the product worker) locks every page
reported by one initial working-set census, retains that census buffer, then
allocates and locks two dedicated 4MiB regions. Keep both regions live, touch
each page four times, and explicitly trim after each region. Query the residency
of every promised page after trimming. Reject any failed lock or nonresident
promised page; retain raw errors, controls, current/peak RSS, private commit,
complete durations, and exact allocation/touch/checksum counts. All locks and
regions retire with this newly owned process; no privilege is enabled.

Run one supported-floor process and one separate deliberately hard-capped
process. The latter must fail closed rather than declare its reduced RSS valid.
This is an API mechanism discrimination test, not a performance reference or
proof that every page of the actual product is covered. Future integration must
cover actual allocation, image and stack lifetimes, warmup, every descendant,
page reuse, lock quota failures, cleanup, and any source change before it can
claim complete measurement protection. Unobserved pages remain explicitly
outside this experiment's guarantee.

Successful readback would establish feasibility only. It does not prove that
snapshots provide continuous controls or that hard minima prevent every form of
trimming. Explicit trimming, allocation/free churn, failed allocations, competing
ancestor constraints, shared image/data pages, and workload-internal control
changes require adversarial analysis before promotion. Source-reviewed controls
must cover every measured descendant; no policy can infer unlimited CPU ancestry.

Existing original sample counts, raw RSS ceilings, CLI request/control channels,
all conditioning obligations, fresh reference and source-distinct holdout cohorts,
qualification and isolated trusted verification remain mandatory. No reference
fit, new performance ceiling, favorable sample selection or speedup claim follows
from this bounded diagnostic.
