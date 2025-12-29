# API Reference - F#

[← Back to README](../README.md) | [Developer Hub](../../../docs/index.md)

This document provides a comprehensive reference for the STRling API in **F#**.

## Table of Contents

-   [Anchors](#anchors)
-   [Character Classes](#character-classes)
-   [Escape Sequences](#escape-sequences)
-   [Quantifiers](#quantifiers)
-   [Groups](#groups)
-   [Lookarounds](#lookarounds)
-   [Logic](#logic)
-   [References](#references)
-   [Flags & Modifiers](#flags--modifiers)

---

## Anchors

Anchors match a position within the string, not a character itself.

### Start/End of Line

Matches the beginning (`^`) or end (`$`) of a line.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); lit "abc"; end' () ]
// Start of line, literal "abc", end of line
// Compiles to: ^abc$
```

### Start/End of String

Matches the absolute beginning (`\A`) or end (`\z`) of the string, ignoring multiline mode.

#### Usage (F#)

```fsharp
open STRling.Simply

// For absolute anchors, use emitter directives or explicit anchor types
let pattern = merge [ start (); lit "hello"; end' () ]
// Compiles to: ^hello$
```

### Word Boundaries

Matches the position between a word character and a non-word character (`\b`), or the inverse (`\B`).

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); capture (letter ()); bound (); capture (digit ()); end' () ]
// Word boundary (\b) separates letters from digits
// Compiles to: ^([a-zA-Z])\b(\d)$
```

---

## Character Classes

### Built-in Classes

Standard shorthands for common character sets.

-   `\w`: Word characters (alphanumeric + underscore)
-   `\d`: Digits
-   `\s`: Whitespace
-   `.`: Any character (except newline)

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); capture (digit 3); end' () ]
// Match exactly 3 digits (\d{3})
// Compiles to: ^(\d{3})$
```

### Custom Classes & Ranges

Define a set of allowed characters (`[...]`) or a range (`a-z`).

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); anyOf "abc"; end' () ]
// Match one of: a, b, or c (custom class)
// Compiles to: ^[abc]$
```

### Negated Classes

Match any character _not_ in the set (`[^...]`).

#### Usage (F#)

```fsharp
open STRling.Simply

let notVowels = notInChars "aeiou"
let pattern = merge [ start (); notVowels; end' () ]
// Match any character except vowels
// Compiles to: ^[^aeiou]$
```

### Unicode Properties

Match characters based on Unicode properties (`\p{...}`), such as scripts, categories, or blocks.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); charProperty "Lu"; end' () ]
// Match a Unicode uppercase letter (\p{Lu})
// Compiles to: ^\p{Lu}$
```

## Escape Sequences

Represent special characters, control codes, and numeric character code escapes.

### Control Characters

Standard control escapes supported across most engines:

-   `\\n`: Newline
-   `\\r`: Carriage Return
-   `\\t`: Tab
-   `\\f`: Form Feed
-   `\\v`: Vertical Tab
-   `\\0`: Null Byte

#### Usage (F#)

```fsharp
open STRling.Simply

// Control character examples
let patternN = merge [ lit "\n"; lit "end" ]
let patternT = merge [ lit "\t"; lit "data" ]
// Matches newline followed by "end", or tab followed by "data"
```

### Hexadecimal & Unicode

Define characters by their code point.

-   `\\xHH`: 2-digit hexadecimal (e.g. `\\x0A`)
-   `\\uHHHH`: 4-digit Unicode (e.g. `\\u00A9`)

#### Usage (F#)

```fsharp
open STRling.Simply

let patternHex = merge [ lit "\x41"; lit "end" ]  // \x41 -> 'A'
let patternU = merge [ lit "\u0041"; lit "end" ]  // \u0041 -> 'A'
// Both match "Aend"
```

---

## Quantifiers

### Greedy Quantifiers

Match as much as possible (standard behavior).

-   `*`: 0 or more
-   `+`: 1 or more
-   `?`: 0 or 1
-   `{n,m}`: Specific range

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); letter 1 0; end' () ]
// Match one or more letters (greedy)
// The second parameter 0 means "no upper limit"
// Compiles to: ^[a-zA-Z]+$
```

### Lazy Quantifiers

Match as little as possible. Appending `?` to a quantifier (e.g., `*?`).

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); (letter () |> rep 1 5 |> lazy'); end' () ]
// Match between 1 and 5 letters lazily
// Compiles to: ^[a-zA-Z]{1,5}?$
```

### Possessive Quantifiers

Match as much as possible and **do not backtrack**. Appending `+` to a quantifier (e.g., `++`, `*+`).

> **Note:** This is a key performance feature in STRling.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); (digit () |> rep 1 0 |> possessive); end' () ]
// Match one or more digits possessively
// Compiles to: ^\d++$
```

---

## Groups

### Capturing Groups

Standard groups `(...)` that capture the matched text.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = capture (letter 3)
// Capture three letters for later extraction
// Compiles to: ([a-zA-Z]{3})
```

### Named Groups

Capturing groups with a specific name `(?<name>...)` for easier extraction.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = group "area" (digit 3)
// Named group 'area' captures three digits
// Compiles to: (?<area>\d{3})
```

### Non-Capturing Groups

Groups `(?:...)` that group logic without capturing text.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ start (); (digit 3 |> nonCapture); end' () ]
// Non-capturing grouping used for grouping logic
// Compiles to: ^(?:\d{3})$
```

### Atomic Groups

Groups `(?>...)` that discard backtracking information once the group matches.

> **Note:** Useful for optimizing performance and preventing catastrophic backtracking.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = atomic (merge [ digit 1 0; letter 1 0 ])
// Atomic grouping prevents internal backtracking
// Compiles to: (?>\d+[a-zA-Z]+)
```

---

## Lookarounds

Zero-width assertions that match a group without consuming characters.

### Lookahead

-   Positive `(?=...)`: Asserts that what follows matches the pattern.
-   Negative `(?!...)`: Asserts that what follows does _not_ match.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ letter (); ahead (digit ()) ]
// Assert that a digit follows (positive lookahead)
// Compiles to: [a-zA-Z](?=\d)
```

### Lookbehind

-   Positive `(?<=...)`: Asserts that what precedes matches the pattern.
-   Negative `(?<!...)`: Asserts that what precedes does _not_ match.

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ behind (letter ()); digit () ]
// Assert that a letter precedes (positive lookbehind)
// Compiles to: (?<=[a-zA-Z])\d
```

---

## Logic

### Alternation

Matches one pattern OR another (`|`).

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = anyOf' [ lit "cat"; lit "dog" ]
// Match either 'cat' or 'dog'
// Compiles to: cat|dog
```

---

## References

### Backreferences

Reference a previously captured group by index (`\1`) or name (`\k<name>`).

#### Usage (F#)

```fsharp
open STRling.Simply

let p = capture (letter 3)
let pattern = merge [ p; lit "-"; backref 1 ]
// Backreference to the first numbered capture group
// Compiles to: ([a-zA-Z]{3})-\1
```

---

## Flags & Modifiers

Global flags that alter the behavior of the regex engine.

-   `i`: Case-insensitive
-   `m`: Multiline mode
-   `s`: Dotall (single line) mode
-   `x`: Extended mode (ignore whitespace)

#### Usage (F#)

```fsharp
open STRling.Simply

let pattern = merge [ flag "i"; lit "abc" ]
// Case-insensitive match (flag i)
// Compiles to: (?i)abc
```

---

## Directives

STRling supports a small set of file-level directives which must appear at the top of a pattern file (before any pattern content).

-   `%flags <letters>` — Sets global flags for the pattern.
-   `%lang <language>` — (Optional) Hint to emitters about the target language.
-   `%engine <engine>` — (Optional) Request a specific engine/emitter.

Example directives block:

```text
%flags imsux
%lang fsharp
%engine pcre2
```
