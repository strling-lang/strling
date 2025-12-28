--[[
    STRling Parser - Recursive Descent Parser for Lua
    
    Transforms STRling DSL patterns into AST nodes.
    Mirrors the TypeScript reference implementation.
]]

local Parser = {}
Parser.__index = Parser

-- Control escape mappings
local CONTROL_ESCAPES = {
    n = "\n",
    r = "\r",
    t = "\t",
    f = "\f",
    v = "\v"
}

-- STRlingParseError class
local STRlingParseError = {}
STRlingParseError.__index = STRlingParseError

function STRlingParseError.new(message, position, source, hint)
    local self = setmetatable({}, STRlingParseError)
    self.message = message
    self.position = position
    self.source = source
    self.hint = hint
    return self
end

function STRlingParseError:__tostring()
    return string.format("STRlingParseError: %s at position %d", self.message, self.position)
end

-- Flags container
local Flags = {}
Flags.__index = Flags

function Flags.new()
    local self = setmetatable({}, Flags)
    self.ignoreCase = false
    self.multiline = false
    self.dotAll = false
    self.unicode = false
    self.extended = false
    return self
end

function Flags.fromLetters(letters)
    local f = Flags.new()
    for ch in letters:lower():gmatch(".") do
        if ch == "i" then f.ignoreCase = true
        elseif ch == "m" then f.multiline = true
        elseif ch == "s" then f.dotAll = true
        elseif ch == "u" then f.unicode = true
        elseif ch == "x" then f.extended = true
        end
    end
    return f
end

function Flags:toDict()
    return {
        ignoreCase = self.ignoreCase,
        multiline = self.multiline,
        dotAll = self.dotAll,
        unicode = self.unicode,
        extended = self.extended
    }
end

-- Cursor class for tracking position
local Cursor = {}
Cursor.__index = Cursor

function Cursor.new(text, extendedMode)
    local self = setmetatable({}, Cursor)
    self.text = text
    self.i = 1  -- Lua is 1-indexed
    self.extendedMode = extendedMode or false
    self.inClass = 0
    return self
end

function Cursor:eof()
    return self.i > #self.text
end

function Cursor:peek(offset)
    offset = offset or 0
    local j = self.i + offset
    if j > #self.text then return "" end
    return self.text:sub(j, j)
end

function Cursor:take()
    if self:eof() then return "" end
    local ch = self.text:sub(self.i, self.i)
    self.i = self.i + 1
    return ch
end

function Cursor:match(s)
    local len = #s
    if self.i + len - 1 > #self.text then return false end
    if self.text:sub(self.i, self.i + len - 1) == s then
        self.i = self.i + len
        return true
    end
    return false
end

function Cursor:skipWsAndComments()
    if not self.extendedMode or self.inClass > 0 then return end
    while not self:eof() do
        local ch = self:peek()
        if ch == " " or ch == "\t" or ch == "\r" or ch == "\n" then
            self.i = self.i + 1
        elseif ch == "#" then
            while not self:eof() and self:peek() ~= "\r" and self:peek() ~= "\n" do
                self.i = self.i + 1
            end
        else
            break
        end
    end
end

-- Parser implementation
function Parser.new(text)
    local self = setmetatable({}, Parser)
    self.original = text
    self.flags, self.src = self:parseDirectives(text)
    self.cur = Cursor.new(self.src, self.flags.extended)
    self.capCount = 0
    self.capNames = {}
    return self
end

function Parser:parseDirectives(text)
    local flags = Flags.new()
    local pattern = text
    
    -- Match %flags directive
    local flagStr = text:match("^%s*%%flags%s*([imsux,%[%]%s]*)")
    if flagStr then
        -- Clean and parse flags
        flagStr = flagStr:lower():gsub("[,%[%]%s]", "")
        flags = Flags.fromLetters(flagStr)
        
        -- Remove directive lines
        local lines = {}
        local inPattern = false
        for line in (text .. "\n"):gmatch("([^\n]*)\n") do
            local trimmed = line:match("^%s*(.-)%s*$")
            if not inPattern and (trimmed:match("^%%flags") or trimmed == "" or trimmed:match("^#")) then
                -- skip
            else
                inPattern = true
                table.insert(lines, line)
            end
        end
        pattern = table.concat(lines, "\n")
    end
    
    return flags, pattern
end

function Parser:parse()
    local node = self:parseAlt()
    self.cur:skipWsAndComments()
    
    if not self.cur:eof() then
        local ch = self.cur:peek()
        if ch == ")" then
            error(STRlingParseError.new("Unmatched ')'", self.cur.i, self.src))
        end
        error(STRlingParseError.new("Unexpected trailing input", self.cur.i, self.src))
    end
    
    return self.flags, node
end

