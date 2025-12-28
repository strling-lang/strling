-- Interaction Tests - Parser → Compiler → Emitter handoffs
--
-- This test suite validates the handoff between pipeline stages:
-- - Parser → Compiler: Ensures AST is correctly consumed
-- - Compiler → Emitter: Ensures IR is correctly transformed to regex

local strling = require("src.strling")
local parser = require("src.parser")
local pcre2 = require("src.pcre2")

describe("Parser → Compiler Handoff", function()
  it("handles SimpleLiteral", function()
    local flags, ast = parser.parse("hello")
    local ir = strling.compile(ast)
    assert.are.equal("Lit", ir.ir)
  end)

  it("handles Quantifier", function()
    local flags, ast = parser.parse("a+")
    local ir = strling.compile(ast)
    assert.are.equal("Quant", ir.ir)
  end)

  it("handles CharacterClass", function()
    local flags, ast = parser.parse("[abc]")
    local ir = strling.compile(ast)
    assert.are.equal("CharClass", ir.ir)
  end)

  it("handles CapturingGroup", function()
    local flags, ast = parser.parse("(abc)")
    local ir = strling.compile(ast)
    assert.are.equal("Group", ir.ir)
  end)

  it("handles Alternation", function()
    local flags, ast = parser.parse("a|b")
    local ir = strling.compile(ast)
    assert.are.equal("Alt", ir.ir)
  end)

  it("handles NamedGroup", function()
    local flags, ast = parser.parse("(?<name>abc)")
    local ir = strling.compile(ast)
    assert.are.equal("Group", ir.ir)
  end)

  it("handles Lookahead", function()
    local flags, ast = parser.parse("(?=abc)")
    local ir = strling.compile(ast)
    assert.are.equal("Look", ir.ir)
  end)

  it("handles Lookbehind", function()
    local flags, ast = parser.parse("(?<=abc)")
    local ir = strling.compile(ast)
    assert.are.equal("Look", ir.ir)
  end)
end)

describe("Compiler → Emitter Handoff", function()
  local function compile_to_regex(dsl)
    local flags, ast = parser.parse(dsl)
    local ir = strling.compile(ast)
    return pcre2.emit(ir, flags)
  end

  it("emits SimpleLiteral", function()
    assert.are.equal("hello", compile_to_regex("hello"))
  end)

  it("emits DigitShorthand", function()
    assert.are.equal("\\d+", compile_to_regex("\\d+"))
  end)

  it("emits CharacterClass", function()
    assert.are.equal("[abc]", compile_to_regex("[abc]"))
  end)

  it("emits CharacterClassRange", function()
    assert.are.equal("[a-z]", compile_to_regex("[a-z]"))
  end)

  it("emits NegatedClass", function()
    assert.are.equal("[^abc]", compile_to_regex("[^abc]"))
  end)

  it("emits QuantifierPlus", function()
    assert.are.equal("a+", compile_to_regex("a+"))
  end)

  it("emits QuantifierStar", function()
    assert.are.equal("a*", compile_to_regex("a*"))
  end)

  it("emits QuantifierOptional", function()
    assert.are.equal("a?", compile_to_regex("a?"))
  end)

  it("emits QuantifierExact", function()
    assert.are.equal("a{3}", compile_to_regex("a{3}"))
  end)

  it("emits QuantifierRange", function()
    assert.are.equal("a{2,5}", compile_to_regex("a{2,5}"))
  end)

  it("emits QuantifierLazy", function()
    assert.are.equal("a+?", compile_to_regex("a+?"))
  end)

  it("emits CapturingGroup", function()
    assert.are.equal("(abc)", compile_to_regex("(abc)"))
  end)

  it("emits NonCapturingGroup", function()
    assert.are.equal("(?:abc)", compile_to_regex("(?:abc)"))
  end)

  it("emits NamedGroup", function()
    assert.are.equal("(?<name>abc)", compile_to_regex("(?<name>abc)"))
  end)

  it("emits Alternation", function()
    assert.are.equal("cat|dog", compile_to_regex("cat|dog"))
  end)

  it("emits Anchors", function()
    assert.are.equal("^abc$", compile_to_regex("^abc$"))
  end)

  it("emits PositiveLookahead", function()
    assert.are.equal("foo(?=bar)", compile_to_regex("foo(?=bar)"))
  end)

  it("emits NegativeLookahead", function()
    assert.are.equal("foo(?!bar)", compile_to_regex("foo(?!bar)"))
  end)

  it("emits PositiveLookbehind", function()
    assert.are.equal("(?<=foo)bar", compile_to_regex("(?<=foo)bar"))
  end)

  it("emits NegativeLookbehind", function()
    assert.are.equal("(?<!foo)bar", compile_to_regex("(?<!foo)bar"))
  end)
end)

describe("Semantic Edge Cases", function()
  it("test_semantic_duplicate_capture_group", function()
    assert.has_error(function()
      parser.parse("(?<name>a)(?<name>b)")
    end)
  end)

  it("test_semantic_ranges", function()
    -- Invalid range [z-a] should produce an error
    assert.has_error(function()
      parser.parse("[z-a]")
    end)
  end)
end)

describe("Full Pipeline", function()
  local function compile_to_regex(dsl)
    local flags, ast = parser.parse(dsl)
    local ir = strling.compile(ast)
    return pcre2.emit(ir, flags)
  end

  it("handles PhoneNumber", function()
    local regex = compile_to_regex("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})")
    assert.are.equal("(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})", regex)
  end)

  it("handles IPv4", function()
    local regex = compile_to_regex("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})")
    assert.are.equal("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})", regex)
  end)
end)
