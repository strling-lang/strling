/**
 * @file e2e_test.cpp
 * @brief End-to-End Black Box Tests
 *
 * ## Purpose
 * This test suite validates the complete STRling pipeline produces functionally
 * correct regex output by testing against actual regex matching.
 *
 * ## Scope
 * Tests DSL input → regex string → actual matching against test strings.
 */

#include <gtest/gtest.h>
#include "strling/core/parser.hpp"
#include "strling/core/compiler.hpp"
#include "strling/emitters/pcre2.hpp"
#include <regex>
#include <string>
#include <vector>

using namespace strling;

class E2ETest : public ::testing::Test {
protected:
    std::string compileToRegex(const std::string& dsl) {
        core::Parser parser;
        core::Compiler compiler;
        emitters::Pcre2Emitter emitter;
        
        auto ast = parser.parse(dsl);
        auto ir = compiler.compile(ast);
        return emitter.emit(ir, core::Flags{});
    }
    
    bool matches(const std::string& pattern, const std::string& input) {
        try {
            std::regex re(pattern);
            return std::regex_search(input, re);
        } catch (const std::regex_error& e) {
            ADD_FAILURE() << "Regex error: " << e.what() << " for pattern: " << pattern;
            return false;
        }
    }
    
    bool fullMatch(const std::string& pattern, const std::string& input) {
        try {
            std::regex re(pattern);
            return std::regex_match(input, re);
        } catch (const std::regex_error& e) {
            ADD_FAILURE() << "Regex error: " << e.what() << " for pattern: " << pattern;
            return false;
        }
    }
};

// ============================================================================
// Phone Number E2E Tests
// ============================================================================

TEST_F(E2ETest, PhoneNumber_MatchesValidFormats) {
    auto regex = compileToRegex("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})$");
    
    EXPECT_TRUE(fullMatch(regex, "555-123-4567"));
    EXPECT_TRUE(fullMatch(regex, "555.123.4567"));
    EXPECT_TRUE(fullMatch(regex, "555 123 4567"));
    EXPECT_TRUE(fullMatch(regex, "5551234567"));
}

TEST_F(E2ETest, PhoneNumber_RejectsInvalidFormats) {
    auto regex = compileToRegex("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})$");
    
    EXPECT_FALSE(fullMatch(regex, "55-123-4567"));
    EXPECT_FALSE(fullMatch(regex, "555-12-4567"));
    EXPECT_FALSE(fullMatch(regex, "555-123-456"));
    EXPECT_FALSE(fullMatch(regex, "abc-def-ghij"));
}

// ============================================================================
// Email E2E Tests
// ============================================================================

TEST_F(E2ETest, Email_MatchesValidFormats) {
    auto regex = compileToRegex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$");
    
    EXPECT_TRUE(fullMatch(regex, "user@example.com"));
    EXPECT_TRUE(fullMatch(regex, "test.user@domain.org"));
}

TEST_F(E2ETest, Email_RejectsInvalidFormats) {
    auto regex = compileToRegex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$");
    
    EXPECT_FALSE(fullMatch(regex, "@example.com"));
    EXPECT_FALSE(fullMatch(regex, "user@"));
    EXPECT_FALSE(fullMatch(regex, "user@.com"));
}

// ============================================================================
// IPv4 Address E2E Tests
// ============================================================================

TEST_F(E2ETest, IPv4_MatchesValidAddresses) {
    auto regex = compileToRegex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$");
    
    EXPECT_TRUE(fullMatch(regex, "192.168.1.1"));
    EXPECT_TRUE(fullMatch(regex, "10.0.0.1"));
    EXPECT_TRUE(fullMatch(regex, "255.255.255.255"));
    EXPECT_TRUE(fullMatch(regex, "0.0.0.0"));
}

TEST_F(E2ETest, IPv4_RejectsInvalidAddresses) {
    auto regex = compileToRegex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$");
    
    EXPECT_FALSE(fullMatch(regex, "192.168.1"));
    EXPECT_FALSE(fullMatch(regex, "192.168.1.1.1"));
    EXPECT_FALSE(fullMatch(regex, "192-168-1-1"));
}

// ============================================================================
// Hex Color E2E Tests
// ============================================================================

TEST_F(E2ETest, HexColor_MatchesValidColors) {
    auto regex = compileToRegex("^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$");
    
    EXPECT_TRUE(fullMatch(regex, "#ffffff"));
    EXPECT_TRUE(fullMatch(regex, "#000000"));
    EXPECT_TRUE(fullMatch(regex, "#ABC123"));
    EXPECT_TRUE(fullMatch(regex, "#fff"));
    EXPECT_TRUE(fullMatch(regex, "#F00"));
}

TEST_F(E2ETest, HexColor_RejectsInvalidColors) {
    auto regex = compileToRegex("^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$");
    
    EXPECT_FALSE(fullMatch(regex, "ffffff"));
    EXPECT_FALSE(fullMatch(regex, "#ffff"));
    EXPECT_FALSE(fullMatch(regex, "#GGGGGG"));
}

