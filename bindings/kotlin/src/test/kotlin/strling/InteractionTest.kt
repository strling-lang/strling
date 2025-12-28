package strling

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.assertThrows
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import strling.core.Parser
import strling.core.Compiler
import strling.core.STRlingParseError
import strling.emitters.Pcre2Emitter

/**
 * Interaction Tests - Parser → Compiler → Emitter handoffs
 *
 * This test suite validates the handoff between pipeline stages:
 * - Parser → Compiler: Ensures AST is correctly consumed
 * - Compiler → Emitter: Ensures IR is correctly transformed to regex
 */
class InteractionTest {

    // ========================================================================
    // Parser → Compiler Handoff Tests
    // ========================================================================

    @Test
    fun `Parser to Compiler - SimpleLiteral`() {
        val (flags, ast) = Parser.parse("hello")
        val ir = Compiler.compile(ast)
        
        assertNotNull(ir)
        assertEquals("Lit", ir.irType)
    }

    @Test
    fun `Parser to Compiler - Quantifier`() {
        val (flags, ast) = Parser.parse("a+")
        val ir = Compiler.compile(ast)
        
        assertEquals("Quant", ir.irType)
    }

    @Test
    fun `Parser to Compiler - CharacterClass`() {
        val (flags, ast) = Parser.parse("[abc]")
        val ir = Compiler.compile(ast)
        
        assertEquals("CharClass", ir.irType)
    }

    @Test
    fun `Parser to Compiler - CapturingGroup`() {
        val (flags, ast) = Parser.parse("(abc)")
        val ir = Compiler.compile(ast)
        
        assertEquals("Group", ir.irType)
    }

    @Test
    fun `Parser to Compiler - Alternation`() {
        val (flags, ast) = Parser.parse("a|b")
        val ir = Compiler.compile(ast)
        
        assertEquals("Alt", ir.irType)
    }

    @Test
    fun `Parser to Compiler - NamedGroup`() {
        val (flags, ast) = Parser.parse("(?<name>abc)")
        val ir = Compiler.compile(ast)
        
        assertEquals("Group", ir.irType)
    }

    @Test
    fun `Parser to Compiler - Lookahead`() {
        val (flags, ast) = Parser.parse("(?=abc)")
        val ir = Compiler.compile(ast)
        
        assertEquals("Look", ir.irType)
    }

    @Test
    fun `Parser to Compiler - Lookbehind`() {
        val (flags, ast) = Parser.parse("(?<=abc)")
        val ir = Compiler.compile(ast)
        
        assertEquals("Look", ir.irType)
    }

    // ========================================================================
    // Compiler → Emitter Handoff Tests
    // ========================================================================

    @Test
    fun `Compiler to Emitter - SimpleLiteral`() {
        assertEquals("hello", compileToRegex("hello"))
    }

    @Test
    fun `Compiler to Emitter - DigitShorthand`() {
        assertEquals("\\d+", compileToRegex("\\d+"))
    }

    @Test
    fun `Compiler to Emitter - CharacterClass`() {
        assertEquals("[abc]", compileToRegex("[abc]"))
    }

    @Test
    fun `Compiler to Emitter - CharacterClassRange`() {
        assertEquals("[a-z]", compileToRegex("[a-z]"))
    }

    @Test
    fun `Compiler to Emitter - NegatedClass`() {
        assertEquals("[^abc]", compileToRegex("[^abc]"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierPlus`() {
        assertEquals("a+", compileToRegex("a+"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierStar`() {
        assertEquals("a*", compileToRegex("a*"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierOptional`() {
        assertEquals("a?", compileToRegex("a?"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierExact`() {
        assertEquals("a{3}", compileToRegex("a{3}"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierRange`() {
        assertEquals("a{2,5}", compileToRegex("a{2,5}"))
    }

    @Test
    fun `Compiler to Emitter - QuantifierLazy`() {
        assertEquals("a+?", compileToRegex("a+?"))
    }

    @Test
    fun `Compiler to Emitter - CapturingGroup`() {
        assertEquals("(abc)", compileToRegex("(abc)"))
    }

    @Test
    fun `Compiler to Emitter - NonCapturingGroup`() {
        assertEquals("(?:abc)", compileToRegex("(?:abc)"))
    }

    @Test
    fun `Compiler to Emitter - NamedGroup`() {
        assertEquals("(?<name>abc)", compileToRegex("(?<name>abc)"))
    }

    @Test
    fun `Compiler to Emitter - Alternation`() {
        assertEquals("cat|dog", compileToRegex("cat|dog"))
    }

    @Test
    fun `Compiler to Emitter - Anchors`() {
        assertEquals("^abc\$", compileToRegex("^abc\$"))
    }

    @Test
    fun `Compiler to Emitter - PositiveLookahead`() {
        assertEquals("foo(?=bar)", compileToRegex("foo(?=bar)"))
    }

    @Test
    fun `Compiler to Emitter - NegativeLookahead`() {
        assertEquals("foo(?!bar)", compileToRegex("foo(?!bar)"))
    }

    @Test
    fun `Compiler to Emitter - PositiveLookbehind`() {
        assertEquals("(?<=foo)bar", compileToRegex("(?<=foo)bar"))
    }

    @Test
    fun `Compiler to Emitter - NegativeLookbehind`() {
        assertEquals("(?<!foo)bar", compileToRegex("(?<!foo)bar"))
    }

    // ========================================================================
    // Semantic Edge Case Tests
    // ========================================================================

    @Test
    fun test_semantic_duplicate_capture_group() {
        assertThrows<STRlingParseError> {
            Parser.parse("(?<name>a)(?<name>b)")
        }
    }

    @Test
    fun test_semantic_ranges() {
        // Invalid range [z-a] should produce an error
        assertThrows<STRlingParseError> {
            Parser.parse("[z-a]")
        }
    }

    // ========================================================================
    // Full Pipeline Tests
    // ========================================================================

    @Test
    fun `Full Pipeline - PhoneNumber`() {
        val regex = compileToRegex("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})")
        assertEquals("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})", regex)
    }

    @Test
    fun `Full Pipeline - IPv4`() {
        val regex = compileToRegex("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})")
        assertEquals("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})", regex)
    }

    // ========================================================================
    // Helper Methods
    // ========================================================================

    private fun compileToRegex(dsl: String): String {
        val (flags, ast) = Parser.parse(dsl)
        val ir = Compiler.compile(ast)
        return Pcre2Emitter.emit(ir, flags)
    }
}
