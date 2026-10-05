# Semantic frontend token storage regression

## Scope and authority

This implementation regression test supports the H08 editor/parser performance
correction. The ratified `spec/frontends/semantic/1.0` grammar, lexical rules,
diagnostics, formatting and Semantic IR mapping remain authoritative and
unchanged. Editor projection remains non-normative. Test agreement cannot
authorize new syntax or altered semantics.

## Cases

-   Words and numeric spellings borrow their exact immutable source slices.
-   Cloning an unescaped token preserves that same slice instead of allocating.
-   UTF-8 words, CRLF layout and comments retain their original byte spans.
-   Escaped strings remain decoded owned values with unchanged source spans.
-   String parsing moves the checked decoded token into owned syntax; it does not
    clone it or change the ordering of the next-token lexical check.
-   EOF retains the exact end-of-input span.

## Verification and completion

The private regression lives in `core/src/semantic_frontend.rs`. Existing
`semantic_frontend`, `semantic_frontend_properties` and `editor_intelligence`
integration suites retain all cases and independently authored expectations.
Complete core tests, registered generated-artifact verification and both
source-distinct certification campaigns must still pass. No performance
baseline, limit, sample count, conditioning or isolation gate is changed by
this test or correction.
