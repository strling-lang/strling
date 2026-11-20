//! Independent Lab candidate transport for existing canonical compiler operations.
#![deny(unsafe_op_in_unsafe_fn)]

use std::time::Duration;

use serde::Deserialize;
use serde_json::{json, Value};
use strling_kernel::diagnostic::Severity;
use strling_kernel::no_match_explanation::{
    explain_no_match_with_clock, NoMatchExecutionMode, NoMatchExplanationErrorCode, NoMatchLimits,
};
use strling_kernel::protocol::{
    CompileInput, CompileRequest, CompilerOptions, DiagnosticPolicy, PartialSemantics,
    RequestedOutput,
};
use strling_kernel::semantic::SemanticProgram;
use strling_kernel::semantic_conversion::{
    convert_semantic_program, SemanticConversionDestination,
};
use strling_kernel::semantic_frontend;
use strling_kernel::source::{SourceContent, SourceDocument};
use strling_kernel::target::TargetProfile;

pub const PROTOCOL: &str = "strling.lab-compiler-tools@1.0.0-rc.1";
pub const BASE_REVISION: &str = "4e58730bbf67eaff683268e285e7084ccda5fadd";
pub const MAX_REQUEST: usize = 1_048_576;
pub const MAX_RESPONSE: usize = 1_048_576;
// A canonical node can contribute one object and one children array. Allow
// the canonical frontend's depth plus room for the protocol and model headers.
const MAX_JSON_DEPTH: usize = 2 * semantic_frontend::MAX_NESTING_DEPTH + 16;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    protocol: String,
    request: Operation,
}

#[derive(Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
enum Operation {
    Describe {},
    Format {
        document: Box<SourceDocument>,
    },
    Convert {
        program: Box<SemanticProgram>,
        destination: SemanticConversionDestination,
    },
    Explain {
        program: Box<SemanticProgram>,
        subject: String,
        target_profile: Option<Box<TargetProfile>>,
    },
}

impl Operation {
    fn name(&self) -> &'static str {
        match self {
            Self::Describe {} => "describe",
            Self::Format { .. } => "format",
            Self::Convert { .. } => "convert",
            Self::Explain { .. } => "explain",
        }
    }
}

fn execute(operation: Operation, now: &dyn Fn() -> Duration) -> Result<Value, &'static str> {
    match operation {
        Operation::Describe {} => Ok(json!({
            "adapter_version": env!("CARGO_PKG_VERSION"),
            "compiler_base_revision": BASE_REVISION,
            "operations": ["format", "convert", "explain"],
            "max_request_bytes": MAX_REQUEST,
            "max_response_bytes": MAX_RESPONSE,
            "max_json_depth": MAX_JSON_DEPTH
        })),
        Operation::Format { document } => {
            match &document.content {
                SourceContent::Inline { text, .. } if text.len() <= 32_768 => {}
                _ => return Err("invalid_format_source"),
            }
            match semantic_frontend::parse(&document) {
                Ok(parsed) => {
                    Ok(json!({"status":"formatted","text":semantic_frontend::format(&parsed)}))
                }
                Err(error) => match error.diagnostic() {
                    Some(error) => {
                        Ok(json!({"status":"rejected","diagnostics":[error.diagnostic]}))
                    }
                    None => Err("invalid_format_source"),
                },
            }
        }
        Operation::Convert {
            program,
            destination,
        } => convert_semantic_program(&program, destination, None)
            .map(|result| json!(result))
            .map_err(|_| "invalid_conversion_program"),
        Operation::Explain {
            program,
            subject,
            target_profile,
        } => {
            let target_reference = target_profile
                .as_deref()
                .map(TargetProfile::reference)
                .transpose()
                .map_err(|_| "invalid_target_profile")?;
            let mut requested_outputs = vec![RequestedOutput::Semantic, RequestedOutput::Analysis];
            if target_reference.is_some() {
                requested_outputs.push(RequestedOutput::Portability);
            }
            let request = CompileRequest {
                contract_version: program.contract_version,
                specification_version: program.specification_version.clone(),
                input: CompileInput::Semantic { program },
                target_profile: target_reference,
                requested_outputs,
                compiler_options: CompilerOptions {
                    partial_semantics: PartialSemantics::Forbid,
                    diagnostic_policy: DiagnosticPolicy {
                        minimum_severity: Severity::Hint,
                    },
                    resource_limits: None,
                },
            };
            let compiled =
                strling_kernel::compile_with_evidence(&request, target_profile.as_deref())
                    .map_err(|_| "explanation_prerequisite_failed")?;
            let evidence = compiled
                .explanation
                .as_ref()
                .ok_or("explanation_prerequisite_failed")?;
            let semantic = compiled
                .result
                .semantic_result
                .as_ref()
                .ok_or("explanation_prerequisite_failed")?;
            explain_no_match_with_clock(
                &semantic.program,
                evidence,
                &subject,
                NoMatchExecutionMode::Search,
                NoMatchLimits::default(),
                now,
            )
            .map(|result| json!(result))
            .map_err(|errors| {
                if errors
                    .errors
                    .iter()
                    .any(|error| error.code == NoMatchExplanationErrorCode::SubjectExceedsHardLimit)
                {
                    "subject_too_large"
                } else {
                    "explanation_evaluation_failed"
                }
            })
        }
    }
}

