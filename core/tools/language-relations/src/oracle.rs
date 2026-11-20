//! Independent finite-word denotation over the original canonical IR.
//!
//! Word positions and split points are used directly without a graph or
//! representative alphabet. Only the checked input fragment reaches replay.

use std::collections::{BTreeSet, HashMap, VecDeque};

use strling_kernel::semantic::{CharacterSetMember, Node, RepetitionMaximum, RepetitionMode};
use strling_kernel::source::NodeId;

#[derive(Debug)]
pub enum ReplayError {
    WorkLimit,
    Projection,
}

pub fn replay(root: &Node, word: &[char], work_limit: usize) -> Result<bool, ReplayError> {
    let mut denotation = Denotation {
        word,
        remaining: work_limit,
        memo: HashMap::new(),
    };
    Ok(denotation.ends(root, 0)?.binary_search(&word.len()).is_ok())
}

struct Denotation<'a, 'w> {
    word: &'w [char],
    remaining: usize,
    memo: HashMap<(&'a NodeId, usize), Vec<usize>>,
}

impl<'a> Denotation<'a, '_> {
    fn charge(&mut self, work: usize) -> Result<(), ReplayError> {
        self.remaining = self
            .remaining
            .checked_sub(work)
            .ok_or(ReplayError::WorkLimit)?;
        Ok(())
    }

    fn ends(&mut self, node: &'a Node, at: usize) -> Result<Vec<usize>, ReplayError> {
        self.charge(1)?;
        let key = (node.node_id(), at);
        if let Some(reused) = self.memo.get(&key).cloned() {
            self.charge(reused.len())?;
            return Ok(reused);
        }
        let result = match node {
            Node::Empty { .. } => vec![at],
            Node::Literal { text, .. } => {
                let count = text.chars().count();
                self.charge(count)?;
                match self.word.get(at..at + count) {
                    Some(part) if part.iter().copied().eq(text.chars()) => vec![at + count],
                    _ => vec![],
                }
            }
            Node::CharacterSet {
                negated: false,
                members,
                ..
            } => {
                if let Some(&scalar) = self.word.get(at) {
                    let mut found = false;
                    for member in members {
                        self.charge(1)?;
                        found |= match member {
                            CharacterSetMember::Literal { value } => value.get() == scalar,
                            CharacterSetMember::Range { start, end } => {
                                start.get() <= scalar && scalar <= end.get()
                            }
                            _ => return Err(ReplayError::Projection),
                        };
                    }
                    if found {
                        vec![at + 1]
                    } else {
                        vec![]
                    }
                } else {
                    vec![]
                }
            }
            Node::Sequence { items, .. } => {
                let mut positions = vec![at];
                for part in items {
                    positions = self.compose(part, &positions)?;
                    if positions.is_empty() {
                        break;
                    }
                }
                positions
            }
            Node::Alternation { branches, .. } => {
                let mut points = BTreeSet::new();
                for branch in branches {
                    points.extend(self.ends(branch, at)?);
                }
                points.into_iter().collect()
            }
            Node::Repeat {
                body,
                min,
                max,
                mode: RepetitionMode::Greedy | RepetitionMode::Lazy,
                ..
            } => self.repeat(body, at, *min, *max)?,
            _ => return Err(ReplayError::Projection),
        };
        self.charge(result.len())?;
        self.memo.insert(key, result.clone());
        Ok(result)
    }

    fn compose(&mut self, child: &'a Node, positions: &[usize]) -> Result<Vec<usize>, ReplayError> {
        let mut next = BTreeSet::new();
        for &start in positions {
            next.extend(self.ends(child, start)?);
        }
        Ok(next.into_iter().collect())
    }

    fn repeat(
        &mut self,
        body: &'a Node,
        at: usize,
        min: u64,
        max: RepetitionMaximum,
    ) -> Result<Vec<usize>, ReplayError> {
        let mut positions = vec![at];
        for _ in 0..min {
            self.charge(1)?;
            positions = self.compose(body, &positions)?;
            if positions.is_empty() {
                return Ok(vec![]);
            }
        }
        let mut ends: BTreeSet<_> = positions.iter().copied().collect();
        match max {
            RepetitionMaximum::Bounded(max) => {
                for _ in min..max {
                    self.charge(1)?;
                    positions = self.compose(body, &positions)?;
                    if positions.is_empty() {
                        break;
                    }
                    ends.extend(positions.iter().copied());
                }
            }
            RepetitionMaximum::Unbounded => {
                let mut pending = VecDeque::from(positions);
                while let Some(position) = pending.pop_front() {
                    for advance in self.ends(body, position)? {
                        if ends.insert(advance) {
                            pending.push_back(advance);
                        }
                    }
                }
            }
        }
        Ok(ends.into_iter().collect())
    }
}
