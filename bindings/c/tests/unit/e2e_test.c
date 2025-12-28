/**
 * @file e2e_test.c
 * @brief E2E Tests - Black Box: Input DSL → Match Regex against String
 *
 * End-to-end tests that validate the full pipeline from DSL input
 * to regex matching against target strings using PCRE2.
 */

#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/strling.h"

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) static void test_##name(void)
#define RUN_TEST(name) do { \
    printf("  Running %s...", #name); \
    test_##name(); \
    printf(" PASSED\n"); \
    tests_passed++; \
} while(0)

#define ASSERT(cond, msg) do { \
    if (!(cond)) { \
        printf(" FAILED: %s\n", msg); \
        tests_failed++; \
        return; \
    } \
} while(0)

/* Helper function to compile DSL to PCRE2 regex */
static pcre2_code* compile_pattern(const char* dsl) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse(dsl, &flags);
    if (ast == NULL) {
        return NULL;
    }
    
    strling_ir_t* ir = strling_compile(ast);
    if (ir == NULL) {
        strling_node_free(ast);
        return NULL;
    }
    
    char* regex = strling_emit_pcre2(ir, &flags);
    strling_ir_free(ir);
    strling_node_free(ast);
    
    if (regex == NULL) {
        return NULL;
    }
    
    int errornumber;
    PCRE2_SIZE erroroffset;
    uint32_t options = 0;
    
    if (flags.case_insensitive) options |= PCRE2_CASELESS;
    if (flags.multiline) options |= PCRE2_MULTILINE;
    if (flags.dotall) options |= PCRE2_DOTALL;
    if (flags.unicode) options |= PCRE2_UCP | PCRE2_UTF;
    if (flags.extended) options |= PCRE2_EXTENDED;
    
    pcre2_code* code = pcre2_compile(
        (PCRE2_SPTR)regex,
        PCRE2_ZERO_TERMINATED,
        options,
        &errornumber,
        &erroroffset,
        NULL
    );
    
    free(regex);
    return code;
}

/* Helper function to check if pattern matches string */
static int matches(const char* dsl, const char* subject) {
    pcre2_code* code = compile_pattern(dsl);
    if (code == NULL) {
        return -1; /* Compile error */
    }
    
    pcre2_match_data* match_data = pcre2_match_data_create_from_pattern(code, NULL);
    
    int rc = pcre2_match(
        code,
        (PCRE2_SPTR)subject,
        strlen(subject),
        0,
        0,
        match_data,
        NULL
    );
    
    pcre2_match_data_free(match_data);
    pcre2_code_free(code);
    
    return rc >= 0 ? 1 : 0;
}

/* Helper to check full match */
static int full_matches(const char* dsl, const char* subject) {
    char* anchored_dsl = malloc(strlen(dsl) + 3);
    sprintf(anchored_dsl, "^%s$", dsl);
    int result = matches(anchored_dsl, subject);
    free(anchored_dsl);
    return result;
}

/* ============================================================================
 * Phone Number Tests
 * ============================================================================ */

TEST(e2e_phone_number_basic) {
    const char* dsl = "\\d{3}-\\d{3}-\\d{4}";
    
    ASSERT(matches(dsl, "555-123-4567") == 1, "Should match valid phone");
    ASSERT(matches(dsl, "123-456-7890") == 1, "Should match valid phone");
    ASSERT(matches(dsl, "12-345-6789") == 0, "Should not match invalid phone");
    ASSERT(matches(dsl, "not a phone") == 0, "Should not match text");
}

TEST(e2e_phone_number_with_groups) {
    const char* dsl = "(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})";
    
    ASSERT(matches(dsl, "555-123-4567") == 1, "Should match dashed phone");
    ASSERT(matches(dsl, "555.123.4567") == 1, "Should match dotted phone");
    ASSERT(matches(dsl, "555 123 4567") == 1, "Should match spaced phone");
    ASSERT(matches(dsl, "5551234567") == 1, "Should match no-separator phone");
}

/* ============================================================================
 * Email Tests
 * ============================================================================ */

