/*
 * STRling Parser Implementation - Recursive Descent Parser for C
 *
 * Implements a complete recursive-descent parser that transforms STRling
 * DSL patterns into AST nodes. Mirrors the TypeScript reference implementation.
 */

#include "parser.h"
#include "nodes.h"
#include "errors.h"
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdio.h>

/* ============================================================================
 * Cursor - tracks position in input text
 * ============================================================================ */

typedef struct {
    const char* text;
    size_t len;
    size_t i;
    int extended_mode;
    int in_class;
} Cursor;

static void cursor_init(Cursor* c, const char* text, int extended_mode) {
    c->text = text;
    c->len = strlen(text);
    c->i = 0;
    c->extended_mode = extended_mode;
    c->in_class = 0;
}

static int cursor_eof(Cursor* c) {
    return c->i >= c->len;
}

static char cursor_peek(Cursor* c, int offset) {
    size_t j = c->i + offset;
    if (j >= c->len) return '\0';
    return c->text[j];
}

static char cursor_take(Cursor* c) {
    if (cursor_eof(c)) return '\0';
    return c->text[c->i++];
}

static int cursor_match(Cursor* c, const char* s) {
    size_t slen = strlen(s);
    if (c->i + slen > c->len) return 0;
    if (strncmp(c->text + c->i, s, slen) == 0) {
        c->i += slen;
        return 1;
    }
    return 0;
}

static void cursor_skip_ws_and_comments(Cursor* c) {
    if (!c->extended_mode || c->in_class > 0) return;
    while (!cursor_eof(c)) {
        char ch = cursor_peek(c, 0);
        if (ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n') {
            c->i++;
            continue;
        }
        if (ch == '#') {
            while (!cursor_eof(c) && cursor_peek(c, 0) != '\r' && cursor_peek(c, 0) != '\n') {
                c->i++;
            }
            continue;
        }
        break;
    }
}

/* ============================================================================
 * Parser State
 * ============================================================================ */

typedef struct {
    Cursor cur;
    STRlingFlags flags;
    const char* src;
    const char* original;
    int cap_count;
    char** cap_names;
    size_t cap_names_count;
    size_t cap_names_capacity;
    STRlingError* error;
} Parser;

static void parser_init(Parser* p, const char* text);
static void parser_cleanup(Parser* p);
static STRlingASTNode* parser_parse(Parser* p);
static STRlingASTNode* parse_alt(Parser* p);
static STRlingASTNode* parse_seq(Parser* p);
static STRlingASTNode* parse_atom(Parser* p);
static STRlingASTNode* parse_quant_if_any(Parser* p, STRlingASTNode* child);
static STRlingASTNode* parse_group_or_look(Parser* p);
static STRlingASTNode* parse_char_class(Parser* p);
static STRlingASTNode* parse_escape_atom(Parser* p);
static STRlingClassItem* parse_class_escape(Parser* p);

/* Helper: duplicate string */
static char* str_dup(const char* s) {
    if (!s) return NULL;
    size_t len = strlen(s) + 1;
    char* r = (char*)malloc(len);
    if (r) memcpy(r, s, len);
    return r;
}

/* Helper: substring */
static char* str_substr(const char* s, size_t start, size_t len) {
    char* r = (char*)malloc(len + 1);
    if (!r) return NULL;
    strncpy(r, s + start, len);
    r[len] = '\0';
    return r;
}

/* Helper: check if name exists in cap_names */
static int has_cap_name(Parser* p, const char* name) {
    for (size_t i = 0; i < p->cap_names_count; i++) {
        if (strcmp(p->cap_names[i], name) == 0) return 1;
    }
    return 0;
}

/* Helper: add capture name */
static void add_cap_name(Parser* p, const char* name) {
    if (p->cap_names_count >= p->cap_names_capacity) {
        size_t new_cap = p->cap_names_capacity == 0 ? 8 : p->cap_names_capacity * 2;
        char** new_names = (char**)realloc(p->cap_names, new_cap * sizeof(char*));
        if (!new_names) return;
        p->cap_names = new_names;
        p->cap_names_capacity = new_cap;
    }
    p->cap_names[p->cap_names_count++] = str_dup(name);
}

