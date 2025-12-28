//! Unit Tests for STRling Rust Binding
//!
//! This module provides comprehensive unit tests for all core components:
//! - Parser tests
//! - Compiler tests  
//! - Emitter tests
//! - Interaction tests (Parser→Compiler, Compiler→Emitter)
//! - Semantic edge case tests

use strling::core::parser::Parser;
use strling::core::compiler::Compiler;
use strling::core::nodes::*;
use strling::core::ir::*;
use strling::core::errors::STRlingParseError;
use strling::emitters::pcre2::Pcre2Emitter;

// ============================================================================
// Parser Unit Tests
// ============================================================================

#[cfg(test)]
mod parser_tests {
    use super::*;

    #[test]
    fn test_parse_simple_literal() {
        let mut parser = Parser::new("hello".to_string());
        let (ast, _flags) = parser.parse().unwrap();
        
        match ast {
            Node::Literal(lit) => assert_eq!(lit.value, "hello"),
            _ => panic!("Expected Literal node"),
        }
    }

    #[test]
    fn test_parse_digit_shorthand() {
        let mut parser = Parser::new("\\d".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Shorthand(sh) => assert_eq!(sh.kind, "Digit"),
            _ => panic!("Expected Shorthand node"),
        }
    }

    #[test]
    fn test_parse_word_shorthand() {
        let mut parser = Parser::new("\\w".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Shorthand(sh) => assert_eq!(sh.kind, "Word"),
            _ => panic!("Expected Shorthand node"),
        }
    }

    #[test]
    fn test_parse_whitespace_shorthand() {
        let mut parser = Parser::new("\\s".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Shorthand(sh) => assert_eq!(sh.kind, "Space"),
            _ => panic!("Expected Shorthand node"),
        }
    }

    #[test]
    fn test_parse_character_class() {
        let mut parser = Parser::new("[abc]".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::CharacterClass(cc) => {
                assert!(!cc.negated);
            }
            _ => panic!("Expected CharacterClass node"),
        }
    }

    #[test]
    fn test_parse_negated_character_class() {
        let mut parser = Parser::new("[^abc]".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::CharacterClass(cc) => {
                assert!(cc.negated);
            }
            _ => panic!("Expected CharacterClass node"),
        }
    }

    #[test]
    fn test_parse_quantifier_plus() {
        let mut parser = Parser::new("a+".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Quantifier(q) => {
                assert_eq!(q.min, 1);
                assert!(!q.lazy);
            }
            _ => panic!("Expected Quantifier node"),
        }
    }

    #[test]
    fn test_parse_quantifier_star() {
        let mut parser = Parser::new("a*".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Quantifier(q) => {
                assert_eq!(q.min, 0);
            }
            _ => panic!("Expected Quantifier node"),
        }
    }

    #[test]
    fn test_parse_quantifier_optional() {
        let mut parser = Parser::new("a?".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Quantifier(q) => {
                assert_eq!(q.min, 0);
                match q.max {
                    MaxBound::Finite(n) => assert_eq!(n, 1),
                    _ => panic!("Expected Finite(1)"),
                }
            }
            _ => panic!("Expected Quantifier node"),
        }
    }

    #[test]
    fn test_parse_lazy_quantifier() {
        let mut parser = Parser::new("a+?".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Quantifier(q) => {
                assert!(q.lazy);
            }
            _ => panic!("Expected Quantifier node"),
        }
    }