TEST(e2e_email_simple) {
    const char* dsl = "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}";
    
    ASSERT(matches(dsl, "test@example.com") == 1, "Should match simple email");
    ASSERT(matches(dsl, "user.name@domain.org") == 1, "Should match email with dot");
    ASSERT(matches(dsl, "user+tag@domain.co.uk") == 1, "Should match email with plus");
    ASSERT(matches(dsl, "invalid-email") == 0, "Should not match invalid email");
}

/* ============================================================================
 * IPv4 Tests
 * ============================================================================ */

TEST(e2e_ipv4_address) {
    const char* dsl = "\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}";
    
    ASSERT(matches(dsl, "192.168.1.1") == 1, "Should match private IP");
    ASSERT(matches(dsl, "10.0.0.255") == 1, "Should match 10.x range");
    ASSERT(matches(dsl, "255.255.255.0") == 1, "Should match subnet mask");
    ASSERT(matches(dsl, "192.168.1") == 0, "Should not match incomplete IP");
}

/* ============================================================================
 * Hex Color Tests
 * ============================================================================ */

TEST(e2e_hex_color) {
    const char* dsl = "#[0-9a-fA-F]{6}";
    
    ASSERT(matches(dsl, "#FFFFFF") == 1, "Should match white");
    ASSERT(matches(dsl, "#000000") == 1, "Should match black");
    ASSERT(matches(dsl, "#ff5733") == 1, "Should match lowercase hex");
    ASSERT(matches(dsl, "#GGG") == 0, "Should not match invalid hex");
}

/* ============================================================================
 * Date Tests
 * ============================================================================ */

TEST(e2e_date_format) {
    const char* dsl = "\\d{4}-\\d{2}-\\d{2}";
    
    ASSERT(matches(dsl, "2024-01-15") == 1, "Should match ISO date");
    ASSERT(matches(dsl, "1999-12-31") == 1, "Should match Y2K date");
    ASSERT(matches(dsl, "24-01-15") == 0, "Should not match short year");
}

/* ============================================================================
 * Lookahead/Lookbehind Tests
 * ============================================================================ */

TEST(e2e_lookahead_positive) {
    const char* dsl = "foo(?=bar)";
    
    ASSERT(matches(dsl, "foobar") == 1, "Should match foo followed by bar");
    ASSERT(matches(dsl, "foobaz") == 0, "Should not match foo followed by baz");
    ASSERT(matches(dsl, "foo") == 0, "Should not match just foo");
}

TEST(e2e_lookahead_negative) {
    const char* dsl = "foo(?!bar)";
    
    ASSERT(matches(dsl, "foobaz") == 1, "Should match foo NOT followed by bar");
    ASSERT(matches(dsl, "foobar") == 0, "Should not match foo followed by bar");
}

TEST(e2e_lookbehind_positive) {
    const char* dsl = "(?<=foo)bar";
    
    ASSERT(matches(dsl, "foobar") == 1, "Should match bar preceded by foo");
    ASSERT(matches(dsl, "bazbar") == 0, "Should not match bar preceded by baz");
}

TEST(e2e_lookbehind_negative) {
    const char* dsl = "(?<!foo)bar";
    
    ASSERT(matches(dsl, "bazbar") == 1, "Should match bar NOT preceded by foo");
    ASSERT(matches(dsl, "foobar") == 0, "Should not match bar preceded by foo");
}

/* ============================================================================
 * Word Boundary Tests
 * ============================================================================ */

TEST(e2e_word_boundary) {
    const char* dsl = "\\bcat\\b";
    
    ASSERT(matches(dsl, "the cat sat") == 1, "Should match standalone cat");
    ASSERT(matches(dsl, "cat") == 1, "Should match just cat");
    ASSERT(matches(dsl, "category") == 0, "Should not match category");
    ASSERT(matches(dsl, "concatenate") == 0, "Should not match concatenate");
}

/* ============================================================================
 * Alternation Tests
 * ============================================================================ */