/* Set error on parser */
static void parser_set_error(Parser* p, const char* message, int position) {
    if (p->error) return; /* Keep first error */
    p->error = strling_error_create(message, position, NULL);
}

/* Control escape map */
static char control_escape(char ch) {
    switch (ch) {
        case 'n': return '\n';
        case 'r': return '\r';
        case 't': return '\t';
        case 'f': return '\f';
        case 'v': return '\v';
        default: return '\0';
    }
}

static int is_control_escape(char ch) {
    return ch == 'n' || ch == 'r' || ch == 't' || ch == 'f' || ch == 'v';
}

/* ============================================================================
 * Directive Parsing
 * ============================================================================ */

static void parse_directives(Parser* p, const char* text) {
    /* Initialize flags */
    p->flags.ignoreCase = 0;
    p->flags.multiline = 0;
    p->flags.dotAll = 0;
    p->flags.unicode = 0;
    p->flags.extended = 0;

    /* Find %flags directive */
    const char* flags_pos = strstr(text, "%flags");
    if (!flags_pos) {
        p->src = text;
        return;
    }

    /* Parse flag letters */
    const char* after = flags_pos + 6; /* strlen("%flags") */
    while (*after && (*after == ' ' || *after == '\t' || *after == ',' || *after == '[' || *after == ']')) {
        after++;
    }

    /* Collect flag letters */
    const char* flag_start = after;
    while (*after && (*after == 'i' || *after == 'm' || *after == 's' || *after == 'u' || *after == 'x' ||
                      *after == 'I' || *after == 'M' || *after == 'S' || *after == 'U' || *after == 'X' ||
                      *after == ',' || *after == ' ' || *after == '\t')) {
        char c = *after;
        switch (c) {
            case 'i': case 'I': p->flags.ignoreCase = 1; break;
            case 'm': case 'M': p->flags.multiline = 1; break;
            case 's': case 'S': p->flags.dotAll = 1; break;
            case 'u': case 'U': p->flags.unicode = 1; break;
            case 'x': case 'X': p->flags.extended = 1; break;
        }
        after++;
    }

    /* Find where pattern starts (skip rest of directive line) */
    while (*after && *after != '\n' && *after != '\r') {
        after++;
    }
    while (*after && (*after == '\n' || *after == '\r')) {
        after++;
    }

    p->src = after;
}

/* ============================================================================
 * Parser Implementation
 * ============================================================================ */

static void parser_init(Parser* p, const char* text) {
    memset(p, 0, sizeof(Parser));
    p->original = text;
    parse_directives(p, text);
    cursor_init(&p->cur, p->src, p->flags.extended);
    p->cap_count = 0;
    p->cap_names = NULL;
    p->cap_names_count = 0;
    p->cap_names_capacity = 0;
    p->error = NULL;
}

static void parser_cleanup(Parser* p) {
    for (size_t i = 0; i < p->cap_names_count; i++) {
        free(p->cap_names[i]);
    }
    free(p->cap_names);
}

static STRlingASTNode* parser_parse(Parser* p) {
    STRlingASTNode* node = parse_alt(p);
    if (p->error) {
        strling_ast_node_free(node);
        return NULL;
    }
    cursor_skip_ws_and_comments(&p->cur);
    if (!cursor_eof(&p->cur)) {
        char ch = cursor_peek(&p->cur, 0);
        if (ch == ')') {
            parser_set_error(p, "Unmatched ')'", (int)p->cur.i);
        } else {
            parser_set_error(p, "Unexpected trailing input", (int)p->cur.i);
        }
        strling_ast_node_free(node);
        return NULL;
    }
    return node;
}

