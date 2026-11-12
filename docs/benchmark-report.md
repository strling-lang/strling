# Fourth Edition benchmark and resource-safety report

This report separates mandatory functional safety from informational
quantitative performance. Its controlling contract is
[`strling-deterministic-certification-v1`](../governance/deterministic-certification.md).
It makes no claim of compliance with the superseded performance thresholds.

## Mandatory safety scope

The current certification model retains bounded frontend/kernel operations,
termination and resource-limit correctness, structural safety, required denial
behavior, native/interop memory safety and the registered sanitizer, property
and fuzz checks. Missing or failed mandatory safety evidence blocks acceptance.
The functional resource contract is `strling-functional-resource-v2`; the old
resource-v1 envelope cannot substitute for it.

Compiler safety findings are not a universal runtime complexity guarantee.
Application engine execution, input size, timeouts and deployment controls
remain separate. A lexical-shape helper is not a standards validator or a ReDoS
certificate.

## Historical measurements and acquisition limits

The earlier performance-inclusive H08 campaign retained a failed Full
CLI-startup result and 64,248 consumed authenticated samples. Those samples,
ledgers and failures remain historical evidence for their exact source,
workload, toolchain, environment and former contract. They are not fresh
measurements of the final product candidate and cannot be relabeled as passing
deterministic certification.

The later accepted public-verification implementation
`3e7061271d906251cb17c3eb06b6c748ac3068e7` recorded these engineering execution
times:

| Workload                     | Recorded wrapper seconds | Meaning                                          |
| ---------------------------- | -----------------------: | ------------------------------------------------ |
| Local profile                |        790.9924104749953 | Complete profile execution, not compiler latency |
| Pull Request profile         |       2621.3474850259954 | Complete profile execution, not throughput       |
| Full profile                 |           4893.460244952 | Integration/certification wall time              |
| Independent no-reuse Release |       5852.0006502609995 | Fresh preparation plus independent certification |

The [source-bound historical completion report](migration/public-distribution-verification.md)
and its signed evidence retain the operation, runtime and toolchain identities.
These figures are reproducible evidence identifiers, not normalized speed
claims or a comparison against the final candidate. They include orchestration
and prerequisite work; they must not be presented as product benchmarks.

## Current measurement conclusion

No new quantitative product-performance result is admitted as a certification
requirement. The final candidate's mandatory resource-safety results belong in
its fresh Full/Release artifacts and signed completion record. Old component
tests, staged installs and profile wall times cannot replace those results.

Windows process launch, recorder lifetime, scheduling and normalization showed
environment-dependent variability in the historical campaign. The standalone
Windows memory-recorder lifetime diagnostic is not a product memory-safety
test; its platform-disabled zero-test result establishes no resource coverage.
Measurements acquired under different recorder/normalization contracts cannot
be compared as if the environments and workloads were identical.

Latency, throughput, warmup, CPU-idle admission, profiling privilege, statistical
normalization and benchmark regression thresholds do not gate the current
candidate. Physical storage admission and protection of active Fortress workers
remain operational requirements; CPU utilization and memory-performance
measurements are not certification conditions.

## Deferred performance engineering

Windows process-launch latency and normalization variability remain explicit
non-gating investigations. Future measurements need an exact source, complete
workload, qualified recorder, toolchain/environment provenance and honest
failed-acquisition accounting. They must remain separate from authoritative
functional certification unless a new governed contract is ratified. No
performance improvement, cross-platform ranking or statistical regression
conclusion is asserted here.
