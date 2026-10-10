# Performance and resource-budget certification

Status: active migration evidence

Authority: this document records engineering measurement and certification
design. It does not define STRling semantics, target behavior, diagnostics,
public APIs, support tiers, or regex-engine performance promises.

## Starting evidence

At the clean task anchor `f4f9cc03cc1277d99a65470ef911e9bfbdee78eb`,
the repository has three performance tests. Each is embedded in one of the
PCRE2, ECMAScript, or Python `re` runtime-certification suites. They use 16
warmups, 128 samples, and a median in an unoptimized Rust test build. Their
ceilings are 10,000 microseconds for analysis and planning, 5,000 for lowering,
and 5,000 for serialization.

A clean starting replay passed with these observed medians:

| Target      | Analysis and planning | Lowering | Serialization |
| ----------- | --------------------: | -------: | ------------: |
| ECMAScript  |              1,133 us |   416 us |         54 us |
| PCRE2       |              1,546 us |   597 us |         58 us |
| Python `re` |              1,233 us |   434 us |         61 us |

These values are reconnaissance, not baselines. The tests do not authenticate
the environment, compiler profile, fixture identity, distribution, variance,
memory, artifact size, or comparison source. Their target-specific duplication
also prevents one complete performance result from being consumed by product
certification.

The repository separately contains 61 searched `MAX_*` declarations across
the core, interop, editor, and verification paths. They bound source, request,
profile and response bytes; semantic material, depth and diagnostics; analysis,
capability, portability, lowering and serialization work; editor results;
no-match explanation; and related result sizes. Existing exact/one-over and
property tests are authoritative behavior evidence. This task will inventory
and authenticate those existing limits and tests; it will not change a limit.

## Closed measurement matrix

The certification denominator has five independent families:

1. Compiler work measures semantic parsing, legacy import, Simply/kernel
   request decoding, normalization, semantic/structural/safety analysis,
   capability and portability evaluation, PCRE2/ECMAScript/Python `re`
   lowering and serialization, and end-to-end compilation.
2. Product entrypoints measure the canonical CLI startup and representative
   commands plus bounded editor diagnostics, formatting, completion, symbols,
   and rewrite interactions.
3. Transport work measures canonical interop request decoding, kernel
   invocation, response encoding, and whole round trips. Supported-host adapter
   overhead is reported separately when its governed toolchain is available;
   it is never substituted for compiler time or support certification.
4. Resource observations measure peak resident memory and governed binary or
   library artifact sizes on supported environments.
5. Pathological cases certify existing hard source, request, node, depth,
   relationship, output, protocol, editor, and explanation ceilings. They
   record functional exact/one-over results separately from elapsed-time and
   memory observations.

Every family uses authored, bounded fixtures in four classes: tiny for startup
and fixed overhead, common for representative development work, large for
scaling, and pathological for declared resource boundaries. Fixture bytes,
semantic intent, expected status, and identity must be authenticated before a
measurement can be accepted.

Target regex-engine matching throughput is not in the denominator. The target
runtime suites continue to prove target acceptance, semantics, safety, and
their own bounded compile-stage smoke budgets; this task makes no universal
claim about PCRE2, JavaScript, or Python regex execution speed.

## Evidence rules to freeze in CP2

The versioned contract must distinguish four artifacts:

-   an authored operation and fixture manifest;
-   an environment-bound measured baseline;
-   a comparison result against exactly one compatible baseline; and
-   a complete certification result consumed by quality profiles.

Environment identity includes operating system and version, architecture, CPU
identity and logical count, available memory, Rust and relevant host toolchain
versions, build profile, target triple, feature set, repository commit,
producer fingerprint, and fixture fingerprint. A comparison is valid only when
the contract declares the identities compatible. Otherwise the result is
truthfully unavailable or informational.

Latency and throughput evidence must retain samples and report at least median,
p95, and median absolute deviation after fixed warmup and sample rules. The
controller must randomize operation order within deterministic rounds, avoid
concurrent benchmark workers, and reject incomplete samples. Peak resident
memory and artifact bytes use their own units and aggregation; they are never
converted into latency scores.

Each metric is either hard or informational. Hard metrics have both a measured
relative regression budget and, where product risk requires it, an absolute
ceiling. Informational metrics preserve the same observations, comparisons,
and trend reporting but do not independently fail aggregate certification
unless their governing operation is explicitly reclassified as hard.
Baseline creation or replacement is an explicit command that records its
source commit and rationale; an ordinary certification run cannot rewrite its
comparison authority.

Numeric budgets are deliberately not chosen in CP1. CP2 must derive them from
repeated controlled measurements and documented variance, then use controlled
mutations to prove that just-inside values pass and just-outside values fail.

## CP2 evidence contract

The versioned `1.0.0` contract closes 22 ordered operations: seventeen planned
latency, peak-RSS, and artifact-size measurements and five active groups of
existing hard resource checks. It closes twelve deterministic recipe fixtures
across the four required size classes and nine resource families containing 56
canonical declarations. Nineteen exact test-source fingerprints prevent a
resource claim from retaining its evidence identity after its proving test
changes.

The current pre-calibration manifest fingerprint is
`sha256:c8ebb142d2351651457eb9e5f9db638d93ffbf57fee92228b9a7d572c5ab0bc7`.
The fixture-manifest fingerprint is
`sha256:6a8e4aad41dd1b00c8e4bf441ea929a21259737f7ff7aa96b57f465e741c40c4`,
and the resource-inventory fingerprint is
`sha256:e1f5c1a3a1163cab3432b7e63115e09559939f5bc8e4ce41ca3a70a21ee0d5f8`.

The locked sampling policy uses sixteen warmups, 64 measurements, five
baseline repetitions, deterministic operation-order seed `1804`, one worker,
nearest-rank p95, median, and median absolute deviation. A coordinate shorter
than one millisecond selects a batch against a two-millisecond safety target,
bounded to 4,096 operations. The selected integer count is authenticated in
the baseline and reused exactly by Full and Release. Raw batch durations and
normalized per-operation nanoseconds are both retained, and every repetition's
batch-duration median must reach the one-millisecond governed minimum. A hard
relative budget is `max(1000 basis points, ceil(6 * MAD / median * 10000))`; a
baseline whose derived budget exceeds 4000 basis points or whose relative MAD
exceeds 500 basis points cannot become hard comparison authority. Every hard
live metric also requires an explicit absolute ceiling.

A candidate batch count is accepted only after two consecutive selector probes
reach the same two-millisecond target. A faster confirmation rejects a cold or
interrupted first probe and continues the existing proportional selection. The
selector probes are neither samples nor warmups: all coordinates still execute
exactly sixteen warmups with the selected batch before collecting the same 64
samples, and the safety target, maximum batch count, and minimum accepted batch
median are unchanged.

Baseline calibration acquires and retains a valid native conditioning snapshot
immediately before every coordinate in every repetition. The five top-level
repetition snapshots identify the repetition envelope; each measurement row
binds its five coordinate-local snapshots. This matches Full and Release
pre-coordinate conditioning and prevents a long randomized calibration
repetition from carrying an earlier quiet observation across later host drift.

All performance operations remain `planned` in CP2. The positive result is
explicitly a synthetic contract fixture with zero commit identity and flags
that deny live-measurement and baseline authority. CP3 must implement the
release-build producer, execute five stable calibration repetitions, record a
real source commit and exact environment, activate measured budgets, and prove
the complete live denominator. This prevents contract design from fabricating
numbers before the measurement path exists.

Fourteen focused tests validate the schema, exact denominators, authenticated
source declarations and tests, robust statistics, exact environment
compatibility, explicit baseline replacement, and controlled just-inside,
exact-boundary, relative-over, and absolute-over comparisons. Mutations that
shrink operations or profiles, prematurely activate metrics, change samples
without statistics, weaken derived budgets, alter environments or update
commands, or promote the synthetic fixture fail closed.