static STRlingASTNode* parse_alt(Parser* p) {
    if (p->error) return NULL;

    cursor_skip_ws_and_comments(&p->cur);
    if (cursor_peek(&p->cur, 0) == '|') {
        parser_set_error(p, "Alternation lacks left-hand side", (int)p->cur.i);
        return NULL;
    }

    STRlingASTNode** branches = NULL;
    size_t nbranches = 0;
    size_t capacity = 0;

    STRlingASTNode* first = parse_seq(p);
    if (p->error || !first) {
        return NULL;
    }

    /* Check for more branches */
    cursor_skip_ws_and_comments(&p->cur);
    if (cursor_peek(&p->cur, 0) != '|') {
        return first; /* Single branch, no Alt needed */
    }

    /* Multiple branches */
    capacity = 4;
    branches = (STRlingASTNode**)malloc(capacity * sizeof(STRlingASTNode*));
    branches[nbranches++] = first;

    while (cursor_peek(&p->cur, 0) == '|') {
        cursor_take(&p->cur); /* consume '|' */
        cursor_skip_ws_and_comments(&p->cur);
        
        if (cursor_eof(&p->cur) || cursor_peek(&p->cur, 0) == '|') {
            parser_set_error(p, "Alternation lacks right-hand side", (int)p->cur.i);
            for (size_t i = 0; i < nbranches; i++) strling_ast_node_free(branches[i]);
            free(branches);
            return NULL;
        }

        STRlingASTNode* branch = parse_seq(p);
        if (p->error || !branch) {
            for (size_t i = 0; i < nbranches; i++) strling_ast_node_free(branches[i]);
            free(branches);
            return NULL;
        }

        if (nbranches >= capacity) {
            capacity *= 2;
            branches = (STRlingASTNode**)realloc(branches, capacity * sizeof(STRlingASTNode*));
        }
        branches[nbranches++] = branch;
        cursor_skip_ws_and_comments(&p->cur);
    }

    STRlingASTNode* alt = strling_ast_alt_create(branches, nbranches);
    free(branches);
    return alt;
}

static STRlingASTNode* parse_seq(Parser* p) {
    if (p->error) return NULL;

    STRlingASTNode** parts = NULL;
    size_t nparts = 0;
    size_t capacity = 0;

    while (1) {
        cursor_skip_ws_and_comments(&p->cur);
        char ch = cursor_peek(&p->cur, 0);

        /* Check for invalid quantifier at start */
        if ((ch == '*' || ch == '+' || ch == '?' || ch == '{') && nparts == 0) {
            parser_set_error(p, "Invalid quantifier - nothing to quantify", (int)p->cur.i);
            goto cleanup;
        }

        if (ch == '\0' || ch == '|' || ch == ')') break;

        STRlingASTNode* atom = parse_atom(p);
        if (p->error) goto cleanup;
        if (!atom) break;

        atom = parse_quant_if_any(p, atom);
        if (p->error) {
            strling_ast_node_free(atom);
            goto cleanup;
        }

        if (nparts >= capacity) {
            capacity = capacity == 0 ? 4 : capacity * 2;
            parts = (STRlingASTNode**)realloc(parts, capacity * sizeof(STRlingASTNode*));
        }
        parts[nparts++] = atom;
    }

    if (nparts == 0) {
        return strling_ast_seq_create(NULL, 0);
    }
    if (nparts == 1) {
        STRlingASTNode* single = parts[0];
        free(parts);
        return single;
    }

    STRlingASTNode* seq = strling_ast_seq_create(parts, nparts);
    free(parts);
    return seq;

cleanup:
    for (size_t i = 0; i < nparts; i++) strling_ast_node_free(parts[i]);
    free(parts);
    return NULL;
}

static STRlingASTNode* parse_atom(Parser* p) {
    if (p->error) return NULL;

    cursor_skip_ws_and_comments(&p->cur);
    char ch = cursor_peek(&p->cur, 0);

    if (ch == '\0') return NULL;

    if (ch == '.') {
        cursor_take(&p->cur);
        return strling_ast_dot_create();
    }
    if (ch == '^') {
        cursor_take(&p->cur);
        return strling_ast_anchor_create("Start");
    }
    if (ch == '$') {
        cursor_take(&p->cur);
        return strling_ast_anchor_create("End");
    }
    if (ch == '(') {
        return parse_group_or_look(p);
    }
    if (ch == '[') {
        return parse_char_class(p);
    }
    if (ch == '\\') {
        return parse_escape_atom(p);
    }
    if (ch == ')') {
        parser_set_error(p, "Unmatched ')'", (int)p->cur.i);
        return NULL;
    }
    if (ch == '|') {
        return NULL;
    }

    /* Literal character */
    char lit[2] = { cursor_take(&p->cur), '\0' };
    return strling_ast_lit_create(lit);
}

