# Final product candidate preparation and clean-room certification

Status: engineering in progress. No final candidate is frozen or certified.
Publication is prohibited. The intended terminal state is RELEASE CANDIDATE
CERTIFIED — PUBLICATION AUTHORIZATION PENDING.

## Scope and contract lock

The admitted baseline is `d284446710c8164efc870d60071eeb5faf542a95` on local
`dev`. The worktree and index were clean. Remote `dev` remains at H08 closure
`2d8d897504663211d3768517f0be9f0e28d0f11e`; remote `main` remains at
`664d08de53565929c8f62379b006cd29f93b239f`. The dedicated public-verification
feature branch contains the admitted baseline. No integration or publication
ref may be inferred from another ref.

The H08 certificate's 96 files, packaging certificate's 154 files and public
verification certificate's 218 files exactly match their historical closure
trees, including modes and blob identities. The existing final public-integrity
run [passed all three jobs](https://github.com/strling-lang/strling/actions/runs/43077488253)
for the admitted baseline. These are accepted prerequisites, not fresh candidate
evidence. Historical trust policies, certificates, failures and source identities
remain protected.

STRling `4.0.0` remains the product authority. The independently versioned
specification, source dialects, ABI, transport and target profiles remain
separate. All 17 distribution routes, 15 Supported consumer scopes and five
registered target-profile claims retain their exact ratified boundaries.
Quantitative performance is non-gating; mandatory functional resource safety
is unchanged. The only existing waiver is `WVR-SEC-VSCE-LICENSE-001`, which
expires November 13, 2026; it must be valid when used and cannot be extended by
this task.

The former Notion master-plan links in the packaging report still return
object-not-found. The owner's current task provides the explicit V0–V12 mapping,
including mandatory clean-room packaging and certification at V10 and V12.
Current executable authority remains the deterministic contract, toolchain
profiles, release policy and controlled registries. No missing historical
acceptance definition is invented.

## Initial source-grounded gaps

1. The strategy guide still describes retired host compilers and wrongly names
   the Python manifest as product-version authority. The architecture guide
   also retains obsolete transition and product-orchestration statements.
   Correct explanatory implementation status without redesigning semantics.
2. Fourteen host source-helper routes default to `semantic_strling` and couple
   the frontend dialect to specification `1.0-draft.1`. The canonical kernel
   supports `strling.semantic@1.0.0` and `strling.regex-compat@1.0.0`; it correctly
   refuses the obsolete identity. A retained non-authoritative reproduction
   returns `STRL-PROTOCOL-0002` with the default Python helper and succeeds with
   the explicit ratified Semantic identity, dialect and complete source text.
   Repair the affected factories and prove actual native/WASM behavior. Preserve
   explicit unsupported-frontend refusal; do not add semantic aliases in the
   compiler or hide the defect with documentation-only workarounds.
3. Several binding examples pass regex-shaped or incomplete source to a
   Semantic default. The initial current-facing documentation inventory contains
   40 documents and 95 fenced blocks. Every applicable block needs an explicit
   executable contract, contextual classification or honest environment bound;
   seven existing CLI examples alone cannot establish complete coverage.
4. Finish a coherent 3.x-to-4.0 migration guide, first-use instructions, exact
   host/target matrices, invariant-to-test architecture review and evidence-backed
   benchmark report. Keep historical observations distinct from fresh evidence.
5. Preserve the three historical signing contexts. Establish a separate final
   candidate evidence namespace and qualify any actually new trusted policy.
   The hosted public-verification job must preserve its completed historical
   closure when a new complete-product source becomes the event candidate.
6. Derive the provisional RC coordinate through read-only availability checks
   and the existing channel policy. Do not occupy a public coordinate, edit the
   stable product authority or imply that an inaccessible registry is empty.
7. After focused corrections and generated reconciliation, freeze one clean
   commit and run fresh Local, Pull Request, Full, independent no-reuse Release,
   all required package comparisons and isolated consumers. Independently
   reconstruct, sign, verify and obtain actual hosted acceptance before closure.

## Checkpoints and evidence

The [task record](records/final-release-candidate.yaml) controls scope and
checkpoint acceptance. Preparation evidence is retained under
`target/release-candidate/preparation-d2844467`, including the source admission,
document inventory and original diagnostic/control outcomes. The initial
incomplete control lacked the required case declaration; its syntax failure is
preserved separately from the passing complete-source control.

No candidate certification, public installation, registry ownership, public RC,
stable release or complete Fourth Edition campaign closure is claimed here.