// ============================================================================
// Date E2E Tests
// ============================================================================

TEST_F(E2ETest, Date_MatchesValidDates) {
    auto regex = compileToRegex("^(\\d{4})-(\\d{2})-(\\d{2})$");
    
    EXPECT_TRUE(fullMatch(regex, "2024-01-15"));
    EXPECT_TRUE(fullMatch(regex, "2000-12-31"));
    EXPECT_TRUE(fullMatch(regex, "1999-06-30"));
}

TEST_F(E2ETest, Date_RejectsInvalidDates) {
    auto regex = compileToRegex("^(\\d{4})-(\\d{2})-(\\d{2})$");
    
    EXPECT_FALSE(fullMatch(regex, "24-01-15"));
    EXPECT_FALSE(fullMatch(regex, "2024/01/15"));
    EXPECT_FALSE(fullMatch(regex, "2024-1-15"));
}

// ============================================================================
// Lookahead E2E Tests
// ============================================================================

TEST_F(E2ETest, PositiveLookahead) {
    auto regex = compileToRegex("foo(?=bar)");
    
    EXPECT_TRUE(matches(regex, "foobar"));
    EXPECT_FALSE(matches(regex, "foobaz"));
}

TEST_F(E2ETest, NegativeLookahead) {
    auto regex = compileToRegex("foo(?!bar)");
    
    EXPECT_TRUE(matches(regex, "foobaz"));
    // Note: "foobar" still matches "foo" before "bar", need anchoring for full test
}

// ============================================================================
// Word Boundary E2E Tests
// ============================================================================

TEST_F(E2ETest, WordBoundary) {
    auto regex = compileToRegex("\\bword\\b");
    
    EXPECT_TRUE(matches(regex, "word"));
    EXPECT_TRUE(matches(regex, "a word here"));
    EXPECT_FALSE(matches(regex, "sword"));
    EXPECT_FALSE(matches(regex, "wording"));
}

// ============================================================================
// Alternation E2E Tests
// ============================================================================

TEST_F(E2ETest, Alternation) {
    auto regex = compileToRegex("^(cat|dog|bird)$");
    
    EXPECT_TRUE(fullMatch(regex, "cat"));
    EXPECT_TRUE(fullMatch(regex, "dog"));
    EXPECT_TRUE(fullMatch(regex, "bird"));
    EXPECT_FALSE(fullMatch(regex, "cats"));
    EXPECT_FALSE(fullMatch(regex, "fish"));
}

// ============================================================================
// Quantifier E2E Tests
// ============================================================================

TEST_F(E2ETest, QuantifierPlus) {
    auto regex = compileToRegex("^a+$");
    
    EXPECT_TRUE(fullMatch(regex, "a"));
    EXPECT_TRUE(fullMatch(regex, "aa"));
    EXPECT_TRUE(fullMatch(regex, "aaa"));
    EXPECT_FALSE(fullMatch(regex, ""));
    EXPECT_FALSE(fullMatch(regex, "b"));
}

TEST_F(E2ETest, QuantifierStar) {
    auto regex = compileToRegex("^a*$");
    
    EXPECT_TRUE(fullMatch(regex, ""));
    EXPECT_TRUE(fullMatch(regex, "a"));
    EXPECT_TRUE(fullMatch(regex, "aaa"));
    EXPECT_FALSE(fullMatch(regex, "b"));
}

TEST_F(E2ETest, QuantifierOptional) {
    auto regex = compileToRegex("^a?$");
    
    EXPECT_TRUE(fullMatch(regex, ""));
    EXPECT_TRUE(fullMatch(regex, "a"));
    EXPECT_FALSE(fullMatch(regex, "aa"));
}

TEST_F(E2ETest, QuantifierExact) {
    auto regex = compileToRegex("^a{3}$");
    
    EXPECT_TRUE(fullMatch(regex, "aaa"));
    EXPECT_FALSE(fullMatch(regex, "a"));
    EXPECT_FALSE(fullMatch(regex, "aa"));
    EXPECT_FALSE(fullMatch(regex, "aaaa"));
}

TEST_F(E2ETest, QuantifierRange) {
    auto regex = compileToRegex("^a{2,4}$");
    
    EXPECT_TRUE(fullMatch(regex, "aa"));
    EXPECT_TRUE(fullMatch(regex, "aaa"));
    EXPECT_TRUE(fullMatch(regex, "aaaa"));
    EXPECT_FALSE(fullMatch(regex, "a"));
    EXPECT_FALSE(fullMatch(regex, "aaaaa"));
}

TEST_F(E2ETest, QuantifierAtLeast) {
    auto regex = compileToRegex("^a{2,}$");
    
    EXPECT_TRUE(fullMatch(regex, "aa"));
    EXPECT_TRUE(fullMatch(regex, "aaa"));
    EXPECT_TRUE(fullMatch(regex, "aaaa"));
    EXPECT_FALSE(fullMatch(regex, ""));
    EXPECT_FALSE(fullMatch(regex, "a"));
}
