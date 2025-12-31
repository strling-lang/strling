/// STRling Parser - Recursive Descent Parser for Swift
///
/// Transforms STRling DSL patterns into AST nodes.
/// Mirrors the TypeScript reference implementation.

import Foundation

// MARK: - Control Escapes

private let controlEscapes: [Character: String] = [
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "f": "\u{000C}",
    "v": "\u{000B}"
]

// MARK: - Cursor

/// Cursor for tracking position in input text
private class Cursor {
    let text: String
    var i: String.Index
    var extendedMode: Bool
    var inClass: Int = 0
    
    init(_ text: String, extendedMode: Bool = false) {
        self.text = text
        self.i = text.startIndex
        self.extendedMode = extendedMode
    }
    
    var eof: Bool {
        i >= text.endIndex
    }
    
    var position: Int {
        text.distance(from: text.startIndex, to: i)
    }
    
    func peek(_ offset: Int = 0) -> Character? {
        guard let idx = text.index(i, offsetBy: offset, limitedBy: text.index(before: text.endIndex)) else {
            if offset == 0 && !eof {
                return text[i]
            }
            return nil
        }
        if idx >= text.endIndex {
            return nil
        }
        return text[idx]
    }
    
    func peekString(_ offset: Int = 0) -> String {
        guard let ch = peek(offset) else { return "" }
        return String(ch)
    }
    
    func take() -> Character? {
        guard !eof else { return nil }
        let ch = text[i]
        i = text.index(after: i)
        return ch
    }
    
    func takeString() -> String {
        guard let ch = take() else { return "" }
        return String(ch)
    }
    
    func match(_ s: String) -> Bool {
        guard let endIdx = text.index(i, offsetBy: s.count, limitedBy: text.endIndex) else {
            return false
        }
        if text[i..<endIdx] == s {
            i = endIdx
            return true
        }
        return false
    }
    
    func skipWsAndComments() {
        guard extendedMode && inClass == 0 else { return }
        while !eof {
            guard let ch = peek() else { break }
            if " \t\r\n".contains(ch) {
                _ = take()
                continue
            }
            if ch == "#" {
                while !eof {
                    guard let c = peek() else { break }
                    if "\r\n".contains(c) { break }
                    _ = take()
                }
                continue
            }
            break
        }
    }
}

// MARK: - Parser

/// STRling DSL Parser
public class Parser {
    private var flags: Flags
    private var src: String
    private var cur: Cursor
    private var capCount: Int = 0
    private var capNames: Set<String> = []
    
    /// Initialize parser with source text
    ///
    /// - Parameter text: The STRling DSL source text
    public init(_ text: String) {
        let (parsedFlags, pattern) = Parser.parseDirectives(text)
        self.flags = parsedFlags
        self.src = pattern
        self.cur = Cursor(pattern, extendedMode: parsedFlags.extended)
    }
    
    private static func parseDirectives(_ text: String) -> (Flags, String) {
        var flags = Flags()
        var pattern = text
        
        // Match %flags directive
        if let match = text.range(of: #"^\s*%flags\s*([imsux,\[\]\s]*)"#, options: .regularExpression) {
            let flagStr = String(text[match]).components(separatedBy: "%flags").last ?? ""
            let cleaned = flagStr.lowercased().filter { !",[]\t\n\r ".contains($0) }
            flags = Flags.fromLetters(cleaned)
            
            // Remove directive lines
            let lines = text.components(separatedBy: "\n")
            var patternLines: [String] = []
            var inPattern = false
            
            for line in lines {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if !inPattern && (trimmed.hasPrefix("%flags") || trimmed.isEmpty || trimmed.hasPrefix("#")) {
                    continue
                }
                inPattern = true
                patternLines.append(line)
            }
            pattern = patternLines.joined(separator: "\n")
        }
        
        return (flags, pattern)
    }
    
    /// Parse the source text
    ///
    /// - Returns: Tuple of flags and root AST node
    /// - Throws: STRlingParseError on parse failure
    public func parse() throws -> (Flags, Node) {
        let node = try parseAlt()
        cur.skipWsAndComments()
        
        if !cur.eof {
            if cur.peekString() == ")" {
                throw STRlingParseError(message: "Unmatched ')'", pos: cur.position, text: src)
            }
            throw STRlingParseError(message: "Unexpected trailing input", pos: cur.position, text: src)
        }
        
        return (flags, node)
    }
    
