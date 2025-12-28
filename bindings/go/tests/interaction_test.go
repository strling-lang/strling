package tests

import (
	"regexp"
	"testing"

	"github.com/thecyberlocal/strling/bindings/go/core"
	"github.com/thecyberlocal/strling/bindings/go/emitters"
)

// TestParserToCompiler verifies the Parser → Compiler handoff.
// These tests ensure the AST produced by the parser is correctly consumed by the compiler.
func TestParserToCompiler(t *testing.T) {
	testCases := []struct {
		name     string
		dsl      string
		wantIR   string // IR type expected
	}{
		{
			name:   "SimpleLiteral",
			dsl:    "hello",
			wantIR: "Lit",
		},
		{
			name:   "Quantifier",
			dsl:    "a+",
			wantIR: "Quant",
		},
		{
			name:   "CharacterClass",
			dsl:    "[abc]",
			wantIR: "CharClass",
		},
		{
			name:   "CapturingGroup",
			dsl:    "(abc)",
			wantIR: "Group",
		},
		{
			name:   "Alternation",
			dsl:    "a|b",
			wantIR: "Alt",
		},
		{
			name:   "Sequence",
			dsl:    "ab",
			wantIR: "Lit", // Adjacent literals get coalesced
		},
		{
			name:   "Anchor",
			dsl:    "^abc$",
			wantIR: "Seq",
		},
		{
			name:   "NamedGroup",
			dsl:    "(?<name>abc)",
			wantIR: "Group",
		},
		{
			name:   "Lookahead",
			dsl:    "(?=abc)",
			wantIR: "Look",
		},
		{
			name:   "Lookbehind",
			dsl:    "(?<=abc)",
			wantIR: "Look",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Parse
			parser := core.NewParser(tc.dsl)
			ast, err := parser.Parse()
			if err != nil {
				t.Fatalf("Parser failed: %v", err)
			}

			// Compile
			compiler := core.NewCompiler()
			result := compiler.CompileWithMetadata(ast)

			ir, ok := result["ir"].(core.IROp)
			if !ok {
				t.Fatalf("Expected IROp in result, got %T", result["ir"])
			}

			irType := ir.ToDict()["ir"]
			if irType != tc.wantIR {
				t.Errorf("Expected IR type %q, got %q", tc.wantIR, irType)
			}
		})
	}
}

// TestCompilerToEmitter verifies the Compiler → Emitter handoff.
// These tests ensure the IR produced by the compiler is correctly consumed by the emitter.
func TestCompilerToEmitter(t *testing.T) {
	testCases := []struct {
		name      string
		dsl       string
		wantRegex string
	}{
		{
			name:      "SimpleLiteral",
			dsl:       "hello",
			wantRegex: "hello",
		},
		{
			name:      "DigitShorthand",
			dsl:       `\d+`,
			wantRegex: `\d+`,
		},
		{
			name:      "CharacterClassBasic",
			dsl:       "[abc]",
			wantRegex: "[abc]",
		},
		{
			name:      "CharacterClassRange",
			dsl:       "[a-z]",
			wantRegex: "[a-z]",
		},
		{
			name:      "NegatedClass",
			dsl:       "[^abc]",
			wantRegex: "[^abc]",
		},
		{
			name:      "QuantifierPlus",
			dsl:       "a+",
			wantRegex: "a+",
		},
		{
			name:      "QuantifierStar",
			dsl:       "a*",
			wantRegex: "a*",
		},
		{
			name:      "QuantifierOptional",
			dsl:       "a?",
			wantRegex: "a?",
		},
		{
			name:      "QuantifierExact",
			dsl:       "a{3}",
			wantRegex: "a{3}",
		},
		{
			name:      "QuantifierRange",
			dsl:       "a{2,5}",
			wantRegex: "a{2,5}",
		},
		{
			name:      "QuantifierLazy",
			dsl:       "a+?",
			wantRegex: "a+?",
		},
		{
			name:      "CapturingGroup",
			dsl:       "(abc)",
			wantRegex: "(abc)",
		},
		{
			name:      "NonCapturingGroup",
			dsl:       "(?:abc)",
			wantRegex: "(?:abc)",
		},
		{
			name:      "NamedGroup",
			dsl:       "(?<name>abc)",
			wantRegex: "(?<name>abc)",
		},
		{
			name:      "Alternation",
			dsl:       "cat|dog",
			wantRegex: "cat|dog",
		},
		{
			name:      "AnchorStart",
			dsl:       "^abc",
			wantRegex: "^abc",
		},
		{
			name:      "AnchorEnd",
			dsl:       "abc$",
			wantRegex: "abc$",
		},
		{
			name:      "PositiveLookahead",
			dsl:       "foo(?=bar)",
			wantRegex: "foo(?=bar)",
		},
		{
			name:      "NegativeLookahead",
			dsl:       "foo(?!bar)",
			wantRegex: "foo(?!bar)",
		},
		{
			name:      "PositiveLookbehind",
			dsl:       "(?<=foo)bar",
			wantRegex: "(?<=foo)bar",
		},
		{
			name:      "NegativeLookbehind",
			dsl:       "(?<!foo)bar",
			wantRegex: "(?<!foo)bar",
		},
		{
			name:      "Dot",
			dsl:       "a.b",
			wantRegex: "a.b",
		},
		{
			name:      "EscapedDot",
			dsl:       `a\.b`,
			wantRegex: `a\.b`,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Parse
			parser := core.NewParser(tc.dsl)
			ast, err := parser.Parse()
			if err != nil {
				t.Fatalf("Parser failed: %v", err)
			}

			// Compile
			compiler := core.NewCompiler()
			ir := compiler.Compile(ast)

			// Emit
			regex := emitters.Emit(ir, core.Flags{})

			if regex != tc.wantRegex {
				t.Errorf("Expected regex %q, got %q", tc.wantRegex, regex)
			}
		})
	}
}

// TestSemanticDuplicateNames verifies duplicate named group detection.
func TestSemanticDuplicateNames(t *testing.T) {
	dsl := "(?<name>a)(?<name>b)"
	parser := core.NewParser(dsl)
	_, err := parser.Parse()

	if err == nil {
		t.Error("Expected error for duplicate named groups, got nil")
	}
}

// TestSemanticRangeValidation verifies character class range validation.
func TestSemanticRangeValidation(t *testing.T) {
	// Invalid range: z-a (z > a)
	dsl := "[z-a]"
	parser := core.NewParser(dsl)
	_, err := parser.Parse()

	if err == nil {
		t.Error("Expected error for invalid range [z-a], got nil")
	}
}

// TestFullPipeline tests the complete Parse → Compile → Emit pipeline.
func TestFullPipeline(t *testing.T) {
	testCases := []struct {
		name      string
		dsl       string
		wantRegex string
	}{
		{
			name:      "PhoneNumber",
			dsl:       `(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})`,
			wantRegex: `(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})`,
		},
		{
			name:      "Email",
			dsl:       `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`,
			wantRegex: `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`,
		},
		{
			name:      "IPv4Address",
			dsl:       `(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})`,
			wantRegex: `(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})`,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Full pipeline
			parser := core.NewParser(tc.dsl)
			ast, err := parser.Parse()
			if err != nil {
				t.Fatalf("Parser failed: %v", err)
			}

			compiler := core.NewCompiler()
			ir := compiler.Compile(ast)
			regex := emitters.Emit(ir, core.Flags{})

			if regex != tc.wantRegex {
				t.Errorf("Expected %q, got %q", tc.wantRegex, regex)
			}
		})
	}
}