## CP3 release harness and local proof

The verification-only producer is a standalone, `publish = false` Rust release
binary with its own governed lockfile. It consumes public canonical kernel,
interop, and supported Rust-host surfaces but exports no product API. Every
timed result passes through `black_box`; latency is retained as integer
nanoseconds so tiny operations do not acquire artificial microsecond-scale
variance. The 54 live coordinates comprise 50 latency fixture pairs, three
isolated peak-RSS fixture pairs, and one fixture-free aggregate of the release
kernel binary and native interop library.

Live fixture realization corrected one CP2 recipe claim: the Semantic frontend
accepts 127 `without backtracking` wrappers because the root occupies the 128th
depth slot. The previously described 128-wrapper input is the exact one-over
rejection case. The authenticated current manifest and fixture fingerprints are
the values above; no frontend or resource limit changed.

Five calibration repetitions remain explicit in the baseline instead of being
collapsed. Each latency repetition preserves 64 normalized nanosecond samples,
64 raw batch durations, and the exact selected batch count after 16 batched
warmups; each peak-RSS or artifact-size repetition preserves one isolated byte
observation and a batch count of one. Calibration selects a count once per
coordinate and reuses it for the other four repetitions. Full and Release must
reuse that same authenticated count. The baseline distribution is the five
repetition medians. Relative budgets retain the locked six-MAD rule, and each
absolute ceiling is two derived relative budgets above the median. The
controller rejects incomplete coordinates, repetitions, samples, batch
durations or counts, statistics, budgets, fixture-free identity, or partially
activated manifests.

The initial environment-control correction required each WSL2 calibration and
comparison process to inherit one fixed guest logical CPU affinity. That
Ubuntu 24.04 / WSL2 / Intel Core i9-14900HX investigation selected guest CPU
`20`; both controller and runner verified `[20]`. It proved that guest affinity
is necessary, but not that the guest CPU is a stable physical host resource.
The correction did not change warmups, samples, statistics, budgets, ceilings,
product code, or the Windows host power plan.

The first fresh governed five-repetition calibration from clean commit
`078154cb991cef9b1a2183b8e94ad93e03946cc7` failed closed with
`unstable-baseline` before any manifest, baseline, or evidence file was written.
An exact non-promoting diagnostic replay on the same logical CPU then found all
54 coordinates inside the unchanged contracts, but left
`latency:pcre2-lower-serialize / fixture:semantic-large` at 488 basis points,
only 12 basis points below the 500-basis-point limit. The original
`latency:python-re-lower-serialize / fixture:simply-large` coordinate measured
205 basis points in that replay. Because a governed run failed and a retry
cannot erase that evidence, CP3 remains in progress with no active baseline;
Full, CP4, and FINAL are not advanced.

The differential investigation established that the two paths were not
environmentally equivalent. The governed writer performed fresh release builds
and environment probes immediately before timing; the replay reused those
artifacts after the failed hour-long calibration. Their five-round measurement
loops, order seeds, runner processes, timing source, warmups, samples, batching,
and guest affinity were otherwise equivalent. The original writer emitted only
an aggregate derived-budget error before its atomic write, so its exact failing
coordinate is not recoverable and must not be inferred from the replay.

More importantly, WSL2 guest affinity does not attest host-CPU placement. The
runner's process affinity was `[20]`, but the actual container cgroup cpuset was
`0-31`, CPU quota was unlimited, and the existing `effective_cpuset` field
merely repeated the process affinity. Windows counter probes observed guest
CPU-20 work across the same host scheduling pool as material background load;
host CPU 20 was not its physical execution identity. WSL2 exposes neither a
verifiable host-vCPU binding nor the native host scheduling controls to this
harness. A valid next environment must therefore be an authenticated native
bare-metal host, or a virtual environment with an attested host-pinned
reservation. No further calibration is valid in the current WSL2 guest.
Differential evidence fingerprint:
`sha256:545b3f41e738fbd16da37ad41e619958039174c41ede4081327c465823a4174c`.

That WSL2 result is retained as non-authoritative environment-limitation
evidence. It is not a failed product benchmark, is not superseded by a passing
replay, and cannot be promoted by retrying the guest. The 500-basis-point MAD
limit, 4000-basis-point derived-budget maximum, five repetitions, batching,
sampling, and all product behavior remain unchanged.

## Native host qualification gates

Authoritative performance evidence may be produced on native bare-metal Linux
or native bare-metal Windows x86_64. A hypervisor-pinned environment remains
eligible in policy only when a host-side trust path can authenticate and
enforce its physical CPU reservation. WSL2 and other guest-generated placement
claims remain non-authoritative. Native Windows is not a guest merely because
the same machine can host WSL2.

The offline bare-metal conditioner at
`tests/certification/performance-resource/1.0/environment/bare_metal_linux.py`
must be installed as a root-owned, non-writable executable outside the checkout.
It rejects any hypervisor, any execution affinity or unified-cgroup-v2 effective
cpuset other than logical CPU `20`, a finite CPU quota, a non-`tsc` clocksource,
an online sibling thread on the measured physical core, incomplete
`isolcpus`/`nohz_full`/`rcu_nocbs` isolation, IRQ affinity that includes CPU
`20`, a non-performance governor or energy preference, unavailable or nonzero
thermal-throttle counters, and any unrelated process or kernel thread that can
migrate onto CPU `20`.

The resulting root-owned attestation embeds, rather than merely asserts, the
actual cgroup path/cpuset/quota, host and selected-CPU topology, online CPU set,
processor and microcode identity, isolation and IRQ sets, power controls,
thermal counters, unrelated-task scan, clocksource, and conditioner hash. The
controller independently fingerprints Python, Rust 1.75 `rustc` and Cargo, the
release runner, kernel executable, and native interop library. The Rust runner
independently reads its real cgroup v2 path, `cpuset.cpus.effective`, `cpu.max`,
and current clocksource before either latency or RSS work.

For the dedicated-Linux path, the host must boot with CPU `20` isolated from
scheduling ticks, RCU callbacks, and managed IRQ work; its sibling hardware
thread must be offline; and all
housekeeping services and kernel threads must exclude CPU `20`. After those
host controls are applied, the minimal governed execution sequence is one
persistent systemd scope so attestation, qualification, and calibration retain
the same cgroup identity:

```bash
sudo install -o root -g root -m 0555 \
  tests/certification/performance-resource/1.0/environment/bare_metal_linux.py \
  /usr/local/libexec/strling-performance-bare-metal
sudo systemd-run --scope --pty \
  --unit=strling-performance-certification \
  --property=AllowedCPUs=20 --property=CPUQuota= /bin/bash
taskset --cpu-list --pid 20 $$
/usr/local/libexec/strling-performance-bare-metal attest \
  --selected-logical-cpu 20 \
  --output /run/strling-performance-host-attestation.json
export STRLING_PERFORMANCE_HOST_ATTESTATION=/run/strling-performance-host-attestation.json
python3 -m tooling.performance_resource_certification qualify --json
python3 -m tooling.performance_resource_certification baseline --replace \
  --rationale "P18-T04 dedicated bare-metal five-repetition calibration" --json
```

