# STRling 4.0.0 partial publication and 4.0.1 fix forward

The owner-approved publication run
[43803833092, attempt 2](https://github.com/strling-lang/strling/actions/runs/43803833092/attempts/2)
ended with partial publication. STRling 4.0.0 is not a completely verified public
release. Existing immutable coordinates must not be overwritten or relabeled.

The nine successful publisher jobs were C, C#, Dart, Go, Java (including the JVM
bridge), PHP, R, Rust and Swift. Perl, Lua, Python, TypeScript and Ruby failed.
F# and Kotlin were cancelled before upload after in-flight operations finished.
ConanCenter remained deferred under the owner's distribution decision.

Independent read-only retrieval authenticated the retained artifact bytes and
associated documents for eight successful routes. Dart retrieval found all eight
published payload files unchanged, but the signed staged graph also contained
`.pubignore`, which pub.dev omits. This prevents accepting its original graph as
public verification. No complete public clean-consumer qualification was claimed.

Python's upload was rejected because its Linux wheel used an unsupported raw
`linux_x86_64` platform tag. Engineering diagnosis also found the native payload
in wheel `purelib`. npm rejected duplicate user/global configuration paths before
upload. CPAN's empty release envelope was misclassified as a collision. LuaRocks
availability handling did not account for the server's omitted nil fields; the
actual failing response body was not retained. Ruby's command failed without
retained stderr, so its registry-side cause remains undetermined.

The owner authorized 4.0.1 engineering and fresh certification as the governed
fix forward. It repairs packaging, protocol handling and safe failure diagnostics;
it does not change compiler semantics or expand support claims. All seventeen
build routes remain registered. The public scope retains 232 applicable
obligations and 24 explicitly deferred ConanCenter obligations out of 256.

Historical product source `a58f126b2721773ab9346d4dc449910371adccd9`, closure
`33afe5b9caef918afbd2b1790e2f16973ef40db1`, official `v4.0.0`, operational
`publication-v4.0.0`, ecosystem tags, signed evidence and actual registry receipts
remain preserved. Historical certification establishes their original source
claims; it does not establish 4.0.1 certification or complete 4.0.0 publication.

No 4.0.1 publication, tag, GitHub Release or permanent-branch update is authorized
by the engineering decision. A clean frozen source, fresh certification, exact
artifact handoff and a new owner-approved source-bound publication plan are
required before another public release operation.
