use std::collections::BTreeSet;

use serde::Deserialize;
use strling_kernel::semantic::SemanticProgram;

use super::*;
use crate::oracle::replay;

fn program(expression: &str) -> SemanticProgram {
    let document = format!("semantic strling 1.0; case sensitive; pattern {expression}");
    decode(document.as_bytes(), InputFormat::Semantic, "left")
        .unwrap_or_else(|error| panic!("{expression}: {error:?}"))
        .program
}

#[derive(Deserialize)]
struct Fixture {
    name: String,
    query: Query,
    left: String,
    right: String,
    status: String,
    witness: Option<String>,
    left_accepts: Option<bool>,
    right_accepts: Option<bool>,
}

#[test]
fn authored_fixtures_agree_with_their_independent_expectations() {
    let fixtures: Vec<Fixture> = serde_json::from_str(include_str!("../fixtures.json")).unwrap();
    for fixture in fixtures {
        let report = serde_json::to_value(compare(
            &program(&fixture.left),
            &program(&fixture.right),
            Limits::default(),
            fixture.query,
        ))
        .unwrap();
        assert_eq!(
            report["status"], fixture.status,
            "{}: {report}",
            fixture.name
        );
        if let Some(expected) = fixture.witness {
            assert_eq!(report["witness"], expected, "{}", fixture.name);
            assert_eq!(report["left_accepts"], fixture.left_accepts.unwrap());
            assert_eq!(report["right_accepts"], fixture.right_accepts.unwrap());
            assert_eq!(report["independent_replay"], true);
        }
    }
}

#[test]
fn all_budget_exhaustions_refuse_to_claim_an_answer() {
    let left = program("text \"aa\";");
    let right = program("text \"ab\";");
    let defaults = Limits::default();
    let cases = [
        (
            Limits {
                state_pairs: 1,
                ..defaults
            },
            "state_pair_limit",
        ),
        (
            Limits {
                nfa_work: 0,
                ..defaults
            },
            "nfa_work_limit",
        ),
        (
            Limits {
                witness_scalars: 1,
                ..defaults
            },
            "witness_length_limit",
        ),
        (
            Limits {
                nfa_states_each: 1,
                ..defaults
            },
            "nfa_state_limit",
        ),
        (
            Limits {
                alphabet_classes: 2,
                ..defaults
            },
            "alphabet_class_limit",
        ),
        (
            Limits {
                replay_work_each: 0,
                ..defaults
            },
            "independent_replay_work_limit",
        ),
    ];
    for (limits, expected) in cases {
        assert!(matches!(
            compare(&left, &right, limits, Query::Equivalent),
            Outcome::Unknown { reason, .. } if reason == expected
        ));
    }
}

#[test]
fn canonical_ir_inputs_check_version_case_and_skipped_nodes() {
    let literal = program("text \"a\";");
    let mut ir = serde_json::to_value(&literal).unwrap();
    let bytes = serde_json::to_vec(&ir).unwrap();
    assert_eq!(
        decode(&bytes, InputFormat::Ir, "left").unwrap().program,
        literal
    );

    ir["contract_version"] = json!("9.0.0");
    let bytes = serde_json::to_vec(&ir).unwrap();
    assert!(matches!(
        decode(&bytes, InputFormat::Ir, "left"),
        Err(Outcome::Invalid { .. })
    ));

    ir["contract_version"] = json!(CONTRACT);
    ir["specification_version"] = json!("1.0-draft.2");
    let bytes = serde_json::to_vec(&ir).unwrap();
    assert!(matches!(
        decode(&bytes, InputFormat::Ir, "left"),
        Err(Outcome::Unsupported {
            reason: "input_contract_identity",
            ..
        })
    ));
    ir["specification_version"] = json!(SPECIFICATION);
    ir["root"]["text"] = json!("");
    let bytes = serde_json::to_vec(&ir).unwrap();
    assert!(matches!(
        decode(&bytes, InputFormat::Ir, "left"),
        Err(Outcome::Invalid { .. })
    ));

    assert!(matches!(
        decode(&[0xFF], InputFormat::Semantic, "left"),
        Err(Outcome::Invalid { .. })
    ));
    assert!(matches!(
        decode(&vec![0; INPUT_BYTES as usize + 1], InputFormat::Ir, "right"),
        Err(Outcome::Unknown {
            reason: "input_byte_limit",
            ..
        })
    ));

    let mut folded = literal.clone();
    folded.case_matching = strling_kernel::semantic::CaseMatching::Insensitive;
    assert!(matches!(
        compare(&folded, &literal, Limits::default(), Query::Equivalent),
        Outcome::Unsupported {
            reason: "case_folding",
            ..
        }
    ));
}