static STRlingASTNode* parse_quant_if_any(Parser* p, STRlingASTNode* child) {
    if (p->error || !child) return child;

    char ch = cursor_peek(&p->cur, 0);
    int minv = -1, maxv = -1;
    const char* mode = "Greedy";

    if (ch == '*') {
        minv = 0; maxv = -1;
        cursor_take(&p->cur);
    } else if (ch == '+') {
        minv = 1; maxv = -1;
        cursor_take(&p->cur);
    } else if (ch == '?') {
        minv = 0; maxv = 1;
        cursor_take(&p->cur);
    } else if (ch == '{') {
        size_t save = p->cur.i;
        cursor_take(&p->cur); /* consume '{' */

        /* Read min */
        int m = 0;
        int has_min = 0;
        while (isdigit(cursor_peek(&p->cur, 0))) {
            m = m * 10 + (cursor_peek(&p->cur, 0) - '0');
            cursor_take(&p->cur);
            has_min = 1;
        }

        if (!has_min) {
            /* Not a valid quantifier, backtrack */
            p->cur.i = save;
            return child;
        }

        minv = m;
        maxv = m;

        if (cursor_peek(&p->cur, 0) == ',') {
            cursor_take(&p->cur);
            if (cursor_peek(&p->cur, 0) == '}') {
                maxv = -1; /* Infinity */
            } else {
                int n = 0;
                while (isdigit(cursor_peek(&p->cur, 0))) {
                    n = n * 10 + (cursor_peek(&p->cur, 0) - '0');
                    cursor_take(&p->cur);
                }
                maxv = n;
            }
        }

        if (cursor_peek(&p->cur, 0) != '}') {
            parser_set_error(p, "Incomplete quantifier", (int)p->cur.i);
            return child;
        }
        cursor_take(&p->cur);
    } else {
        return child;
    }

    /* Check for anchor quantification */
    if (child->type == AST_TYPE_ANCHOR) {
        parser_set_error(p, "Cannot quantify anchor", (int)p->cur.i);
        return child;
    }

    /* Check for lazy/possessive mode */
    char nxt = cursor_peek(&p->cur, 0);
    if (nxt == '?') {
        mode = "Lazy";
        cursor_take(&p->cur);
    } else if (nxt == '+') {
        mode = "Possessive";
        cursor_take(&p->cur);
    }

    return strling_ast_quant_create(child, minv, maxv, mode);
}

static STRlingASTNode* parse_group_or_look(Parser* p) {
    if (cursor_take(&p->cur) != '(') {
        parser_set_error(p, "Expected '('", (int)p->cur.i);
        return NULL;
    }

    /* Non-capturing group */
    if (cursor_match(&p->cur, "?:")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated group", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_group_create(0, body, NULL, 0);
    }

    /* Lookbehind positive */
    if (cursor_match(&p->cur, "?<=")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated lookbehind", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_look_create("Behind", 0, body);
    }

    /* Lookbehind negative */
    if (cursor_match(&p->cur, "?<!")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated lookbehind", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_look_create("Behind", 1, body);
    }

    /* Named capturing group */
    if (cursor_match(&p->cur, "?<")) {
        char name[256];
        size_t name_len = 0;
        while (cursor_peek(&p->cur, 0) != '>' && cursor_peek(&p->cur, 0) != '\0' && name_len < 255) {
            name[name_len++] = cursor_take(&p->cur);
        }
        name[name_len] = '\0';

        if (!cursor_match(&p->cur, ">")) {
            parser_set_error(p, "Unterminated group name", (int)p->cur.i);
            return NULL;
        }

        if (has_cap_name(p, name)) {
            parser_set_error(p, "Duplicate group name", (int)p->cur.i);
            return NULL;
        }

        p->cap_count++;
        add_cap_name(p, name);

        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated group", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_group_create(1, body, name, 0);
    }

    /* Atomic group */
    if (cursor_match(&p->cur, "?>")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated atomic group", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_group_create(0, body, NULL, 1);
    }

    /* Lookahead positive */
    if (cursor_match(&p->cur, "?=")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated lookahead", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_look_create("Ahead", 0, body);
    }

    /* Lookahead negative */
    if (cursor_match(&p->cur, "?!")) {
        STRlingASTNode* body = parse_alt(p);
        if (p->error) return NULL;
        if (!cursor_match(&p->cur, ")")) {
            parser_set_error(p, "Unterminated lookahead", (int)p->cur.i);
            strling_ast_node_free(body);
            return NULL;
        }
        return strling_ast_look_create("Ahead", 1, body);
    }

    /* Regular capturing group */
    p->cap_count++;
    STRlingASTNode* body = parse_alt(p);
    if (p->error) return NULL;
    if (!cursor_match(&p->cur, ")")) {
        parser_set_error(p, "Unterminated group", (int)p->cur.i);
        strling_ast_node_free(body);
        return NULL;
    }
    return strling_ast_group_create(1, body, NULL, 0);
}