    private func parseAlt() throws -> Node {
        cur.skipWsAndComments()
        
        if cur.peekString() == "|" {
            throw STRlingParseError(message: "Alternation lacks left-hand side", pos: cur.position, text: src)
        }
        
        var branches: [Node] = [try parseSeq()]
        cur.skipWsAndComments()
        
        while cur.peekString() == "|" {
            let pipePos = cur.position
            _ = cur.take()
            cur.skipWsAndComments()
            
            if cur.eof || cur.peekString() == "|" {
                throw STRlingParseError(message: "Alternation lacks right-hand side", pos: pipePos, text: src)
            }
            
            branches.append(try parseSeq())
            cur.skipWsAndComments()
        }
        
        if branches.count == 1 { return branches[0] }
        return .alt(Alt(branches: branches))
    }
    
    private func parseSeq() throws -> Node {
        var parts: [Node] = []
        
        while true {
            cur.skipWsAndComments()
            let ch = cur.peekString()
            
            if "*+?{".contains(ch) && parts.isEmpty {
                throw STRlingParseError(message: "Invalid quantifier '\(ch)'", pos: cur.position, text: src)
            }
            
            if ch.isEmpty || "|)".contains(ch) { break }
            
            var atom = try parseAtom()
            atom = try parseQuantIfAny(child: atom)
            parts.append(atom)
        }
        
        if parts.count == 1 { return parts[0] }
        return .seq(Seq(parts: parts))
    }
    
    private func parseAtom() throws -> Node {
        cur.skipWsAndComments()
        let ch = cur.peekString()
        
        if ch == "." {
            _ = cur.take()
            return .dot(Dot())
        }
        if ch == "^" {
            _ = cur.take()
            return .anchor(Anchor(at: "Start"))
        }
        if ch == "$" {
            _ = cur.take()
            return .anchor(Anchor(at: "End"))
        }
        if ch == "(" {
            return try parseGroupOrLook()
        }
        if ch == "[" {
            return try parseCharClass()
        }
        if ch == "\\" {
            return try parseEscapeAtom()
        }
        if ch == ")" {
            throw STRlingParseError(message: "Unmatched ')'", pos: cur.position, text: src)
        }
        
        return .lit(Lit(value: cur.takeString()))
    }
    
    private func parseQuantIfAny(child: Node) throws -> Node {
        let ch = cur.peekString()
        var min: Int?
        var max: QuantMax?
        var mode = "Greedy"
        
        if ch == "*" {
            min = 0
            max = .inf
            _ = cur.take()
        } else if ch == "+" {
            min = 1
            max = .inf
            _ = cur.take()
        } else if ch == "?" {
            min = 0
            max = .count(1)
            _ = cur.take()
        } else if ch == "{" {
            let _ = cur.position  // savePos - reserved for future use
            let saveI = cur.i
            _ = cur.take()
            
            guard let m = readIntOptional() else {
                cur.i = saveI
                return child
            }
            
            min = m
            max = .count(m)
            
            if cur.peekString() == "," {
                _ = cur.take()
                if let n = readIntOptional() {
                    max = .count(n)
                } else {
                    max = .inf
                }
            }
            
            if cur.peekString() != "}" {
                throw STRlingParseError(message: "Incomplete quantifier", pos: cur.position, text: src)
            }
            _ = cur.take()
        } else {
            return child
        }
        
        // Check if child is an anchor
        if case .anchor = child {
            throw STRlingParseError(message: "Cannot quantify anchor", pos: cur.position, text: src)
        }
        
        let nxt = cur.peekString()
        if nxt == "?" {
            mode = "Lazy"
            _ = cur.take()
        } else if nxt == "+" {
            mode = "Possessive"
            _ = cur.take()
        }
        
        return .quant(Quant(child: child, min: min!, max: max!, mode: mode))
    }
    
    private func readIntOptional() -> Int? {
        var s = ""
        while let ch = cur.peek(), ch.isNumber {
            s += cur.takeString()
        }
        return s.isEmpty ? nil : Int(s)
    }
    
