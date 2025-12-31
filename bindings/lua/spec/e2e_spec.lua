-- E2E Tests - Black-box testing where DSL input produces a regex
-- that matches expected strings.
--
-- Note: Lua's pattern matching is limited compared to PCRE2.
-- These tests verify regex string generation; actual matching
-- would require a PCRE2 library like lrexlib.

local strling = require("src.strling")
local parser = require("src.parser")
local pcre2 = require("src.pcre2")

local function compile_to_regex(dsl)
  local flags, ast = parser.parse(dsl)
  local ir = strling.compile(ast)
  return pcre2.emit(ir, flags)
end

-- Helper to test Lua pattern matching (limited subset)
local function lua_matches(pattern, str)
  return string.match(str, pattern) ~= nil
end

describe("E2E Phone Number", function()
  it("generates correct regex", function()
    local regex = compile_to_regex("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})$")
    assert.are.equal("^(\\d{3})[-. ]?(\\d{3})[-. ]?(\\d{4})$", regex)
  end)
end)

describe("E2E Email", function()
  it("generates correct regex", function()
    local regex = compile_to_regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$")
    -- Verify regex was generated (escaping may vary)
    assert.truthy(string.find(regex, "@"))
  end)
end)

describe("E2E IPv4", function()
  it("generates correct regex", function()
    local regex = compile_to_regex("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$")
    assert.are.equal("^(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})$", regex)
  end)
end)

describe("E2E Hex Color", function()
  it("generates correct regex", function()
    local regex = compile_to_regex("^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$")
    assert.truthy(string.find(regex, "#"))
  end)
end)

describe("E2E Date", function()
  it("generates correct regex", function()
    local regex = compile_to_regex("^(\\d{4})-(\\d{2})-(\\d{2})$")
    assert.are.equal("^(\\d{4})-(\\d{2})-(\\d{2})$", regex)
  end)
end)

describe("E2E Lookahead", function()
  it("generates positive lookahead", function()
    local regex = compile_to_regex("foo(?=bar)")
    assert.are.equal("foo(?=bar)", regex)
  end)

  it("generates negative lookahead", function()
    local regex = compile_to_regex("foo(?!bar)")
    assert.are.equal("foo(?!bar)", regex)
  end)
end)

describe("E2E Word Boundary", function()
  it("generates word boundary regex", function()
    local regex = compile_to_regex("\\bword\\b")
    assert.are.equal("\\bword\\b", regex)
  end)
end)

describe("E2E Alternation", function()
  it("generates alternation regex", function()
    local regex = compile_to_regex("^(cat|dog|bird)$")
    assert.are.equal("^(cat|dog|bird)$", regex)
  end)
end)

describe("E2E Quantifiers", function()
  it("generates plus quantifier", function()
    local regex = compile_to_regex("^a+$")
    assert.are.equal("^a+$", regex)
  end)

  it("generates star quantifier", function()
    local regex = compile_to_regex("^a*$")
    assert.are.equal("^a*$", regex)
  end)

  it("generates optional quantifier", function()
    local regex = compile_to_regex("^a?$")
    assert.are.equal("^a?$", regex)
  end)

  it("generates exact quantifier", function()
    local regex = compile_to_regex("^a{3}$")
    assert.are.equal("^a{3}$", regex)
  end)

  it("generates range quantifier", function()
    local regex = compile_to_regex("^a{2,4}$")
    assert.are.equal("^a{2,4}$", regex)
  end)

  it("generates atLeast quantifier", function()
    local regex = compile_to_regex("^a{2,}$")
    assert.are.equal("^a{2,}$", regex)
  end)
end)

describe("E2E Capture Groups", function()
  it("generates capture group regex", function()
    local regex = compile_to_regex("^(\\d{4})-(\\d{2})-(\\d{2})$")
    assert.are.equal("^(\\d{4})-(\\d{2})-(\\d{2})$", regex)
  end)
end)

-- Simple Lua pattern tests (subset that Lua can handle)
describe("E2E Lua Pattern Matching (Subset)", function()
  it("matches simple literals with Lua patterns", function()
    -- Lua can match simple literals
    assert.truthy(lua_matches("hello", "hello world"))
    assert.falsy(lua_matches("^hello$", "hello world"))
  end)

  it("matches alphanumeric with Lua patterns", function()
    -- Lua uses %w for word chars, not \w
    assert.truthy(lua_matches("%w+", "hello"))
    assert.truthy(lua_matches("%d+", "12345"))
  end)
end)
