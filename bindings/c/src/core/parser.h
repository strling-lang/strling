/*
 * STRling Parser - Recursive Descent Parser for STRling DSL
 *
 * This module implements a hand-rolled recursive-descent parser that transforms
 * STRling pattern syntax into Abstract Syntax Tree (AST) nodes.
 */
#ifndef STRLING_PARSER_H
#define STRLING_PARSER_H

#include "nodes.h"
#include "errors.h"
#include "../../include/strling.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Parse result structure */
typedef struct STRlingParseResult {
    STRlingFlags flags;
    STRlingASTNode* root;
    STRlingError* error;
} STRlingParseResult;

/* Parse a DSL string into an AST
 * Returns a parse result containing the flags, AST root, and any error.
 * Caller must free the result with strling_parse_result_free().
 */
STRlingParseResult* strling_parse(const char* src);

/* Free a parse result */
void strling_parse_result_free(STRlingParseResult* result);

#ifdef __cplusplus
}
#endif

#endif /* STRLING_PARSER_H */