The native-Windows path runs directly on Windows, never through WSL, Docker, or
a guest. The offline helper at `tooling/performance_windows.py` rejects a
32-bit compatibility process, multiple processor groups in the current
versioned path, firmware that identifies a virtual guest, battery power,
battery saver, a missing power-policy GUID, a CPU-rate-limited Job Object, an
unavailable CPU-set mapping, a processor policy other than minimum/maximum
100 percent with boost disabled, a selected-processor frequency below its
authenticated non-boosted maximum/limit, or any mismatch after applying both
`SetProcessAffinityMask` and `SetProcessDefaultCpuSets`. It also calls
`SetProcessInformation(ProcessPowerThrottling)` with execution-speed control
enabled and state cleared, selecting HighQoS explicitly instead of allowing
Windows heuristics to infer EcoQoS. The selected controller, conditioner, and
every timed runner enforce this policy fail closed. Every timed runner is also
independently constrained to group 0, logical processor `20`, CPU-set `276` on
the current candidate host. Child CLI processes inherit the hard process mask,
and the runner records the actual processor group and logical processor
observed outside every timed interval. Soft CPU-set affinity is not sufficient
by itself: it is combined with the one-bit hard process-affinity mask, exact
process-default CPU-set assignment, fixed execution-speed policy, unlimited
quota, one-shot noise gate, and the five-repetition statistical contract. After
assignment, the controller, conditioner, and each timed runner query
`GetSystemCpuSetInformation` with their own process handle. They fingerprint the
selected set's `Allocated`, `AllocatedToTargetProcess`, `Realtime`, and
allocation-tag values. An ordinary unallocated set reports both allocation
booleans false and is accepted. A set allocated to another process, or an
internally inconsistent allocation result, fails closed. Every timed runner
authenticates the same allocation state before and after its measured workload.
The transient parked flag is not stable identity; actual processor observations
retain authority for placement.

When a Full performance producer is dispatched from WSL, the bridge selects
the current clean worktree if that worktree is on a Windows-mounted volume.
This keeps production Release certification inside its clean detached source
worktree even when the canonical checkout is at the same commit. For a caller
outside a Windows-mounted worktree, delegation still requires exactly one
clean native candidate at the source commit. Native Git invocation translates
the detached worktree's WSL `.git` pointer explicitly; candidate identity and
cleanliness remain fail-closed.

The Core Reservation capability audit was performed on the certification
candidate's native Windows Professional 25H2 installation, build
`26200.9168`, against installed Windows SDK `10.0.26100.0` and the exact
`KernelBase.dll` exports. The documented native CPU-set surface contains only
[`GetSystemCpuSetInformation`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getsystemcpusetinformation),
process/thread CPU-set getters, and
[`SetProcessDefaultCpuSets`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessdefaultcpusets)
and its thread counterpart. The setters select soft CPU Sets; they do not
allocate a Core Reservation. Microsoft describes Core Reservation as present
only on some Windows versions and exposes its state as a query in the
[`CPU Sets` documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/cpu-sets),
but publishes no native-application reservation creator, administrator command,
PowerShell command, policy/CSP, or power-policy setting for this client
platform. The documented
[`Hyper-V CPU-group`](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/manage/manage-hyper-v-cpugroups)
controls reserve host processors for virtual machines; they neither create a
reservation for a native process nor satisfy the direct-native execution
contract. The current token also has no reservation-specific privilege, and no
such privilege or policy is documented for the exposed API family.

The exact host reports zero allocated CPU Sets, but this is a platform-control
capability finding rather than a hardware-suitability finding. The earlier
`Allocated`/`AllocatedToTargetProcess` hard gate therefore overconstrained
native-Windows certification and is retained only in history. No unsupported
registry change, kernel interface, third-party tuner, or guest/VM workaround is
used to manufacture exclusivity that this Windows platform cannot provision.

The Windows fingerprint records the physical processor identity and microcode
revision exposed by the native registry, complete CPU-set topology, selected
core, sibling set, efficiency and scheduling classes, firmware/board/BIOS
identity, OS edition/build/UBR, physical memory, active processor-group counts,
hard affinity and CPU-set identifiers, Job Object CPU-rate state, AC source and
active power-policy GUID/name, exact minimum/maximum/boost settings, selected
processor current/maximum/limit MHz from `CallNtPowerInformation`,
the selected CPU-set allocation flags and allocation tag, the successfully
enforced process HighQoS execution-speed policy,
QueryPerformanceCounter frequency and resolution, Rust/Cargo/Python identities
and hashes, release profile/target, and the three release artifact hashes. The
runner identity is a deterministic bundle manifest that binds the general
measurement runner and its kernel-only peak-RSS worker; kernel and interop keep
their direct binary fingerprints. Windows peak RSS comes from the isolated
worker's native process peak-working-set counter rather than a compatibility
utility. The parent first enforces and verifies the complete Windows resource
contract. The worker then reapplies the exact attested affinity, CPU-set ID,
HighQoS policy, and unlimited Job quota, observes the selected processor, and
executes the unchanged canonical warmup and measured compile. This prevents
unrelated general-runner code pages from being counted as kernel peak RSS.