function Parser:parseAlt()
    self.cur:skipWsAndComments()
    
    if self.cur:peek() == "|" then
        error(STRlingParseError.new("Alternation lacks left-hand side", self.cur.i, self.src))
    end
    
    local branches = { self:parseSeq() }
    self.cur:skipWsAndComments()
    
    while self.cur:peek() == "|" do
        local pipePos = self.cur.i
        self.cur:take()
        self.cur:skipWsAndComments()
        
        if self.cur:eof() or self.cur:peek() == "|" then
            error(STRlingParseError.new("Alternation lacks right-hand side", pipePos, self.src))
        end
        
        table.insert(branches, self:parseSeq())
        self.cur:skipWsAndComments()
    end
    
    if #branches == 1 then return branches[1] end
    return { type = "Alternation", alternatives = branches }
end

function Parser:parseSeq()
    local parts = {}
    
    while true do
        self.cur:skipWsAndComments()
        local ch = self.cur:peek()
        
        if ("*+?{"):find(ch, 1, true) and #parts == 0 then
            error(STRlingParseError.new("Invalid quantifier '" .. ch .. "'", self.cur.i, self.src))
        end
        
        if ch == "" or ch == "|" or ch == ")" then break end
        
        local atom = self:parseAtom()
        atom = self:parseQuantIfAny(atom)
        table.insert(parts, atom)
    end
    
    if #parts == 1 then return parts[1] end
    return { type = "Sequence", parts = parts }
end

function Parser:parseAtom()
    self.cur:skipWsAndComments()
    local ch = self.cur:peek()
    
    if ch == "." then
        self.cur:take()
        return { type = "Dot" }
    end
    if ch == "^" then
        self.cur:take()
        return { type = "Anchor", at = "Start" }
    end
    if ch == "$" then
        self.cur:take()
        return { type = "Anchor", at = "End" }
    end
    if ch == "(" then
        return self:parseGroupOrLook()
    end
    if ch == "[" then
        return self:parseCharClass()
    end
    if ch == "\\" then
        return self:parseEscapeAtom()
    end
    if ch == ")" then
        error(STRlingParseError.new("Unmatched ')'", self.cur.i, self.src))
    end
    
    return { type = "Literal", value = self.cur:take() }
end

function Parser:parseQuantIfAny(child)
    local ch = self.cur:peek()
    local min, max
    local greedy = true
    local lazy = false
    local possessive = false
    
    if ch == "*" then
        min, max = 0, nil
        self.cur:take()
    elseif ch == "+" then
        min, max = 1, nil
        self.cur:take()
    elseif ch == "?" then
        min, max = 0, 1
        self.cur:take()
    elseif ch == "{" then
        local save = self.cur.i
        self.cur:take()
        
        local m = self:readIntOptional()
        if not m then
            self.cur.i = save
            return child
        end
        
        min = m
        max = m
        
        if self.cur:peek() == "," then
            self.cur:take()
            max = self:readIntOptional()
        end
        
        if self.cur:peek() ~= "}" then
            error(STRlingParseError.new("Incomplete quantifier", self.cur.i, self.src))
        end
        self.cur:take()
    else
        return child
    end
    
    if child.type == "Anchor" then
        error(STRlingParseError.new("Cannot quantify anchor", self.cur.i, self.src))
    end
    
    local nxt = self.cur:peek()
    if nxt == "?" then
        greedy = false
        lazy = true
        self.cur:take()
    elseif nxt == "+" then
        greedy = false
        possessive = true
        self.cur:take()
    end
    
    return {
        type = "Quantifier",
        target = child,
        min = min,
        max = max,
        greedy = greedy,
        lazy = lazy,
        possessive = possessive
    }
end

function Parser:readIntOptional()
    local s = ""
    while self.cur:peek():match("%d") do
        s = s .. self.cur:take()
    end
    return s ~= "" and tonumber(s) or nil
end

