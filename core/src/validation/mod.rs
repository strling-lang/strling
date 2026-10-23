//! Structured cross-contract validation support.

use std::error::Error;
use std::fmt;
use std::io::{self, Write};

use serde::de::DeserializeOwned;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

/// Stable categories for structural contract validation failures.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ValidationCode {
    DuplicateIdentity,
    EmptyCollection,
    EmptyValue,
    InvalidBounds,
    InvalidDigest,
    InvalidIdentity,
    InvalidProvenance,
    InvalidSpan,
    InvalidUri,
    InvalidVersion,
    NonCanonicalOrder,
    NonCanonicalStructure,
    SpecificationMismatch,
    UnresolvedReference,
    Utf8Boundary,
}

/// One machine-classifiable validation failure with a stable data path.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ValidationError {
    pub code: ValidationCode,
    pub path: String,
    pub message: String,
}

impl ValidationError {
    #[must_use]
    #[inline(never)]
    pub fn new(code: ValidationCode, path: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code,
            path: path.into(),
            message: message.into(),
        }
    }
}

/// Ordered validation failures returned for externally supplied contract data.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ValidationErrors {
    pub errors: Vec<ValidationError>,
}

impl ValidationErrors {
    #[must_use]
    #[inline(never)]
    pub fn single(error: ValidationError) -> Self {
        Self {
            errors: vec![error],
        }
    }

    #[inline(never)]
    pub(crate) fn push(&mut self, error: ValidationError) {
        self.errors.push(error);
    }

    pub(crate) fn extend(&mut self, other: Self) {
        self.errors.extend(other.errors);
    }

    pub(crate) fn finish(self) -> Result<(), Self> {
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err(self)
        }
    }
}

impl fmt::Display for ValidationErrors {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} contract validation error(s)",
            self.errors.len()
        )
    }
}

impl Error for ValidationErrors {}

/// Structural validation implemented by every externally supplied contract root.
pub trait Validate {
    /// Validate invariants that Rust and Serde cannot express by construction.
    fn validate(&self) -> Result<(), ValidationErrors>;
}

/// Deserialization and validation failures remain distinguishable without prose parsing.
#[derive(Debug)]
pub enum ContractError {
    Deserialization(serde_json::Error),
    Validation(ValidationErrors),
}

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Deserialization(error) => {
                write!(formatter, "contract deserialization failed: {error}")
            }
            Self::Validation(errors) => errors.fmt(formatter),
        }
    }
}

impl Error for ContractError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Deserialization(error) => Some(error),
            Self::Validation(errors) => Some(errors),
        }
    }
}

/// Deserialize closed JSON data and apply its domain invariants.
pub fn from_json<T>(input: &str) -> Result<T, ContractError>
where
    T: DeserializeOwned + Validate,
{
    let value: T = serde_json::from_str(input).map_err(ContractError::Deserialization)?;
    value.validate().map_err(ContractError::Validation)?;
    Ok(value)
}

/// Serialize a contract value using deterministic struct and ordered-map traversal.
pub fn to_json<T>(value: &T) -> Result<String, serde_json::Error>
where
    T: Serialize,
{
    serde_json::to_string(value)
}

/// SHA-256 of compact JSON with recursively sorted object keys and UTF-8 text.
pub fn canonical_sha256<T>(value: &T) -> Result<[u8; 32], serde_json::Error>
where
    T: Serialize,
{
    let mut value = serde_json::to_value(value)?;
    canonicalize(&mut value);
    serialized_sha256(&value)
}

/// Hash the exact deterministic Serde JSON byte stream without materializing a
/// second heap buffer. This deliberately does not canonicalize struct fields;
/// callers that require recursively sorted object keys do so before this step.
pub(crate) fn serialized_sha256<T>(value: &T) -> Result<[u8; 32], serde_json::Error>
where
    T: Serialize,
{
    let mut writer = JsonDigestWriter {
        digest: Sha256::new(),
        buffer: [0; 512],
        used: 0,
    };
    serde_json::to_writer(&mut writer, value)?;
    writer.drain();
    Ok(writer.digest.finalize().into())
}

struct JsonDigestWriter {
    digest: Sha256,
    buffer: [u8; 512],
    used: usize,
}

impl JsonDigestWriter {
    fn drain(&mut self) {
        self.digest.update(&self.buffer[..self.used]);
        self.used = 0;
    }
}