Before qualification and every calibration repetition, one two-second native
processor-counter observation rejects selected-CPU busy time above 500 basis
points, selected DPC/interrupt time above 100 basis points, or whole-host busy
time above 1500 basis points. The installed SDK declares
`SystemProcessorPerformanceInformation` and its record layout, and Microsoft
documents the query contract under
[`NtQuerySystemInformation`](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntquerysysteminformation).
Because Microsoft marks that documented query as version-sensitive, the helper
resolves it dynamically and rejects the host if the declared response is
unavailable or malformed. Each observation is performed once; there is no
retry loop. The threshold identities, placement, allocation state, effective
quota controls, timer, and power policy must remain exact across repetitions,
while the raw passing observations are retained individually. Windows
[`IsProcessInJob`](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob)
membership is also recorded, but it is wrapper ancestry rather than a quota:
when both contexts report `ControlFlags == 0`, rate control disabled, and an
effective unlimited quota, the direct controller's `in_job=true` and the native
Bash profile wrapper's `in_job=false` project to the same governed quota
identity. Microsoft documents the enabling and limiting flags through
[`JOBOBJECT_CPU_RATE_CONTROL_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_cpu_rate_control_information).
Any enabled, weighted, hard-cap, or min/max CPU rate control remains a
fail-closed mismatch. The noise gate does not claim
scheduler exclusivity. Windows records `exclusive` and
`unrelated_workloads_excluded` as false on this unallocated host and
`housekeeping_excluded` remains false; the unchanged statistical gates decide
whether this strongest supported control set is stable enough to certify.

The superseded reservation requirement was added from measured evidence, not
assumed.
The first exact-environment canonical Full replay retained CPU 20, CPU-set 276,
HighQoS, fixed 2.2 GHz reporting, and every artifact hash, but its process CPU
time was only 94.9 percent of wall time during a sustained coordinate. The
single failing coordinate was 153 nanoseconds above its unchanged relative
ceiling. [Windows documents ordinary CPU Sets as soft affinity](https://learn.microsoft.com/en-us/windows/win32/procthread/cpu-sets)
and exposes Core Reservation state through `Allocated` and
`AllocatedToTargetProcess`. That observation justified investigating Core
Reservation, but the supported-platform audit above proves that the candidate
host cannot provision the primitive. The failed canonical Full, sustained
preemption diagnostic, zero-allocation qualification, and the temporary hard
gate remain preserved evidence. They do not authorize a threshold change or
convert an unavailable OS mechanism into a native-Windows prerequisite.

The native-Windows policy is a dedicated, reversible clone; the user's Balanced
scheme is not modified. Disabling boost and fixing the processor state is an
environment control, not a warmup or benchmark change. The stable scheme must
remain active through qualification, calibration, controlled regression, and
Full certification. `qualify` applies and authenticates the supported process
controls and rejects any drift or noisy precheck before timing:

```powershell
$certScheme = "37dbead1-8ee2-4ebd-b7f4-0f21a5f4c180"
powercfg /duplicatescheme SCHEME_BALANCED $certScheme
powercfg /changename $certScheme "STRling Performance Certification" `
  "P18 native Windows invariant-frequency certification"
powercfg /setacvalueindex $certScheme SUB_PROCESSOR PROCTHROTTLEMIN 100
powercfg /setdcvalueindex $certScheme SUB_PROCESSOR PROCTHROTTLEMIN 100
powercfg /setacvalueindex $certScheme SUB_PROCESSOR PROCTHROTTLEMAX 100
powercfg /setdcvalueindex $certScheme SUB_PROCESSOR PROCTHROTTLEMAX 100
powercfg /setacvalueindex $certScheme SUB_PROCESSOR PERFBOOSTMODE 0
powercfg /setdcvalueindex $certScheme SUB_PROCESSOR PERFBOOSTMODE 0
powercfg /setactive $certScheme
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
python -m tooling.performance_resource_certification qualify --json
python -m tooling.performance_resource_certification baseline --replace `
  --rationale "P18-T04 native Windows five-repetition calibration" --json
```

After all evidence has been produced and authenticated, restore the prior
scheme and remove only the disposable certification clone:

```powershell
powercfg /setactive SCHEME_BALANCED
powercfg /delete 37dbead1-8ee2-4ebd-b7f4-0f21a5f4c180
```

`qualify` requires a clean checkout, builds and hashes the release artifacts,
authenticates the live environment, and runs the conditioner without collecting
performance samples. Baseline creation is permitted only after that command
passes. It runs the conditioner immediately before each of the five repetitions
and rejects any conditioning-identity drift before promotion. Full repeats the
same exact environment and conditioning-identity checks before comparison and
binds the denominator to the calibrated artifact set. A rebuilt runner, kernel,
or interop artifact must either equal its calibrated fingerprint exactly or have
a changed transitive build-input closure between the baseline source commit and
the clean candidate commit. That closure is derived from committed Cargo
manifests and locks, Rust source, and compile-time embedded contract data for the
specific artifact. The baseline commit must be an ancestor, and an incomplete
artifact set, unprovable Git state, or same-source fingerprint drift remains
unavailable before measurement. A source-bound candidate retains its freshly
built fingerprints as the numerator identity and still runs every normal Full
comparison without rewriting the baseline, thresholds, or samples. Rust 1.75
resource-limit tests use a dedicated target directory so build-script state
from another Rust toolchain cannot contaminate certification.

An authenticated OS-build change on the same certified hardware, product
artifacts, toolchains, placement controls, and benchmark contract is handled as
an immutable environment-version rollover. The reviewed reset command first
copies the active manifest, baseline, and synthetic contract evidence into
`tests/certification/performance-resource/1.0/history/<baseline-fingerprint>/`
and refuses to overwrite an existing history directory. It then returns only
the performance operations to the planned state; resource operations and every
benchmark coordinate, policy, stability limit, resource limit, sampling rule,
and fail-closed control remain unchanged. The reset and calibration must be
separate clean commits.

After native qualification, exactly one baseline producer invocation names the
archived authority and expected Windows build. Before promotion, the producer
requires identical release artifact hashes, rejects every non-OS environment
identity difference, and compares every candidate calibration median against
the archived baseline's relative and absolute limits. A failed comparison or
unstable coordinate leaves the manifest planned and cannot be retried merely to
obtain favorable samples:

```powershell
python -m tooling.performance_resource_certification reset-environment `
  --confirm-environment-rollover `
  --rationale "Reviewed same-host Windows environment-version rollover" --json
# Commit the planned manifest and immutable history, then qualify the clean SHA.
python -m tooling.performance_resource_certification qualify --json
python -m tooling.performance_resource_certification baseline --replace `
  --rollover-from <prior-baseline-fingerprint> `
  --expected-os-build <build.ubr> `
  --rationale "Reviewed same-host Windows environment-version calibration" --json
```

This rollover authority does not cover a hardware change, product-artifact
change, toolchain change, benchmark or sampling change, threshold-policy or
resource-limit change, or unexplained performance change. Each remains a
separate substantive review boundary. Historical environment authority remains
addressable by its immutable Git commit and archived baseline fingerprint.

There is no retry loop or partial preconditioning path: a qualification failure
blocks timing, and an unstable coordinate remains a product/harness or
Windows-environment investigation under the unchanged limits.

A reviewed same-build conditioner migration has a separate, narrower command.
It is authorized only for the recorded Windows CPU 20 to reviewed quiet
performance-core CPU 1 move and the conditioner v5/2-second to v6/10-second
transition. The command requires the clean planned reset plus its immutable
archived authority, permits only the 34 enumerated derived placement, processor-
class, reservation, attestation, and conditioner identity coordinates, keeps
all quietness thresholds unchanged, rebuilds source-bound release artifacts,
and recalibrates all 54 coordinates. Every new non-CLI median and paired CLI
ratio must pass the archived relative and absolute ceilings before the command
writes active authority:

```powershell
python -m tooling.performance_resource_certification `
  migrate-conditioning-cpu `
  --confirm-sustained-recovery `
  --selected-logical-cpu 1 `
  --rollover-from <prior-baseline-fingerprint> `
  --rationale "Reviewed sustained recovery on quiet Windows performance core" `
  --json
```

This command authorizes only the exact recorded efficiency-0 single-thread to
efficiency-1 sibling-pair topology transition on the same processor, group,
last-level cache, NUMA node, power controls, timer, toolchains, and Windows
build. Any other topology, hardware, toolchain, workload, sampling, threshold,
or product-identity mismatch, or any prior-ceiling regression, fails before
writes.

Native Windows focused proof covers the exact CPU-set/core/class mapping,
affinity and CPU-set enforcement, actual execution-processor observation,
effective unlimited CPU rate-control state plus raw Job-membership diagnostics,
AC and fixed-frequency power-policy identity,
native processor MHz state, QPC identity, native peak working set, firmware
guest rejection, and exact-boundary/one-over quiescence cases. Full remains
fail-closed unless one clean five-repetition calibration produces an active
baseline on the exact qualified native host.

That gate is now satisfied. One clean calibration at source checkpoint
`847c36c3a83b7b3428b3ae0ac4a3c972c71d3c71` completed all 54 coordinates,
sixteen warmups, 64 samples, frozen batching, and five repetitions. It promoted
baseline fingerprint
`15261bbd1c81c3dc21396b72d322ea1a2303540a9076991d3554e599201aabcb` and
manifest fingerprint
`2c1036d9e9438200200ae6951725dbc3ef880c610efcdd43f731edc1faaf8cae`.
The worst stability coordinate was 444 basis points and the maximum derived
budget was 2663 basis points, below the unchanged 500- and 4000-basis-point
limits. Clean checkpoint `eed9232c205f5852e4d6e74d38ad419469f91504`
then passed all 65 direct Full checks and the canonical profile-default Full
route. Raw wrapper Job ancestry remains visible in evidence, while the governed
environment identity has zero mismatches. No threshold, ceiling, batch floor,
warmup, sample, repetition, benchmark definition, or product behavior changed.

## Windows CLI launch control

`latency:cli-startup` retains raw process startup plus canonical request latency
as authenticated diagnostic evidence. Its hard regression signal is the ratio
of the request median to a separately warmed median from the same kernel
executable invoked with `--help`. After separately warming both commands, the
runner measures each request immediately beside its control and alternates
request-first and control-first order. Both arrays use the same warmup count,
sample count, affinity, timer, pipes, executable image, and conditioning window.
Both arrays are authenticated evidence and count as consumed samples.

This paired model isolates product request work from normal Windows process
creation and image-load variance. Both a derived relative ratio limit and a
derived absolute ratio ceiling remain release blocking. Raw request nanoseconds
and the prior raw ceiling remain in authenticated evidence as diagnostics. The
existing hard in-process latency coordinates and kernel artifact-size coordinate
continue to cover compiler work and executable growth.

Migration from the raw relative signal is a one-time, clean-source operation.
It archives the prior manifest, baseline, and valid evidence by baseline
fingerprint; rebuilds source-bound release artifacts; requires the unchanged
baseline environment and conditioning identity; calibrates only the two CLI
coordinates for five repetitions and rejects an unstable paired signal. Every
non-CLI measurement is copied byte for byte, and both prior raw CLI ceilings are
preserved as diagnostic history:

```powershell
python -m tooling.performance_resource_certification `
  migrate-cli-launch-control `
  --confirm-paired-launch-control `
  --rationale "Reviewed same-binary launch-control migration" `
  --json
```

If the authenticated Windows build changed before migration, the same command must name the active baseline fingerprint and exact new build with `--rollover-from` and `--expected-os-build`. That combined path recalibrates the complete performance denominator, admits only the reviewed CLI comparison-model change, and requires every non-CLI coordinate to pass the prior contract before writing the new authority.

A native conditioner exit that contains exactly the existing
`processor performance counters regressed` unavailable report is treated as an
invalid observation and reacquired under the same bounded sample-free policy.
Other empty, malformed, identity, power, or conditioner failures remain
immediately unavailable. This preserves the busy and interrupt thresholds and
prevents a transient counter epoch change on an unrelated logical processor
from being misreported as an unparseable conditioner result.

## Reviewed typical-launch normalization transition

Historical manifests retain their own estimator interpretation. The optional
`exact-ratio-of-all-sample-marginal-medians` estimator must be declared together
with `half-complementary-adjacent-pairs-64-v1`. Its acquisition performs 32
control-first adjacent pairs followed by 32 request-first pairs, retaining all
64 request and 64 control observations. Every fixed physical-launch period
from 2 through 64 has label discrepancy at most two; divisors of 64 cancel
exactly. Constant and linear ordinal log-cost trends also cancel. These are
ordinal guarantees, not an assumption that host cleanup never changes phase.

On activation, the governed typical warmed-latency signal becomes the exact ratio
of the two marginal medians. With sorted positive integer arrays `R` and `C`, it is
`ceil(10000 * (R[31] + R[32]) / (C[31] + C[32]))`. There is no intermediate
median rounding, floating-point computation, filtering, rejection or sample
deletion. Raw arrays, per-pair diagnostic ratios, wall/CPU evidence, median,
p95, MAD, launch labels and doubled authenticated consumption remain retained.
The verifier independently reconstructs the statistic and allocation from
the immutable source contract and complete evidence.

This location statistic has exact identical-distribution and arbitrary
re-pairing invariance, exact common-unit scaling, reciprocity subject only to
final conservative rounding, monotonicity and full-array slowdown sensitivity.
It does not claim immunity at or beyond 50% contamination. Deterministic
negative controls demonstrate why the historical arithmetic interpolation of
order-stratum pair-ratio medians is not a valid normalization: identical
distributions can produce 16668 basis points in both comparison directions.
Separately, changing host cleanup phase can bias even an all-sample geometric
ratio despite fixed-period-balanced acquisition. Neither counterexample
retroactively changes any failed authoritative result.

Activation is an explicit, one-use clean-source migration:

```powershell
python -m tooling.performance_resource_certification migrate-cli-normalization `
  --confirm-launch-normalization `
  --rationale "Reviewed normalization invariants and independent live proofs" `
  --json
```

The migration rebuilds exact-source artifacts, requires the existing environment
and conditioning, and freshly calibrates all 54 coordinates with the existing
512 warmups, 64 latency samples and nine repetitions. Each new median must pass
the prior contract. Every active absolute ceiling is capped by the minimum of
its freshly derived value and the prior _effective_ relative/absolute ceiling;
every relative budget is capped by its prior value. The 500bp variability limit,
all workloads, isolation, security and profile membership remain unchanged.
The prior manifest, baseline and synthetic evidence are archived byte-for-byte.
The ignored, source-keyed calibration attempt retains start events, complete raw
observations, conditioning and terminal failure before any activation; an
unchanged source cannot repeat a consumed calibration attempt. Prospective live
negative controls and direct regressions precede this migration. Calibration
and diagnostic evidence are never authoritative profile or closure evidence.

## Native in-process CPU-accounting batch resolution

The clean engineering source `58145a0b889ba3a6d71004452203440e74b1ceb0`
passed its fixed 36-window prospective CLI-normalization proof. Its first fresh
54-coordinate, nine-repetition calibration nevertheless failed at
`latency:supported-host-overhead/fixture:protocol-common`: repetition medians
393230, 362370, 417960, 416600, 369250, 404990, 359660, 370120 and 389090ns
yielded 510bp MAD, above the unchanged 500bp gate. All 973 ledger events,
complete raw observations and terminal failure remain retained; no active
baseline, budget or history artifact changed. This source is consumed and is
not retried as a calibration.

The retained approximately 2ms in-process batches reported CPU deltas of one
(the existing zero-delta sentinel) or 15,625,000ns. A FILETIME value's 100ns
representation does not establish its interval resolution. An independently
authored integer accounting-clock model demonstrates that identical 2ms work
can report zero or one quantum depending on phase; an exact two-quantum interval
has the same CPU delta for every phase. This is an attribution/measurement
precision defect, not evidence that compiler output or semantics are wrong.

A fixed diagnostic then acquired nine each of prior-short batches (5
operations, 512 warmups), long batches (80 operations, 512 warmups), and short
batches with equal total warmup work (5 operations, 8192 warmups), in rotating
order. Every window retained all 64 observations and real unchanged pre/post
isolation and conditioning. Independent reconstruction of all 27 windows and
1728 samples passed. Between-window MAD was respectively 181, 81 and 258bp;
zero-delta CPU samples numbered 507, 3 and 506 out of 576 per variant. Every
long-window median remained below the prior 430750ns ceiling. This supports
stronger batching rather than more warmups or a product-slowdown claim; it does
not invalidate the original 510bp failure or certify a new source.

The prospective schema-bound native in-process selection target is
31,250,000ns, two observed accounting quanta. It supplements, never reduces,
the prior 2ms selector target. Legacy manifests keep their original target,
and CLI process-launch controls keep separate unchanged batching. Two
consecutive selector probes are still required; every count remains capped at
4096 and is reused exactly by Full and independent Release. This is a target,
not a claim that every later batch reaches it: the existing maximum count and
1ms minimum accepted batch median still govern fast operations. No sample is
filtered because of quantization or unfavorable timing. CPU raw evidence stays
visible, including any residual zero deltas.

The 512 warmups, 64 samples, nine repetitions, per-coordinate conditioning,
50ms descheduling rule, 500bp MAD, budget floor/maximum, isolation and all prior
effective ceilings remain unchanged. Only explicit clean-source migration may
introduce the declared target, using a fresh all-54-coordinate calibration and
immutable prior history. New pure clock, native/legacy/CLI routing, exact-count
reuse and cap/policy-drift regressions pass; new-source direct dependents,
registered checks, clean freeze, prospective proof, calibration and both full
authoritative campaigns remain required. No acceptance gate is made easier.

The engineering direct checks subsequently completed at
2026-10-09T16:37:25Z: all 86 performance/normalization unit cases and a separate
13-case normalization repeat pass; all 36 negative freeze guards pass. The
registered identity-only generator and verifier changed zero outputs and
preserved the original baseline bytes. Complete generated validation,
governance, exact runtime, contracts, hygiene, formatting, static analysis,
dependency integrity, two real dependency-risk runs, attestation contract and
definition identity all pass. The repeated real risk denominator remains
54 PASS plus only the existing VSCE license waiver. This is sample-free
development evidence, not exact-SHA qualification or authoritative profile
evidence; the clean new-source proof/calibration and both complete campaigns
are still required.

## Retained ceiling failures and allocation-only product correction

Engineering source `03eb9400e8d85c15d767d0b13ec4d6f86f931a17`
passed its actual 36-window prospective launch proof. Its first complete
54-coordinate, nine-repetition calibration acquired all 973 ledger events and
passed every 500bp MAD gate, but failed eleven unchanged prior ceilings:
legacy import/common; kernel request validation/Simply tiny and common;
semantic analysis/common and pathological; structural safety/common and
pathological; end-to-end/Simply tiny and common; interop/protocol common;
and peak RSS/protocol common. All raw distributions and terminal failure
remain immutable. The source is consumed, no baseline activated and an
unchanged whole-stage retry is forbidden.

The fixed 27-window Simply-tiny batch diagnostic retained all 1728 wall/CPU
samples. Nine-window medians for batch73/warmups512, batch942/warmups512,
and batch73/warmups8192 were 34124, 34433 and 33615ns; all exceed the
unchanged 27920ns ceiling despite MAD133/169/96bp passing. The last variant
is longer warmup work, not an equal-work control. This rules out batching or
warmup count as the sole cause, not the failed verdict or other source causes.

Subsequent wall-only attribution measured nine rotations of fifteen current
public stages, 135 windows/8640 raw timings, and independently reconstructed
all observations, artifact/source identities, conditioning and isolation.
The review is retained at
`target/codex-tools/h08-simply-tiny-stage-independent-review-03eb9400.json`,
SHA256 `72c92939b5389712ffdaa2b7a5bc6723b3d5e7666a61a07f9680bcb1f8e58884`.
Explanation projection including serialization median10973ns, explicit
serialization2223ns, clone701ns and canonical digest2399ns identify current
avoidable work. These overlap and are not additive exclusive intervals.
The separate-build whole-operation29248ns result is diagnostic, not an
authenticated acceptance value or a proven historical-source comparison.
Failed initial import, diagnostic-ID and archive-build receipts remain failed
zero-timing evidence; public API, dependency and native-access recovery did
not weaken isolation, policy or architecture.

Under the later explicit autonomous-remediation authority, the smallest
allocation correction moves existing completed explanation evidence and streams
the same serialized JSON bytes into SHA256 through a 512-byte stack buffer.
It preserves all result/stage validation and correspondence, canonical object
ordering, typed field order, serialization errors and public contracts. No
memoization, validation bypass, unsafe code, dependency, ceiling, sample,
baseline or waiver change is introduced. Three actual native Rust1.75 library
runs passed all30 tests each, 90 executions, including byte/pointer equivalence
and refusing serialization after a valid prefix. These are unfrozen-source
correctness proofs; performance improvement, registered synchronization,
subsystem/prerequisite validation, clean new-source proof/calibration and both
complete authoritative campaigns remain pending. No previous sample is
relabeled and no failed consumed source is retried.

Canonical core489/interop22/direct tooling146 actual tests then passed, with
all Cargo failure/ignore/filter counts zero. All five affected checked-in
registered generator/verifier pairs passed; only adversarial producer metadata
and its dependent fingerprint changed, with raw observations unchanged.
The performance baseline byteSHA remains
`12efe6ff072e79c98c2e94c56be81a39a54d60b6e97a9605234e15b401e20073`.
Disposable LSP payload certification remains required in Full/Release.
The engineering owner stopped at governance because the task record omitted
the exact three later-authorized compiler allocation paths; all33 architecture
rules passed. The failed receipt is preserved and the unchanged atomic scope
validator reproduced all three findings. Only those exact task paths are
declared in recovery, without wildcard, exemption, security or gate changes.
Scope regression proof and the never-executed prerequisites remain pending;
completed expensive core/dependent and generator operations are not repeated.
No performance or authoritative certification progress is inferred.

The subsequent exact scope correction passed eleven negative rejection cases,
with every other scope field unchanged; review SHA256 is
`336b7dbf6709805a54ed213801c5363a7bd7bc8c6ae4c383fb55a3251be7b511`.
Independent prefix review SHA256
`40c8973f6a8bc0ad95ebfbddc56e87e63df0e07a262b48a800beb1894f3c9093`
reconstructs fourteen completed operations, actual test counts, baseline bytes
and all41 unchanged adversarial cases. Text generator success markers are
checked as text, not inferred from their misleading `.json` filenames or a
failed JSON-reading diagnostic. Corrected governance regression/full checks
and only the unrun prerequisites follow. Performance benefit, new clean
source, fresh predictor/calibration and both campaigns remain unproved.

The separate one-use sample-free remainder completed terminal0 at
2026-10-10T02:53:31Z. Its47 governance regressions, corrected full governance,
33 architecture rules, generated/hygiene/format/static/integrity prerequisites,
attestation contract and definition identity pass. Two new actual security
runs retain54PASS plus only the exact VSCE license waiver and no
failed/unavailable/incomplete check. Both retain the actual Jest30.5.2,
@types/jest30.0.0 and ts-jest29.4.14 proofs and ten exact test-only JUnit
bindings. A review-only filter failure including existing Trove4j is preserved;
the corrected exact JUnit selection rejects seven invalid mutations. No
security producer, license approval or waiver changed. Independent review
SHA256 is `73af5a6377e2ff6abe53acf68c9b97f376acc65241f3f5eca2cac7f7b39070dd`.
The fourteen original completed operations were not replayed and original
governance failure remains failed. These are working-source engineering proofs,
not a clean-source profile or measured improvement. Fresh atomic performance
proof at a newly frozen source precedes any eligible full calibration;
consumed03 never retries. Both whole campaigns and final closure remain required.

An initial exact-path stage failed before mutation on an empty orphaned Git
index lock. Read-only native/Linux queries found no Git owner; the lock was
recoverably preserved, not discarded, without resetting the index or
interrupting a process. Original cause is unproved. This tooling recovery
does not change source, performance policy, samples or certification authority.

The allocation correction was frozen at clean
`eeb691a1d5ad394d38d041cff2aba1f64507b889` with exact eight-path engineering
proof. Its fresh-source native build and nine 64-sample Simply-tiny windows
completed acquisition at 2026-10-10T03:39:29Z. All 576 raw wall/CPU observations
independently reconstruct: median 31,150 ns, MAD 42 basis points, nonzero CPU
accounting, but unchanged 27,920 ns prior effective cap FAIL. Review SHA256 is
`b9e815591007a971b8db73a11a10a83ec8aec45b5c6cda3a2efd3cd52090152e`.
Acquisition exit0 is not performance acceptance. All unfavorable data, old
authority and baseline bytes remain intact; no full calibration or authoritative
profile was rerun or accepted.

Current retained stage attribution and source identify duplicate identity
serialization/node-set allocation inside diagnostic generation and explanation.
The next small product correction retains every check but shares a fresh,
immutable, per-invocation correspondence context for adjacent validations.
Private fields bind the digest and node set to a borrowed program; there is no
cross-call cache or untrusted fact-derived identity. All version, digest,
coverage, kind, relationship, evidence, canonical order, resource and diagnostic
checks remain in original order. Differential controls and new stale-identity,
coverage, malformed-evidence and resource tests are required, followed by
repeated native correctness, direct dependents and exact registered generator
verification. Focused safety validation passes six actual tests, followed by
three complete native Rust 1.75 library runs at 32/32 each (96 repeated passes,
zero failed, ignored or filtered tests). Independent source-bound raw-log review
SHA256 is `44778eb30ff306f8042ffafff70156f9e0d004e907858e4be60cf29ba650355b`;
14 launch negatives and nine exact-scope negatives pass. Direct dependents,
registered generators and cheap/security prerequisites remain pending. None of
these dirty-source correctness results are authoritative measurements.
Performance benefit remains unproved until a newly frozen source
passes fresh measurements against every unchanged cap. H08 remains OPEN.

The first corrected-source prerequisite owner stopped at contract verification
with exit 2 because its new task-record evidence used `status` where the
unchanged governance schema requires `result`. The failed record and terminal
are preserved; exact one-field correction and seven negative schema cases pass
(review SHA256 `617f912fa21c40e84080b884ad8db2f8329bb8593eefdf5f44e966e8b8d90693`).
Independent reconstruction proves the five completed commands, including core
491 PASS, interop 22 PASS, 146 tooling tests and 26 unchanged contract snapshots.
Only the failed verifier and previously unrun prerequisites continue, with no
completed-prefix replay, product change, baseline activation or performance
claim. H08 remains OPEN.

The one-use correspondence recovery completed native/shell exit0 at
2026-10-10T05:27:38Z. Independent review SHA256
`59401355c990ec1f7bb64f48de70298a3b301daa806dde71a7a7d78ca0a35859`
reconstructs all19 actual recovery commands plus the five retained prefix
commands without replay. Both real55-check security runs retain54PASS plus
only the exact VSCE license waiver and zero failed/unavailable/incomplete;
Jest30.5.2/@types-jest30.0.0/ts-jest29.4.14 and ten exact non-distributed-test
JUnit bindings remain intact. All33 architecture rules, generated, hygiene,
format, static, integrity, attestation contract and definition identity pass.
Only registered adversarial provenance/result fingerprint changed; all41 raw
observations, repeat2, other checked-in families and original measured baseline
bytes remain unchanged. LSP payload certification remains actual Full/Release
work, not a skipped or waived prerequisite.

The initial review helper's byte-digest versus canonical-result-digest assertion
failed and is preserved with its original helper bytes. Independent canonical
unsigned-JSON reconstruction plus three negative tests corrects that reviewer
alone. Twenty-two completion guards and seven exact JUnit guards pass; no real
producer, threshold or historical failure is changed. These are dirty-source
engineering prerequisites, not measured performance or authoritative profiles.
Exact seven-path clean freeze and a fresh source-bound atomic product predictor
come next; CLI proof/calibration, both whole campaigns, signing, isolated trust,
fresh independent Release and closure remain required. H08 remains OPEN.

The clean `932dfd60ee5766c82f4f73fda223942c50f5e7ac` correspondence candidate's
fresh native atomic acquisition completed 2026-10-10T06:07:32Z. All nine
64-sample windows, three release builds, source identities, conditioning,
isolation, raw wall/CPU observations and historical receipts reconstruct under
review SHA256 `c707bea481d9e5810a8573127ba73fc4e356fcc35a41f1c35312caa9dc828dcf`.
Median 28,176 ns exceeds the unchanged 27,920 ns Simply-tiny end-to-end cap;
MAD 62 basis points passes 500 bp. CPU medians are 26,893 ns, but native
15.625-ms accounting is quantized and one zero batch remains preserved.
No rejected batch, sample exclusion, changed gate, baseline activation,
authoritative success or unchanged-candidate retry is permitted or inferred.

Current source inspection finds another repeated digest and node-set
construction across adjacent diagnostics and explanation. The smallest next
product correction retains the fresh context from diagnostics for explanation
of only the same immutable borrowed program. All validation and fingerprint
checks remain; standalone public calls retain fresh contexts. Differential
outputs and negative evidence/input cases, repeated native tests, dependents,
registered synchronization and cheap/security checks must pass before a new
clean source and fresh proof. The four focused differential tests pass, followed
by three complete native Rust1.75 library runs36/36 each,108actual passes with
zero failed/ignored/measured/filtered. Raw-log/source/terminal reconstruction
SHA256 is `dbd2b7fdf6093d4d65a46c8c2e6351bbfdafd85e2d3ed31140a969de6ee3f93e`;
33 negative exact-source guards pass. Direct dependents, registered generators
and prerequisites remain pending. Performance benefit is not yet established.
H08 stays OPEN; both complete campaigns, fresh independent Releases, actual
signing, isolated reviewed then immutable pinned verification and closure
remain mandatory.

The subsequent sample-free prerequisite owner40896/WSL68040 terminated exit2
at 2026-10-10T07:23:44Z on an existing adversarial observation shard write,
after twelve completed operations. All failed receipts, prefix logs and41 raw
shard byte identities are preserved by review
`b24c8f83121fa6e2a8fd35b47dc447801e99aca84162ed342ddf2b6b9ef062f7`.
An atomic backed-up same-byte write succeeds; a persistent host cause remains
unproven. The reversible generator correction avoids writing exact identical
UTF-8 JSON outputs while retaining changed writes and fail-closed I/O errors.
It changes no product semantics or certification property. Five pre-correction
regressions fail and then pass; a complete39-test run rejects stale source
identity with two failures/one error and remains failed evidence. Exact
registered refresh/check, three repeated complete suites and unrun cheap/
security checks must pass before independent review and new clean source.
No completed expensive prerequisite is replayed, no historical sample is
discarded, no baseline/gate changes, and no performance result is inferred.
H08 remains OPEN.

The corrected sample-free owner completed at 2026-10-10T08:04:28Z. Independent
review `1ec0aec7b3931446c827acd9e37352a7cfff84cc0c7b35390667b84be10ad429`
reconstructs all17 actual recovery commands and12 preserved prerequisites,
without replaying their expensive prefix: core495, interop22 and tooling146
pass, in addition to native36x3. Five current I/O tests and three complete
39-test adversarial repetitions pass. Both fresh real security invocations
have54PASS plus the sole VSCE license waiver; exact Jest30.5.2/types30.0.0/
ts-jest29.4.14 and ten test-only JUnit approvals remain unchanged. Contracts26,
architecture33 plus4 governance checks and all cheap prerequisites pass.
Registered regeneration changes only the adversarial provenance envelope;
all41 raw shards and original measured baseline bytes remain unchanged.

Two review-only failures are preserved: write-versus-comparison contract
classification and full-evidence-versus-sharded-index digest scope. Independent
full205-row reconstruction, all41 shard identities and27 completion/source/
scope,4 denominator,3 canonical,3 shard and7 JUnit negative guards pass; no
registered verifier or acceptance property changes. These are dirty-source
engineering proofs, not performance acceptance or authoritative certification.
Exact11path clean freeze and a new source-bound atomic predictor come next.
CLI proof, all54x9 capped calibration, both whole campaigns, fresh independent
Releases, signing, isolated reviewed then pinned verification and closure
remain required. H08 stays OPEN; no favorable-environment wait is authorized.

## Supplementary CPU-cycle work attribution

The clean adjacent-context candidate
`209fc16b999c1dd7301f12b751904bb78431bd7b` completed its fresh native three-build,
nine-window atomic acquisition at 2026-10-10T08:56:21Z. Independent review
`e19598d50211433aab1d2222ecd826aa48a4f4a541802dd106b41899545383a9`
reconstructs all 576 observations with batch 1007 and 512 warmups per window.
Window medians are 26193, 25913, 26376, 26470, 26159, 26463, 25259, 26404 and
25173ns; the aggregate median 26193ns passes the unchanged 27920ns prior cap,
and 104bp MAD passes the unchanged 500bp stability gate. No batch was rejected.
The diagnostic predictor nevertheless remains FAILED: eleven GetProcessTimes
zero deltas, retained as the original one-nanosecond sentinel, fail its added
per-batch nonzero-CPU heuristic. Acquisition exit0 is not predictor acceptance.
This sampled source is not retried, and its original summary is not relabeled.

A separate one-use clock-property diagnostic executes no STRling operations and
changes no host settings. It retains 128 busy-work intervals and 128 adjacent
empty controls, 64 each at 1ms and 26ms. Sixty 1ms work intervals report zero
process time despite positive process and thread cycles; no 26ms probe reports
zero. Minimum work process/thread cycles (2371586/2186292) exceed maximum empty
control values (905432/22013). All samples remain visible, including controls
and zero-time values. Raw receipt SHA256
`d5e21a70496db2b6d34a7dd2e7db8158dc2a0325e02e322030134714f57f4262`
and eleven negative diagnostic guards independently establish that zero
GetProcessTimes delta is not a valid no-CPU-work predicate. The probe does not
prove a particular scheduler cause for the eleven retained product deltas, or
claim product performance qualification.

The prospective optional internal runner mode
`--cpu-cycle-audit process-cycle-endpoints-v1` supplements in-process Windows
diagnostics with QueryProcessCycleTime endpoints and an immediate empty
counter-read control for every accepted and rejected batch. Endpoint ordering,
exact integer subtraction and complete denominator are independently checked;
work must exceed its counter-read control before a diagnostic work proof can
pass. Zero or control-dominated cycle evidence stays retained and fails that
proof, never filtering an otherwise valid wall-time sample. API errors and
unsupported hosts, child-process CLI work, or peak-RSS work fail closed.

Cycles are not nanoseconds and are never converted into time or substituted
for wall/CPU-time performance budgets. The ordinary profile invocation and
output are unchanged when this optional mode is absent. In audit mode the
cycle queries bracket, but do not enter, the original wall-timed product batch.
Existing GetProcessTimes fields, 31.25ms selection target, 4096 maximum batch,
512 warmups, 64 samples, nine windows, 1ms minimum, 50ms descheduling, 500bp MAD,
prior ceilings, conditioning, isolation, authentication and security all stay
unchanged. Earlier failures cannot be accepted under this new diagnostic mode;
a fresh clean-source proof, CLI36 and all54x9 capped calibration are required.

The runner, existing charter and three migration records match no registered
generated family under registry SHA256
`ef571beb4bffb12bba1ed064056b84b46961b0bc3d56db4326511f5e4e2a0c12`.
No generated authority or command is invented; the original measured baseline
remains byte-identical. Repeated native and direct-dependent regressions and
cheap prerequisites precede a guarded exact-path commit/freeze. This is a
measurement-property correction, not a loosened performance gate, baseline
activation, authoritative profile result or trust promotion. H08 remains OPEN;
both complete campaigns, independent Releases, signing and isolated reviewed
then immutable pinned verification and formal closure remain required.

The API's declared process-cycle meaning is documented by
[Microsoft QueryProcessCycleTime](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-queryprocesscycletime);
the time API's FILETIME representation is documented separately by
[Microsoft GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes).
Representation alone is not an interval-resolution guarantee.

The complete native engineering run finished at 2026-10-10T09:30:55Z. All
15 runner tests pass in each of three actual Rust 1.75 `--all-targets` runs
(45 passes; the memory-worker target has zero tests), with no failed, ignored,
measured or filtered cases. Four directly dependent tooling modules pass
73+7+13+11=104 tests with no errors or skips. The original helper still has a
failed terminal: it incorrectly required unittest's `OK` footer at EOF, although
the existing controlled-producer exception test intentionally prints its exact
incomplete-diagnostic JSON afterward. No product or test expectation changes.
Independent raw-prefix review
`cfde132f6af0b166aea0f7c20ca3eda35ccf5fedcf85a6449c73684ddf7dec26`
checks every raw-log/source/terminal pin, all native test names and complete
denominators, and only that precise expected diagnostic suffix. Twenty-five
negative completion, denominator and suffix guards reject altered results.

Only the previously unexecuted sample-free Local performance contract runs in
the separate recovery. Its single manifest check passes, receipt
`1e5cffe7a47da01704e613800b90c20cb3709c1b08b9301565736be1797f34b2`;
recovery terminal
`d1f501386a724d5638baefc00e65031d504ffc5312ebfe092862468719fdcb5c`
is complete at 2026-10-10T09:44:03Z. This is not Local37 or measured acceptance.
No completed prefix was replayed. Earlier pre-execution malformed hash and
review-script import-location guard failures are retained separately, with
their original helpers unchanged. Remaining repository, static, generated,
exact-runtime and repeated real security prerequisites precede the new clean
freeze; no baseline activation, campaign acceptance, trust or closure is claimed.

## Profile ownership

-   Local validates the authored contract and fixture identities without timing
    a developer workstation.
-   Pull Request executes deterministic resource-limit checks and bounded
    controlled comparisons that do not depend on noisy wall-clock equivalence.
-   Full and Release execute optimized latency, throughput, peak-memory, artifact
    size, interop, and available supported-host observations on a compatible,
    fingerprinted environment.
-   Scheduled native hosts reach the same Full producer through the canonical
    profile router; workflow YAML does not own a second implementation.

A hard regression beyond its governed budget or an absolute resource ceiling
fails certification. Waivers, if ever needed, must use the repository's
existing explicit governance rather than editing evidence or widening a
baseline in place.

## Forbidden expansion

The task cannot change product semantics, compiler implementation, diagnostics,
target profiles or outputs, public APIs, packages, dependencies, support tiers,
or existing hard resource values. It cannot publish, upload, release, push, or
turn measurements from unlike machines into a common performance claim. Any
need for one of those changes is a new governed decision, not a benchmark fix.

That paragraph retains the original measurement-only task boundary. The later
human autonomous-remediation instruction separately authorizes narrowly
cause-backed reversible product optimizations and compatible secure tooling
corrections, with regression and generated-artifact verification. It does not
authorize semantic, public-output, security, comparison-ceiling, evidence,
license, isolation or trust weakening, nor publication.

## Supplementary cycle-audit engineering prerequisite completion

The ordinary-token native Python owner1872 and hidden WSL39708 completed the
twelve planned sample-free prerequisites at 2026-10-10T10:22:11.960732Z.
Native terminal byteSHA
`63627dc4c37d856e8d5ccb6a43d48d94d294e6ac8f404aa574f3af780595f8f9`
and shell terminal
`53c289089e4ea04f3d9a9c642eb5c0f39422fbf6f847c73257346665caaf4683`
are exit0 and required-complete. Independent reconstruction
`265e65ef655540bf1adcf08133d447c45b781d3518f61183f085dfa0ad7740a9`
binds every source/raw/event/terminal identity and25 negative completion,
denominator and exact contract-detail guards. Contracts26, architecture33 plus
four governance checks, exact runtimes, hygiene, formatting, static analysis,
dependency integrity30, attestation contract and source definitions pass.
Generated verification records32 passed families, one transitional lockfile
family and two Full/Release-profile-enforced families; the latter are not
executed or accepted here. All five changed paths match zero registered
families; no generated output, original baseline or acceptance ceiling changes.

Two separate real dependency-risk invocations each return54PASS plus only
`WVR-SEC-VSCE-LICENSE-001`, with zero failed/unavailable/incomplete checks.
Their raw bytes are identical, SHA256
`488efd7b1e6802a57f7c7564913be90ee14665eb903a4468414f7775f147970f`;
distinct START/PASS events establish execution, not reused evidence. Exact
Jest30.5.2, @types/jest30.0.0 and ts-jest29.4.14 remain governed. Each scan
retains all ten exact JUnit EPL-2.0 non-distributed-build-test bindings and
passes seven negative expansion/version/scope guards. No runtime approval or
waiver expansion occurs.

The rejected unsigned Windows PowerShell launcher remains failed, receipt
`10753071c2113a18b97287b8442c96c5c8a417d82e229ceb6e9905ded6fbf3b4`.
The separate native Python controller neither evaluates that script nor changes
execution policy, security or privilege settings. Independent review attempts
17dd8a and be4a71 are preserved failures: they compared canonical JSON identity
to file bytes and omitted the already declared root-CLI additive certification
detail, respectively. Separate V3 corrects only those review assumptions and
strictly reconstructs the exact known detail. No prerequisite operation or
completed45native/104tooling/one-contract prefix is replayed. No product failure
is inferred from these helper defects and no failed receipt is relabeled.

This remains dirty-source engineering proof, not Local37, PR79, Full125,
Release125, performance acceptance, signing, trust or closure. A guarded exact
five-path clean source precedes fresh cycle-audited atomic evidence, CLI36 and
all54x9 capped calibration, exact-source readiness and both whole authoritative
campaigns with fresh independent Releases, signing, isolated reviewed-verifier
qualification, pin-only promotion and immutable pinned verification. H08 OPEN.