    private func parseGroupOrLook() throws -> Node {
        _ = cur.take() // consume '('
        
        if cur.match("?:") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated group", pos: cur.position, text: src)
            }
            return .group(Group(capturing: false, body: body))
        }
        
        if cur.match("?<=") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated lookbehind", pos: cur.position, text: src)
            }
            return .look(Look(dir: "Behind", neg: false, body: body))
        }
        
        if cur.match("?<!") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated lookbehind", pos: cur.position, text: src)
            }
            return .look(Look(dir: "Behind", neg: true, body: body))
        }
        
        if cur.match("?<") {
            var name = ""
            while cur.peekString() != ">" && !cur.eof {
                name += cur.takeString()
            }
            if !cur.match(">") {
                throw STRlingParseError(message: "Unterminated group name", pos: cur.position, text: src)
            }
            if capNames.contains(name) {
                throw STRlingParseError(message: "Duplicate group name <\(name)>", pos: cur.position, text: src)
            }
            capCount += 1
            capNames.insert(name)
            
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated group", pos: cur.position, text: src)
            }
            return .group(Group(capturing: true, body: body, name: name))
        }
        
        if cur.match("?>") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated atomic group", pos: cur.position, text: src)
            }
            return .group(Group(capturing: false, body: body, atomic: true))
        }
        
        if cur.match("?=") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated lookahead", pos: cur.position, text: src)
            }
            return .look(Look(dir: "Ahead", neg: false, body: body))
        }
        
        if cur.match("?!") {
            let body = try parseAlt()
            if !cur.match(")") {
                throw STRlingParseError(message: "Unterminated lookahead", pos: cur.position, text: src)
            }
            return .look(Look(dir: "Ahead", neg: true, body: body))
        }
        
        capCount += 1
        let body = try parseAlt()
        if !cur.match(")") {
            throw STRlingParseError(message: "Unterminated group", pos: cur.position, text: src)
        }
        return .group(Group(capturing: true, body: body))
    }
    
    private func parseCharClass() throws -> Node {
        _ = cur.take() // consume '['
        cur.inClass += 1
        
        var neg = false
        if cur.peekString() == "^" {
            neg = true
            _ = cur.take()
        }
        
        var items: [ClassItem] = []
        
        while !cur.eof && cur.peekString() != "]" {
            if cur.peekString() == "\\" {
                items.append(try parseClassEscape())
            } else {
                let ch = cur.takeString()
                
                if cur.peekString() == "-" && cur.peek(1).map({ String($0) }) != "]" {
                    _ = cur.take() // consume '-'
                    let endCh = cur.takeString()
                    items.append(ClassRange(fromCh: ch, toCh: endCh))
                } else {
                    items.append(ClassLiteral(ch: ch))
                }
            }
        }
        
        if cur.eof {
            throw STRlingParseError(message: "Unterminated character class", pos: cur.position, text: src)
        }
        
        _ = cur.take() // consume ']'
        cur.inClass -= 1
        
        return .charClass(CharClass(negated: neg, items: items))
    }
    
    private func parseClassEscape() throws -> ClassItem {
        let startPos = cur.position
        _ = cur.take() // consume '\'
        
        guard let nxt = cur.peek() else {
            throw STRlingParseError(message: "Unexpected end of escape", pos: startPos, text: src)
        }
        
        if "dDwWsS".contains(nxt) {
            let ch = cur.takeString()
            let type = switch ch {
                case "d": "d"
                case "D": "D"
                case "w": "w"
                case "W": "W"
                case "s": "s"
                case "S": "S"
                default: ch
            }
            return ClassEscape(type: type)
        }
        
        if nxt == "p" || nxt == "P" {
            let tp = cur.takeString()
            if !cur.match("{") {
                throw STRlingParseError(message: "Expected '{' after \\p/\\P", pos: startPos, text: src)
            }
            var prop = ""
            while cur.peekString() != "}" && !cur.eof {
                prop += cur.takeString()
            }
            if !cur.match("}") {
                throw STRlingParseError(message: "Unterminated \\p{...}", pos: startPos, text: src)
            }
            return ClassEscape(type: tp, property: prop)
        }
        
        if let escaped = controlEscapes[nxt] {
            _ = cur.take()
            return ClassLiteral(ch: escaped)
        }
        
        if nxt == "b" {
            _ = cur.take()
            return ClassLiteral(ch: "\u{0008}")  // Backspace
        }
        
        if nxt == "0" {
            _ = cur.take()
            return ClassLiteral(ch: "\0")
        }
        
        return ClassLiteral(ch: cur.takeString())
    }
    
    private func parseEscapeAtom() throws -> Node {
        let startPos = cur.position
        _ = cur.take() // consume '\'
        
        guard let nxt = cur.peek() else {
            throw STRlingParseError(message: "Unexpected end of escape", pos: startPos, text: src)
        }
        
        // Backreference
        if nxt.isNumber && nxt != "0" {
            var num = 0
            while let ch = cur.peek(), ch.isNumber {
                num = num * 10 + Int(String(cur.take()!))!
                if num > capCount {
                    throw STRlingParseError(message: "Backreference to undefined group \\\(num)", pos: startPos, text: src)
                }
            }
            return .backref(Backref(byIndex: num))
        }
        
        if nxt == "b" {
            _ = cur.take()
            return .anchor(Anchor(at: "WordBoundary"))
        }
        if nxt == "B" {
            _ = cur.take()
            return .anchor(Anchor(at: "NotWordBoundary"))
        }
        if nxt == "A" {
            _ = cur.take()
            return .anchor(Anchor(at: "AbsoluteStart"))
        }
        if nxt == "Z" {
            _ = cur.take()
            return .anchor(Anchor(at: "EndBeforeFinalNewline"))
        }
        
        if nxt == "k" {
            _ = cur.take()
            if !cur.match("<") {
                throw STRlingParseError(message: "Expected '<' after \\k", pos: startPos, text: src)
            }
            var name = ""
            while cur.peekString() != ">" && !cur.eof {
                name += cur.takeString()
            }
            if !cur.match(">") {
                throw STRlingParseError(message: "Unterminated named backref", pos: startPos, text: src)
            }
            if !capNames.contains(name) {
                throw STRlingParseError(message: "Backreference to undefined group <\(name)>", pos: startPos, text: src)
            }
            return .backref(Backref(byName: name))
        }
        
        if "dDwWsS".contains(nxt) {
            let ch = cur.takeString()
            let type = switch ch {
                case "d": "d"
                case "D": "D"
                case "w": "w"
                case "W": "W"
                case "s": "s"
                case "S": "S"
                default: ch
            }
            return .charClass(CharClass(negated: false, items: [ClassEscape(type: type)]))
        }
        
        if nxt == "p" || nxt == "P" {
            let tp = cur.takeString()
            if !cur.match("{") {
                throw STRlingParseError(message: "Expected '{' after \\p/\\P", pos: startPos, text: src)
            }
            var prop = ""
            while cur.peekString() != "}" && !cur.eof {
                prop += cur.takeString()
            }
            if !cur.match("}") {
                throw STRlingParseError(message: "Unterminated \\p{...}", pos: startPos, text: src)
            }
            return .charClass(CharClass(negated: false, items: [ClassEscape(type: tp, property: prop)]))
        }
        
        if let escaped = controlEscapes[nxt] {
            _ = cur.take()
            return .lit(Lit(value: escaped))
        }
        
        if nxt == "x" {
            _ = cur.take()
            return .lit(Lit(value: try parseHexEscape(startPos)))
        }
        
        if nxt == "u" || nxt == "U" {
            return .lit(Lit(value: try parseUnicodeEscape(startPos)))
        }
        
        if nxt == "0" {
            _ = cur.take()
            return .lit(Lit(value: "\0"))
        }
        
        return .lit(Lit(value: cur.takeString()))
    }
    
    private func parseHexEscape(_ startPos: Int) throws -> String {
        if cur.match("{") {
            var hex = ""
            while let ch = cur.peek(), ch.isHexDigit {
                hex += cur.takeString()
            }
            if !cur.match("}") {
                throw STRlingParseError(message: "Unterminated \\x{...}", pos: startPos, text: src)
            }
            let code = Int(hex.isEmpty ? "0" : hex, radix: 16) ?? 0
            return String(UnicodeScalar(code)!)
        }
        
        let h1 = cur.takeString()
        let h2 = cur.takeString()
        guard h1.first?.isHexDigit == true && h2.first?.isHexDigit == true else {
            throw STRlingParseError(message: "Invalid \\xHH escape", pos: startPos, text: src)
        }
        let code = Int(h1 + h2, radix: 16) ?? 0
        return String(UnicodeScalar(code)!)
    }
    
    private func parseUnicodeEscape(_ startPos: Int) throws -> String {
        let tp = cur.takeString()
        
        if tp == "u" && cur.match("{") {
            var hex = ""
            while let ch = cur.peek(), ch.isHexDigit {
                hex += cur.takeString()
            }
            if !cur.match("}") {
                throw STRlingParseError(message: "Unterminated \\u{...}", pos: startPos, text: src)
            }
            let code = Int(hex.isEmpty ? "0" : hex, radix: 16) ?? 0
            return String(UnicodeScalar(code)!)
        }
        
        if tp == "u" {
            var hex = ""
            for _ in 0..<4 {
                hex += cur.takeString()
            }
            guard hex.count == 4, Int(hex, radix: 16) != nil else {
                throw STRlingParseError(message: "Invalid \\uHHHH escape", pos: startPos, text: src)
            }
            let code = Int(hex, radix: 16)!
            return String(UnicodeScalar(code)!)
        }
        
        if tp == "U" {
            var hex = ""
            for _ in 0..<8 {
                hex += cur.takeString()
            }
            guard hex.count == 8, Int(hex, radix: 16) != nil else {
                throw STRlingParseError(message: "Invalid \\UHHHHHHHH escape", pos: startPos, text: src)
            }
            let code = Int(hex, radix: 16)!
            return String(UnicodeScalar(code)!)
        }
        
        throw STRlingParseError(message: "Invalid unicode escape", pos: startPos, text: src)
    }
}

// MARK: - Convenience Function

/// Parse a STRling DSL string into flags and AST
///
/// - Parameter src: The STRling DSL source text
/// - Returns: Tuple of flags and root AST node
/// - Throws: STRlingParseError on parse failure
public func parse(_ src: String) throws -> (Flags, Node) {
    let parser = Parser(src)
    return try parser.parse()
}
