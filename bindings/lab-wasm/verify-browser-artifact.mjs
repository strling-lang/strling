import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [candidatePath, candidateDigest, releasePackage] = process.argv.slice(2);
assert.ok(
    candidatePath && candidateDigest && releasePackage,
    "Provide the candidate Wasm path, expected SHA-256, and installed 4.0.3 package directory.",
);
const protocol = "strling.lab-compiler-tools@1.0.0-rc.1";
const baseRevision = "4e58730bbf67eaff683268e285e7084ccda5fadd";
const sealedDigest =
    "6a24a334d5d7e78b17c09e6d9a62d33299d65ac79e52212c4f8db130250656d7";
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const json = async (path) => JSON.parse(await readFile(path, "utf8"));

const release = resolve(releasePackage);
const releaseMetadata = await json(resolve(release, "package.json"));
assert.equal(releaseMetadata.name, "@strling-lang/strling");
assert.equal(releaseMetadata.version, "4.0.3");
const sealedBytes = await readFile(
    resolve(release, "dist/strling_interop.wasm"),
);
assert.equal(sha256(sealedBytes), sealedDigest);
const { instantiateWasm, sourceCompileRequest } = await import(
    pathToFileURL(resolve(release, "dist/index.js"))
);
const sealed = await instantiateWasm(sealedBytes);
assert.deepEqual(sealed.describe().operations, [
    "describe",
    "compile",
    "target_profile.inspect",
    "simply.compile",
]);
for (const operation of ["format", "convert", "explain"]) {
    const reply = sealed.execute({
        interop_protocol_version: "1.0.0",
        operation,
        payload: {},
    });
    assert.equal(reply.status, "error", operation);
    assert.equal(reply.error.code, "STRL-INTEROP-0005", operation);
}

const candidateBytes = await readFile(candidatePath);
assert.equal(sha256(candidateBytes), candidateDigest);
const module = await WebAssembly.compile(candidateBytes);
assert.deepEqual(WebAssembly.Module.imports(module), [
    { module: "strling_lab", name: "monotonic_milliseconds", kind: "function" },
]);
let clock = 0;
let clockStep = 0;
const { exports: wasm } = await WebAssembly.instantiate(module, {
    strling_lab: { monotonic_milliseconds: () => (clock += clockStep) },
});
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });
function send(request, version = protocol) {
    const inputBytes = encoder.encode(
        JSON.stringify({ protocol: version, request }),
    );
    const input = wasm.strling_lab_input_v1();
    new Uint8Array(wasm.memory.buffer, input, inputBytes.length).set(
        inputBytes,
    );
    const size = wasm.strling_lab_run_v1(inputBytes.length);
    assert.ok(size > 0 && size <= 1_048_576);
    const output = wasm.strling_lab_output_v1();
    const reply = JSON.parse(
        decoder.decode(new Uint8Array(wasm.memory.buffer, output, size)),
    );
    assert.equal(reply.protocol, protocol);
    return reply;
}
function result(request) {
    const reply = send(request);
    assert.equal(reply.operation, request.operation);
    assert.equal(reply.error, undefined);
    return reply.result;
}
const descriptor = result({ operation: "describe" });
assert.equal(descriptor.adapter_version, "0.1.0-rc.1");
assert.equal(descriptor.compiler_base_revision, baseRevision);
assert.deepEqual(descriptor.operations, ["format", "convert", "explain"]);
assert.equal(descriptor.max_request_bytes, 1_048_576);
assert.equal(descriptor.max_response_bytes, 1_048_576);
assert.equal(
    send({ operation: "describe" }, "strling.interop@1.0.0").error,
    "unsupported_protocol",
);
assert.equal(wasm.strling_lab_run_v1(descriptor.max_request_bytes + 1), 0);

const sourceRequest = (source) =>
    sourceCompileRequest(source, {
        sourceId: "src:lab.adapter.qualification",
        requestedOutputs: ["semantic"],
    });
const format = (source) =>
    result({
        operation: "format",
        document: sourceRequest(source).input.document,
    });
const frontend = new URL(
    "../../spec/frontends/semantic/1.0/fixtures/",
    import.meta.url,
);
const positive = (await json(new URL("positive.json", frontend))).cases;
for (const item of positive) {
    const formatted = format(item.source);
    assert.equal(formatted.status, "formatted", item.id);
    assert.ok(formatted.text.endsWith("\n"), item.id);
    assert.deepEqual(format(formatted.text), formatted, item.id);
}
const negative = (await json(new URL("negative.json", frontend))).cases;
for (const item of negative) {
    const rejected = format(item.source);
    assert.equal(rejected.status, "rejected", item.id);
    const [diagnostic] = rejected.diagnostics;
    assert.equal(diagnostic.code, item.expected.diagnostic_code, item.id);
    assert.equal(
        diagnostic.primary_location.coordinate_system,
        "utf8-bytes",
        item.id,
    );
    assert.equal(
        diagnostic.primary_location.start,
        item.expected.byte_offset,
        item.id,
    );
}
const unicodeBad =
    'semantic strling 1.0; case sensitive; pattern sequence { text "é😀"; bogus; }';
const unicodeOffset =
    Buffer.byteLength(unicodeBad.slice(0, unicodeBad.indexOf("bogus"))) + 1;