function Parser:parseGroupOrLook()
    self.cur:take()  -- consume '('
    
    if self.cur:match("?:") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated group", self.cur.i, self.src))
        end
        return { type = "Group", capturing = false, body = body }
    end
    
    if self.cur:match("?<=") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated lookbehind", self.cur.i, self.src))
        end
        return { type = "Lookbehind", body = body }
    end
    
    if self.cur:match("?<!") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated lookbehind", self.cur.i, self.src))
        end
        return { type = "NegativeLookbehind", body = body }
    end
    
    if self.cur:match("?<") then
        local name = ""
        while self.cur:peek() ~= ">" and self.cur:peek() ~= "" do
            name = name .. self.cur:take()
        end
        if not self.cur:match(">") then
            error(STRlingParseError.new("Unterminated group name", self.cur.i, self.src))
        end
        if self.capNames[name] then
            error(STRlingParseError.new("Duplicate group name <" .. name .. ">", self.cur.i, self.src))
        end
        self.capCount = self.capCount + 1
        self.capNames[name] = true
        
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated group", self.cur.i, self.src))
        end
        return { type = "Group", capturing = true, body = body, name = name }
    end
    
    if self.cur:match("?>") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated atomic group", self.cur.i, self.src))
        end
        return { type = "Group", capturing = false, body = body, atomic = true }
    end
    
    if self.cur:match("?=") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated lookahead", self.cur.i, self.src))
        end
        return { type = "Lookahead", body = body }
    end
    
    if self.cur:match("?!") then
        local body = self:parseAlt()
        if not self.cur:match(")") then
            error(STRlingParseError.new("Unterminated lookahead", self.cur.i, self.src))
        end
        return { type = "NegativeLookahead", body = body }
    end
    
    self.capCount = self.capCount + 1
    local body = self:parseAlt()
    if not self.cur:match(")") then
        error(STRlingParseError.new("Unterminated group", self.cur.i, self.src))
    end
    return { type = "Group", capturing = true, body = body }
end

function Parser:parseCharClass()
    self.cur:take()  -- consume '['
    self.cur.inClass = self.cur.inClass + 1
    
    local neg = false
    if self.cur:peek() == "^" then
        neg = true
        self.cur:take()
    end
    
    local members = {}
    
    while not self.cur:eof() and self.cur:peek() ~= "]" do
        if self.cur:peek() == "\\" then
            table.insert(members, self:parseClassEscape())
        else
            local ch = self.cur:take()
            
            if self.cur:peek() == "-" and self.cur:peek(1) ~= "]" then
                self.cur:take()  -- consume '-'
                local endCh = self.cur:take()
                table.insert(members, { type = "Range", from = ch, to = endCh })
            else
                table.insert(members, { type = "Literal", value = ch })
            end
        end
    end
    
    if self.cur:eof() then
        error(STRlingParseError.new("Unterminated character class", self.cur.i, self.src))
    end
    
    self.cur:take()  -- consume ']'
    self.cur.inClass = self.cur.inClass - 1
    
    return { type = "CharacterClass", negated = neg, members = members }
end

function Parser:parseClassEscape()
    local startPos = self.cur.i
    self.cur:take()  -- consume '\'
    
    local nxt = self.cur:peek()
    
    if ("dDwWsS"):find(nxt, 1, true) then
        local ch = self.cur:take()
        local kind
        if ch == "d" then kind = "digit"
        elseif ch == "D" then kind = "not-digit"
        elseif ch == "w" then kind = "word"
        elseif ch == "W" then kind = "not-word"
        elseif ch == "s" then kind = "space"
        elseif ch == "S" then kind = "not-space"
        end
        return { type = "Escape", kind = kind }
    end
    
    if nxt == "p" or nxt == "P" then
        local tp = self.cur:take()
        if not self.cur:match("{") then
            error(STRlingParseError.new("Expected '{' after \\p/\\P", startPos, self.src))
        end
        local prop = ""
        while self.cur:peek() ~= "}" and self.cur:peek() ~= "" do
            prop = prop .. self.cur:take()
        end
        if not self.cur:match("}") then
            error(STRlingParseError.new("Unterminated \\p{...}", startPos, self.src))
        end
        return { type = "UnicodeProperty", value = prop, negated = (tp == "P") }
    end
    
    if CONTROL_ESCAPES[nxt] then
        self.cur:take()
        return { type = "Literal", value = CONTROL_ESCAPES[nxt] }
    end
    
    if nxt == "b" then
        self.cur:take()
        return { type = "Literal", value = "\b" }
    end
    
    if nxt == "0" then
        self.cur:take()
        return { type = "Literal", value = "\0" }
    end
    
    return { type = "Literal", value = self.cur:take() }
end

