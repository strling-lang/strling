/// E2E Tests - Black-box testing where DSL input produces a regex
/// that matches expected strings.
module E2ETests

open System
open System.Text.RegularExpressions
open Xunit
open STRling

let compileToRegex (dsl: string) =
    let flags, ast = Parser.parse dsl
    let ir = Compiler.compile ast
    Pcre2.emit ir flags

// ============================================================================
// Phone Number E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Phone Number - matches valid formats`` () =
    let regex = compileToRegex @"^(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("555-123-4567"))
    Assert.True(re.IsMatch("555.123.4567"))
    Assert.True(re.IsMatch("555 123 4567"))
    Assert.True(re.IsMatch("5551234567"))

[<Fact>]
let ``E2E Phone Number - rejects invalid formats`` () =
    let regex = compileToRegex @"^(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})$"
    let re = Regex(regex)

    Assert.False(re.IsMatch("55-123-4567"))
    Assert.False(re.IsMatch("555-12-4567"))
    Assert.False(re.IsMatch("555-123-456"))
    Assert.False(re.IsMatch("abc-def-ghij"))

// ============================================================================
// Email E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Email - matches valid formats`` () =
    let regex = compileToRegex @"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("user@example.com"))
    Assert.True(re.IsMatch("test.user@domain.org"))

[<Fact>]
let ``E2E Email - rejects invalid formats`` () =
    let regex = compileToRegex @"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    let re = Regex(regex)

    Assert.False(re.IsMatch("@example.com"))
    Assert.False(re.IsMatch("user@"))
    Assert.False(re.IsMatch("user@.com"))

// ============================================================================
// IPv4 E2E Tests
// ============================================================================

[<Fact>]
let ``E2E IPv4 - matches valid addresses`` () =
    let regex = compileToRegex @"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("192.168.1.1"))
    Assert.True(re.IsMatch("10.0.0.1"))
    Assert.True(re.IsMatch("255.255.255.255"))
    Assert.True(re.IsMatch("0.0.0.0"))

[<Fact>]
let ``E2E IPv4 - rejects invalid addresses`` () =
    let regex = compileToRegex @"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
    let re = Regex(regex)

    Assert.False(re.IsMatch("192.168.1"))
    Assert.False(re.IsMatch("192.168.1.1.1"))
    Assert.False(re.IsMatch("192-168-1-1"))

// ============================================================================
// Hex Color E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Hex Color - matches valid colors`` () =
    let regex = compileToRegex @"^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("#ffffff"))
    Assert.True(re.IsMatch("#000000"))
    Assert.True(re.IsMatch("#ABC123"))
    Assert.True(re.IsMatch("#fff"))
    Assert.True(re.IsMatch("#F00"))

[<Fact>]
let ``E2E Hex Color - rejects invalid colors`` () =
    let regex = compileToRegex @"^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$"
    let re = Regex(regex)

    Assert.False(re.IsMatch("ffffff"))
    Assert.False(re.IsMatch("#ffff"))
    Assert.False(re.IsMatch("#GGGGGG"))

// ============================================================================
// Date E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Date - matches valid dates`` () =
    let regex = compileToRegex @"^(\d{4})-(\d{2})-(\d{2})$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("2024-01-15"))
    Assert.True(re.IsMatch("2000-12-31"))
    Assert.True(re.IsMatch("1999-06-30"))

[<Fact>]
let ``E2E Date - rejects invalid dates`` () =
    let regex = compileToRegex @"^(\d{4})-(\d{2})-(\d{2})$"
    let re = Regex(regex)

    Assert.False(re.IsMatch("24-01-15"))
    Assert.False(re.IsMatch("2024/01/15"))
    Assert.False(re.IsMatch("2024-1-15"))

// ============================================================================
// Lookahead E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Positive Lookahead`` () =
    let regex = compileToRegex "foo(?=bar)"
    let re = Regex(regex)

    Assert.True(re.IsMatch("foobar"))
    Assert.False(re.IsMatch("foobaz"))

[<Fact>]
let ``E2E Negative Lookahead`` () =
    let regex = compileToRegex "foo(?!bar)"
    let re = Regex(regex)

    Assert.True(re.IsMatch("foobaz"))

// ============================================================================
// Word Boundary E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Word Boundary`` () =
    let regex = compileToRegex @"\bword\b"
    let re = Regex(regex)

    Assert.True(re.IsMatch("word"))
    Assert.True(re.IsMatch("a word here"))
    Assert.False(re.IsMatch("sword"))
    Assert.False(re.IsMatch("wording"))

// ============================================================================
// Alternation E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Alternation`` () =
    let regex = compileToRegex @"^(cat|dog|bird)$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("cat"))
    Assert.True(re.IsMatch("dog"))
    Assert.True(re.IsMatch("bird"))
    Assert.False(re.IsMatch("cats"))
    Assert.False(re.IsMatch("fish"))

// ============================================================================
// Quantifier E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Quantifier Plus`` () =
    let regex = compileToRegex @"^a+$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("a"))
    Assert.True(re.IsMatch("aa"))
    Assert.True(re.IsMatch("aaa"))
    Assert.False(re.IsMatch(""))
    Assert.False(re.IsMatch("b"))

[<Fact>]
let ``E2E Quantifier Star`` () =
    let regex = compileToRegex @"^a*$"
    let re = Regex(regex)

    Assert.True(re.IsMatch(""))
    Assert.True(re.IsMatch("a"))
    Assert.True(re.IsMatch("aaa"))
    Assert.False(re.IsMatch("b"))

[<Fact>]
let ``E2E Quantifier Optional`` () =
    let regex = compileToRegex @"^a?$"
    let re = Regex(regex)

    Assert.True(re.IsMatch(""))
    Assert.True(re.IsMatch("a"))
    Assert.False(re.IsMatch("aa"))

[<Fact>]
let ``E2E Quantifier Exact`` () =
    let regex = compileToRegex @"^a{3}$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("aaa"))
    Assert.False(re.IsMatch("a"))
    Assert.False(re.IsMatch("aa"))
    Assert.False(re.IsMatch("aaaa"))

[<Fact>]
let ``E2E Quantifier Range`` () =
    let regex = compileToRegex @"^a{2,4}$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("aa"))
    Assert.True(re.IsMatch("aaa"))
    Assert.True(re.IsMatch("aaaa"))
    Assert.False(re.IsMatch("a"))
    Assert.False(re.IsMatch("aaaaa"))

[<Fact>]
let ``E2E Quantifier AtLeast`` () =
    let regex = compileToRegex @"^a{2,}$"
    let re = Regex(regex)

    Assert.True(re.IsMatch("aa"))
    Assert.True(re.IsMatch("aaa"))
    Assert.True(re.IsMatch("aaaa"))
    Assert.False(re.IsMatch(""))
    Assert.False(re.IsMatch("a"))

// ============================================================================
// Capture Groups E2E Tests
// ============================================================================

[<Fact>]
let ``E2E Capture Groups`` () =
    let regex = compileToRegex @"^(\d{4})-(\d{2})-(\d{2})$"
    let re = Regex(regex)
    let m = re.Match("2024-12-25")

    Assert.True(m.Success)
    Assert.Equal("2024", m.Groups.[1].Value)
    Assert.Equal("12", m.Groups.[2].Value)
    Assert.Equal("25", m.Groups.[3].Value)
