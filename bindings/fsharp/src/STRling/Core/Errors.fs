namespace STRling.Core

open System

/// STRling Parse Error with position tracking and instructional hints.
/// This error class transforms parse failures into learning opportunities.
type STRlingParseError(message: string, pos: int, text: string, ?hint: string) =
    inherit Exception(STRlingParseError.FormatError(message, pos, text, hint))
    
    /// The error message.
    member _.ErrorMessage = message
    
    /// The character position (0-indexed) where the error occurred.
    member _.Pos = pos
    
    /// The full input text being parsed.
    member _.Text = text
    
    /// An instructional hint explaining how to fix the error.
    member _.Hint = hint
    
    static member private FormatError(message: string, pos: int, text: string, hint: string option) =
        if String.IsNullOrEmpty(text) then
            sprintf "%s at position %d" message pos
        else
            // Find the line containing the error
            let lines = text.Split('\n')
            let mutable currentPos = 0
            let mutable lineNum = 1
            let mutable lineText = ""
            let mutable col = pos
            
            for i = 0 to lines.Length - 1 do
                let line = lines.[i]
                let lineLen = line.Length + 1 // +1 for newline
                if currentPos + lineLen > pos && lineText = "" then
                    lineNum <- i + 1
                    lineText <- line.TrimEnd('\r')
                    col <- pos - currentPos
                currentPos <- currentPos + lineLen
            
            // Error is beyond the last line
            if lineText = "" && lines.Length > 0 then
                lineNum <- lines.Length
                lineText <- lines.[lines.Length - 1]
                col <- lineText.Length
            elif lineText = "" then
                lineText <- text
                col <- pos
            
            // Build the formatted error message
            let parts = ResizeArray<string>()
            parts.Add(sprintf "STRling Parse Error: %s" message)
            parts.Add("")
            parts.Add(sprintf "> %d | %s" lineNum lineText)
            parts.Add(sprintf ">   | %s^" (String.replicate col " "))
            
            match hint with
            | Some h ->
                parts.Add("")
                parts.Add(sprintf "Hint: %s" h)
            | None -> ()
            
            String.concat "\n" parts

/// Hint Engine for generating instructional error hints.
module HintEngine =
    /// Generate a helpful hint based on the error message and context.
    let getHint (message: string) (source: string) (pos: int) : string option =
        let msg = message.ToLower()
        
        if msg.Contains("unexpected token") then
            Some "Check for unbalanced parentheses or brackets."
        elif msg.Contains("unterminated") then
            Some "Make sure all groups, classes, and quoted sequences are properly closed."
        elif msg.Contains("invalid quantifier") then
            Some "Quantifiers like *, +, ?, {} must follow an expression to quantify."
        elif msg.Contains("invalid flag") then
            Some "Valid flags are: i (ignore case), m (multiline), s (dotAll), u (unicode), x (extended)"
        elif msg.Contains("escape sequence") then
            Some "Use valid escape sequences like \\n, \\t, \\d, \\w, \\s, or escape special chars with \\."
        elif msg.Contains("directive") then
            Some "Directives like %flags must appear at the start of the pattern, before any regex content."
        else
            None
