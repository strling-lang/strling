# API Reference - Ruby

[← Back to README](../README.md) | [Developer Hub](../../../docs/index.md)

This document provides a comprehensive reference for the STRling API in **Ruby**.

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

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.lit("abc"),
  STRling::Simply.end()
)
# Start of line, literal "abc", end of line
# Compiles to: ^abc$
```

### Start/End of String

Matches the absolute beginning (`\A`) or end (`\z`) of the string, ignoring multiline mode.

#### Usage (Ruby)

```ruby
require 'strling'

# For absolute anchors, use emitter directives
pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.lit("hello"),
  STRling::Simply.end()
)
# Compiles to: ^hello$
```

### Word Boundaries

Matches the position between a word character and a non-word character (`\b`), or the inverse (`\B`).

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.capture(STRling::Simply.letter()),
  STRling::Simply.bound(),
  STRling::Simply.capture(STRling::Simply.digit()),
  STRling::Simply.end()
)
# Word boundary (\b) separates letters from digits
```

---

## Character Classes

### Built-in Classes

Standard shorthands for common character sets.

-   `\w`: Word characters (alphanumeric + underscore)
-   `\d`: Digits
-   `\s`: Whitespace
-   `.`: Any character (except newline)

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.capture(STRling::Simply.digit(3)),
  STRling::Simply.end()
)
# Match exactly 3 digits (\d{3})
# Compiles to: ^(\d{3})$
```

### Custom Classes & Ranges

Define a set of allowed characters (`[...]`) or a range (`a-z`).

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.any_of("abc"),
  STRling::Simply.end()
)
# Match one of: a, b, or c (custom class)
# Compiles to: ^[abc]$
```

### Negated Classes

Match any character _not_ in the set (`[^...]`).

#### Usage (Ruby)

```ruby
require 'strling'

not_vowels = STRling::Simply.not_in_chars("aeiou")
pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  not_vowels,
  STRling::Simply.end()
)
# Match any character except vowels
# Compiles to: ^[^aeiou]$
```

### Unicode Properties

Match characters based on Unicode properties (`\p{...}`), such as scripts, categories, or blocks.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.char_property("Lu"),
  STRling::Simply.end()
)
# Match a Unicode uppercase letter (\p{Lu})
# Compiles to: ^\p{Lu}$
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

#### Usage (Ruby)

```ruby
require 'strling'

# Control character examples
pattern_n = STRling::Simply.merge(STRling::Simply.lit("\n"), STRling::Simply.lit("end"))
pattern_t = STRling::Simply.merge(STRling::Simply.lit("\t"), STRling::Simply.lit("data"))
# Matches newline followed by "end", or tab followed by "data"
```

### Hexadecimal & Unicode

Define characters by their code point.

-   `\\xHH`: 2-digit hexadecimal (e.g. `\\x0A`)
-   `\\uHHHH`: 4-digit Unicode (e.g. `\\u00A9`)

#### Usage (Ruby)

```ruby
require 'strling'

pattern_hex = STRling::Simply.merge(STRling::Simply.lit("\x41"), STRling::Simply.lit("end"))  # \x41 -> 'A'
pattern_u = STRling::Simply.merge(STRling::Simply.lit("\u0041"), STRling::Simply.lit("end"))  # \u0041 -> 'A'
# Both match "Aend"
```

---

## Quantifiers

### Greedy Quantifiers

Match as much as possible (standard behavior).

-   `*`: 0 or more
-   `+`: 1 or more
-   `?`: 0 or 1
-   `{n,m}`: Specific range

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.letter(1, 0),
  STRling::Simply.end()
)
# Match one or more letters (greedy)
# The second parameter 0 means "no upper limit"
# Compiles to: ^[a-zA-Z]+$
```

### Lazy Quantifiers

Match as little as possible. Appending `?` to a quantifier (e.g., `*?`).

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.letter().rep(1, 5).lazy(),
  STRling::Simply.end()
)
# Match between 1 and 5 letters lazily
# Compiles to: ^[a-zA-Z]{1,5}?$
```

### Possessive Quantifiers

Match as much as possible and **do not backtrack**. Appending `+` to a quantifier (e.g., `++`, `*+`).

> **Note:** This is a key performance feature in STRling.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.digit().rep(1, 0).possessive(),
  STRling::Simply.end()
)
# Match one or more digits possessively
# Compiles to: ^\d++$
```

---

## Groups

### Capturing Groups

Standard groups `(...)` that capture the matched text.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.capture(STRling::Simply.letter(3))
# Capture three letters for later extraction
# Compiles to: ([a-zA-Z]{3})
```

### Named Groups

Capturing groups with a specific name `(?<name>...)` for easier extraction.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.group("area", STRling::Simply.digit(3))
# Named group 'area' captures three digits
# Compiles to: (?<area>\d{3})
```

### Non-Capturing Groups

Groups `(?:...)` that group logic without capturing text.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.start(),
  STRling::Simply.digit(3).non_capture(),
  STRling::Simply.end()
)
# Non-capturing grouping used for grouping logic
# Compiles to: ^(?:\d{3})$
```

### Atomic Groups

Groups `(?>...)` that discard backtracking information once the group matches.

> **Note:** Useful for optimizing performance and preventing catastrophic backtracking.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.atomic(
  STRling::Simply.merge(STRling::Simply.digit(1, 0), STRling::Simply.letter(1, 0))
)
# Atomic grouping prevents internal backtracking
# Compiles to: (?>\d+[a-zA-Z]+)
```

---

## Lookarounds

Zero-width assertions that match a group without consuming characters.

### Lookahead

-   Positive `(?=...)`: Asserts that what follows matches the pattern.
-   Negative `(?!...)`: Asserts that what follows does _not_ match.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.letter(),
  STRling::Simply.ahead(STRling::Simply.digit())
)
# Assert that a digit follows (positive lookahead)
# Compiles to: [a-zA-Z](?=\d)
```

### Lookbehind

-   Positive `(?<=...)`: Asserts that what precedes matches the pattern.
-   Negative `(?<!...)`: Asserts that what precedes does _not_ match.

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(
  STRling::Simply.behind(STRling::Simply.letter()),
  STRling::Simply.digit()
)
# Assert that a letter precedes (positive lookbehind)
# Compiles to: (?<=[a-zA-Z])\d
```

---

## Logic

### Alternation

Matches one pattern OR another (`|`).

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.any_of(STRling::Simply.lit("cat"), STRling::Simply.lit("dog"))
# Match either 'cat' or 'dog'
# Compiles to: cat|dog
```

---

## References

### Backreferences

Reference a previously captured group by index (`\1`) or name (`\k<name>`).

#### Usage (Ruby)

```ruby
require 'strling'

p = STRling::Simply.capture(STRling::Simply.letter(3))
pattern = STRling::Simply.merge(p, STRling::Simply.lit("-"), STRling::Simply.backref(1))
# Backreference to the first numbered capture group
# Compiles to: ([a-zA-Z]{3})-\1
```

---

## Flags & Modifiers

Global flags that alter the behavior of the regex engine.

-   `i`: Case-insensitive
-   `m`: Multiline mode
-   `s`: Dotall (single line) mode
-   `x`: Extended mode (ignore whitespace)

#### Usage (Ruby)

```ruby
require 'strling'

pattern = STRling::Simply.merge(STRling::Simply.flag("i"), STRling::Simply.lit("abc"))
# Case-insensitive match (flag i)
# Compiles to: (?i)abc
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
%lang ruby
%engine pcre2
```
