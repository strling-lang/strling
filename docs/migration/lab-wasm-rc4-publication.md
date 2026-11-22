# RC4 Preview immutable GitHub release

The Preview adapter is independently versioned. Its exact artifact, signed
closure, source policies and asset inventory are pinned in
[the RC4 publication specification](../../governance/lab-wasm-rc4-publication.json).
The historical STRling 4.0.3 release remains under its existing policy.

## Prepublication

Dispatch [the RC4 workflow](../../.github/workflows/rc4-preview-publication.yml)
from reviewed compiler main with its default input. The read-only job
authenticates the complete signed closure and verifies the GitHub coordinate
and immutable Git source. The hosted artifact is the decision proposal and
verification receipt. The independent local dry run checks the actual frozen
files. Only the repository administrator can independently read the effective
GitHub immutability setting through the Administration API.

The same workflow can prepare an exact protected decision with the request
review input. The proposal binds the workflow commit, run ID, attempt,
release environment, exact seven-file inventory, release notes and source
identities. The release environment holds the authorization job. It grants
read-only permissions and authenticates the named Program Owner's GitHub
review against the exact proposal digest. A general approval or a replayed
decision from another attempt fails.

## Separately authorized publication

The Program Owner must first explicitly approve the exact proposal. The
review comment must be P20-T05 approve sha256: followed by that proposal's
digest. The final job rechecks this GitHub review before the first release
request. The protected environment must provide an authorized repository
Administration read-only credential through RC4_IMMUTABILITY_READER so GitHub
immutability can be independently confirmed before draft creation and again
immediately before publication.

1. The protected writer creates the one approved prerelease as a draft at the
   frozen Git source and reports its release ID. The approved operator attaches
   the seven exact frozen files to that draft. The Wasm is transported from
   retained custody without rebuilding or uploading a separate staging artifact.
2. The writer checks that every attached asset has the expected name,
   byte count and GitHub SHA-256 digest. An unexpected asset, source,
   public collision or missing prerequisite holds the release. The protected
   writer publishes once, checks the immutable flag and tag, and verifies
   GitHub's release attestation.
3. Independently download the public Wasm and evidence and verify the public
   bytes and attestation before admitting website shipping. Preserve the
   release ID and receipts. An incomplete draft is retained for inspection.
   Reuse or replacement requires an explicit reviewed recovery for the exact
   prior draft and coordinate.

The read-only runs perform no Registry, Marketplace, Git tag or GitHub Release
writes. The website's production deployment is separately controlled.