impl Write for JsonDigestWriter {
    #[inline]
    fn write_all(&mut self, bytes: &[u8]) -> io::Result<()> {
        // Serde emits many small fragments. Keep those on a bounded, single
        // copy path rather than entering Write::write_all's retry loop and
        // the general buffer-boundary loop for every punctuation byte.
        let available = self.buffer.len() - self.used;
        if bytes.len() <= available {
            self.buffer[self.used..self.used + bytes.len()].copy_from_slice(bytes);
            self.used += bytes.len();
            Ok(())
        } else {
            // This writer always consumes the full slice or returns an error.
            self.write(bytes).map(|_| ())
        }
    }

    fn write(&mut self, mut bytes: &[u8]) -> io::Result<usize> {
        let length = bytes.len();
        while !bytes.is_empty() {
            let available = self.buffer.len() - self.used;
            let taken = available.min(bytes.len());
            self.buffer[self.used..self.used + taken].copy_from_slice(&bytes[..taken]);
            self.used += taken;
            bytes = &bytes[taken..];
            if self.used == self.buffer.len() {
                self.drain();
            }
        }
        Ok(length)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.drain();
        Ok(())
    }
}

fn canonicalize(value: &mut Value) {
    match value {
        Value::Array(items) => {
            for item in items {
                canonicalize(item);
            }
        }
        Value::Object(object) => {
            // Default JSON maps are already sorted. Preserve their allocations,
            // while still handling insertion-ordered maps from feature unification.
            if object
                .keys()
                .zip(object.keys().skip(1))
                .all(|(left, right)| left <= right)
            {
                for child in object.values_mut() {
                    canonicalize(child);
                }
                return;
            }
            let mut entries: Vec<_> = std::mem::take(object).into_iter().collect();
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            let mut sorted = Map::new();
            for (key, mut child) in entries {
                canonicalize(&mut child);
                sorted.insert(key, child);
            }
            *object = sorted;
        }
        _ => {}
    }
}

/// Optional schema fields reject explicit JSON null while accepting omission.
pub(crate) fn deserialize_optional_non_null<'de, D, T>(
    deserializer: D,
) -> Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(deserializer).map(Some)
}

pub(crate) fn nonempty(value: &str, path: impl Into<String>, errors: &mut ValidationErrors) {
    if value.is_empty() {
        errors.push(ValidationError::new(
            ValidationCode::EmptyValue,
            path,
            "value must not be empty",
        ));
    }
}

/// Construct dynamic diagnostic paths only when validation actually fails.
pub(crate) fn nonempty_with_path(
    value: &str,
    path: impl FnOnce() -> String,
    errors: &mut ValidationErrors,
) {
    if value.is_empty() {
        nonempty(value, path(), errors);
    }
}

#[cfg(test)]
mod nonempty_path_tests {
    use super::{nonempty, nonempty_with_path, ValidationErrors};
    use std::cell::Cell;

    #[test]
    fn valid_text_never_constructs_a_diagnostic_path() {
        let mut errors = ValidationErrors::default();
        for value in ["x", " ", "\0", "\u{1f680}"] {
            nonempty_with_path(
                value,
                || panic!("valid value needs no error path"),
                &mut errors,
            );
        }
        assert!(errors.errors.is_empty());
    }

    #[test]
    fn empty_text_constructs_the_original_error_exactly_once() {
        let calls = Cell::new(0);
        let mut actual = ValidationErrors::default();
        let mut expected = ValidationErrors::default();
        nonempty("", "$.root.items[12].text", &mut expected);
        nonempty_with_path(
            "",
            || {
                calls.set(calls.get() + 1);
                "$.root.items[12].text".to_owned()
            },
            &mut actual,
        );
        assert_eq!(calls.get(), 1);
        assert_eq!(actual, expected);
    }
}

#[cfg(test)]
mod canonical_digest_tests {
    use super::{canonical_sha256, serialized_sha256, JsonDigestWriter};
    use serde::{Serialize, Serializer};
    use serde_json::Value;
    use sha2::{Digest, Sha256};
    use std::fmt::Write;

