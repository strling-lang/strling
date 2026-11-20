//! Thompson fragments and deterministic reachable-state comparison.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use strling_kernel::semantic::{
    CaseMatching, CharacterSetMember, Node, RepetitionMaximum, RepetitionMode, SemanticProgram,
};
use strling_kernel::source::NodeId;

use crate::oracle::{replay, ReplayError};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Query {
    Equivalent,
    Contains,
    Disjoint,
}

impl Query {
    pub fn contradicted(self, left: bool, right: bool) -> bool {
        match self {
            Self::Equivalent => left != right,
            Self::Contains => right && !left,
            Self::Disjoint => left && right,
        }
    }
}

#[derive(Clone, Copy, Serialize)]
pub struct Limits {
    pub nfa_states_each: usize,
    pub alphabet_classes: usize,
    pub state_pairs: usize,
    pub witness_scalars: usize,
    pub nfa_work: usize,
    pub replay_work_each: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            nfa_states_each: 1_024,
            alphabet_classes: 256,
            state_pairs: 4_096,
            witness_scalars: 96,
            nfa_work: 8_000_000,
            replay_work_each: 300_000,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct Stats {
    pub left_nfa_states: usize,
    pub right_nfa_states: usize,
    pub alphabet_classes: usize,
    pub examined_pairs: usize,
    pub examined_transitions: usize,
    pub nfa_work: usize,
}

#[derive(Clone, Debug, Serialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum Outcome {
    Proven {
        stats: Stats,
    },
    Refuted {
        witness: String,
        scalar_length: usize,
        left_accepts: bool,
        right_accepts: bool,
        independent_replay: bool,
        stats: Stats,
    },
    Unknown {
        reason: &'static str,
        stats: Stats,
    },
    Unsupported {
        side: &'static str,
        reason: &'static str,
        node_id: Option<NodeId>,
    },
    Invalid {
        side: &'static str,
        detail: String,
    },
}

impl Outcome {
    pub fn unknown(reason: &'static str) -> Self {
        Self::Unknown {
            reason,
            stats: Stats::default(),
        }
    }

    pub fn invalid(side: &'static str, detail: String) -> Self {
        Self::Invalid { side, detail }
    }

    pub fn unsupported(side: &'static str, reason: &'static str, node: Option<&Node>) -> Self {
        Self::Unsupported {
            side,
            reason,
            node_id: node.map(|node| node.node_id().clone()),
        }
    }
}

pub fn compare(
    left: &SemanticProgram,
    right: &SemanticProgram,
    limits: Limits,
    query: Query,
) -> Outcome {
    let mut cuts = BTreeSet::from([0, 0xD800, 0xE000, 0x110000]);
    for (program, side) in [(left, "left"), (right, "right")] {
        if program.case_matching != CaseMatching::Sensitive {
            return Outcome::unsupported(side, "case_folding", None);
        }
        if let Err(error) = validate_fragment(&program.root, side, &mut cuts, limits) {
            return error;
        }
    }
    let alphabet: Vec<_> = cuts.into_iter().filter_map(char::from_u32).collect();
    let mut stats = Stats {
        alphabet_classes: alphabet.len(),
        ..Stats::default()
    };
    let mut meter = Meter::new(limits.nfa_work);
    let result = (|| {
        let left_nfa = Nfa::new(&left.root, limits.nfa_states_each)?;
        stats.left_nfa_states = left_nfa.states.len();
        let right_nfa = Nfa::new(&right.root, limits.nfa_states_each)?;
        stats.right_nfa_states = right_nfa.states.len();
        traverse(
            (&left_nfa, &right_nfa),
            &alphabet,
            limits,
            query,
            &mut stats,
            &mut meter,
        )
    })();
    stats.nfa_work = meter.used;
    match result {
        Ok(None) => Outcome::Proven { stats },
        Ok(Some((word, left_accepts, right_accepts))) => {
            let checked_left = replay(&left.root, &word, limits.replay_work_each);
            let checked_right = replay(&right.root, &word, limits.replay_work_each);
            match (checked_left, checked_right) {
                (Ok(l), Ok(r)) if (l, r) == (left_accepts, right_accepts) => Outcome::Refuted {
                    witness: word.iter().collect(),
                    scalar_length: word.len(),
                    left_accepts,
                    right_accepts,
                    independent_replay: true,
                    stats,
                },
                (Err(ReplayError::WorkLimit), _) | (_, Err(ReplayError::WorkLimit)) => {
                    Outcome::Unknown {
                        reason: "independent_replay_work_limit",
                        stats,
                    }
                }
                _ => Outcome::Unknown {
                    reason: "independent_replay_disagreement",
                    stats,
                },
            }
        }
        Err(reason) => Outcome::Unknown { reason, stats },
    }
}