function Parser:parseEscapeAtom()
    local startPos = self.cur.i
    self.cur:take()  -- consume '\'
    
    local nxt = self.cur:peek()
    
    -- Backreference
    if nxt:match("%d") and nxt ~= "0" then
        local num = 0
        while self.cur:peek():match("%d") do
            num = num * 10 + tonumber(self.cur:take())
            if num > self.capCount then
                error(STRlingParseError.new("Backreference to undefined group \\" .. num, startPos, self.src))
            end
        end
        return { type = "Backreference", index = num }
    end
    
    if nxt == "b" then
        self.cur:take()
        return { type = "Anchor", at = "WordBoundary" }
    end
    if nxt == "B" then
        self.cur:take()
        return { type = "Anchor", at = "NotWordBoundary" }
    end
    if nxt == "A" then
        self.cur:take()
        return { type = "Anchor", at = "AbsoluteStart" }
    end
    if nxt == "Z" then
        self.cur:take()
        return { type = "Anchor", at = "EndBeforeFinalNewline" }
    end
    
    if nxt == "k" then
        self.cur:take()
        if not self.cur:match("<") then
            error(STRlingParseError.new("Expected '<' after \\k", startPos, self.src))
        end
        local name = ""
        while self.cur:peek() ~= ">" and self.cur:peek() ~= "" do
            name = name .. self.cur:take()
        end
        if not self.cur:match(">") then
            error(STRlingParseError.new("Unterminated named backref", startPos, self.src))
        end
        if not self.capNames[name] then
            error(STRlingParseError.new("Backreference to undefined group <" .. name .. ">", startPos, self.src))
        end
        return { type = "Backreference", name = name }
    end
    
    if ("dDwWsS"):find(nxt, 1, true) then
        local ch = self.cur:take()
        local kind
        if ch == "d" then kind = "digit"
        elseif ch == "D" then kind = "not-digit"
        elseif ch == "w" then kind = "word"
        elseif ch == "W" then kind = "not-word"
        elseif ch == "s" then kind = "space"
        elseif ch == "S" then kind = "not-space"
        end
        return { type = "CharacterClass", negated = false, members = { { type = "Escape", kind = kind } } }
    end
    
    if nxt == "p" or nxt == "P" then
        local tp = self.cur:take()
        if not self.cur:match("{") then
            error(STRlingParseError.new("Expected '{' after \\p/\\P", startPos, self.src))
        end
        local prop = ""
        while self.cur:peek() ~= "}" and self.cur:peek() ~= "" do
            prop = prop .. self.cur:take()
        end
        if not self.cur:match("}") then
            error(STRlingParseError.new("Unterminated \\p{...}", startPos, self.src))
        end
        return {
            type = "CharacterClass",
            negated = false,
            members = { { type = "UnicodeProperty", value = prop, negated = (tp == "P") } }
        }
    end
    
    if CONTROL_ESCAPES[nxt] then
        self.cur:take()
        return { type = "Literal", value = CONTROL_ESCAPES[nxt] }
    end
    
    if nxt == "x" then
        self.cur:take()
        return { type = "Literal", value = self:parseHexEscape(startPos) }
    end
    
    if nxt == "u" or nxt == "U" then
        return { type = "Literal", value = self:parseUnicodeEscape(startPos) }
    end
    
    if nxt == "0" then
        self.cur:take()
        return { type = "Literal", value = "\0" }
    end
    
    return { type = "Literal", value = self.cur:take() }
end

function Parser:parseHexEscape(startPos)
    if self.cur:match("{") then
        local hex = ""
        while self.cur:peek():match("[0-9A-Fa-f]") do
            hex = hex .. self.cur:take()
        end
        if not self.cur:match("}") then
            error(STRlingParseError.new("Unterminated \\x{...}", startPos, self.src))
        end
        local code = tonumber(hex == "" and "0" or hex, 16)
        return utf8.char(code)
    end
    
    local h1 = self.cur:take()
    local h2 = self.cur:take()
    if not h1:match("[0-9A-Fa-f]") or not h2:match("[0-9A-Fa-f]") then
        error(STRlingParseError.new("Invalid \\xHH escape", startPos, self.src))
    end
    return string.char(tonumber(h1 .. h2, 16))
end

function Parser:parseUnicodeEscape(startPos)
    local tp = self.cur:take()
    
    if tp == "u" and self.cur:match("{") then
        local hex = ""
        while self.cur:peek():match("[0-9A-Fa-f]") do
            hex = hex .. self.cur:take()
        end
        if not self.cur:match("}") then
            error(STRlingParseError.new("Unterminated \\u{...}", startPos, self.src))
        end
        local code = tonumber(hex == "" and "0" or hex, 16)
        return utf8.char(code)
    end
    
    if tp == "u" then
        local hex = ""
        for _ = 1, 4 do
            hex = hex .. self.cur:take()
        end
        if not hex:match("^[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]$") then
            error(STRlingParseError.new("Invalid \\uHHHH escape", startPos, self.src))
        end
        return utf8.char(tonumber(hex, 16))
    end
    
    if tp == "U" then
        local hex = ""
        for _ = 1, 8 do
            hex = hex .. self.cur:take()
        end
        if not hex:match("^[0-9A-Fa-f]+$") or #hex ~= 8 then
            error(STRlingParseError.new("Invalid \\UHHHHHHHH escape", startPos, self.src))
        end
        return utf8.char(tonumber(hex, 16))
    end
    
    error(STRlingParseError.new("Invalid unicode escape", startPos, self.src))
end

-- Module exports
local M = {}
M.Parser = Parser
M.Flags = Flags
M.STRlingParseError = STRlingParseError

function M.parse(src)
    local parser = Parser.new(src)
    return parser:parse()
end

return M
