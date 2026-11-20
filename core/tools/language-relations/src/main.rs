//! Repository-only review entrypoint for a bounded whole-input relation.

#![forbid(unsafe_code)]

mod engine;
mod oracle;
#[cfg(test)]
mod tests;

use std::env;
use std::fs::{metadata, File};
use std::io::{self, Read};
use std::path::Path;
use std::process::ExitCode;

use engine::{compare, Limits, Outcome, Query};
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use strling_kernel::semantic::SemanticProgram;
use strling_kernel::semantic_frontend::{self, DIALECT_VERSION, FRONTEND_ID, MEDIA_TYPE};
use strling_kernel::source::{ContractVersion, Sha256Digest, SourceDocument};
use strling_kernel::validation::{canonical_sha256, Validate};

const MODEL: &str = "strling.language-relation.review/1";
const CONTRACT: &str = "1.0.0";
const SPECIFICATION: &str = "1.0-draft.1";
const INPUT_BYTES: u64 = 65_536;
const USAGE: &str =
    "Usage: strling-language-relations-review <equivalent|contains|disjoint> <--semantic|--ir> <left-file> <right-file>";

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "--help" {
        println!("{USAGE}");
        return ExitCode::SUCCESS;
    }
    if args.len() != 4 {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    }
    let query = match args[0].to_str() {
        Some("equivalent") => Query::Equivalent,
        Some("contains") => Query::Contains,
        Some("disjoint") => Query::Disjoint,
        _ => {
            eprintln!("{USAGE}");
            return ExitCode::from(2);
        }
    };
    let format = match args[1].to_str() {
        Some("--semantic") => InputFormat::Semantic,
        Some("--ir") => InputFormat::Ir,
        _ => {
            eprintln!("{USAGE}");
            return ExitCode::from(2);
        }
    };
    let limits = Limits::default();
    let left = read(Path::new(&args[2]), format, "left");
    let right = read(Path::new(&args[3]), format, "right");
    let left_id = left.as_ref().ok().map(|input| &input.identity);
    let right_id = right.as_ref().ok().map(|input| &input.identity);
    let outcome = match (&left, &right) {
        (Ok(left), Ok(right)) => compare(&left.program, &right.program, limits, query),
        (Err(error), _) | (_, Err(error)) => error.clone(),
    };
    let report = json!({
        "model": MODEL,
        "status_authority": "repository_review_candidate",
        "relation": query,
        "input_format": format,
        "subject_domain": "whole_input_unicode_scalars",
        "input_byte_limit_each": INPUT_BYTES,
        "target_profile": null,
        "inputs": {"left": left_id, "right": right_id},
        "limits": limits,
        "result": outcome
    });
    println!("{report}");
    ExitCode::SUCCESS
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum InputFormat {
    Semantic,
    Ir,
}

#[derive(Serialize)]
struct InputIdentity {
    input_sha256: String,
    canonical_ir_sha256: Sha256Digest,
    contract_version: String,
    specification_version: String,
}

struct Input {
    identity: InputIdentity,
    program: SemanticProgram,
}

fn read(path: &Path, format: InputFormat, side: &'static str) -> Result<Input, Outcome> {
    if !metadata(path)
        .map_err(|error| io_error(side, error))?
        .is_file()
    {
        return Err(Outcome::invalid(
            side,
            "input must be a regular file".into(),
        ));
    }
    let mut bytes = Vec::new();
    let mut file = File::open(path).map_err(|error| io_error(side, error))?;
    (&mut file)
        .take(INPUT_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| io_error(side, error))?;
    decode(&bytes, format, side)
}

fn io_error(side: &'static str, error: io::Error) -> Outcome {
    Outcome::invalid(side, format!("input I/O failure ({:?})", error.kind()))
}

fn decode(bytes: &[u8], format: InputFormat, side: &'static str) -> Result<Input, Outcome> {
    if bytes.len() as u64 > INPUT_BYTES {
        return Err(Outcome::unknown("input_byte_limit"));
    }
    let program: SemanticProgram = match format {
        InputFormat::Semantic => {
            let source = std::str::from_utf8(bytes)
                .map_err(|error| Outcome::invalid(side, error.to_string()))?;
            let id = format!("src:language-relation.{side}");
            let document: SourceDocument = serde_json::from_value(json!({
                "contract_version": CONTRACT,
                "source_id": id,
                "specification_version": SPECIFICATION,
                "frontend": {"id": FRONTEND_ID, "dialect_version": DIALECT_VERSION},
                "content": {
                    "kind": "inline",
                    "encoding": "utf-8",
                    "media_type": MEDIA_TYPE,
                    "text": source
                },
                "provenance": {
                    "kind": "authored",
                    "description": "Input to the language relation review candidate"
                }
            }))
            .expect("the internal source envelope is valid");
            semantic_frontend::parse(&document)
                .map_err(|error| Outcome::invalid(side, error.to_string()))?
                .program
        }
        InputFormat::Ir => serde_json::from_slice(bytes)
            .map_err(|error| Outcome::invalid(side, error.to_string()))?,
    };

    if program.contract_version != ContractVersion::V1_0_0
        || program.specification_version.as_str() != SPECIFICATION
    {
        return Err(Outcome::unsupported(side, "input_contract_identity", None));
    }
    program.validate().map_err(|errors| {
        let first = &errors.errors[0];
        Outcome::invalid(side, format!("{} {}", first.path, first.message))
    })?;
    let canonical = canonical_sha256(&program).expect("validated Semantic IR serializes");
    Ok(Input {
        identity: InputIdentity {
            input_sha256: format!("{:x}", Sha256::digest(bytes)),
            canonical_ir_sha256: Sha256Digest::from_bytes(canonical),
            contract_version: CONTRACT.to_string(),
            specification_version: program.specification_version.as_str().to_string(),
        },
        program,
    })
}
