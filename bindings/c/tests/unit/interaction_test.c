/**
 * @file interaction_test.c
 * @brief Interaction Tests - Parser → Compiler → Emitter handoffs
 *
 * This test suite validates the handoff between pipeline stages:
 * - Parser → Compiler: Ensures AST is correctly consumed
 * - Compiler → Emitter: Ensures IR is correctly transformed to regex
 */

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

#define ASSERT_EQ(expected, actual) do { \
    if (strcmp(expected, actual) != 0) { \
        printf(" FAILED: expected '%s', got '%s'\n", expected, actual); \
        tests_failed++; \
        return; \
    } \
} while(0)

#define ASSERT_IR_TYPE(expected_type) do { \
    ASSERT(ir != NULL, "IR should not be NULL"); \
    ASSERT(ir->type == expected_type, "IR type mismatch"); \
} while(0)

/* Helper function to compile DSL to regex */
static char* compile_to_regex(const char* dsl) {
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
    
    return regex;
}

/* ============================================================================
 * Parser → Compiler Handoff Tests
 * ============================================================================ */

TEST(parser_compiler_simple_literal) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("hello", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_LIT, "Expected IR_LIT");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_quantifier) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("a+", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_QUANT, "Expected IR_QUANT");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_character_class) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("[abc]", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_CHARCLASS, "Expected IR_CHARCLASS");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_capturing_group) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("(abc)", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_GROUP, "Expected IR_GROUP");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_alternation) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("a|b", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_ALT, "Expected IR_ALT");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_named_group) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("(?<name>abc)", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_GROUP, "Expected IR_GROUP");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_lookahead) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("(?=abc)", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_LOOK, "Expected IR_LOOK");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

TEST(parser_compiler_lookbehind) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("(?<=abc)", &flags);
    ASSERT(ast != NULL, "AST should not be NULL");
    
    strling_ir_t* ir = strling_compile(ast);
    ASSERT(ir != NULL, "IR should not be NULL");
    ASSERT(ir->type == IR_LOOK, "Expected IR_LOOK");
    
    strling_ir_free(ir);
    strling_node_free(ast);
}

/* ============================================================================
 * Compiler → Emitter Handoff Tests
 * ============================================================================ */

TEST(compiler_emitter_simple_literal) {
    char* regex = compile_to_regex("hello");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("hello", regex);
    free(regex);
}

TEST(compiler_emitter_digit_shorthand) {
    char* regex = compile_to_regex("\\d+");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("\\d+", regex);
    free(regex);
}

TEST(compiler_emitter_character_class) {
    char* regex = compile_to_regex("[abc]");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("[abc]", regex);
    free(regex);
}

TEST(compiler_emitter_quantifier_plus) {
    char* regex = compile_to_regex("a+");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("a+", regex);
    free(regex);
}

TEST(compiler_emitter_quantifier_star) {
    char* regex = compile_to_regex("a*");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("a*", regex);
    free(regex);
}

TEST(compiler_emitter_quantifier_optional) {
    char* regex = compile_to_regex("a?");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("a?", regex);
    free(regex);
}

TEST(compiler_emitter_capturing_group) {
    char* regex = compile_to_regex("(abc)");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("(abc)", regex);
    free(regex);
}

TEST(compiler_emitter_non_capturing_group) {
    char* regex = compile_to_regex("(?:abc)");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("(?:abc)", regex);
    free(regex);
}

TEST(compiler_emitter_alternation) {
    char* regex = compile_to_regex("cat|dog");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("cat|dog", regex);
    free(regex);
}

TEST(compiler_emitter_anchors) {
    char* regex = compile_to_regex("^abc$");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("^abc$", regex);
    free(regex);
}

TEST(compiler_emitter_lookahead) {
    char* regex = compile_to_regex("foo(?=bar)");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("foo(?=bar)", regex);
    free(regex);
}

TEST(compiler_emitter_lookbehind) {
    char* regex = compile_to_regex("(?<=foo)bar");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("(?<=foo)bar", regex);
    free(regex);
}

/* ============================================================================
 * Semantic Edge Case Tests
 * ============================================================================ */

TEST(semantic_duplicate_capture_group) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("(?<name>a)(?<name>b)", &flags);
    /* Should fail with duplicate name error */
    ASSERT(ast == NULL, "Parser should reject duplicate named groups");
}

TEST(semantic_ranges) {
    strling_flags_t flags;
    strling_node_t* ast = strling_parse("[z-a]", &flags);
    /* Should fail with invalid range error */
    ASSERT(ast == NULL, "Parser should reject invalid range [z-a]");
}

/* ============================================================================
 * Full Pipeline Tests
 * ============================================================================ */

TEST(full_pipeline_phone_number) {
    char* regex = compile_to_regex("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})", regex);
    free(regex);
}

TEST(full_pipeline_ipv4) {
    char* regex = compile_to_regex("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})");
    ASSERT(regex != NULL, "Regex should not be NULL");
    ASSERT_EQ("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})", regex);
    free(regex);
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("=== Parser → Compiler Handoff Tests ===\n");
    RUN_TEST(parser_compiler_simple_literal);
    RUN_TEST(parser_compiler_quantifier);
    RUN_TEST(parser_compiler_character_class);
    RUN_TEST(parser_compiler_capturing_group);
    RUN_TEST(parser_compiler_alternation);
    RUN_TEST(parser_compiler_named_group);
    RUN_TEST(parser_compiler_lookahead);
    RUN_TEST(parser_compiler_lookbehind);
    
    printf("\n=== Compiler → Emitter Handoff Tests ===\n");
    RUN_TEST(compiler_emitter_simple_literal);
    RUN_TEST(compiler_emitter_digit_shorthand);
    RUN_TEST(compiler_emitter_character_class);
    RUN_TEST(compiler_emitter_quantifier_plus);
    RUN_TEST(compiler_emitter_quantifier_star);
    RUN_TEST(compiler_emitter_quantifier_optional);
    RUN_TEST(compiler_emitter_capturing_group);
    RUN_TEST(compiler_emitter_non_capturing_group);
    RUN_TEST(compiler_emitter_alternation);
    RUN_TEST(compiler_emitter_anchors);
    RUN_TEST(compiler_emitter_lookahead);
    RUN_TEST(compiler_emitter_lookbehind);
    
    printf("\n=== Semantic Edge Case Tests ===\n");
    RUN_TEST(semantic_duplicate_capture_group);
    RUN_TEST(semantic_ranges);
    
    printf("\n=== Full Pipeline Tests ===\n");
    RUN_TEST(full_pipeline_phone_number);
    RUN_TEST(full_pipeline_ipv4);
    
    printf("\n=== Summary ===\n");
    printf("Passed: %d, Failed: %d\n", tests_passed, tests_failed);
    
    return tests_failed > 0 ? 1 : 0;
}
