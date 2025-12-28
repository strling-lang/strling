namespace STRling.Core

open System
open System.Text.RegularExpressions
open STRling

/// Recursive descent parser for the STRling DSL.
/// Parses pattern syntax into Abstract Syntax Tree (AST) nodes.
module Parser =
    
    /// Control escape character mappings.
    let private controlEscapes =
        dict [
            'n', "\n"
            'r', "\r"
            't', "\t"
            'f', "\f"
            'v', "\u000B"
        ]
    
    /// Internal cursor for tracking position within the input text.
    type private Cursor(text: string, startPos: int, extendedMode: bool, inClass: int) =
        let mutable i = startPos
        let mutable inClassCount = inClass
        
        member _.Text = text
        member _.I with get() = i and set(v) = i <- v
        member _.ExtendedMode = extendedMode
        member _.InClass with get() = inClassCount and set(v) = inClassCount <- v
        
        member _.Eof() = i >= text.Length
        
        member _.Peek(?n: int) =
            let offset = defaultArg n 0
            let j = i + offset
            if j >= text.Length then '\000' else text.[j]
        
        member this.Take() =
            if this.Eof() then '\000'
            else
                let ch = text.[i]
                i <- i + 1
                ch
        
        member this.Match(s: string) =
            if text.Substring(i).StartsWith(s) then
                i <- i + s.Length
                true
            else
                false
        
        member this.SkipWsAndComments() =
            if not extendedMode || inClassCount > 0 then ()
            else
                let mutable cont = true
                while cont && not (this.Eof()) do
                    let ch = this.Peek()
                    if " \t\r\n".Contains(ch) then
                        i <- i + 1
                    elif ch = '#' then
                        while not (this.Eof()) && not ("\r\n".Contains(this.Peek())) do
                            i <- i + 1
                    else
                        cont <- false
    
    /// Result of parsing directives from the input.
    type private DirectiveResult = {
        Flags: Flags
        Pattern: string
    }
    
    /// Parse directives (like %flags) from the pattern.
    let private parseDirectives (text: string) : DirectiveResult =
        let mutable flags = Flags.defaultFlags
        let lines = text.Split('\n')
        let patternLines = ResizeArray<string>()
        let mutable inPattern = false
        let mutable lineNum = 0
        
        for rawLine in lines do
            lineNum <- lineNum + 1
            let line = rawLine.TrimEnd('\r')
            let stripped = line.Trim()
            
            // Skip leading blank lines or comments
            if not inPattern && (stripped = "" || stripped.StartsWith("#")) then
                ()
            // Process %flags directive
            elif not inPattern && stripped.StartsWith("%flags") then
                let idx = line.IndexOf("%flags")
                let after = line.Substring(idx + "%flags".Length)
                
                // Normalize separators and whitespace
                let letters = Regex.Replace(after, @"[,\[\]\s]+", " ").Trim().ToLower()
                let validFlags = set ['i'; 'm'; 's'; 'u'; 'x']
                
                for ch in letters.Replace(" ", "") do
                    if ch <> '\000' && not (validFlags.Contains(ch)) then
                        let pos = lines |> Seq.take (lineNum - 1) |> Seq.sumBy (fun l -> l.Length + 1)
                        let hint = HintEngine.getHint (sprintf "Invalid flag '%c'" ch) text pos
                        raise (STRlingParseError(sprintf "Invalid flag '%c'" ch, pos + idx, text, ?hint = hint))
                
                flags <- Flags.fromLetters letters
                
                // Check for remainder pattern content on the same line
                let remainder = after.Trim()
                if remainder.Length > 0 && not (remainder |> Seq.forall (fun c -> " ,\t[]imsuxIMSUX".Contains(c))) then
                    inPattern <- true
                    let patternStart = after |> Seq.takeWhile (fun c -> " ,\t[]imsuxIMSUX".Contains(c)) |> Seq.length
                    if patternStart < after.Length then
                        patternLines.Add(after.Substring(patternStart))
                else
                    inPattern <- true
            // Reject unknown directives
            elif not inPattern && stripped.StartsWith("%") then
                ()
            // Check for directive after pattern content
            elif line.Contains("%flags") then
                let pos = lines |> Seq.take (lineNum - 1) |> Seq.sumBy (fun l -> l.Length + 1)
                let hint = HintEngine.getHint "Directive after pattern content" text pos
                raise (STRlingParseError("Directive after pattern content", pos + line.IndexOf("%flags"), text, ?hint = hint))
            else
                inPattern <- true
                patternLines.Add(line)
        
        { Flags = flags; Pattern = String.concat "\n" patternLines }
    
    /// Parse a STRling pattern string into flags and AST.
    let parse (text: string) : Flags * Node =
        let dirResult = parseDirectives text
        let src = dirResult.Pattern
        let flags = dirResult.Flags
        let cur = Cursor(src, 0, flags.Extended, 0)
        let mutable capCount = 0
        let capNames = System.Collections.Generic.HashSet<string>()
        
        let raiseError msg pos =
            let hint = HintEngine.getHint msg src pos
            raise (STRlingParseError(msg, pos, src, ?hint = hint))
        
        let rec parsePattern () =
            cur.SkipWsAndComments()
            if cur.Eof() then Lit ""
            else
                let node = parseAlt()
                cur.SkipWsAndComments()
                if not (cur.Eof()) then
                    raiseError "Unexpected trailing input" cur.I
                node
        
        and parseAlt () =
            let branches = ResizeArray<Node>()
            branches.Add(parseSeq())
            
            while cur.Peek() = '|' do
                cur.Take() |> ignore
                cur.SkipWsAndComments()
                branches.Add(parseSeq())
            
            if branches.Count = 1 then branches.[0]
            else Alt (List.ofSeq branches)
        
        and parseSeq () =
            let parts = ResizeArray<Node>()
            let mutable prevHadFailedQuant = false
            
            let mutable cont = true
            while cont && not (cur.Eof()) do
                cur.SkipWsAndComments()
                let ch = cur.Peek()
                
                if ch <> '\000' && "*+?{".Contains(ch) && parts.Count = 0 then
                    raiseError (sprintf "Invalid quantifier '%c'" ch) cur.I
                
                if ch = '|' || ch = ')' || ch = '\000' then
                    cont <- false
                else
                    let atom = parseAtom()
                    let (quantified, hadFailedQuant) = parseQuantIfAny atom
                    
                    let mutable shouldCoalesce = false
                    match quantified, (if parts.Count > 0 then Some parts.[parts.Count - 1] else None) with
                    | Lit currentVal, Some (Lit lastVal) when not cur.ExtendedMode && not prevHadFailedQuant && not (currentVal.Contains("\n")) && not (lastVal.Contains("\n")) ->
                        shouldCoalesce <- true
                        parts.[parts.Count - 1] <- Lit (lastVal + currentVal)
                    | _ -> ()
                    
                    if not shouldCoalesce then
                        parts.Add(quantified)
                    
                    prevHadFailedQuant <- hadFailedQuant
            
            if parts.Count = 0 then Lit ""
            elif parts.Count = 1 then parts.[0]
            else Seq (List.ofSeq parts)
        
        and parseAtom () =
            cur.SkipWsAndComments()
            let ch = cur.Peek()
            
            match ch with
            | '^' ->
                cur.Take() |> ignore
                Anchor "Start"
            | '$' ->
                cur.Take() |> ignore
                Anchor "End"
            | '.' ->
                cur.Take() |> ignore
                Dot
            | '\\' ->
                parseEscapeAtom()
            | '(' ->
                parseGroupOrLook()
            | '[' ->
                parseCharClass()
            | ')' | ']' | '|' | '*' | '+' | '?' | '{' ->
                raiseError (sprintf "Unexpected token '%c'" ch) cur.I
                Lit ""
            | _ ->
                takeLiteralChar()
        
        and parseEscapeAtom () =
            let startPos = cur.I
            cur.Take() |> ignore
            
            if cur.Eof() then
                raiseError "Unexpected end of pattern after '\\'" startPos
            
            let ch = cur.Take()
            
            match ch with
            | 'b' -> Anchor "WordBoundary"
            | 'B' -> Anchor "NotWordBoundary"
            | 'A' -> Anchor "AbsoluteStart"
            | 'Z' -> Anchor "EndBeforeFinalNewline"
            | 'd' -> CharClass (false, [ClassEscape "digit"])
            | 'D' -> CharClass (false, [ClassEscape "not-digit"])
            | 'w' -> CharClass (false, [ClassEscape "word"])
            | 'W' -> CharClass (false, [ClassEscape "not-word"])
            | 's' -> CharClass (false, [ClassEscape "whitespace"])
            | 'S' -> CharClass (false, [ClassEscape "not-whitespace"])
            | 'n' -> Lit (controlEscapes.['n'])
            | 'r' -> Lit (controlEscapes.['r'])
            | 't' -> Lit (controlEscapes.['t'])
            | 'f' -> Lit (controlEscapes.['f'])
            | 'v' -> Lit (controlEscapes.['v'])
            | 'k' ->
                // Named backreference \k<name>
                if cur.Peek() = '<' then
                    cur.Take() |> ignore
                    let name = readIdentUntil '>'
                    if cur.Peek() <> '>' then
                        raiseError "Unterminated backreference name" startPos
                    cur.Take() |> ignore
                    Backref (None, Some name)
                else
                    raiseError "Expected '<' after \\k" startPos
                    Lit ""
            | c when c >= '1' && c <= '9' ->
                // Numeric backreference
                let mutable numStr = string c
                while cur.Peek() >= '0' && cur.Peek() <= '9' do
                    numStr <- numStr + string (cur.Take())
                Backref (Some (int numStr), None)
            | c when "^$.*+?()[]{}|\\".Contains(c) ->
                Lit (string c)
            | c ->
                raiseError (sprintf "Unknown escape sequence \\%c" c) startPos
                Lit ""
        
        and parseGroupOrLook () =
            let startPos = cur.I
            cur.Take() |> ignore
            cur.SkipWsAndComments()
            
            if cur.Peek() = '?' then
                cur.Take() |> ignore
                let next = cur.Peek()
                
                match next with
                | ':' ->
                    cur.Take() |> ignore
                    let body = parseAlt()
                    if cur.Peek() <> ')' then raiseError "Unterminated group" startPos
                    cur.Take() |> ignore
                    Group (false, None, false, body)
                | '=' ->
                    cur.Take() |> ignore
                    let body = parseAlt()
                    if cur.Peek() <> ')' then raiseError "Unterminated lookahead" startPos
                    cur.Take() |> ignore
                    Lookahead body
                | '!' ->
                    cur.Take() |> ignore
                    let body = parseAlt()
                    if cur.Peek() <> ')' then raiseError "Unterminated lookahead" startPos
                    cur.Take() |> ignore
                    NegativeLookahead body
                | '<' ->
                    cur.Take() |> ignore
                    let afterAngle = cur.Peek()
                    if afterAngle = '=' then
                        cur.Take() |> ignore
                        let body = parseAlt()
                        if cur.Peek() <> ')' then raiseError "Unterminated lookbehind" startPos
                        cur.Take() |> ignore
                        Lookbehind body
                    elif afterAngle = '!' then
                        cur.Take() |> ignore
                        let body = parseAlt()
                        if cur.Peek() <> ')' then raiseError "Unterminated lookbehind" startPos
                        cur.Take() |> ignore
                        NegativeLookbehind body
                    else
                        // Named capturing group
                        let name = readIdentUntil '>'
                        if cur.Peek() <> '>' then raiseError "Unterminated group name" startPos
                        cur.Take() |> ignore
                        capCount <- capCount + 1
                        capNames.Add(name) |> ignore
                        let body = parseAlt()
                        if cur.Peek() <> ')' then raiseError "Unterminated group" startPos
                        cur.Take() |> ignore
                        Group (true, Some name, false, body)
                | '>' ->
                    cur.Take() |> ignore
                    let body = parseAlt()
                    if cur.Peek() <> ')' then raiseError "Unterminated atomic group" startPos
                    cur.Take() |> ignore
                    Group (false, None, true, body)
                | _ ->
                    raiseError (sprintf "Unknown group type '(?%c'" next) startPos
                    Lit ""
            else
                // Capturing group
                capCount <- capCount + 1
                let body = parseAlt()
                if cur.Peek() <> ')' then raiseError "Unterminated group" startPos
                cur.Take() |> ignore
                Group (true, None, false, body)
        
        and parseCharClass () =
            let startPos = cur.I
            cur.Take() |> ignore
            cur.InClass <- cur.InClass + 1
            
            let negated = 
                if cur.Peek() = '^' then
                    cur.Take() |> ignore
                    true
                else
                    false
            
            let items = ResizeArray<ClassItem>()
            
            while not (cur.Eof()) && cur.Peek() <> ']' do
                items.Add(readClassItem())
            
            if cur.Peek() <> ']' then
                raiseError "Unterminated character class" startPos
            
            cur.InClass <- cur.InClass - 1
            cur.Take() |> ignore
            
            CharClass (negated, List.ofSeq items)
        
        and readClassItem () =
            let ch = cur.Peek()
            
            if ch = '\\' then
                cur.Take() |> ignore
                let escCh = cur.Take()
                
                match escCh with
                | 'd' -> ClassEscape "digit"
                | 'D' -> ClassEscape "not-digit"
                | 'w' -> ClassEscape "word"
                | 'W' -> ClassEscape "not-word"
                | 's' -> ClassEscape "whitespace"
                | 'S' -> ClassEscape "not-whitespace"
                | 'n' -> ClassLiteral "\n"
                | 'r' -> ClassLiteral "\r"
                | 't' -> ClassLiteral "\t"
                | c -> ClassLiteral (string c)
            else
                let literal = string (cur.Take())
                
                if cur.Peek() = '-' && cur.Peek(1) <> ']' then
                    cur.Take() |> ignore
                    let endCh = string (cur.Take())
                    ClassRange (literal, endCh)
                else
                    ClassLiteral literal
        
        and parseQuantIfAny (child: Node) : Node * bool =
            cur.SkipWsAndComments()
            let ch = cur.Peek()
            
            match child with
            | Anchor _ when "*+?{".Contains(ch) ->
                raiseError "Cannot quantify anchor" cur.I
                (child, false)
            | Anchor _ ->
                (child, false)
            | _ ->
                let mutable min = 0
                let mutable max = None
                let mutable greedy = true
                let mutable lazy_ = false
                let mutable possessive = false
                let mutable matched = true
                
                match ch with
                | '*' ->
                    cur.Take() |> ignore
                    min <- 0
                    max <- None
                | '+' ->
                    cur.Take() |> ignore
                    min <- 1
                    max <- None
                | '?' ->
                    cur.Take() |> ignore
                    min <- 0
                    max <- Some 1
                | '{' ->
                    let result = parseBraceQuant()
                    match result with
                    | Some (minVal, maxVal) ->
                        min <- minVal
                        max <- maxVal
                    | None ->
                        matched <- false
                | _ ->
                    matched <- false
                
                if not matched then
                    (child, false)
                else
                    if cur.Peek() = '?' then
                        cur.Take() |> ignore
                        greedy <- false
                        lazy_ <- true
                    elif cur.Peek() = '+' then
                        cur.Take() |> ignore
                        greedy <- false
                        possessive <- true
                    
                    (Quant (child, min, max, greedy, lazy_, possessive), true)
        
        and parseBraceQuant () =
            let startPos = cur.I
            cur.Take() |> ignore
            cur.SkipWsAndComments()
            
            let mutable minStr = ""
            while Char.IsDigit(cur.Peek()) do
                minStr <- minStr + string (cur.Take())
            
            if minStr = "" then
                raiseError "Invalid brace quantifier content" startPos
                None
            else
                let min = int minStr
                let mutable max = Some min
                
                cur.SkipWsAndComments()
                if cur.Peek() = ',' then
                    cur.Take() |> ignore
                    cur.SkipWsAndComments()
                    
                    let mutable maxStr = ""
                    while Char.IsDigit(cur.Peek()) do
                        maxStr <- maxStr + string (cur.Take())
                    
                    max <- if maxStr = "" then None else Some (int maxStr)
                
                cur.SkipWsAndComments()
                if cur.Peek() <> '}' then
                    raiseError "Unterminated {m,n}" startPos
                    None
                else
                    cur.Take() |> ignore
                    Some (min, max)
        
        and takeLiteralChar () =
            let ch = cur.Take()
            Lit (string ch)
        
        and readIdentUntil (endChar: char) =
            let mutable ident = ""
            while not (cur.Eof()) && cur.Peek() <> endChar do
                ident <- ident + string (cur.Take())
            ident
        
        // Execute parsing
        let ast = parsePattern()
        (flags, ast)
