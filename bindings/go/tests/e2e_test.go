package tests

import (
	"regexp"
	"testing"

	"github.com/thecyberlocal/strling/bindings/go/core"
	"github.com/thecyberlocal/strling/bindings/go/emitters"
)

// E2E tests: Black-box testing where DSL input produces a regex that matches expected strings.
// These tests verify the complete pipeline produces functionally correct output.

// TestE2EPhoneNumber tests phone number matching end-to-end.
func TestE2EPhoneNumber(t *testing.T) {
	dsl := `^(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"555-123-4567",
		"555.123.4567",
		"555 123 4567",
		"5551234567",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{
		"55-123-4567",
		"555-12-4567",
		"555-123-456",
		"abc-def-ghij",
		"555-123-45678",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2EEmailAddress tests email address matching end-to-end.
func TestE2EEmailAddress(t *testing.T) {
	dsl := `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"user@example.com",
		"test.user@domain.org",
		"user+tag@company.co.uk",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't (regex: %s)", m, regex)
		}
	}

	// Should not match
	nonMatches := []string{
		"@example.com",
		"user@",
		"user@.com",
		"user@domain",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2EIPv4Address tests IPv4 address matching end-to-end.
func TestE2EIPv4Address(t *testing.T) {
	dsl := `^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"192.168.1.1",
		"10.0.0.1",
		"255.255.255.255",
		"0.0.0.0",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{
		"192.168.1",
		"192.168.1.1.1",
		"192.168.1.abc",
		"192-168-1-1",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2EHexColor tests hex color code matching end-to-end.
func TestE2EHexColor(t *testing.T) {
	dsl := `^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"#ffffff",
		"#000000",
		"#ABC123",
		"#fff",
		"#F00",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{
		"ffffff",
		"#ffff",
		"#fffff",
		"#GGGGGG",
		"#12345",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2EDate tests date matching (YYYY-MM-DD) end-to-end.
func TestE2EDate(t *testing.T) {
	dsl := `^(\d{4})-(\d{2})-(\d{2})$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"2024-01-15",
		"2000-12-31",
		"1999-06-30",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{
		"24-01-15",
		"2024/01/15",
		"2024-1-15",
		"01-15-2024",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2ELookahead tests lookahead assertions end-to-end.
func TestE2ELookahead(t *testing.T) {
	// Match "foo" only if followed by "bar"
	dsl := `foo(?=bar)`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	if !re.MatchString("foobar") {
		t.Error("Expected 'foobar' to match")
	}

	// Should not match
	if re.MatchString("foobaz") {
		t.Error("Expected 'foobaz' NOT to match")
	}
}

// TestE2ENegativeLookahead tests negative lookahead assertions end-to-end.
func TestE2ENegativeLookahead(t *testing.T) {
	// Match "foo" only if NOT followed by "bar"
	dsl := `foo(?!bar)`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	if !re.MatchString("foobaz") {
		t.Error("Expected 'foobaz' to match")
	}

	// Should not match
	if re.MatchString("foobar") {
		t.Error("Expected 'foobar' NOT to match")
	}
}

// TestE2EWordBoundary tests word boundary assertions end-to-end.
func TestE2EWordBoundary(t *testing.T) {
	dsl := `\bword\b`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{
		"word",
		"a word here",
		"word.",
	}

	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{
		"sword",
		"wording",
		"password",
	}

	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2ECaptureGroups tests capture group extraction end-to-end.
func TestE2ECaptureGroups(t *testing.T) {
	dsl := `^(\d{4})-(\d{2})-(\d{2})$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	match := re.FindStringSubmatch("2024-12-25")
	if match == nil {
		t.Fatal("Expected match, got nil")
	}

	if len(match) != 4 {
		t.Fatalf("Expected 4 groups, got %d", len(match))
	}

	if match[1] != "2024" {
		t.Errorf("Expected year '2024', got %q", match[1])
	}
	if match[2] != "12" {
		t.Errorf("Expected month '12', got %q", match[2])
	}
	if match[3] != "25" {
		t.Errorf("Expected day '25', got %q", match[3])
	}
}

// TestE2EAlternation tests alternation end-to-end.
func TestE2EAlternation(t *testing.T) {
	dsl := `^(cat|dog|bird)$`

	regex := compileToRegex(t, dsl)
	re := regexp.MustCompile(regex)

	// Should match
	matches := []string{"cat", "dog", "bird"}
	for _, m := range matches {
		if !re.MatchString(m) {
			t.Errorf("Expected %q to match, but it didn't", m)
		}
	}

	// Should not match
	nonMatches := []string{"cats", "doggy", "fish", "catdog"}
	for _, m := range nonMatches {
		if re.MatchString(m) {
			t.Errorf("Expected %q NOT to match, but it did", m)
		}
	}
}

// TestE2EQuantifiers tests various quantifiers end-to-end.
func TestE2EQuantifiers(t *testing.T) {
	testCases := []struct {
		name      string
		dsl       string
		matches   []string
		noMatches []string
	}{
		{
			name:      "Plus",
			dsl:       `^a+$`,
			matches:   []string{"a", "aa", "aaa"},
			noMatches: []string{"", "b", "ab"},
		},
		{
			name:      "Star",
			dsl:       `^a*$`,
			matches:   []string{"", "a", "aa", "aaa"},
			noMatches: []string{"b", "ab"},
		},
		{
			name:      "Optional",
			dsl:       `^a?$`,
			matches:   []string{"", "a"},
			noMatches: []string{"aa", "b"},
		},
		{
			name:      "Exact",
			dsl:       `^a{3}$`,
			matches:   []string{"aaa"},
			noMatches: []string{"a", "aa", "aaaa"},
		},
		{
			name:      "Range",
			dsl:       `^a{2,4}$`,
			matches:   []string{"aa", "aaa", "aaaa"},
			noMatches: []string{"a", "aaaaa"},
		},
		{
			name:      "AtLeast",
			dsl:       `^a{2,}$`,
			matches:   []string{"aa", "aaa", "aaaa", "aaaaa"},
			noMatches: []string{"", "a"},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			regex := compileToRegex(t, tc.dsl)
			re := regexp.MustCompile(regex)

			for _, m := range tc.matches {
				if !re.MatchString(m) {
					t.Errorf("Expected %q to match, but it didn't", m)
				}
			}

			for _, m := range tc.noMatches {
				if re.MatchString(m) {
					t.Errorf("Expected %q NOT to match, but it did", m)
				}
			}
		})
	}
}

// compileToRegex is a helper that runs the full DSL → Regex pipeline.
func compileToRegex(t *testing.T, dsl string) string {
	t.Helper()

	parser := core.NewParser(dsl)
	ast, err := parser.Parse()
	if err != nil {
		t.Fatalf("Parser failed for %q: %v", dsl, err)
	}

	compiler := core.NewCompiler()
	ir := compiler.Compile(ast)
	regex := emitters.Emit(ir, core.Flags{})

	return regex
}