    #[test]
    fn test_parse_capturing_group() {
        let mut parser = Parser::new("(abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Group(g) => {
                assert!(g.capturing);
                assert!(g.name.is_none());
            }
            _ => panic!("Expected Group node"),
        }
    }

    #[test]
    fn test_parse_non_capturing_group() {
        let mut parser = Parser::new("(?:abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Group(g) => {
                assert!(!g.capturing);
            }
            _ => panic!("Expected Group node"),
        }
    }

    #[test]
    fn test_parse_named_group() {
        let mut parser = Parser::new("(?<name>abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Group(g) => {
                assert!(g.capturing);
                assert_eq!(g.name, Some("name".to_string()));
            }
            _ => panic!("Expected Group node"),
        }
    }

    #[test]
    fn test_parse_alternation() {
        let mut parser = Parser::new("a|b".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Alternation(alt) => {
                assert_eq!(alt.branches.len(), 2);
            }
            _ => panic!("Expected Alternation node"),
        }
    }

    #[test]
    fn test_parse_positive_lookahead() {
        let mut parser = Parser::new("(?=abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Lookaround(la) => {
                assert!(la.positive);
                assert!(la.ahead);
            }
            _ => panic!("Expected Lookaround node"),
        }
    }

    #[test]
    fn test_parse_negative_lookahead() {
        let mut parser = Parser::new("(?!abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Lookaround(la) => {
                assert!(!la.positive);
                assert!(la.ahead);
            }
            _ => panic!("Expected Lookaround node"),
        }
    }

    #[test]
    fn test_parse_positive_lookbehind() {
        let mut parser = Parser::new("(?<=abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Lookaround(la) => {
                assert!(la.positive);
                assert!(!la.ahead);
            }
            _ => panic!("Expected Lookaround node"),
        }
    }

    #[test]
    fn test_parse_negative_lookbehind() {
        let mut parser = Parser::new("(?<!abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Lookaround(la) => {
                assert!(!la.positive);
                assert!(!la.ahead);
            }
            _ => panic!("Expected Lookaround node"),
        }
    }

    #[test]
    fn test_parse_dot() {
        let mut parser = Parser::new(".".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Dot(_) => {}
            _ => panic!("Expected Dot node"),
        }
    }

    #[test]
    fn test_parse_anchor_start() {
        let mut parser = Parser::new("^".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Anchor(a) => assert_eq!(a.at, "Start"),
            _ => panic!("Expected Anchor node"),
        }
    }

    #[test]
    fn test_parse_anchor_end() {
        let mut parser = Parser::new("$".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Anchor(a) => assert_eq!(a.at, "End"),
            _ => panic!("Expected Anchor node"),
        }
    }

    #[test]
    fn test_parse_word_boundary() {
        let mut parser = Parser::new("\\b".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        match ast {
            Node::Anchor(a) => assert_eq!(a.at, "WordBoundary"),
            _ => panic!("Expected Anchor node"),
        }
    }

    #[test]
    fn test_parse_flags() {
        let mut parser = Parser::new("%flags i,m,s\nhello".to_string());
        let (_, flags) = parser.parse().unwrap();
        
        assert!(flags.ignore_case);
        assert!(flags.multiline);
        assert!(flags.dot_all);
    }

    #[test]
    fn test_parse_unicode_property() {
        let mut parser = Parser::new("\\p{L}".to_string());
        let result = parser.parse();
        
        assert!(result.is_ok());
    }

    #[test]
    fn test_parse_backreference() {
        let mut parser = Parser::new("(a)\\1".to_string());
        let result = parser.parse();
        
        assert!(result.is_ok());
    }

    #[test]
    fn test_parse_named_backreference() {
        let mut parser = Parser::new("(?<name>a)\\k<name>".to_string());
        let result = parser.parse();
        
        assert!(result.is_ok());
    }
}

// ============================================================================
// Compiler Unit Tests
// ============================================================================

#[cfg(test)]
mod compiler_tests {
    use super::*;

    #[test]
    fn test_compile_literal() {
        let lit = Node::Literal(Literal { value: "test".to_string() });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&lit);
        
