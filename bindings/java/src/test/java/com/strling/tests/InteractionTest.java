package com.strling.tests;

import com.strling.core.Parser;
import com.strling.core.Compiler;
import com.strling.core.IR.IROp;
import com.strling.core.Nodes.Node;
import com.strling.core.Nodes.Flags;
import com.strling.core.STRlingParseError;
import com.strling.emitters.Pcre2Emitter;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Interaction Tests - Parser → Compiler → Emitter handoffs
 *
 * This test suite validates the handoff between pipeline stages:
 * - Parser → Compiler: Ensures AST is correctly consumed
 * - Compiler → Emitter: Ensures IR is correctly transformed to regex
 */
public class InteractionTest {
    
    private Compiler compiler;
    private Pcre2Emitter emitter;
    
    @BeforeEach
    void setUp() {
        compiler = new Compiler();
        emitter = new Pcre2Emitter();
    }
    
    // ========================================================================
    // Parser → Compiler Handoff Tests
    // ========================================================================
    
    @Test
    void testParserCompiler_SimpleLiteral() {
        Parser.ParseResult result = Parser.parse("hello");
        IROp ir = compiler.compile(result.node());
        
        assertNotNull(ir);
        assertEquals("Lit", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_Quantifier() {
        Parser.ParseResult result = Parser.parse("a+");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Quant", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_CharacterClass() {
        Parser.ParseResult result = Parser.parse("[abc]");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("CharClass", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_CapturingGroup() {
        Parser.ParseResult result = Parser.parse("(abc)");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Group", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_Alternation() {
        Parser.ParseResult result = Parser.parse("a|b");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Alt", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_NamedGroup() {
        Parser.ParseResult result = Parser.parse("(?<name>abc)");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Group", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_Lookahead() {
        Parser.ParseResult result = Parser.parse("(?=abc)");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Look", ir.getIrType());
    }
    
    @Test
    void testParserCompiler_Lookbehind() {
        Parser.ParseResult result = Parser.parse("(?<=abc)");
        IROp ir = compiler.compile(result.node());
        
        assertEquals("Look", ir.getIrType());
    }
    
    // ========================================================================
    // Compiler → Emitter Handoff Tests
    // ========================================================================
    
    @Test
    void testCompilerEmitter_SimpleLiteral() {
        String regex = compileToRegex("hello");
        assertEquals("hello", regex);
    }
    
    @Test
    void testCompilerEmitter_DigitShorthand() {
        String regex = compileToRegex("\\d+");
        assertEquals("\\d+", regex);
    }
    
    @Test
    void testCompilerEmitter_CharacterClass() {
        String regex = compileToRegex("[abc]");
        assertEquals("[abc]", regex);
    }
    
    @Test
    void testCompilerEmitter_CharacterClassRange() {
        String regex = compileToRegex("[a-z]");
        assertEquals("[a-z]", regex);
    }
    
    @Test
    void testCompilerEmitter_NegatedClass() {
        String regex = compileToRegex("[^abc]");
        assertEquals("[^abc]", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierPlus() {
        String regex = compileToRegex("a+");
        assertEquals("a+", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierStar() {
        String regex = compileToRegex("a*");
        assertEquals("a*", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierOptional() {
        String regex = compileToRegex("a?");
        assertEquals("a?", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierExact() {
        String regex = compileToRegex("a{3}");
        assertEquals("a{3}", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierRange() {
        String regex = compileToRegex("a{2,5}");
        assertEquals("a{2,5}", regex);
    }
    
    @Test
    void testCompilerEmitter_QuantifierLazy() {
        String regex = compileToRegex("a+?");
        assertEquals("a+?", regex);
    }
    
    @Test
    void testCompilerEmitter_CapturingGroup() {
        String regex = compileToRegex("(abc)");
        assertEquals("(abc)", regex);
    }
    
    @Test
    void testCompilerEmitter_NonCapturingGroup() {
        String regex = compileToRegex("(?:abc)");
        assertEquals("(?:abc)", regex);
    }
    
    @Test
    void testCompilerEmitter_NamedGroup() {
        String regex = compileToRegex("(?<name>abc)");
        assertEquals("(?<name>abc)", regex);
    }
    
    @Test
    void testCompilerEmitter_Alternation() {
        String regex = compileToRegex("cat|dog");
        assertEquals("cat|dog", regex);
    }
    
    @Test
    void testCompilerEmitter_Anchors() {
        String regex = compileToRegex("^abc$");
        assertEquals("^abc$", regex);
    }
    
    @Test
    void testCompilerEmitter_PositiveLookahead() {
        String regex = compileToRegex("foo(?=bar)");
        assertEquals("foo(?=bar)", regex);
    }
    
    @Test
    void testCompilerEmitter_NegativeLookahead() {
        String regex = compileToRegex("foo(?!bar)");
        assertEquals("foo(?!bar)", regex);
    }
    
    @Test
    void testCompilerEmitter_PositiveLookbehind() {
        String regex = compileToRegex("(?<=foo)bar");
        assertEquals("(?<=foo)bar", regex);
    }
    
    @Test
    void testCompilerEmitter_NegativeLookbehind() {
        String regex = compileToRegex("(?<!foo)bar");
        assertEquals("(?<!foo)bar", regex);
    }
    
    // ========================================================================
    // Semantic Edge Case Tests
    // ========================================================================
    
    @Test
    void test_semantic_duplicate_capture_group() {
        assertThrows(STRlingParseError.class, () -> {
            Parser.parse("(?<name>a)(?<name>b)");
        });
    }
    
    @Test
    void test_semantic_ranges() {
        // Invalid range [z-a] should produce an error
        assertThrows(STRlingParseError.class, () -> {
            Parser.parse("[z-a]");
        });
    }
    
    // ========================================================================
    // Full Pipeline Tests
    // ========================================================================
    
    @Test
    void testFullPipeline_PhoneNumber() {
        String regex = compileToRegex("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})");
        assertEquals("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})", regex);
    }
    
    @Test
    void testFullPipeline_IPv4() {
        String regex = compileToRegex("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})");
        assertEquals("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})", regex);
    }
    
    // ========================================================================
    // Helper Methods
    // ========================================================================
    
    private String compileToRegex(String dsl) {
        Parser.ParseResult result = Parser.parse(dsl);
        IROp ir = compiler.compile(result.node());
        return emitter.emit(ir, result.flags());
    }
}