#[test]
fn shortest_witness_at_depth_limit_survives_other_truncated_paths() {
    let left = program("choice { text \"aa\"; text \"b\"; }");
    let right = program("text \"aa\";");
    let limits = Limits {
        witness_scalars: 1,
        ..Limits::default()
    };
    assert!(matches!(
        compare(&left, &right, limits, Query::Equivalent),
        Outcome::Refuted { witness, .. } if witness == "b"
    ));
}

#[test]
fn independent_replay_distinguishes_a_forged_witness() {
    let left = program("text \"a👋\";");
    let right = program("text \"a😀\";");
    let membership = |word: &str| {
        let word: Vec<_> = word.chars().collect();
        (
            replay(&left.root, &word, 10_000).unwrap(),
            replay(&right.root, &word, 10_000).unwrap(),
        )
    };
    assert_eq!(membership("a👋"), (true, false));
    assert_eq!(membership("a🟢"), (false, false));
}

// Independent reference. These expressions are specified before DSL parsing;
// none are reconstructed from the solver's graph, alphabet cuts, or answers.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum Expr {
    Never,
    Empty,
    Atom(char),
    Alt(Vec<Expr>),
    Cat(Vec<Expr>),
    Star(Box<Expr>),
}

impl Expr {
    fn alt(terms: impl IntoIterator<Item = Self>) -> Self {
        let mut set = BTreeSet::new();
        for term in terms {
            match term {
                Self::Never => {}
                Self::Alt(nested) => set.extend(nested),
                other => {
                    set.insert(other);
                }
            }
        }
        let mut terms: Vec<_> = set.into_iter().collect();
        match terms.len() {
            0 => Self::Never,
            1 => terms.pop().unwrap(),
            _ => Self::Alt(terms),
        }
    }

    fn cat(terms: impl IntoIterator<Item = Self>) -> Self {
        let mut flattened = Vec::new();
        for term in terms {
            match term {
                Self::Never => return Self::Never,
                Self::Empty => {}
                Self::Cat(nested) => flattened.extend(nested),
                other => flattened.push(other),
            }
        }
        match flattened.len() {
            0 => Self::Empty,
            1 => flattened.pop().unwrap(),
            _ => Self::Cat(flattened),
        }
    }

    fn nullable(&self) -> bool {
        match self {
            Self::Never | Self::Atom(_) => false,
            Self::Empty | Self::Star(_) => true,
            Self::Alt(terms) => terms.iter().any(Self::nullable),
            Self::Cat(terms) => terms.iter().all(Self::nullable),
        }
    }

    fn derivative(&self, char: char) -> Self {
        match self {
            Self::Atom(literal) if *literal == char => Self::Empty,
            Self::Never | Self::Empty | Self::Atom(_) => Self::Never,
            Self::Alt(terms) => Self::alt(terms.iter().map(|term| term.derivative(char))),
            Self::Cat(terms) => {
                let mut alternatives = Vec::new();
                for (index, term) in terms.iter().enumerate() {
                    alternatives.push(Self::cat(
                        [term.derivative(char)]
                            .into_iter()
                            .chain(terms[index + 1..].iter().cloned()),
                    ));
                    if !term.nullable() {
                        break;
                    }
                }
                Self::alt(alternatives)
            }
            Self::Star(body) => Self::cat([body.derivative(char), self.clone()]),
        }
    }