        match ir {
            IROp::Lit(l) => assert_eq!(l.value, "test"),
            _ => panic!("Expected IRLit"),
        }
    }

    #[test]
    fn test_compile_dot() {
        let dot = Node::Dot(Dot {});
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&dot);
        
        match ir {
            IROp::Dot(_) => {}
            _ => panic!("Expected IRDot"),
        }
    }

    #[test]
    fn test_compile_anchor() {
        let anchor = Node::Anchor(Anchor { at: "Start".to_string() });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&anchor);
        
        match ir {
            IROp::Anchor(a) => assert_eq!(a.at, "Start"),
            _ => panic!("Expected IRAnchor"),
        }
    }

    #[test]
    fn test_compile_sequence() {
        let seq = Node::Sequence(Sequence {
            parts: vec![
                Node::Literal(Literal { value: "a".to_string() }),
                Node::Literal(Literal { value: "b".to_string() }),
            ],
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&seq);
        
        match ir {
            IROp::Seq(s) => assert!(!s.parts.is_empty()),
            IROp::Lit(_) => {} // May be coalesced
            _ => panic!("Expected IRSeq or IRLit"),
        }
    }

    #[test]
    fn test_compile_alternation() {
        let alt = Node::Alternation(Alternation {
            branches: vec![
                Node::Literal(Literal { value: "a".to_string() }),
                Node::Literal(Literal { value: "b".to_string() }),
            ],
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&alt);
        
        match ir {
            IROp::Alt(a) => assert_eq!(a.branches.len(), 2),
            _ => panic!("Expected IRAlt"),
        }
    }

    #[test]
    fn test_compile_quantifier_plus() {
        let quant = Node::Quantifier(Quantifier {
            target: QuantifierTarget {
                child: Box::new(Node::Literal(Literal { value: "a".to_string() })),
            },
            min: 1,
            max: MaxBound::Infinite("Inf".to_string()),
            lazy: false,
            possessive: false,
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&quant);
        
        match ir {
            IROp::Quant(q) => {
                assert_eq!(q.min, 1);
                assert_eq!(q.mode, "Greedy");
            }
            _ => panic!("Expected IRQuant"),
        }
    }

    #[test]
    fn test_compile_lazy_quantifier() {
        let quant = Node::Quantifier(Quantifier {
            target: QuantifierTarget {
                child: Box::new(Node::Literal(Literal { value: "a".to_string() })),
            },
            min: 0,
            max: MaxBound::Infinite("Inf".to_string()),
            lazy: true,
            possessive: false,
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&quant);
        
        match ir {
            IROp::Quant(q) => {
                assert_eq!(q.mode, "Lazy");
            }
            _ => panic!("Expected IRQuant"),
        }
    }

    #[test]
    fn test_compile_character_class() {
        let cc = Node::CharacterClass(CharacterClass {
            negated: false,
            items: vec![
                CharClassItem::Literal(Literal { value: "a".to_string() }),
            ],
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&cc);
        
        match ir {
            IROp::CharClass(_) => {}
            _ => panic!("Expected IRCharClass"),
        }
    }

    #[test]
    fn test_compile_group() {
        let group = Node::Group(Group {
            capturing: true,
            name: None,
            child: Box::new(Node::Literal(Literal { value: "abc".to_string() })),
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&group);
        
        match ir {
            IROp::Group(g) => assert!(g.capturing),
            _ => panic!("Expected IRGroup"),
        }
    }

    #[test]
    fn test_compile_named_group() {
        let group = Node::Group(Group {
            capturing: true,
            name: Some("name".to_string()),
            child: Box::new(Node::Literal(Literal { value: "abc".to_string() })),
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&group);
        
        match ir {
            IROp::Group(g) => {
                assert!(g.capturing);
                assert_eq!(g.name, Some("name".to_string()));
            }
            _ => panic!("Expected IRGroup"),
        }
    }

    #[test]
    fn test_compile_lookahead() {
        let la = Node::Lookaround(Lookaround {
            positive: true,
            ahead: true,
            child: Box::new(Node::Literal(Literal { value: "abc".to_string() })),
        });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&la);
        
        match ir {
            IROp::Look(l) => {
                assert!(l.positive);
                assert!(l.ahead);
            }
            _ => panic!("Expected IRLook"),
        }
    }

    #[test]
    fn test_compile_shorthand() {
        let sh = Node::Shorthand(Shorthand { kind: "Digit".to_string() });
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&sh);
        
        match ir {
            IROp::Shorthand(s) => assert_eq!(s.kind, "Digit"),
            _ => panic!("Expected IRShorthand"),
        }
    }

    #[test]
    fn test_compile_with_metadata() {
        let mut parser = Parser::new("(\\d+)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        let mut compiler = Compiler::new();
        let result = compiler.compile_with_metadata(&ast);
        
        assert!(result.metadata.features_used.len() > 0);
    }
}

// ============================================================================
// Emitter Unit Tests
// ============================================================================

#[cfg(test)]
mod emitter_tests {
    use super::*;

    fn emit_ir(ir: IROp) -> String {
        let flags = Flags::default();
        let emitter = Pcre2Emitter::new();
        emitter.emit(&ir, &flags)
    }

    #[test]
    fn test_emit_literal() {
        let ir = IROp::Lit(IRLit { value: "hello".to_string() });
        assert_eq!(emit_ir(ir), "hello");
    }

    #[test]
    fn test_emit_dot() {
        let ir = IROp::Dot(IRDot {});
        assert_eq!(emit_ir(ir), ".");
    }

    #[test]
    fn test_emit_anchor_start() {
        let ir = IROp::Anchor(IRAnchor { at: "Start".to_string() });
        assert_eq!(emit_ir(ir), "^");
    }

    #[test]
    fn test_emit_anchor_end() {
        let ir = IROp::Anchor(IRAnchor { at: "End".to_string() });
        assert_eq!(emit_ir(ir), "$");
    }

    #[test]
    fn test_emit_word_boundary() {
        let ir = IROp::Anchor(IRAnchor { at: "WordBoundary".to_string() });
        assert_eq!(emit_ir(ir), "\\b");
    }

    #[test]
    fn test_emit_shorthand_digit() {
        let ir = IROp::Shorthand(IRShorthand { kind: "Digit".to_string() });
        assert_eq!(emit_ir(ir), "\\d");
    }

    #[test]
    fn test_emit_shorthand_word() {
        let ir = IROp::Shorthand(IRShorthand { kind: "Word".to_string() });
        assert_eq!(emit_ir(ir), "\\w");
    }

    #[test]
    fn test_emit_shorthand_space() {
        let ir = IROp::Shorthand(IRShorthand { kind: "Space".to_string() });
        assert_eq!(emit_ir(ir), "\\s");
    }

    #[test]
    fn test_emit_quantifier_plus() {
        let ir = IROp::Quant(IRQuant {
            child: Box::new(IROp::Lit(IRLit { value: "a".to_string() })),
            min: 1,
            max: IRMaxBound::Infinite("Inf".to_string()),
            mode: "Greedy".to_string(),
        });
        assert_eq!(emit_ir(ir), "a+");
    }

    #[test]
    fn test_emit_quantifier_star() {
        let ir = IROp::Quant(IRQuant {
            child: Box::new(IROp::Lit(IRLit { value: "a".to_string() })),
            min: 0,
            max: IRMaxBound::Infinite("Inf".to_string()),
            mode: "Greedy".to_string(),
        });
        assert_eq!(emit_ir(ir), "a*");
    }

    #[test]
    fn test_emit_quantifier_optional() {
        let ir = IROp::Quant(IRQuant {
            child: Box::new(IROp::Lit(IRLit { value: "a".to_string() })),
            min: 0,
            max: IRMaxBound::Finite(1),
            mode: "Greedy".to_string(),
        });
        assert_eq!(emit_ir(ir), "a?");
    }

    #[test]
    fn test_emit_quantifier_lazy() {
        let ir = IROp::Quant(IRQuant {
            child: Box::new(IROp::Lit(IRLit { value: "a".to_string() })),
            min: 1,
            max: IRMaxBound::Infinite("Inf".to_string()),
            mode: "Lazy".to_string(),
        });
        assert_eq!(emit_ir(ir), "a+?");
    }

    #[test]
    fn test_emit_capturing_group() {
        let ir = IROp::Group(IRGroup {
            capturing: true,
            name: None,
            child: Box::new(IROp::Lit(IRLit { value: "abc".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(abc)");
    }

    #[test]
    fn test_emit_non_capturing_group() {
        let ir = IROp::Group(IRGroup {
            capturing: false,
            name: None,
            child: Box::new(IROp::Lit(IRLit { value: "abc".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?:abc)");
    }

    #[test]
    fn test_emit_named_group() {
        let ir = IROp::Group(IRGroup {
            capturing: true,
            name: Some("name".to_string()),
            child: Box::new(IROp::Lit(IRLit { value: "abc".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?<name>abc)");
    }

    #[test]
    fn test_emit_alternation() {
        let ir = IROp::Alt(IRAlt {
            branches: vec![
                IROp::Lit(IRLit { value: "cat".to_string() }),
                IROp::Lit(IRLit { value: "dog".to_string() }),
            ],
        });
        assert_eq!(emit_ir(ir), "cat|dog");
    }

    #[test]
    fn test_emit_positive_lookahead() {
        let ir = IROp::Look(IRLook {
            positive: true,
            ahead: true,
            child: Box::new(IROp::Lit(IRLit { value: "bar".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?=bar)");
    }

    #[test]
    fn test_emit_negative_lookahead() {
        let ir = IROp::Look(IRLook {
            positive: false,
            ahead: true,
            child: Box::new(IROp::Lit(IRLit { value: "bar".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?!bar)");
    }

    #[test]
    fn test_emit_positive_lookbehind() {
        let ir = IROp::Look(IRLook {
            positive: true,
            ahead: false,
            child: Box::new(IROp::Lit(IRLit { value: "foo".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?<=foo)");
    }

    #[test]
    fn test_emit_negative_lookbehind() {
        let ir = IROp::Look(IRLook {
            positive: false,
            ahead: false,
            child: Box::new(IROp::Lit(IRLit { value: "foo".to_string() })),
        });
        assert_eq!(emit_ir(ir), "(?<!foo)");
    }

    #[test]
    fn test_emit_escapes_special_chars() {
        let ir = IROp::Lit(IRLit { value: ".+*?".to_string() });
        let result = emit_ir(ir);
        assert!(result.contains("\\"));
    }

    #[test]
    fn test_emit_character_class() {
        let ir = IROp::CharClass(IRCharClass {
            negated: false,
            items: vec![
                IRCharClassItem::Lit(IRLit { value: "a".to_string() }),
                IRCharClassItem::Lit(IRLit { value: "b".to_string() }),
                IRCharClassItem::Lit(IRLit { value: "c".to_string() }),
            ],
        });
        assert_eq!(emit_ir(ir), "[abc]");
    }

    #[test]
    fn test_emit_negated_character_class() {
        let ir = IROp::CharClass(IRCharClass {
            negated: true,
            items: vec![
                IRCharClassItem::Lit(IRLit { value: "a".to_string() }),
            ],
        });
        assert_eq!(emit_ir(ir), "[^a]");
    }
}

// ============================================================================
// Interaction Tests (Parser → Compiler → Emitter)
// ============================================================================

#[cfg(test)]
mod interaction_tests {
    use super::*;

    fn compile_dsl(dsl: &str) -> String {
        let mut parser = Parser::new(dsl.to_string());
        let (ast, flags) = parser.parse().unwrap();
        
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&ast);
        
        let emitter = Pcre2Emitter::new();
        emitter.emit(&ir, &flags)
    }

    #[test]
    fn test_parser_to_compiler_literal() {
        let mut parser = Parser::new("hello".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&ast);
        
        match ir {
            IROp::Lit(_) => {}
            _ => panic!("Expected IR Lit"),
        }
    }

    #[test]
    fn test_parser_to_compiler_quantifier() {
        let mut parser = Parser::new("a+".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&ast);
        
        match ir {
            IROp::Quant(_) => {}
            _ => panic!("Expected IR Quant"),
        }
    }

    #[test]
    fn test_parser_to_compiler_group() {
        let mut parser = Parser::new("(abc)".to_string());
        let (ast, _) = parser.parse().unwrap();
        
        let mut compiler = Compiler::new();
        let ir = compiler.compile(&ast);
        
        match ir {
            IROp::Group(_) => {}
            _ => panic!("Expected IR Group"),
        }
    }

    #[test]
    fn test_compiler_to_emitter_literal() {
        assert_eq!(compile_dsl("hello"), "hello");
    }

    #[test]
    fn test_compiler_to_emitter_digit() {
        assert_eq!(compile_dsl("\\d+"), "\\d+");
    }

    #[test]
    fn test_compiler_to_emitter_character_class() {
        assert_eq!(compile_dsl("[abc]"), "[abc]");
    }

    #[test]
    fn test_compiler_to_emitter_anchors() {
        assert_eq!(compile_dsl("^abc$"), "^abc$");
    }

    #[test]
    fn test_compiler_to_emitter_alternation() {
        assert_eq!(compile_dsl("cat|dog"), "cat|dog");
    }

    #[test]
    fn test_compiler_to_emitter_lookahead() {
        assert_eq!(compile_dsl("foo(?=bar)"), "foo(?=bar)");
    }

    #[test]
    fn test_compiler_to_emitter_lookbehind() {
        assert_eq!(compile_dsl("(?<=foo)bar"), "(?<=foo)bar");
    }

    #[test]
    fn test_full_pipeline_phone() {
        let result = compile_dsl("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})");
        assert_eq!(result, "(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})");
    }

    #[test]
    fn test_full_pipeline_ipv4() {
        let result = compile_dsl("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})");
        assert_eq!(result, "(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})");
    }
}

// ============================================================================
// Semantic Edge Case Tests
// ============================================================================

#[cfg(test)]
mod semantic_tests {
    use super::*;

    #[test]
    fn test_semantic_duplicate_capture_group() {
        let mut parser = Parser::new("(?<name>a)(?<name>b)".to_string());
        let result = parser.parse();
        
        // Should fail with duplicate name error
        assert!(result.is_err(), "Parser should reject duplicate named groups");
    }

    #[test]
    fn test_semantic_invalid_range() {
        let mut parser = Parser::new("[z-a]".to_string());
        let result = parser.parse();
        
        // Should fail with invalid range error
        assert!(result.is_err(), "Parser should reject invalid range [z-a]");
    }

    #[test]
    fn test_semantic_valid_range() {
        let mut parser = Parser::new("[a-z]".to_string());
        let result = parser.parse();
        
        // Should succeed
        assert!(result.is_ok(), "Parser should accept valid range [a-z]");
    }

    #[test]
    fn test_semantic_unbalanced_parens() {
        let mut parser = Parser::new("(abc".to_string());
        let result = parser.parse();
        
        // Should fail
        assert!(result.is_err(), "Parser should reject unbalanced parens");
    }

    #[test]
    fn test_semantic_unbalanced_bracket() {
        let mut parser = Parser::new("[abc".to_string());
        let result = parser.parse();
        
        // Should fail
        assert!(result.is_err(), "Parser should reject unbalanced bracket");
    }

    #[test]
    fn test_semantic_invalid_quantifier() {
        let mut parser = Parser::new("a{5,3}".to_string());
        let result = parser.parse();
        
        // Should fail (min > max)
        assert!(result.is_err(), "Parser should reject invalid quantifier {5,3}");
    }
}