    #[test]
    fn serialized_digest_preserves_all_bytes_across_buffer_boundaries() {
        #[derive(Serialize)]
        struct Example {
            z_text: String,
            a_values: Vec<u64>,
        }
        for length in [
            0, 1, 63, 64, 65, 255, 256, 257, 511, 512, 513, 1023, 1024, 1025, 8192,
        ] {
            let value = Example {
                z_text: format!("{}\0\r\n\t\"\\βé😀", "x".repeat(length)),
                a_values: vec![0, 1, u64::MAX],
            };
            let exact_bytes = serde_json::to_vec(&value).unwrap();
            let expected: [u8; 32] = Sha256::digest(&exact_bytes).into();
            assert_eq!(serialized_sha256(&value).unwrap(), expected);
        }
    }

    #[test]
    fn digest_writer_retains_bytes_across_empty_writes_and_explicit_flush() {
        use std::io::Write as IoWrite;
        let mut writer = JsonDigestWriter {
            digest: Sha256::new(),
            buffer: [0; 512],
            used: 0,
        };
        writer.write_all(b"first").unwrap();
        assert_eq!(writer.write(b"").unwrap(), 0);
        writer.flush().unwrap();
        writer.flush().unwrap();
        writer.write_all(&[b'x'; 1025]).unwrap();
        writer.drain();
        let mut expected = b"first".to_vec();
        expected.extend_from_slice(&[b'x'; 1025]);
        assert_eq!(
            <[u8; 32]>::from(writer.digest.finalize()),
            <[u8; 32]>::from(Sha256::digest(expected))
        );
    }

    #[test]
    fn mixed_writes_and_flushes_preserve_arbitrary_bytes_at_every_boundary() {
        use std::io::Write as IoWrite;
        let bytes: Vec<u8> = (0..12_289).map(|index| (index % 256) as u8).collect();
        let chunks = [0, 1, 63, 64, 65, 255, 256, 257, 511, 512, 513, 1024, 4096];
        let mut writer = JsonDigestWriter {
            digest: Sha256::new(),
            buffer: [0; 512],
            used: 0,
        };
        let mut offset = 0;
        let mut step = 0;
        while offset < bytes.len() {
            let end = (offset + chunks[step % chunks.len()]).min(bytes.len());
            if step % 2 == 0 {
                writer.write_all(&bytes[offset..end]).unwrap();
            } else {
                assert_eq!(writer.write(&bytes[offset..end]).unwrap(), end - offset);
            }
            assert!(writer.used <= writer.buffer.len());
            if step % 5 == 0 {
                writer.flush().unwrap();
                writer.flush().unwrap();
            }
            offset = end;
            step += 1;
        }
        writer.drain();
        assert_eq!(
            <[u8; 32]>::from(writer.digest.finalize()),
            <[u8; 32]>::from(Sha256::digest(bytes))
        );
    }

    #[test]
    fn exactly_full_buffer_followed_by_empty_and_large_writes_loses_no_bytes() {
        use std::io::Write as IoWrite;
        let mut writer = JsonDigestWriter {
            digest: Sha256::new(),
            buffer: [0; 512],
            used: 0,
        };
        let mut bytes = Vec::new();
        for length in [512, 0, 1, 511, 0, 512, 0, 1025, 4096, 0] {
            let chunk: Vec<u8> = (0..length).map(|index| (index % 251) as u8).collect();
            writer.write_all(&chunk).unwrap();
            assert!(writer.used <= writer.buffer.len());
            bytes.extend_from_slice(&chunk);
        }
        writer.flush().unwrap();
        writer.write_all(b"").unwrap();
        writer.drain();
        assert_eq!(
            <[u8; 32]>::from(writer.digest.finalize()),
            <[u8; 32]>::from(Sha256::digest(bytes))
        );
    }

    #[test]
    fn typed_semantic_identity_preserves_the_exact_contract_byte_stream() {
        let semantic: crate::semantic::SemanticProgram = serde_json::from_str(include_str!(
            "../../../spec/contracts/1.0/examples/semantic-ir/semantic-all-nodes.json"
        ))
        .expect("specification-authored semantic fixture");
        let exact = serde_json::to_vec(&semantic).unwrap();
        let expected: [u8; 32] = Sha256::digest(&exact).into();
        for _ in 0..16 {
            assert_eq!(serialized_sha256(&semantic).unwrap(), expected);
            let facts = crate::semantic_analysis::analyze(&semantic).unwrap();
            assert_eq!(facts.len(), semantic.node_ids().len());
            assert_eq!(serde_json::to_vec(&semantic).unwrap(), exact);
        }
    }