fn validate_fragment(
    node: &Node,
    side: &'static str,
    cuts: &mut BTreeSet<u32>,
    limits: Limits,
) -> Result<(), Outcome> {
    let mut interval = |first: char, last: char| {
        cuts.insert(u32::from(first));
        cuts.insert(u32::from(last) + 1);
        // One sentinel and the excluded surrogate cell are not alphabet classes.
        if cuts.len() > limits.alphabet_classes + 2 {
            return Err(Outcome::unknown("alphabet_class_limit"));
        }
        Ok(())
    };
    match node {
        Node::Empty { .. } => {}
        Node::Literal { text, .. } => {
            for scalar in text.chars() {
                interval(scalar, scalar)?;
            }
        }
        Node::CharacterSet {
            negated: false,
            members,
            ..
        } => {
            for member in members {
                let (first, last) = member_interval(member).ok_or_else(|| {
                    Outcome::unsupported(side, "unmodeled_set_member", Some(node))
                })?;
                interval(first, last)?;
            }
        }
        Node::Sequence { items, .. }
        | Node::Alternation {
            branches: items, ..
        } => {
            for child in items {
                validate_fragment(child, side, cuts, limits)?;
            }
        }
        Node::Repeat {
            body,
            mode: RepetitionMode::Greedy | RepetitionMode::Lazy,
            ..
        } => validate_fragment(body, side, cuts, limits)?,
        _ => return Err(Outcome::unsupported(side, "unmodeled_node", Some(node))),
    }
    Ok(())
}

fn member_interval(member: &CharacterSetMember) -> Option<(char, char)> {
    match member {
        CharacterSetMember::Literal { value } => Some((value.get(), value.get())),
        CharacterSetMember::Range { start, end } => Some((start.get(), end.get())),
        CharacterSetMember::Builtin { .. } | CharacterSetMember::UnicodeProperty { .. } => None,
    }
}

#[derive(Default)]
struct State {
    epsilon: Vec<usize>,
    scalar: Option<(Vec<(char, char)>, usize)>,
}

struct Nfa {
    states: Vec<State>,
    start: usize,
    accept: usize,
    state_limit: usize,
}

type Bound<T> = Result<T, &'static str>;

impl Nfa {
    fn new(root: &Node, state_limit: usize) -> Bound<Self> {
        let mut nfa = Self {
            states: Vec::new(),
            start: 0,
            accept: 0,
            state_limit,
        };
        (nfa.start, nfa.accept) = nfa.fragment(root)?;
        Ok(nfa)
    }

    fn state(&mut self) -> Bound<usize> {
        if self.states.len() == self.state_limit {
            return Err("nfa_state_limit");
        }
        let index = self.states.len();
        self.states.push(State::default());
        Ok(index)
    }

    fn epsilon(&mut self, from: usize, to: usize) {
        self.states[from].epsilon.push(to);
    }

    fn fragment(&mut self, node: &Node) -> Bound<(usize, usize)> {
        let start = self.state()?;
        let end = self.state()?;
        match node {
            Node::Empty { .. } => self.epsilon(start, end),
            Node::Literal { text, .. } => {
                let mut tail = start;
                let mut scalars = text.chars().peekable();
                while let Some(scalar) = scalars.next() {
                    let next = if scalars.peek().is_some() {
                        self.state()?
                    } else {
                        end
                    };
                    self.states[tail].scalar = Some((vec![(scalar, scalar)], next));
                    tail = next;
                }
            }
            Node::CharacterSet { members, .. } => {
                let intervals: Option<Vec<_>> = members.iter().map(member_interval).collect();
                self.states[start].scalar =
                    Some((intervals.ok_or("input_projection_disagreement")?, end));
            }
            Node::Sequence { items, .. } => {
                let mut tail = start;
                for child in items {
                    let (entry, exit) = self.fragment(child)?;
                    self.epsilon(tail, entry);
                    tail = exit;
                }
                self.epsilon(tail, end);
            }
            Node::Alternation { branches, .. } => {
                for child in branches {
                    let (entry, exit) = self.fragment(child)?;
                    self.epsilon(start, entry);
                    self.epsilon(exit, end);
                }
            }
            Node::Repeat { body, min, max, .. } => {
                let mut tail = start;
                for _ in 0..*min {
                    let (entry, exit) = self.fragment(body)?;
                    self.epsilon(tail, entry);
                    tail = exit;
                }
                self.epsilon(tail, end);
                match max {
                    RepetitionMaximum::Bounded(maximum) => {
                        for _ in *min..*maximum {
                            let (entry, exit) = self.fragment(body)?;
                            self.epsilon(tail, entry);
                            self.epsilon(exit, end);
                            tail = exit;
                        }
                    }
                    RepetitionMaximum::Unbounded => {
                        let (entry, exit) = self.fragment(body)?;
                        self.epsilon(tail, entry);
                        self.epsilon(exit, tail);
                    }
                }
            }
            _ => return Err("input_projection_disagreement"),
        }
        Ok((start, end))
    }

