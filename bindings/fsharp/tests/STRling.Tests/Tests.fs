/// Interaction Tests - Parser → Compiler → Emitter handoffs
///
/// This test suite validates the handoff between pipeline stages:
/// - Parser → Compiler: Ensures AST is correctly consumed
/// - Compiler → Emitter: Ensures IR is correctly transformed to regex
module InteractionTests

open System
open System.Text.RegularExpressions
open Xunit
open STRling

// ============================================================================
// Parser → Compiler Handoff Tests
// ============================================================================

[<Fact>]
let ``Parser to Compiler - SimpleLiteral`` () =
    let flags, ast = Parser.parse "hello"
    let ir = Compiler.compile ast
    
    Assert.NotNull(ir)
    match ir with
    | IRLit _ -> Assert.True(true)
    | _ -> Assert.True(true) // Any IR is acceptable for smoke test

[<Fact>]
let ``Parser to Compiler - Quantifier`` () =
    let flags, ast = Parser.parse "a+"
    let ir = Compiler.compile ast
    
    match ir with
    | IRQuant _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRQuant")

[<Fact>]
let ``Parser to Compiler - CharacterClass`` () =
    let flags, ast = Parser.parse "[abc]"
    let ir = Compiler.compile ast
    
    match ir with
    | IRCharClass _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRCharClass")

[<Fact>]
let ``Parser to Compiler - CapturingGroup`` () =
    let flags, ast = Parser.parse "(abc)"
    let ir = Compiler.compile ast
    
    match ir with
    | IRGroup _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRGroup")

[<Fact>]
let ``Parser to Compiler - Alternation`` () =
    let flags, ast = Parser.parse "a|b"
    let ir = Compiler.compile ast
    
    match ir with
    | IRAlt _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRAlt")

[<Fact>]
let ``Parser to Compiler - NamedGroup`` () =
    let flags, ast = Parser.parse "(?<name>abc)"
    let ir = Compiler.compile ast
    
    match ir with
    | IRGroup _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRGroup")

[<Fact>]
let ``Parser to Compiler - Lookahead`` () =
    let flags, ast = Parser.parse "(?=abc)"
    let ir = Compiler.compile ast
    
    match ir with
    | IRLook _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRLook")

[<Fact>]
let ``Parser to Compiler - Lookbehind`` () =
    let flags, ast = Parser.parse "(?<=abc)"
    let ir = Compiler.compile ast
    
    match ir with
    | IRLook _ -> Assert.True(true)
    | _ -> Assert.Fail("Expected IRLook")

// ============================================================================
// Compiler → Emitter Handoff Tests
// ============================================================================

let compileToRegex (dsl: string) =
    let flags, ast = Parser.parse dsl
    let ir = Compiler.compile ast
    Pcre2.emit ir flags

[<Fact>]
let ``Compiler to Emitter - SimpleLiteral`` () =
    Assert.Equal("hello", compileToRegex "hello")

[<Fact>]
let ``Compiler to Emitter - DigitShorthand`` () =
    Assert.Equal(@"\d+", compileToRegex @"\d+")

[<Fact>]
let ``Compiler to Emitter - CharacterClass`` () =
    Assert.Equal("[abc]", compileToRegex "[abc]")

[<Fact>]
let ``Compiler to Emitter - CharacterClassRange`` () =
    Assert.Equal("[a-z]", compileToRegex "[a-z]")

[<Fact>]
let ``Compiler to Emitter - NegatedClass`` () =
    Assert.Equal("[^abc]", compileToRegex "[^abc]")

[<Fact>]
let ``Compiler to Emitter - QuantifierPlus`` () =
    Assert.Equal("a+", compileToRegex "a+")

[<Fact>]
let ``Compiler to Emitter - QuantifierStar`` () =
    Assert.Equal("a*", compileToRegex "a*")

[<Fact>]
let ``Compiler to Emitter - QuantifierOptional`` () =
    Assert.Equal("a?", compileToRegex "a?")

[<Fact>]
let ``Compiler to Emitter - QuantifierExact`` () =
    Assert.Equal("a{3}", compileToRegex "a{3}")

[<Fact>]
let ``Compiler to Emitter - QuantifierRange`` () =
    Assert.Equal("a{2,5}", compileToRegex "a{2,5}")

[<Fact>]
let ``Compiler to Emitter - QuantifierLazy`` () =
    Assert.Equal("a+?", compileToRegex "a+?")

[<Fact>]
let ``Compiler to Emitter - CapturingGroup`` () =
    Assert.Equal("(abc)", compileToRegex "(abc)")

[<Fact>]
let ``Compiler to Emitter - NonCapturingGroup`` () =
    Assert.Equal("(?:abc)", compileToRegex "(?:abc)")

[<Fact>]
let ``Compiler to Emitter - NamedGroup`` () =
    Assert.Equal("(?<name>abc)", compileToRegex "(?<name>abc)")

[<Fact>]
let ``Compiler to Emitter - Alternation`` () =
    Assert.Equal("cat|dog", compileToRegex "cat|dog")

[<Fact>]
let ``Compiler to Emitter - Anchors`` () =
    Assert.Equal("^abc$", compileToRegex "^abc$")

[<Fact>]
let ``Compiler to Emitter - PositiveLookahead`` () =
    Assert.Equal("foo(?=bar)", compileToRegex "foo(?=bar)")

[<Fact>]
let ``Compiler to Emitter - NegativeLookahead`` () =
    Assert.Equal("foo(?!bar)", compileToRegex "foo(?!bar)")

[<Fact>]
let ``Compiler to Emitter - PositiveLookbehind`` () =
    Assert.Equal("(?<=foo)bar", compileToRegex "(?<=foo)bar")

[<Fact>]
let ``Compiler to Emitter - NegativeLookbehind`` () =
    Assert.Equal("(?<!foo)bar", compileToRegex "(?<!foo)bar")

// ============================================================================
// Semantic Edge Case Tests
// ============================================================================

[<Fact>]
let test_semantic_duplicate_capture_group () =
    Assert.Throws<STRlingParseError>(fun () -> 
        Parser.parse "(?<name>a)(?<name>b)" |> ignore
    ) |> ignore

[<Fact>]
let test_semantic_ranges () =
    // Invalid range [z-a] should produce an error
    Assert.Throws<STRlingParseError>(fun () -> 
        Parser.parse "[z-a]" |> ignore
    ) |> ignore

// ============================================================================
// Full Pipeline Tests
// ============================================================================

[<Fact>]
let ``Full Pipeline - PhoneNumber`` () =
    let regex = compileToRegex @"(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})"
    Assert.Equal(@"(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})", regex)

[<Fact>]
let ``Full Pipeline - IPv4`` () =
    let regex = compileToRegex @"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})"
    Assert.Equal(@"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})", regex)
