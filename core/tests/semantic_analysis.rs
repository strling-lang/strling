use serde_json::{json, Value};
use strling_kernel::semantic::{Node, SemanticProgram};
use strling_kernel::semantic_analysis::{
    analyze, SemanticAnalysisErrorCode, SemanticNodeKind, MAX_ANALYSIS_DEPTH,
};
use strling_kernel::source::NodeId;

const SEMANTIC_ALL: &str =
    include_str!("../../spec/contracts/1.0/examples/semantic-ir/semantic-all-nodes.json");

fn program(root: Value) -> SemanticProgram {
    serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "specification_version": "1.0-draft.1",
        "normalization": "canonical-v1",
        "case_matching": "sensitive",
        "root": root
    }))
    .expect("test candidate must deserialize")
}

fn empty(node_id: &str) -> Value {
    json!({"node_id": node_id, "kind": "empty"})
}

#[test]
fn every_reachable_node_has_one_identity_keyed_fact_record() {
    let semantic: SemanticProgram =
        serde_json::from_str(SEMANTIC_ALL).expect("canonical fixture must deserialize");
    let facts = analyze(&semantic).expect("canonical fixture must analyze");

    assert_eq!(facts.len(), semantic.node_ids().len());
    assert!(!facts.is_empty());
    for node_id in semantic.node_ids() {
        assert!(
            facts.get(&node_id).is_some(),
            "missing facts for {node_id:?}"
        );
    }
    let root = facts
        .get(semantic.root.node_id())
        .expect("root must have facts");
    assert_eq!(root.kind, SemanticNodeKind::Sequence);
}

#[test]
fn fact_iteration_is_deterministic_identity_order() {
    let semantic = program(json!({
        "node_id": "node:z-root",
        "kind": "sequence",
        "items": [empty("node:z-child"), empty("node:a-child")]
    }));

    let first = analyze(&semantic).expect("canonical program must analyze");
    let second = analyze(&semantic).expect("repeated analysis must succeed");
    assert_eq!(first, second);
    let ids: Vec<_> = first.iter().map(|(id, _)| id.as_str()).collect();
    assert_eq!(ids, ["node:a-child", "node:z-child", "node:z-root"]);
}

#[test]
fn returned_facts_own_their_identities_after_the_input_is_dropped() {
    let root = json!({
        "node_id": "node:owned.root",
        "kind": "sequence",
        "items": [
            {
                "node_id": "node:owned.capture",
                "kind": "capture",
                "capture_id": "capture:owned",
                "name": "owned",
                "body": {"node_id": "node:owned.body", "kind": "literal", "text": "λ"}
            },
            {
                "node_id": "node:owned.reference",
                "kind": "backreference",
                "capture_id": "capture:owned"
            }
        ]
    });
    let facts = {
        let temporary_input = program(root.clone());
        analyze(&temporary_input).expect("scoped canonical input must analyze")
    };
    let capture = facts.capture_definitions().next().unwrap().1;
    assert_eq!(capture.capture_id.as_str(), "capture:owned");
    assert_eq!(capture.name.as_deref(), Some("owned"));
    let reference = NodeId::try_from("node:owned.reference").unwrap();
    assert_eq!(
        facts.backreference(&reference).unwrap().capture_id,
        capture.capture_id
    );
    let independently_reconstructed = program(root);
    assert_eq!(
        facts,
        analyze(&independently_reconstructed)
            .expect("identical input must retain exact owned facts")
    );
}

#[test]
fn duplicate_and_missing_identity_states_do_not_enter_the_fact_store() {
    let duplicate = program(json!({
        "node_id": "node:root",
        "kind": "sequence",
        "items": [empty("node:duplicate"), empty("node:duplicate")]
    }));
    let errors = analyze(&duplicate).expect_err("duplicate identity must fail");
    assert!(errors
        .errors
        .iter()
        .any(|error| error.code == SemanticAnalysisErrorCode::InvalidIdentity));

    let missing: Result<SemanticProgram, _> = serde_json::from_value(json!({
        "contract_version": "1.0.0",
        "specification_version": "1.0-draft.1",
        "normalization": "canonical-v1",
        "case_matching": "sensitive",
        "root": {"kind": "empty"}
    }));
    assert!(missing.is_err(), "typed Semantic IR requires node identity");

    let absent = NodeId::try_from("node:not-reachable").expect("test identity must be valid");
    let facts = analyze(&program(empty("node:only"))).expect("empty root must analyze");
    assert!(facts.get(&absent).is_none());
}

#[test]
fn noncanonical_input_is_rejected_without_normalization() {
    let semantic = program(json!({
        "node_id": "node:sequence",
        "kind": "sequence",
        "items": [empty("node:only")]
    }));
    let errors = analyze(&semantic).expect_err("single-child sequence is noncanonical");
    assert!(errors.errors.iter().any(|error| {
        matches!(
            error.code,
            SemanticAnalysisErrorCode::InvalidSemanticStructure
                | SemanticAnalysisErrorCode::NonCanonicalInput
        )
    }));
}

#[test]
fn source_less_and_deeply_nested_programs_are_supported_with_a_safe_limit() {
    let mut semantic = program(empty("node:leaf"));
    for depth in 1..MAX_ANALYSIS_DEPTH {
        semantic.root = Node::Atomic {
            node_id: NodeId::try_from(format!("node:atomic.{depth}"))
                .expect("generated node identity must be valid"),
            origin: None,
            body: Box::new(semantic.root),
        };
    }
    let facts = analyze(&semantic).expect("program at the depth limit must analyze");
    assert_eq!(facts.len(), MAX_ANALYSIS_DEPTH);

    semantic.root = Node::Atomic {
        node_id: NodeId::try_from("node:too-deep").expect("test identity must be valid"),
        origin: None,
        body: Box::new(semantic.root),
    };
    let errors = analyze(&semantic).expect_err("pathological depth must fail safely");
    assert_eq!(
        errors.errors[0].code,
        SemanticAnalysisErrorCode::DepthLimitExceeded
    );
}
