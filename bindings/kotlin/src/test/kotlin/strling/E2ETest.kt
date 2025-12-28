package strling

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.assertFalse
import strling.core.Parser
import strling.core.Compiler
import strling.emitters.Pcre2Emitter

/**
 * E2E Tests - Black-box testing where DSL input produces a regex
 * that matches expected strings.
 */
class E2ETest {

    private fun compileToRegex(dsl: String): String {
        val (flags, ast) = Parser.parse(dsl)
        val ir = Compiler.compile(ast)
        return Pcre2Emitter.emit(ir, flags)
    }

    // ========================================================================
    // Phone Number E2E Tests
    // ========================================================================

    @Test
    fun `E2E Phone Number - matches valid formats`() {
        val regex = compileToRegex("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})\$")
        val re = Regex(regex)

        assertTrue(re.matches("555-123-4567"))
        assertTrue(re.matches("555.123.4567"))
        assertTrue(re.matches("555 123 4567"))
        assertTrue(re.matches("5551234567"))
    }

    @Test
    fun `E2E Phone Number - rejects invalid formats`() {
        val regex = compileToRegex("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})\$")
        val re = Regex(regex)

        assertFalse(re.matches("55-123-4567"))
        assertFalse(re.matches("555-12-4567"))
        assertFalse(re.matches("555-123-456"))
        assertFalse(re.matches("abc-def-ghij"))
    }

    // ========================================================================
    // Email E2E Tests
    // ========================================================================

    @Test
    fun `E2E Email - matches valid formats`() {
        val regex = compileToRegex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\$")
        val re = Regex(regex)

        assertTrue(re.matches("user@example.com"))
        assertTrue(re.matches("test.user@domain.org"))
    }

    @Test
    fun `E2E Email - rejects invalid formats`() {
        val regex = compileToRegex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\$")
        val re = Regex(regex)

        assertFalse(re.matches("@example.com"))
        assertFalse(re.matches("user@"))
        assertFalse(re.matches("user@.com"))
    }

    // ========================================================================
    // IPv4 E2E Tests
    // ========================================================================

    @Test
    fun `E2E IPv4 - matches valid addresses`() {
        val regex = compileToRegex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\$")
        val re = Regex(regex)

        assertTrue(re.matches("192.168.1.1"))
        assertTrue(re.matches("10.0.0.1"))
        assertTrue(re.matches("255.255.255.255"))
        assertTrue(re.matches("0.0.0.0"))
    }

    @Test
    fun `E2E IPv4 - rejects invalid addresses`() {
        val regex = compileToRegex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\$")
        val re = Regex(regex)

        assertFalse(re.matches("192.168.1"))
        assertFalse(re.matches("192.168.1.1.1"))
        assertFalse(re.matches("192-168-1-1"))
    }

    // ========================================================================
    // Hex Color E2E Tests
    // ========================================================================

    @Test
    fun `E2E Hex Color - matches valid colors`() {
        val regex = compileToRegex("^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})\$")
        val re = Regex(regex)

        assertTrue(re.matches("#ffffff"))
        assertTrue(re.matches("#000000"))
        assertTrue(re.matches("#ABC123"))
        assertTrue(re.matches("#fff"))
        assertTrue(re.matches("#F00"))
    }

    @Test
    fun `E2E Hex Color - rejects invalid colors`() {
        val regex = compileToRegex("^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})\$")
        val re = Regex(regex)

        assertFalse(re.matches("ffffff"))
        assertFalse(re.matches("#ffff"))
        assertFalse(re.matches("#GGGGGG"))
    }

    // ========================================================================
    // Date E2E Tests
    // ========================================================================

    @Test
    fun `E2E Date - matches valid dates`() {
        val regex = compileToRegex("^(\\d{4})-(\\d{2})-(\\d{2})\$")
        val re = Regex(regex)

        assertTrue(re.matches("2024-01-15"))
        assertTrue(re.matches("2000-12-31"))
        assertTrue(re.matches("1999-06-30"))
    }

    @Test
    fun `E2E Date - rejects invalid dates`() {
        val regex = compileToRegex("^(\\d{4})-(\\d{2})-(\\d{2})\$")
        val re = Regex(regex)

        assertFalse(re.matches("24-01-15"))
        assertFalse(re.matches("2024/01/15"))
        assertFalse(re.matches("2024-1-15"))
    }