TEST(e2e_alternation) {
    const char* dsl = "cat|dog|bird";
    
    ASSERT(matches(dsl, "I have a cat") == 1, "Should match cat");
    ASSERT(matches(dsl, "I have a dog") == 1, "Should match dog");
    ASSERT(matches(dsl, "I have a bird") == 1, "Should match bird");
    ASSERT(matches(dsl, "I have a fish") == 0, "Should not match fish");
}

/* ============================================================================
 * Quantifier Tests
 * ============================================================================ */

TEST(e2e_quantifier_greedy_vs_lazy) {
    const char* greedy = "<.*>";
    const char* lazy = "<.*?>";
    
    /* Greedy matches as much as possible */
    ASSERT(matches(greedy, "<div><span></span></div>") == 1, "Greedy should match");
    
    /* Lazy matches as little as possible */
    ASSERT(matches(lazy, "<div></div>") == 1, "Lazy should match");
}

TEST(e2e_quantifier_exact) {
    const char* dsl = "a{3}";
    
    ASSERT(full_matches(dsl, "aaa") == 1, "Should match exactly 3 a's");
    ASSERT(full_matches(dsl, "aa") == 0, "Should not match 2 a's");
}

/* ============================================================================
 * Capture Group Tests
 * ============================================================================ */

TEST(e2e_capture_groups) {
    const char* dsl = "(\\w+)\\s+(\\w+)";
    
    ASSERT(matches(dsl, "hello world") == 1, "Should match two words");
    ASSERT(matches(dsl, "one two three") == 1, "Should match in three words");
}

TEST(e2e_named_capture_group) {
    const char* dsl = "(?<word>\\w+)";
    
    ASSERT(matches(dsl, "hello") == 1, "Should match with named group");
}

/* ============================================================================
 * Complex Pattern Tests
 * ============================================================================ */

TEST(e2e_complex_url) {
    const char* dsl = "https?://[a-zA-Z0-9.-]+(/[a-zA-Z0-9./_-]*)?";
    
    ASSERT(matches(dsl, "http://example.com") == 1, "Should match http URL");
    ASSERT(matches(dsl, "https://example.com/path") == 1, "Should match https URL with path");
    ASSERT(matches(dsl, "ftp://example.com") == 0, "Should not match ftp URL");
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("=== Phone Number Tests ===\n");
    RUN_TEST(e2e_phone_number_basic);
    RUN_TEST(e2e_phone_number_with_groups);
    
    printf("\n=== Email Tests ===\n");
    RUN_TEST(e2e_email_simple);
    
    printf("\n=== IPv4 Tests ===\n");
    RUN_TEST(e2e_ipv4_address);
    
    printf("\n=== Hex Color Tests ===\n");
    RUN_TEST(e2e_hex_color);
    
    printf("\n=== Date Tests ===\n");
    RUN_TEST(e2e_date_format);
    
    printf("\n=== Lookahead/Lookbehind Tests ===\n");
    RUN_TEST(e2e_lookahead_positive);
    RUN_TEST(e2e_lookahead_negative);
    RUN_TEST(e2e_lookbehind_positive);
    RUN_TEST(e2e_lookbehind_negative);
    
    printf("\n=== Word Boundary Tests ===\n");
    RUN_TEST(e2e_word_boundary);
    
    printf("\n=== Alternation Tests ===\n");
    RUN_TEST(e2e_alternation);
    
    printf("\n=== Quantifier Tests ===\n");
    RUN_TEST(e2e_quantifier_greedy_vs_lazy);
    RUN_TEST(e2e_quantifier_exact);
    
    printf("\n=== Capture Group Tests ===\n");
    RUN_TEST(e2e_capture_groups);
    RUN_TEST(e2e_named_capture_group);
    
    printf("\n=== Complex Pattern Tests ===\n");
    RUN_TEST(e2e_complex_url);
    
    printf("\n=== Summary ===\n");
    printf("Passed: %d, Failed: %d\n", tests_passed, tests_failed);
    
    return tests_failed > 0 ? 1 : 0;
}