    #[test]
    fn nested_objects_use_sorted_keys_without_reordering_arrays() {
        let canonical = "{\"a\":{\"a\":null,\"β\":false},\"z\":[{\"a\":\"é\\n\\\"\",\"z\":0},3,1]}";
        let expected: [u8; 32] = Sha256::digest(canonical.as_bytes()).into();
        for source in [
            r#"{"z":[{"z":0,"a":"é\n\""},3,1],"a":{"β":false,"a":null}}"#,
            r#"{"a":{"β":false,"a":null},"z":[{"z":0,"a":"é\n\""},3,1]}"#,
        ] {
            let input: Value = serde_json::from_str(source).expect("unordered nested JSON");
            assert_eq!(
                canonical_sha256(&input).expect("canonical digest"),
                expected
            );
            let mut changed_order = input;
            changed_order["z"]
                .as_array_mut()
                .expect("ordered array")
                .swap(1, 2);
            assert_ne!(
                canonical_sha256(&changed_order).expect("changed array digest"),
                expected
            );
        }
    }

    #[test]
    fn governed_target_profiles_keep_their_canonical_fingerprints() {
        for (source, expected) in [
            (
                include_str!("../../../spec/targets/profiles/pcre2-10.42.json"),
                "57941ab3f2a5709d030c6f890b1911564513e0dd785710956d7b8af19711e9e2",
            ),
            (
                include_str!("../../../spec/targets/profiles/pcre2-10.43.json"),
                "56762a1d289d41d0811b007695464916fda0ca5c48c2f5569b4ec26983a24bff",
            ),
            (
                include_str!("../../../spec/targets/profiles/ecmascript-2024.json"),
                "d0f13d7b7b0af92f201dfd29270325d9c3cce50cf39a5969648b71c9c25905bc",
            ),
            (
                include_str!("../../../spec/targets/profiles/python-re-3.11.json"),
                "b3d5e5cbce0a2cd1f0f236914b7d35abc6e7c7614ff9d80d4ee2b7c546d5f3cf",
            ),
            (
                include_str!("../../../spec/targets/profiles/python-re-3.11-bytes.json"),
                "385ed4271e999db85dd0d4c1fd2894c50b2eb16e0d40a3c83b0306fb7fa1805c",
            ),
        ] {
            let profile: crate::target::TargetProfile =
                serde_json::from_str(source).expect("governed target profile");
            let value: Value = serde_json::from_str(source).expect("profile JSON");
            assert_eq!(
                canonical_sha256(&profile).expect("typed profile digest"),
                canonical_sha256(&value).expect("document digest")
            );
            let mut observed = String::with_capacity(64);
            for byte in canonical_sha256(&profile).expect("typed profile digest") {
                write!(&mut observed, "{byte:02x}").expect("write digest to string");
            }
            assert_eq!(observed, expected);
        }
    }

    #[test]
    fn serialization_failure_is_preserved() {
        struct Refused;
        impl Serialize for Refused {
            fn serialize<S>(&self, _serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                Err(serde::ser::Error::custom(
                    "deliberate serialization refusal",
                ))
            }
        }
        assert!(canonical_sha256(&Refused)
            .expect_err("refused serialization cannot produce a digest")
            .to_string()
            .contains("deliberate serialization refusal"));
        assert!(serialized_sha256(&Refused)
            .expect_err("refused streaming serialization cannot produce a digest")
            .to_string()
            .contains("deliberate serialization refusal"));
    }

    #[test]
    fn partial_serialization_failure_never_returns_a_prefix_digest() {
        use serde::ser::SerializeStruct;
        struct PartiallyRefused;
        impl Serialize for PartiallyRefused {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                let mut fields = serializer.serialize_struct("PartiallyRefused", 2)?;
                fields.serialize_field("valid_prefix", &"x".repeat(1025))?;
                Err(serde::ser::Error::custom("refusal after serialized prefix"))
            }
        }
        for error in [
            canonical_sha256(&PartiallyRefused).unwrap_err(),
            serialized_sha256(&PartiallyRefused).unwrap_err(),
        ] {
            assert!(error
                .to_string()
                .contains("refusal after serialized prefix"));
        }
    }
}