static STRlingASTNode* parse_char_class(Parser* p) {
    if (cursor_take(&p->cur) != '[') {
        parser_set_error(p, "Expected '['", (int)p->cur.i);
        return NULL;
    }
    p->cur.in_class++;

    int neg = 0;
    if (cursor_peek(&p->cur, 0) == '^') {
        neg = 1;
        cursor_take(&p->cur);
    }

    STRlingClassItem** items = NULL;
    size_t nitems = 0;
    size_t capacity = 0;

    while (!cursor_eof(&p->cur) && cursor_peek(&p->cur, 0) != ']') {
        STRlingClassItem* item = NULL;

        if (cursor_peek(&p->cur, 0) == '\\') {
            item = parse_class_escape(p);
        } else {
            char ch = cursor_take(&p->cur);
            
            /* Check for range */
            if (cursor_peek(&p->cur, 0) == '-' && cursor_peek(&p->cur, 1) != ']') {
                cursor_take(&p->cur); /* consume '-' */
                char end_ch = cursor_take(&p->cur);
                char from[2] = { ch, '\0' };
                char to[2] = { end_ch, '\0' };
                item = strling_class_range_create(from, to);
            } else {
                char lit[2] = { ch, '\0' };
                item = strling_class_literal_create(lit);
            }
        }

        if (p->error) goto cleanup;
        if (!item) continue;

        if (nitems >= capacity) {
            capacity = capacity == 0 ? 4 : capacity * 2;
            items = (STRlingClassItem**)realloc(items, capacity * sizeof(STRlingClassItem*));
        }
        items[nitems++] = item;
    }

    if (cursor_eof(&p->cur)) {
        parser_set_error(p, "Unterminated character class", (int)p->cur.i);
        goto cleanup;
    }

    cursor_take(&p->cur); /* consume ']' */
    p->cur.in_class--;

    STRlingASTNode* cc = strling_ast_charclass_create(neg, items, nitems);
    free(items);
    return cc;

cleanup:
    for (size_t i = 0; i < nitems; i++) strling_class_item_free(items[i]);
    free(items);
    p->cur.in_class--;
    return NULL;
}

static STRlingClassItem* parse_class_escape(Parser* p) {
    if (cursor_take(&p->cur) != '\\') {
        parser_set_error(p, "Expected '\\'", (int)p->cur.i);
        return NULL;
    }

    char nxt = cursor_peek(&p->cur, 0);

    /* Shorthand classes */
    if (nxt == 'd' || nxt == 'D' || nxt == 'w' || nxt == 'W' || nxt == 's' || nxt == 'S') {
        char type[2] = { cursor_take(&p->cur), '\0' };
        return strling_class_escape_create(type, NULL);
    }

    /* Unicode property */
    if (nxt == 'p' || nxt == 'P') {
        char tp = cursor_take(&p->cur);
        if (!cursor_match(&p->cur, "{")) {
            parser_set_error(p, "Expected '{' after \\p/\\P", (int)p->cur.i);
            return NULL;
        }
        char prop[256];
        size_t prop_len = 0;
        while (cursor_peek(&p->cur, 0) != '}' && cursor_peek(&p->cur, 0) != '\0' && prop_len < 255) {
            prop[prop_len++] = cursor_take(&p->cur);
        }
        prop[prop_len] = '\0';
        if (!cursor_match(&p->cur, "}")) {
            parser_set_error(p, "Unterminated \\p{...}", (int)p->cur.i);
            return NULL;
        }
        char type[2] = { tp, '\0' };
        return strling_class_escape_create(type, prop);
    }

    /* Control escapes */
    if (is_control_escape(nxt)) {
        cursor_take(&p->cur);
        char lit[2] = { control_escape(nxt), '\0' };
        return strling_class_literal_create(lit);
    }

    /* Backspace in class */
    if (nxt == 'b') {
        cursor_take(&p->cur);
        char lit[2] = { '\x08', '\0' };
        return strling_class_literal_create(lit);
    }

    /* Null */
    if (nxt == '0') {
        cursor_take(&p->cur);
        char lit[2] = { '\0', '\0' };
        return strling_class_literal_create(lit);
    }

    /* Identity escape */
    char ch = cursor_take(&p->cur);
    char lit[2] = { ch, '\0' };
    return strling_class_literal_create(lit);
}