const span = format(unicodeBad).diagnostics[0].primary_location;
assert.deepEqual([span.start, span.end], [unicodeOffset, unicodeOffset + 1]);

const compile = (source) =>
    sealed.compile(sourceRequest(source)).semantic_result.program;
const convert = (program, destination) =>
    result({ operation: "convert", program, destination });
function assertExact(conversion) {
    assert.equal(conversion.status, "exact");
    assert.equal(conversion.equivalence.status, "proven");
    assert.equal(
        conversion.equivalence.method,
        "normalized_semantic_alpha_equivalence@1.0.0",
    );
    assert.match(conversion.equivalence.source_fingerprint, /^[0-9a-f]{64}$/);
    assert.equal(
        conversion.equivalence.source_fingerprint,
        conversion.equivalence.reconstructed_fingerprint,
    );
}
const program = compile(
    'semantic strling 1.0; case sensitive; pattern capture word { text "café"; }',
);
const builder = convert(program, "simply_builder");
assertExact(builder);
const rebuilt = sealed.simplyCompile(builder.output.request).compile_result
    .semantic_result.program;
assert.equal(rebuilt.root.name, "word");
assert.equal(rebuilt.root.body.text, "café");
const semantic = convert(rebuilt, "semantic_strling");
assertExact(semantic);
assert.equal(
    semantic.equivalence.source_fingerprint,
    builder.equivalence.source_fingerprint,
);
assert.equal(sha256(semantic.output.text), semantic.output.sha256);
const reparsed = convert(compile(semantic.output.text), "simply_builder");
assertExact(reparsed);
assert.equal(
    reparsed.equivalence.source_fingerprint,
    builder.equivalence.source_fingerprint,
);

const unnamed = { ...program, root: { ...program.root } };
delete unnamed.root.name;
const partial = convert(unnamed, "semantic_strling");
assert.equal(partial.status, "partial");
assert.equal(partial.equivalence.status, "not_proven");
assert.equal(partial.equivalence.reconstructed_fingerprint, undefined);
assert.ok(partial.output && partial.issues.length > 0);
const forward = {
    ...program,
    root: {
        kind: "sequence",
        node_id: "node:qualification/root",
        items: [
            {
                node_id: "node:qualification/forward",
                kind: "backreference",
                capture_id: program.root.capture_id,
            },
            program.root,
        ],
    },
};
const unsupported = convert(forward, "semantic_strling");
assert.equal(unsupported.status, "unsupported");
assert.equal(unsupported.equivalence.status, "not_applicable");
assert.equal(unsupported.output, undefined);

const corpus = await json(
    new URL(
        "../../spec/explanations/no-match/1.0/verification-corpus.json",
        import.meta.url,
    ),
);
const target = await json(
    new URL(
        "../../spec/targets/profiles/ecmascript-2024.json",
        import.meta.url,
    ),
);
const defaultCases = corpus.cases.filter((item) => !item.limits);
const explain = (program, subject, targetProfile) =>
    result({
        operation: "explain",
        program,
        subject,
        target_profile: targetProfile,
    });
for (const item of defaultCases) {
    const input = corpus.programs.find(
        ({ program_id }) => program_id === item.program_id,
    ).program;
    const actual = explain(
        input,
        item.subject,
        item.target ? target : undefined,
    );
    assert.equal(actual.outcome, item.expected.outcome, item.case_id);
    assert.equal(
        actual.explanation_disposition,
        item.expected.disposition,
        item.case_id,
    );
    assert.deepEqual(
        actual.findings.map(({ reason_code }) => reason_code),
        item.expected.reason_codes,
        item.case_id,
    );
    assert.deepEqual(actual.limits, corpus.default_limits, item.case_id);
    assert.equal(actual.subject.sha256, sha256(item.subject), item.case_id);
    assert.equal(
        actual.subject.utf8_bytes,
        Buffer.byteLength(item.subject),
        item.case_id,
    );
    assert.equal(
        actual.subject.unicode_scalars,
        Array.from(item.subject).length,
        item.case_id,
    );
    if (item.target)
        assert.deepEqual(
            actual.target.target_profile,
            item.target.target_profile,
            item.case_id,
        );
}
const syntheticSubject = "unique private fixture 😀 café";
const privateResult = explain(program, syntheticSubject);
assert.ok(!JSON.stringify(privateResult).includes(syntheticSubject));
assert.equal(privateResult.subject.sha256, sha256(syntheticSubject));
clockStep = 251;
const elapsed = explain(program, "a");
assert.equal(elapsed.outcome, "unknown");
assert.equal(elapsed.explanation_disposition, "unknown");
assert.ok(elapsed.work.reached_limits.includes("elapsed"));

console.log(
    JSON.stringify({
        status: "passed",
        node: process.version,
        v8: process.versions.v8,
        base_revision: baseRevision,
        candidate_sha256: candidateDigest,
        sealed_wasm_sha256: sealedDigest,
        sealed_operation_count: sealed.describe().operations.length,
        formatted_cases: positive.length,
        diagnostic_cases: negative.length + 1,
        exact_reconstruction_checks: 3,
        non_exact_conversion_checks: 2,
        explanation_corpus_cases: defaultCases.length,
        explanation_privacy_checked: true,
        explanation_elapsed_limit_checked: true,
    }),
);
