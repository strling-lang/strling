//! Structured cross-contract validation support.

use std::error::Error;
use std::fmt;

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
    pub fn single(error: ValidationError) -> Self {
        Self {
            errors: vec![error],
        }
    }

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
    Ok(Sha256::digest(serde_json::to_vec(&value)?).into())
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

#[cfg(test)]
mod canonical_digest_tests {
    use super::canonical_sha256;
    use serde::{Serialize, Serializer};
    use serde_json::Value;
    use sha2::{Digest, Sha256};

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
            let observed: String = canonical_sha256(&profile)
                .expect("typed profile digest")
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
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
    }
}