fn within_json_depth(bytes: &[u8]) -> bool {
    let mut depth = 0usize;
    let mut in_string = false;
    let mut escaped = false;
    for &byte in bytes {
        if in_string {
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                in_string = false;
            }
            continue;
        }
        match byte {
            b'"' => in_string = true,
            b'{' | b'[' => {
                depth += 1;
                if depth > MAX_JSON_DEPTH {
                    return false;
                }
            }
            b'}' | b']' => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    true
}

fn decode_request(bytes: &[u8]) -> Result<Request, serde_json::Error> {
    // The lexical preflight bounds nesting before recursive deserialization.
    // Serde then validates complete syntax and the closed request model.
    let mut decoder = serde_json::Deserializer::from_slice(bytes);
    decoder.disable_recursion_limit();
    let request = Request::deserialize(&mut decoder)?;
    decoder.end()?;
    Ok(request)
}

/// Dispatch one bounded browser tooling request without altering canonical output models.
pub fn dispatch(bytes: &[u8], now: &dyn Fn() -> Duration) -> Vec<u8> {
    fn failure(operation: Option<&str>, error: &str) -> Value {
        json!({"protocol":PROTOCOL, "operation":operation, "error":error})
    }
    let (operation, response) = if bytes.len() > MAX_REQUEST {
        (None, failure(None, "request_too_large"))
    } else if !within_json_depth(bytes) {
        (None, failure(None, "request_too_deep"))
    } else {
        match decode_request(bytes) {
            Ok(request) if request.protocol == PROTOCOL => {
                let operation = Some(request.request.name());
                let response = match execute(request.request, now) {
                    Ok(result) => {
                        json!({"protocol":PROTOCOL,"operation":operation,"result":result})
                    }
                    Err(error) => failure(operation, error),
                };
                (operation, response)
            }
            Ok(_) => (None, failure(None, "unsupported_protocol")),
            Err(_) => (None, failure(None, "invalid_request")),
        }
    };
    let mut serialized = serde_json::to_vec(&response).expect("JSON value serializes");
    if serialized.len() > MAX_RESPONSE {
        serialized = serde_json::to_vec(&failure(operation, "response_too_large"))
            .expect("JSON value serializes");
    }
    serialized
}

#[cfg(target_arch = "wasm32")]
mod wasm {
    use super::{dispatch, Duration, MAX_REQUEST};
    use std::cell::RefCell;

    #[link(wasm_import_module = "strling_lab")]
    extern "C" {
        fn monotonic_milliseconds() -> f64;
    }

    fn clock() -> Duration {
        // An invalid clock traps so the host can discard the worker.
        let milliseconds = unsafe { monotonic_milliseconds() };
        Duration::try_from_secs_f64(milliseconds / 1000.0)
            .expect("the host clock must be finite and nonnegative")
    }

    thread_local! {
        static INPUT: RefCell<Vec<u8>> = RefCell::new(vec![0; MAX_REQUEST]);
        static OUTPUT: RefCell<Vec<u8>> = const { RefCell::new(Vec::new()) };
    }

    // Pointers designate module-owned buffers. The serial host copies output before its next call.
    #[no_mangle]
    pub extern "C" fn strling_lab_input_v1() -> *mut u8 {
        INPUT.with(|bytes| bytes.borrow_mut().as_mut_ptr())
    }

    #[no_mangle]
    pub extern "C" fn strling_lab_run_v1(length: usize) -> usize {
        let result = INPUT.with(|input| {
            let input = input.borrow();
            if length > MAX_REQUEST {
                return None;
            }
            Some(dispatch(&input[..length], &clock))
        });
        OUTPUT.with(|output| {
            let mut output = output.borrow_mut();
            *output = result.unwrap_or_default();
            output.len()
        })
    }

    #[no_mangle]
    pub extern "C" fn strling_lab_output_v1() -> *const u8 {
        OUTPUT.with(|bytes| bytes.borrow().as_ptr())
    }
}