    fn expression(&self) -> String {
        match self {
            Self::Never => panic!("only derivatives can be the empty language in this corpus"),
            Self::Empty => "empty;".into(),
            Self::Atom(value) => format!("text \"{value}\";"),
            Self::Alt(terms) => {
                let branches: Vec<_> = terms.iter().map(Self::expression).collect();
                format!("choice {{ {} }}", branches.join(" "))
            }
            Self::Cat(terms) => {
                let items: Vec<_> = terms.iter().map(Self::expression).collect();
                format!("sequence {{ {} }}", items.join(" "))
            }
            Self::Star(body) => format!(
                "repeat from 0 to unbounded using greedy {{ {} }}",
                body.expression()
            ),
        }
    }
}

// The reference patterns use only a and b. NUL stands for the entire
// complement. That cell can never consume a symbol in either language.
const REFERENCE_ALPHABET: [char; 3] = ['\0', 'a', 'b'];

fn reference_witness(left: &Expr, right: &Expr, query: Query) -> Option<String> {
    let start = (left.clone(), right.clone());
    let mut seen = BTreeSet::from([start.clone()]);
    let mut queue = vec![(start, String::new())];
    let mut index = 0;
    while index < queue.len() {
        assert!(index < 1_024, "reference exceeded its test envelope");
        let ((left, right), word) = queue[index].clone();
        if query.contradicted(left.nullable(), right.nullable()) {
            return Some(word);
        }
        for scalar in REFERENCE_ALPHABET {
            let next = (left.derivative(scalar), right.derivative(scalar));
            if seen.insert(next.clone()) {
                let mut extended = word.clone();
                extended.push(scalar);
                queue.push((next, extended));
            }
        }
        index += 1;
    }
    None
}

#[test]
fn independent_derivatives_and_direct_membership_crosscheck_the_graph() {
    use Expr::{Atom, Empty, Star};
    let a = Atom('a');
    let b = Atom('b');
    let star = |expr| Star(Box::new(expr));
    let fixtures = [
        Empty,
        a.clone(),
        b.clone(),
        Expr::alt([a.clone(), b.clone()]),
        Expr::cat([a.clone(), b.clone()]),
        star(a.clone()),
        star(Expr::alt([Empty, a.clone()])),
        Expr::cat([star(a.clone()), Expr::alt([Empty, b.clone()])]),
        star(Expr::alt([a.clone(), Expr::cat([a.clone(), b.clone()])])),
    ];
    let programs: Vec<_> = fixtures
        .iter()
        .map(|expr| program(&expr.expression()))
        .collect();

    let mut words = vec![Vec::new()];
    let mut start = 0;
    for _ in 0..3 {
        let end = words.len();
        for index in start..end {
            for scalar in REFERENCE_ALPHABET {
                let mut next = words[index].clone();
                next.push(scalar);
                words.push(next);
            }
        }
        start = end;
    }

    for (left_index, (left_expr, left)) in fixtures.iter().zip(&programs).enumerate() {
        for word in &words {
            let residual = word
                .iter()
                .fold(left_expr.clone(), |expr, &scalar| expr.derivative(scalar));
            let direct = replay(&left.root, word, 10_000).unwrap();
            assert_eq!(residual.nullable(), direct, "{left_expr:?} for {word:?}");
        }
        for (right_index, (right_expr, right)) in fixtures.iter().zip(&programs).enumerate() {
            for query in [Query::Equivalent, Query::Contains, Query::Disjoint] {
                let evidence = compare(left, right, Limits::default(), query);
                match (evidence, reference_witness(left_expr, right_expr, query)) {
                    (Outcome::Proven { .. }, None) => {}
                    (Outcome::Refuted { witness, .. }, Some(expected)) => {
                        assert_eq!(witness, expected, "{left_index} {right_index} {query:?}")
                    }
                    pair => panic!("{left_index} {right_index} {query:?}: {pair:?}"),
                }
            }
        }
    }
    assert_eq!(words.len() * fixtures.len(), 360);
    assert_eq!(fixtures.len() * fixtures.len() * 3, 243);
}
