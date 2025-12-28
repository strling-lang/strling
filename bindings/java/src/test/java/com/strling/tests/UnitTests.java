package com.strling.tests;

import static org.junit.jupiter.api.Assertions.*;

import com.strling.core.*;
import com.strling.emitters.Pcre2Emitter;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;

/**
 * Unit Tests for STRling Java Binding
 *
 * Comprehensive unit tests for all core components:
 * - Parser tests
 * - Compiler tests
 * - Emitter tests
 */
public class UnitTests {

    // ============================================================================
    // Parser Unit Tests
    // ============================================================================

    @Nested
    @DisplayName("Parser Tests")
    class ParserTests {

        @Test
        @DisplayName("Parse simple literal")
        void testParseSimpleLiteral() throws Exception {
            Parser parser = new Parser("hello");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Literal);
            assertEquals("hello", ((Nodes.Literal) ast).getValue());
        }

        @Test
        @DisplayName("Parse digit shorthand")
        void testParseDigitShorthand() throws Exception {
            Parser parser = new Parser("\\d");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Shorthand);
            assertEquals("Digit", ((Nodes.Shorthand) ast).getKind());
        }

        @Test
        @DisplayName("Parse word shorthand")
        void testParseWordShorthand() throws Exception {
            Parser parser = new Parser("\\w");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Shorthand);
            assertEquals("Word", ((Nodes.Shorthand) ast).getKind());
        }

        @Test
        @DisplayName("Parse whitespace shorthand")
        void testParseWhitespaceShorthand() throws Exception {
            Parser parser = new Parser("\\s");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Shorthand);
            assertEquals("Space", ((Nodes.Shorthand) ast).getKind());
        }

        @Test
        @DisplayName("Parse character class")
        void testParseCharacterClass() throws Exception {
            Parser parser = new Parser("[abc]");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.CharacterClass);
            assertFalse(((Nodes.CharacterClass) ast).isNegated());
        }

        @Test
        @DisplayName("Parse negated character class")
        void testParseNegatedCharacterClass() throws Exception {
            Parser parser = new Parser("[^abc]");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.CharacterClass);
            assertTrue(((Nodes.CharacterClass) ast).isNegated());
        }

        @Test
        @DisplayName("Parse quantifier plus")
        void testParseQuantifierPlus() throws Exception {
            Parser parser = new Parser("a+");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Quantifier);
            Nodes.Quantifier q = (Nodes.Quantifier) ast;
            assertEquals(1, q.getMin());
            assertFalse(q.isLazy());
        }

        @Test
        @DisplayName("Parse quantifier star")
        void testParseQuantifierStar() throws Exception {
            Parser parser = new Parser("a*");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Quantifier);
            Nodes.Quantifier q = (Nodes.Quantifier) ast;
            assertEquals(0, q.getMin());
        }

        @Test
        @DisplayName("Parse quantifier optional")
        void testParseQuantifierOptional() throws Exception {
            Parser parser = new Parser("a?");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Quantifier);
            Nodes.Quantifier q = (Nodes.Quantifier) ast;
            assertEquals(0, q.getMin());
            assertEquals(Integer.valueOf(1), q.getMax());
        }

        @Test
        @DisplayName("Parse lazy quantifier")
        void testParseLazyQuantifier() throws Exception {
            Parser parser = new Parser("a+?");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Quantifier);
            assertTrue(((Nodes.Quantifier) ast).isLazy());
        }

        @Test
        @DisplayName("Parse capturing group")
        void testParseCapturingGroup() throws Exception {
            Parser parser = new Parser("(abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Group);
            Nodes.Group g = (Nodes.Group) ast;
            assertTrue(g.isCapturing());
            assertNull(g.getName());
        }

        @Test
        @DisplayName("Parse non-capturing group")
        void testParseNonCapturingGroup() throws Exception {
            Parser parser = new Parser("(?:abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Group);
            assertFalse(((Nodes.Group) ast).isCapturing());
        }

        @Test
        @DisplayName("Parse named group")
        void testParseNamedGroup() throws Exception {
            Parser parser = new Parser("(?<name>abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Group);
            Nodes.Group g = (Nodes.Group) ast;
            assertTrue(g.isCapturing());
            assertEquals("name", g.getName());
        }

        @Test
        @DisplayName("Parse alternation")
        void testParseAlternation() throws Exception {
            Parser parser = new Parser("a|b");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Alternation);
            assertEquals(2, ((Nodes.Alternation) ast).getBranches().size());
        }

        @Test
        @DisplayName("Parse positive lookahead")
        void testParsePositiveLookahead() throws Exception {
            Parser parser = new Parser("(?=abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Lookaround);
            Nodes.Lookaround la = (Nodes.Lookaround) ast;
            assertTrue(la.isPositive());
            assertTrue(la.isAhead());
        }

        @Test
        @DisplayName("Parse negative lookahead")
        void testParseNegativeLookahead() throws Exception {
            Parser parser = new Parser("(?!abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Lookaround);
            Nodes.Lookaround la = (Nodes.Lookaround) ast;
            assertFalse(la.isPositive());
            assertTrue(la.isAhead());
        }

        @Test
        @DisplayName("Parse positive lookbehind")
        void testParsePositiveLookbehind() throws Exception {
            Parser parser = new Parser("(?<=abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Lookaround);
            Nodes.Lookaround la = (Nodes.Lookaround) ast;
            assertTrue(la.isPositive());
            assertFalse(la.isAhead());
        }

        @Test
        @DisplayName("Parse negative lookbehind")
        void testParseNegativeLookbehind() throws Exception {
            Parser parser = new Parser("(?<!abc)");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Lookaround);
            Nodes.Lookaround la = (Nodes.Lookaround) ast;
            assertFalse(la.isPositive());
            assertFalse(la.isAhead());
        }

        @Test
        @DisplayName("Parse dot")
        void testParseDot() throws Exception {
            Parser parser = new Parser(".");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Dot);
        }

        @Test
        @DisplayName("Parse anchor start")
        void testParseAnchorStart() throws Exception {
            Parser parser = new Parser("^");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Anchor);
            assertEquals("Start", ((Nodes.Anchor) ast).getAt());
        }

        @Test
        @DisplayName("Parse anchor end")
        void testParseAnchorEnd() throws Exception {
            Parser parser = new Parser("$");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Anchor);
            assertEquals("End", ((Nodes.Anchor) ast).getAt());
        }

        @Test
        @DisplayName("Parse word boundary")
        void testParseWordBoundary() throws Exception {
            Parser parser = new Parser("\\b");
            Nodes.Node ast = parser.parse();
            
            assertTrue(ast instanceof Nodes.Anchor);
            assertEquals("WordBoundary", ((Nodes.Anchor) ast).getAt());
        }

        @Test
        @DisplayName("Parse Unicode property")
        void testParseUnicodeProperty() throws Exception {
            Parser parser = new Parser("\\p{L}");
            Nodes.Node ast = parser.parse();
            
            assertNotNull(ast);
        }

        @Test
        @DisplayName("Parse backreference")
        void testParseBackreference() throws Exception {
            Parser parser = new Parser("(a)\\1");
            Nodes.Node ast = parser.parse();
            
            assertNotNull(ast);
        }

        @Test
        @DisplayName("Parse named backreference")
        void testParseNamedBackreference() throws Exception {
            Parser parser = new Parser("(?<name>a)\\k<name>");
            Nodes.Node ast = parser.parse();
            
            assertNotNull(ast);
        }
    }

    // ============================================================================
    // Compiler Unit Tests
    // ============================================================================

    @Nested
    @DisplayName("Compiler Tests")
    class CompilerTests {

        @Test
        @DisplayName("Compile literal")
        void testCompileLiteral() throws Exception {
            Parser parser = new Parser("hello");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRLit);
            assertEquals("hello", ((IR.IRLit) ir).getValue());
        }

        @Test
        @DisplayName("Compile dot")
        void testCompileDot() throws Exception {
            Parser parser = new Parser(".");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRDot);
        }

        @Test
        @DisplayName("Compile anchor")
        void testCompileAnchor() throws Exception {
            Parser parser = new Parser("^");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRAnchor);
            assertEquals("Start", ((IR.IRAnchor) ir).getAt());
        }

        @Test
        @DisplayName("Compile alternation")
        void testCompileAlternation() throws Exception {
            Parser parser = new Parser("a|b");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRAlt);
            assertEquals(2, ((IR.IRAlt) ir).getBranches().size());
        }

        @Test
        @DisplayName("Compile quantifier plus")
        void testCompileQuantifierPlus() throws Exception {
            Parser parser = new Parser("a+");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRQuant);
            IR.IRQuant q = (IR.IRQuant) ir;
            assertEquals(1, q.getMin());
            assertEquals("Greedy", q.getMode());
        }

        @Test
        @DisplayName("Compile lazy quantifier")
        void testCompileLazyQuantifier() throws Exception {
            Parser parser = new Parser("a+?");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRQuant);
            assertEquals("Lazy", ((IR.IRQuant) ir).getMode());
        }

        @Test
        @DisplayName("Compile character class")
        void testCompileCharacterClass() throws Exception {
            Parser parser = new Parser("[abc]");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRCharClass);
        }

        @Test
        @DisplayName("Compile group")
        void testCompileGroup() throws Exception {
            Parser parser = new Parser("(abc)");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRGroup);
            assertTrue(((IR.IRGroup) ir).isCapturing());
        }

        @Test
        @DisplayName("Compile named group")
        void testCompileNamedGroup() throws Exception {
            Parser parser = new Parser("(?<name>abc)");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRGroup);
            IR.IRGroup g = (IR.IRGroup) ir;
            assertTrue(g.isCapturing());
            assertEquals("name", g.getName());
        }

        @Test
        @DisplayName("Compile lookahead")
        void testCompileLookahead() throws Exception {
            Parser parser = new Parser("(?=abc)");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRLook);
            IR.IRLook l = (IR.IRLook) ir;
            assertTrue(l.isPositive());
            assertTrue(l.isAhead());
        }

        @Test
        @DisplayName("Compile shorthand")
        void testCompileShorthand() throws Exception {
            Parser parser = new Parser("\\d");
            Nodes.Node ast = parser.parse();
            
            IR.IROp ir = Compiler.compile(ast);
            
            assertTrue(ir instanceof IR.IRShorthand);
            assertEquals("Digit", ((IR.IRShorthand) ir).getKind());
        }
    }

    // ============================================================================
    // Emitter Unit Tests
    // ============================================================================

    @Nested
    @DisplayName("Emitter Tests")
    class EmitterTests {

        private String emit(IR.IROp ir) {
            return Pcre2Emitter.emit(ir, new Nodes.Flags());
        }

        @Test
        @DisplayName("Emit literal")
        void testEmitLiteral() {
            IR.IRLit ir = new IR.IRLit("hello");
            assertEquals("hello", emit(ir));
        }

        @Test
        @DisplayName("Emit dot")
        void testEmitDot() {
            IR.IRDot ir = new IR.IRDot();
            assertEquals(".", emit(ir));
        }

        @Test
        @DisplayName("Emit anchor start")
        void testEmitAnchorStart() {
            IR.IRAnchor ir = new IR.IRAnchor("Start");
            assertEquals("^", emit(ir));
        }

        @Test
        @DisplayName("Emit anchor end")
        void testEmitAnchorEnd() {
            IR.IRAnchor ir = new IR.IRAnchor("End");
            assertEquals("$", emit(ir));
        }

        @Test
        @DisplayName("Emit word boundary")
        void testEmitWordBoundary() {
            IR.IRAnchor ir = new IR.IRAnchor("WordBoundary");
            assertEquals("\\b", emit(ir));
        }

        @Test
        @DisplayName("Emit shorthand digit")
        void testEmitShorthandDigit() {
            IR.IRShorthand ir = new IR.IRShorthand("Digit");
            assertEquals("\\d", emit(ir));
        }

        @Test
        @DisplayName("Emit shorthand word")
        void testEmitShorthandWord() {
            IR.IRShorthand ir = new IR.IRShorthand("Word");
            assertEquals("\\w", emit(ir));
        }

        @Test
        @DisplayName("Emit shorthand space")
        void testEmitShorthandSpace() {
            IR.IRShorthand ir = new IR.IRShorthand("Space");
            assertEquals("\\s", emit(ir));
        }

        @Test
        @DisplayName("Emit quantifier plus")
        void testEmitQuantifierPlus() {
            IR.IRQuant ir = new IR.IRQuant(new IR.IRLit("a"), 1, null, "Greedy");
            assertEquals("a+", emit(ir));
        }

        @Test
        @DisplayName("Emit quantifier star")
        void testEmitQuantifierStar() {
            IR.IRQuant ir = new IR.IRQuant(new IR.IRLit("a"), 0, null, "Greedy");
            assertEquals("a*", emit(ir));
        }

        @Test
        @DisplayName("Emit quantifier optional")
        void testEmitQuantifierOptional() {
            IR.IRQuant ir = new IR.IRQuant(new IR.IRLit("a"), 0, 1, "Greedy");
            assertEquals("a?", emit(ir));
        }

        @Test
        @DisplayName("Emit quantifier lazy")
        void testEmitQuantifierLazy() {
            IR.IRQuant ir = new IR.IRQuant(new IR.IRLit("a"), 1, null, "Lazy");
            assertEquals("a+?", emit(ir));
        }

        @Test
        @DisplayName("Emit capturing group")
        void testEmitCapturingGroup() {
            IR.IRGroup ir = new IR.IRGroup(true, null, new IR.IRLit("abc"));
            assertEquals("(abc)", emit(ir));
        }

        @Test
        @DisplayName("Emit non-capturing group")
        void testEmitNonCapturingGroup() {
            IR.IRGroup ir = new IR.IRGroup(false, null, new IR.IRLit("abc"));
            assertEquals("(?:abc)", emit(ir));
        }

        @Test
        @DisplayName("Emit named group")
        void testEmitNamedGroup() {
            IR.IRGroup ir = new IR.IRGroup(true, "name", new IR.IRLit("abc"));
            assertEquals("(?<name>abc)", emit(ir));
        }

        @Test
        @DisplayName("Emit alternation")
        void testEmitAlternation() {
            IR.IRAlt ir = new IR.IRAlt(java.util.Arrays.asList(
                new IR.IRLit("cat"),
                new IR.IRLit("dog")
            ));
            assertEquals("cat|dog", emit(ir));
        }

        @Test
        @DisplayName("Emit positive lookahead")
        void testEmitPositiveLookahead() {
            IR.IRLook ir = new IR.IRLook(true, true, new IR.IRLit("bar"));
            assertEquals("(?=bar)", emit(ir));
        }

        @Test
        @DisplayName("Emit negative lookahead")
        void testEmitNegativeLookahead() {
            IR.IRLook ir = new IR.IRLook(false, true, new IR.IRLit("bar"));
            assertEquals("(?!bar)", emit(ir));
        }

        @Test
        @DisplayName("Emit positive lookbehind")
        void testEmitPositiveLookbehind() {
            IR.IRLook ir = new IR.IRLook(true, false, new IR.IRLit("foo"));
            assertEquals("(?<=foo)", emit(ir));
        }

        @Test
        @DisplayName("Emit negative lookbehind")
        void testEmitNegativeLookbehind() {
            IR.IRLook ir = new IR.IRLook(false, false, new IR.IRLit("foo"));
            assertEquals("(?<!foo)", emit(ir));
        }
    }

    // ============================================================================
    // Semantic Edge Case Tests
    // ============================================================================

    @Nested
    @DisplayName("Semantic Edge Case Tests")
    class SemanticTests {

        @Test
        @DisplayName("Reject duplicate named groups")
        void testSemanticDuplicateCaptureGroup() {
            assertThrows(STRlingParseError.class, () -> {
                Parser parser = new Parser("(?<name>a)(?<name>b)");
                parser.parse();
            });
        }

        @Test
        @DisplayName("Reject invalid character range")
        void testSemanticInvalidRange() {
            assertThrows(STRlingParseError.class, () -> {
                Parser parser = new Parser("[z-a]");
                parser.parse();
            });
        }

        @Test
        @DisplayName("Accept valid character range")
        void testSemanticValidRange() throws Exception {
            Parser parser = new Parser("[a-z]");
            Nodes.Node ast = parser.parse();
            assertNotNull(ast);
        }

        @Test
        @DisplayName("Reject unbalanced parentheses")
        void testSemanticUnbalancedParens() {
            assertThrows(STRlingParseError.class, () -> {
                Parser parser = new Parser("(abc");
                parser.parse();
            });
        }

        @Test
        @DisplayName("Reject unbalanced brackets")
        void testSemanticUnbalancedBracket() {
            assertThrows(STRlingParseError.class, () -> {
                Parser parser = new Parser("[abc");
                parser.parse();
            });
        }

        @Test
        @DisplayName("Reject invalid quantifier range")
        void testSemanticInvalidQuantifier() {
            assertThrows(STRlingParseError.class, () -> {
                Parser parser = new Parser("a{5,3}");
                parser.parse();
            });
        }
    }
}