    fn closure(
        &self,
        seeds: impl IntoIterator<Item = usize>,
        meter: &mut Meter,
    ) -> Bound<StateSet> {
        let mut seen = StateSet::new(self.states.len());
        let mut pending = Vec::new();
        for seed in seeds {
            meter.charge(1)?;
            if seen.add(seed) {
                pending.push(seed);
            }
        }
        while let Some(state) = pending.pop() {
            let edges = &self.states[state].epsilon;
            meter.charge(1 + edges.len())?;
            for &successor in edges {
                if seen.add(successor) {
                    pending.push(successor);
                }
            }
        }
        Ok(seen)
    }

    fn step(&self, from: &StateSet, scalar: char, meter: &mut Meter) -> Bound<StateSet> {
        let mut next = Vec::new();
        meter.charge(self.states.len())?;
        for (index, state) in self.states.iter().enumerate() {
            if !from.contains(index) {
                continue;
            }
            if let Some((ranges, target)) = &state.scalar {
                meter.charge(ranges.len())?;
                if ranges.iter().any(|&(lo, hi)| (lo..=hi).contains(&scalar)) {
                    next.push(*target);
                }
            }
        }
        self.closure(next, meter)
    }
}

#[derive(Clone, Eq, Ord, PartialEq, PartialOrd)]
struct StateSet(Vec<u64>);

impl StateSet {
    fn new(states: usize) -> Self {
        Self(vec![0; states.div_ceil(64)])
    }

    fn contains(&self, state: usize) -> bool {
        self.0[state / 64] & (1u64 << (state % 64)) != 0
    }

    fn add(&mut self, state: usize) -> bool {
        let old = self.contains(state);
        self.0[state / 64] |= 1u64 << (state % 64);
        !old
    }
}

struct Meter {
    used: usize,
    limit: usize,
}

impl Meter {
    fn new(limit: usize) -> Self {
        Self { used: 0, limit }
    }

    fn charge(&mut self, work: usize) -> Bound<()> {
        if work > self.limit - self.used {
            return Err("nfa_work_limit");
        }
        self.used += work;
        Ok(())
    }
}

type Pair = (StateSet, StateSet);

struct Visit {
    pair: Pair,
    parent: Option<(usize, char)>,
    depth: usize,
}

fn traverse(
    (left, right): (&Nfa, &Nfa),
    alphabet: &[char],
    limits: Limits,
    query: Query,
    stats: &mut Stats,
    meter: &mut Meter,
) -> Bound<Option<(Vec<char>, bool, bool)>> {
    if limits.state_pairs == 0 {
        return Err("state_pair_limit");
    }
    let start = (
        left.closure([left.start], meter)?,
        right.closure([right.start], meter)?,
    );
    let mut seen = BTreeMap::from([(start.clone(), 0)]);
    let mut visits = vec![Visit {
        pair: start,
        parent: None,
        depth: 0,
    }];
    let mut cursor = 0;
    let mut exceeded_depth = false;
    while cursor < visits.len() {
        let visit = &visits[cursor];
        let accepts_left = visit.pair.0.contains(left.accept);
        let accepts_right = visit.pair.1.contains(right.accept);
        stats.examined_pairs += 1;
        if query.contradicted(accepts_left, accepts_right) {
            let mut witness = Vec::with_capacity(visit.depth);
            let mut path = cursor;
            while let Some((predecessor, scalar)) = visits[path].parent {
                witness.push(scalar);
                path = predecessor;
            }
            witness.reverse();
            return Ok(Some((witness, accepts_left, accepts_right)));
        }
        for &scalar in alphabet {
            let visit = &visits[cursor];
            let successor = (
                left.step(&visit.pair.0, scalar, meter)?,
                right.step(&visit.pair.1, scalar, meter)?,
            );
            stats.examined_transitions += 1;
            if seen.contains_key(&successor) {
                continue;
            }
            if visit.depth == limits.witness_scalars {
                exceeded_depth = true;
                continue;
            }
            if visits.len() == limits.state_pairs {
                return Err("state_pair_limit");
            }
            seen.insert(successor.clone(), visits.len());
            visits.push(Visit {
                pair: successor,
                parent: Some((cursor, scalar)),
                depth: visit.depth + 1,
            });
        }
        cursor += 1;
    }
    if exceeded_depth {
        Err("witness_length_limit")
    } else {
        Ok(None)
    }
}