    // ========================================================================
    // Lookahead E2E Tests
    // ========================================================================

    @Test
    fun `E2E Positive Lookahead`() {
        val regex = compileToRegex("foo(?=bar)")
        val re = Regex(regex)

        assertTrue(re.containsMatchIn("foobar"))
        assertFalse(re.containsMatchIn("foobaz"))
    }

    @Test
    fun `E2E Negative Lookahead`() {
        val regex = compileToRegex("foo(?!bar)")
        val re = Regex(regex)

        assertTrue(re.containsMatchIn("foobaz"))
    }

    // ========================================================================
    // Word Boundary E2E Tests
    // ========================================================================

    @Test
    fun `E2E Word Boundary`() {
        val regex = compileToRegex("\\bword\\b")
        val re = Regex(regex)

        assertTrue(re.containsMatchIn("word"))
        assertTrue(re.containsMatchIn("a word here"))
        assertFalse(re.containsMatchIn("sword"))
        assertFalse(re.containsMatchIn("wording"))
    }

    // ========================================================================
    // Alternation E2E Tests
    // ========================================================================

    @Test
    fun `E2E Alternation`() {
        val regex = compileToRegex("^(cat|dog|bird)\$")
        val re = Regex(regex)

        assertTrue(re.matches("cat"))
        assertTrue(re.matches("dog"))
        assertTrue(re.matches("bird"))
        assertFalse(re.matches("cats"))
        assertFalse(re.matches("fish"))
    }

    // ========================================================================
    // Quantifier E2E Tests
    // ========================================================================

    @Test
    fun `E2E Quantifier Plus`() {
        val regex = compileToRegex("^a+\$")
        val re = Regex(regex)

        assertTrue(re.matches("a"))
        assertTrue(re.matches("aa"))
        assertTrue(re.matches("aaa"))
        assertFalse(re.matches(""))
        assertFalse(re.matches("b"))
    }

    @Test
    fun `E2E Quantifier Star`() {
        val regex = compileToRegex("^a*\$")
        val re = Regex(regex)

        assertTrue(re.matches(""))
        assertTrue(re.matches("a"))
        assertTrue(re.matches("aaa"))
        assertFalse(re.matches("b"))
    }

    @Test
    fun `E2E Quantifier Optional`() {
        val regex = compileToRegex("^a?\$")
        val re = Regex(regex)

        assertTrue(re.matches(""))
        assertTrue(re.matches("a"))
        assertFalse(re.matches("aa"))
    }

    @Test
    fun `E2E Quantifier Exact`() {
        val regex = compileToRegex("^a{3}\$")
        val re = Regex(regex)

        assertTrue(re.matches("aaa"))
        assertFalse(re.matches("a"))
        assertFalse(re.matches("aa"))
        assertFalse(re.matches("aaaa"))
    }

    @Test
    fun `E2E Quantifier Range`() {
        val regex = compileToRegex("^a{2,4}\$")
        val re = Regex(regex)

        assertTrue(re.matches("aa"))
        assertTrue(re.matches("aaa"))
        assertTrue(re.matches("aaaa"))
        assertFalse(re.matches("a"))
        assertFalse(re.matches("aaaaa"))
    }

    @Test
    fun `E2E Quantifier AtLeast`() {
        val regex = compileToRegex("^a{2,}\$")
        val re = Regex(regex)

        assertTrue(re.matches("aa"))
        assertTrue(re.matches("aaa"))
        assertTrue(re.matches("aaaa"))
        assertFalse(re.matches(""))
        assertFalse(re.matches("a"))
    }

    // ========================================================================
    // Capture Groups E2E Tests
    // ========================================================================

    @Test
    fun `E2E Capture Groups`() {
        val regex = compileToRegex("^(\\d{4})-(\\d{2})-(\\d{2})\$")
        val re = Regex(regex)
        val match = re.matchEntire("2024-12-25")

        assertEquals("2024", match?.groupValues?.get(1))
        assertEquals("12", match?.groupValues?.get(2))
        assertEquals("25", match?.groupValues?.get(3))
    }
}