static STRlingASTNode* parse_escape_atom(Parser* p) {
    size_t start_pos = p->cur.i;
    if (cursor_take(&p->cur) != '\\') {
        parser_set_error(p, "Expected '\\'", (int)p->cur.i);
        return NULL;
    }

    char nxt = cursor_peek(&p->cur, 0);

    /* Backreference by index */
    if (isdigit(nxt) && nxt != '0') {
        int num = 0;
        while (isdigit(cursor_peek(&p->cur, 0))) {
            num = num * 10 + (cursor_peek(&p->cur, 0) - '0');
            cursor_take(&p->cur);
            if (num > p->cap_count) {
                parser_set_error(p, "Backreference to undefined group", (int)start_pos);
                return NULL;
            }
        }
        return strling_ast_backref_create(num, NULL);
    }

    /* Anchors */
    if (nxt == 'b') { cursor_take(&p->cur); return strling_ast_anchor_create("WordBoundary"); }
    if (nxt == 'B') { cursor_take(&p->cur); return strling_ast_anchor_create("NotWordBoundary"); }
    if (nxt == 'A') { cursor_take(&p->cur); return strling_ast_anchor_create("AbsoluteStart"); }
    if (nxt == 'Z') { cursor_take(&p->cur); return strling_ast_anchor_create("EndBeforeFinalNewline"); }

    /* Named backref \k<name> */
    if (nxt == 'k') {
        cursor_take(&p->cur);
        if (!cursor_match(&p->cur, "<")) {
            parser_set_error(p, "Expected '<' after \\k", (int)start_pos);
            return NULL;
        }
        char name[256];
        size_t name_len = 0;
        while (cursor_peek(&p->cur, 0) != '>' && cursor_peek(&p->cur, 0) != '\0' && name_len < 255) {
            name[name_len++] = cursor_take(&p->cur);
        }
        name[name_len] = '\0';
        if (!cursor_match(&p->cur, ">")) {
            parser_set_error(p, "Unterminated named backref", (int)start_pos);
            return NULL;
        }
        if (!has_cap_name(p, name)) {
            parser_set_error(p, "Backreference to undefined group", (int)start_pos);
            return NULL;
        }
        return strling_ast_backref_create(-1, name);
    }

    /* Shorthand classes */
    if (nxt == 'd' || nxt == 'D' || nxt == 'w' || nxt == 'W' || nxt == 's' || nxt == 'S') {
        cursor_take(&p->cur);
        char type[2] = { nxt, '\0' };
        STRlingClassItem* items[1];
        items[0] = strling_class_escape_create(type, NULL);
        return strling_ast_charclass_create(0, items, 1);
    }

    /* Unicode property */
    if (nxt == 'p' || nxt == 'P') {
        char tp = cursor_take(&p->cur);
        if (!cursor_match(&p->cur, "{")) {
            parser_set_error(p, "Expected '{' after \\p/\\P", (int)start_pos);
            return NULL;
        }
        char prop[256];
        size_t prop_len = 0;
        while (cursor_peek(&p->cur, 0) != '}' && cursor_peek(&p->cur, 0) != '\0' && prop_len < 255) {
            prop[prop_len++] = cursor_take(&p->cur);
        }
        prop[prop_len] = '\0';
        if (!cursor_match(&p->cur, "}")) {
            parser_set_error(p, "Unterminated \\p{...}", (int)start_pos);
            return NULL;
        }
        char type[2] = { tp, '\0' };
        STRlingClassItem* items[1];
        items[0] = strling_class_escape_create(type, prop);
        return strling_ast_charclass_create(0, items, 1);
    }

    /* Control escapes */
    if (is_control_escape(nxt)) {
        cursor_take(&p->cur);
        char lit[2] = { control_escape(nxt), '\0' };
        return strling_ast_lit_create(lit);
    }

    /* Hex escape \xHH */
    if (nxt == 'x') {
        cursor_take(&p->cur);
        if (cursor_peek(&p->cur, 0) == '{') {
            cursor_take(&p->cur);
            int val = 0;
            while (isxdigit(cursor_peek(&p->cur, 0))) {
                char c = cursor_take(&p->cur);
                int d = isdigit(c) ? c - '0' : (tolower(c) - 'a' + 10);
                val = val * 16 + d;
            }
            if (!cursor_match(&p->cur, "}")) {
                parser_set_error(p, "Unterminated \\x{...}", (int)start_pos);
                return NULL;
            }
            char lit[5];
            if (val < 128) {
                lit[0] = (char)val; lit[1] = '\0';
            } else {
                /* Simple UTF-8 encoding for basic cases */
                lit[0] = '?'; lit[1] = '\0';
            }
            return strling_ast_lit_create(lit);
        } else {
            char h1 = cursor_take(&p->cur);
            char h2 = cursor_take(&p->cur);
            if (!isxdigit(h1) || !isxdigit(h2)) {
                parser_set_error(p, "Invalid \\xHH escape", (int)start_pos);
                return NULL;
            }
            int d1 = isdigit(h1) ? h1 - '0' : (tolower(h1) - 'a' + 10);
            int d2 = isdigit(h2) ? h2 - '0' : (tolower(h2) - 'a' + 10);
            char lit[2] = { (char)(d1 * 16 + d2), '\0' };
            return strling_ast_lit_create(lit);
        }
    }

    /* Unicode escape \uHHHH */
    if (nxt == 'u') {
        cursor_take(&p->cur);
        if (cursor_peek(&p->cur, 0) == '{') {
            cursor_take(&p->cur);
            int val = 0;
            while (isxdigit(cursor_peek(&p->cur, 0))) {
                char c = cursor_take(&p->cur);
                int d = isdigit(c) ? c - '0' : (tolower(c) - 'a' + 10);
                val = val * 16 + d;
            }
            if (!cursor_match(&p->cur, "}")) {
                parser_set_error(p, "Unterminated \\u{...}", (int)start_pos);
                return NULL;
            }
            char lit[2] = { '?', '\0' }; /* Simplified */
            return strling_ast_lit_create(lit);
        } else {
            /* \uHHHH */
            int val = 0;
            for (int i = 0; i < 4; i++) {
                char c = cursor_take(&p->cur);
                if (!isxdigit(c)) {
                    parser_set_error(p, "Invalid \\uHHHH escape", (int)start_pos);
                    return NULL;
                }
                int d = isdigit(c) ? c - '0' : (tolower(c) - 'a' + 10);
                val = val * 16 + d;
            }
            char lit[2] = { (char)(val < 128 ? val : '?'), '\0' };
            return strling_ast_lit_create(lit);
        }
    }

    /* Null */
    if (nxt == '0') {
        cursor_take(&p->cur);
        char lit[2] = { '\0', '\0' };
        return strling_ast_lit_create(lit);
    }

    /* Identity escape */
    char ch = cursor_take(&p->cur);
    char lit[2] = { ch, '\0' };
    return strling_ast_lit_create(lit);
}

/* ============================================================================
 * Public API
 * ============================================================================ */

STRlingParseResult* strling_parse(const char* src) {
    STRlingParseResult* result = (STRlingParseResult*)malloc(sizeof(STRlingParseResult));
    if (!result) return NULL;

    Parser p;
    parser_init(&p, src);

    result->flags = p.flags;
    result->root = parser_parse(&p);
    result->error = p.error;

    parser_cleanup(&p);

    return result;
}

void strling_parse_result_free(STRlingParseResult* result) {
    if (!result) return;
    strling_ast_node_free(result->root);
    strling_error_free(result->error);
    free(result);
}
