# **STRling LSP Architecture Specification: The Island Grammar Resolution via Virtual Document Projection**

## **1\. The Strategic Imperative of Embedded Tooling**

### **1.1 The Context of Evolution**

The evolution of the STRling project stands at a critical inflection point. Having successfully established a robust, readable, and object-oriented Domain Specific Language (DSL) for regular expression generation, the framework has effectively solved the _legibility_ problem inherent in raw regex syntax.1 However, the _usability_ problem—specifically the developer experience (DX) within the Integrated Development Environment (IDE)—remains partially unresolved. This document serves as the comprehensive architectural specification for bridging that gap, effectively moving STRling from a static library to a dynamic, integrated language tool.

The current state of the art involves a sophisticated compiler pipeline that transforms STRling code into PCRE2 or ECMAScript regex patterns.1 This pipeline is rigorous, validated by the "3-Test Standard" 1, and capable of producing highly optimized artifacts. Yet, for the end-user writing Python or JavaScript, this power is currently locked behind opaque string literals. When a developer types s.match("..., they step into a "Tooling Void" where the host language server (LSP) ceases to provide assistance. Syntax errors are caught only at runtime, and the rich semantic model of STRling remains inaccessible during the authoring phase.

This specification addresses "Research Directive 5: The Island Grammar Architecture." It proposes a normative, principled approach to injecting STRling intelligence directly into the string literals of host languages. By leveraging the **Virtual Document** pattern within the Language Server Protocol (LSP), we aim to achieve a seamless editing experience where STRling patterns are treated as first-class citizens, complete with syntax validation, highlighting, and autocompletion, even while embedded within Python f-strings or JavaScript template literals.2

### **1.2 Defining the Tooling Void**

The "Tooling Void" is not merely a lack of features; it is a fundamental disconnection between the compiler's capabilities and the editor's view of the code. In modern software engineering, the expectations for tooling have shifted dramatically. Developers expect immediate feedback loops—red squiggles on syntax errors as they type, not after execution.

Currently, a Python file containing STRling code looks like this to the VS Code Pylance server:

Python

\# To Pylance, this is just a string.  
\# It has no internal structure, no semantics, and no validation.  
pattern \= s.match(f"digits: {d.min(3)}")

The host server sees a StringLiteral token. It validates that the string is closed and that the interpolation syntax {...} is valid Python. It does _not_, however, know that digits: is a literal within the STRling DSL, or that d.min(3) should compile to a quantifier. If the user makes a typo in the DSL syntax—for example, writing a malformed group (?\<name—the host server remains silent because the string content itself is valid text.4

This silence is the void we must fill. The objective is to project the internal semantic logic of the STRling compiler _into_ the editor interface. This requires an architecture that can identify these "Islands" of STRling code within the "Water" of the host language, extract them, process them, and map the results back to the user's cursor position with pixel-perfect accuracy.

### **1.3 The "Island Grammar" Theoretical Framework**

The concept of "Island Grammars," originating in parser theory and computational linguistics, provides the theoretical scaffolding for this undertaking. An Island Grammar parser does not attempt to parse the entire source file (the "Water") with the same level of granularity. Instead, it scans the water for specific markers that indicate the presence of an "Island"—a region of interest governed by a different grammar.6

For STRling, the "Water" is the host language (Python, JavaScript, etc.). The "Islands" are the specific string literals that contain STRling patterns. These islands are delimited by function calls (e.g., s.match(...)) or specific variable assignments. The challenge is that these islands are not static landmasses; they are dynamic, often containing holes (interpolations) where the water flows back in.

Implementing Island Grammars in an LSP context requires a departure from monolithic parsing. We cannot simply extend the Python parser to understand STRling, as that would require forking and maintaining complex host language tools.8 Instead, we must adopt a **federated parsing strategy**. The STRling tooling must act as a parasite (in the biological, symbiotic sense), attaching itself to the host language's document structure, extracting the nutrients (strings) it needs, and returning value (diagnostics) to the host organism.

This specification details the **Request Forwarding** architecture as the mechanism to implement this federation. It prioritizes **Decoupling**, ensuring that the STRling Language Server remains a pure, target-agnostic compiler artifact, while a lightweight "Middleware" layer handles the messy reality of host language integration.3 This aligns with our Guiding Principle of **Principled Engineering**: separating concerns to maximize scalability and maintainability.1

## ---

**2\. Architectural Analysis: The Request Forwarding Pattern**

### **2.1 Pattern Selection: Middleware vs. Direct Embedding**

Two primary patterns exist for implementing embedded language support within the VS Code ecosystem: **Language Services (Direct Embedding)** and **Request Forwarding**. A rigorous analysis favors Request Forwarding for the STRling use case.

#### **2.1.1 The Language Services Pattern**

In the Language Services pattern, the host language extension (e.g., the Python extension itself) imports the embedded language's logic as a library. When the host parser encounters an embedded region, it calls the library function directly.3

-   **Advantages:** Zero latency (in-process calls), shared memory state.
-   **Disadvantages:** High coupling. It effectively requires the Python extension maintainers to bundle STRling code. Given that STRling is an independent DSL, we cannot impose this requirement on the broader ecosystem. Furthermore, if STRling's logic is written in a language different from the host extension (e.g., Python vs. TypeScript), direct embedding becomes technically infeasible without complex bindings.

#### **2.1.2 The Request Forwarding Pattern (Virtual Documents)**

The Request Forwarding pattern creates a virtual abstraction layer. The STRling VS Code extension acts as a "Middleware." It intercepts LSP requests (like "Give me completions at line 10"), determines if the cursor is inside a STRling string, and if so, forwards the request to a separate, dedicated STRling Language Server. This forwarding is done by creating a **Virtual Document**—a temporary, in-memory file that contains only the relevant STRling code.3

-   **Mechanism:**
    1. User types inside a Python string.
    2. Middleware detects the context.
    3. Middleware extracts the string content.
    4. Middleware "projects" this content into a new URI: strling://python/file.py.strl.
    5. Middleware asks the STRling Server to validate this virtual file.
    6. The server responds with diagnostics.
    7. Middleware maps the diagnostics back to the original Python file's coordinates.
-   **Strategic Alignment:** This pattern aligns perfectly with STRling's architecture. The STRling Server can run the exact same Python-based compiler logic used in the CLI.1 It doesn't need to know it's running inside VS Code or dealing with a Python host file. It simply receives a .strl document and compiles it. The complexity of "being embedded" is entirely contained within the Client Middleware.

### **2.2 The Iron Law of Emitters Applied to Tooling**

Our documentation defines the "Iron Law of Emitters": _Every emitter must implement a predictable, testable interface with no side effects_.1 In this architecture, we extend this law to the tooling layer. The **Projection Phase**—converting a host string into a virtual document—is essentially a form of emission.

The Middleware "emits" a Virtual Document. This emission process must be:

1. **Deterministic:** The same host string state must always produce the exact same virtual document content.
2. **Lossless (Syntactically):** It must preserve the exact character offsets of the embedded code to ensure that error messages point to the correct column.
3. **Testable:** We must be able to unit-test the projection logic without spinning up a full VS Code instance, feeding it raw strings and asserting the output virtual content and source maps.1

### **2.3 The "Three-Test Standard" for Tooling**

Applying STRling's "3-Test Standard" 1 to this architecture dictates our implementation roadmap:

1. **Unit Tests:** Test the LanguageScanner and SourceMapper classes in isolation. Feed them a Python string with interpolations, assert the correct virtual content and offset mappings.
2. **End-to-End (E2E) Tests:** Run a headless VS Code instance. Open a real Python file. Simulate a keystroke inside an f-string. Assert that a completion item appears.
3. **Conformance Tests:** Ensure that the masking logic (converting interpolations to whitespace) behaves consistently across different host languages (Python vs. JS) and doesn't trigger false positives in the STRling parser.

## ---

**3\. The Virtual Document Lifecycle**

The Virtual Document is the linchpin of this architecture. It is an ephemeral artifact, existing primarily in the editor's memory, that serves as the "clean" representation of the dirty, embedded code. Understanding its lifecycle is crucial for managing performance and state consistency.

### **3.1 The Projection Lifecycle**

The lifecycle of a virtual document is tied to the user's interaction with the host document.

1. **Creation (On Demand):** Virtual documents are not created proactively for every string in the workspace (which would be a performance disaster). They are created **lazily**. When the user opens a file, or when a specific LSP request (like semantic tokens or diagnostics) is triggered, the middleware scans the active viewport or file.
2. **Addressing (The URI Scheme):** We must define a robust URI scheme that uniquely identifies a specific string literal within a specific version of a host file.
    - **Proposed Scheme:** strling-embedded://\<host-lang\>/\<host-file-path\>@\<region-id\>.strl
    - Example: strling-embedded://python/c:/users/dev/app.py@42.strl indicates the 42nd string literal in app.py.
    - This strict addressing ensures that the LSP Server treats each string as a distinct file, maintaining separate compilation contexts/caches if necessary.3
3. **Synchronization (The Update Loop):**
    - User types in app.py.
    - VS Code sends textDocument/didChange for app.py to the Middleware.
    - Middleware calculates the delta. If the change occurred within a known STRling island, the Middleware updates the content of the corresponding virtual document.
    - Middleware sends textDocument/didChange for the _virtual URI_ to the STRling Server.
    - STRling Server recompiles and pushes diagnostics.

### **3.2 State Management and Garbage Collection**

A critical challenge in Virtual Document architectures is memory leaks. If a user opens 100 files and closes them, the associated virtual documents must be disposed of. The Middleware must listen to textDocument/didClose events on the host side and send corresponding close notifications for all associated virtual URIs to the STRling Server, allowing it to free resources.3

### **3.3 The Content Provider Interface**

In VS Code, the TextDocumentContentProvider is the API that serves the content of these custom URIs.

TypeScript

// Conceptual Interface  
class EmbeddedContentProvider implements vscode.TextDocumentContentProvider {  
 provideTextDocumentContent(uri: vscode.Uri): string {  
 // 1\. Decode the host URI from the virtual URI  
 // 2\. Find the host document in the workspace  
 // 3\. Extract the string literal at the specified region ID  
 // 4\. Perform Interpolation Masking (replace {var} with spaces)  
 // 5\. Return the clean.strl content  
 }  
}

This provider allows VS Code to "see" the virtual document. This is critical for debugging—a developer can actually run the command "Open Virtual Document" and see exactly what the STRling Server sees, verifying that masking and extraction are working correctly.9

## ---

**4\. Deep Dive: Projection and Masking Strategies**

The process of converting a host string literal into a valid STRling source file involves two distinct operations: **Extraction** (identifying the boundaries) and **Masking** (neutralizing host-specific syntax).

### **4.1 The Python Challenge: F-Strings**

Python's f-strings (Formatted String Literals) introduced in PEP 498 4 present a complex parsing challenge. They allow embedding arbitrary Python expressions inside curly braces {}.

#### **4.1.1 Syntax Analysis**

An f-string looks like f"text {expression} text".

-   **The Problem:** The {expression} part is valid Python code but invalid STRling code. If we send the raw string text {expression} text to the STRling parser, it will likely choke on the braces or interpret them as a quantifier range {min,max}.1
-   **The Conflict:** STRling uses { for quantifiers ({3,5}). Python uses { for interpolation.
-   **Resolution:** The Middleware _must_ hide the Python interpolation from the STRling parser while preserving the _spatial_ integrity of the string.

#### **4.1.2 The Whitespace Masking Strategy**

To preserve source coordinates (so that column 10 in the virtual doc maps to column 10 in the host string), we must replace the interpolation with a placeholder of exactly the same length.

-   **Strategy:** Replace every character of the interpolation (including the braces) with a space character.
-   **Example:**
    -   **Host:** f"Start {variable \+ 1} End"
    -   **Length:** {variable \+ 1} is 14 characters.
    -   **Virtual:** "Start End" (14 spaces).
-   **Why Spaces?** STRling supports a free-spacing mode (%flags x) where whitespace is ignored.1 By treating the virtual document as implicitly having the x flag (or ensuring the parser tolerates spaces in these contexts), we render the interpolation invisible to the parser logic while keeping the End token at the exact same character offset.
-   **Constraint:** This requires the STRling parser to be robust against unexpected whitespace if the user hasn't explicitly enabled free-spacing mode. Alternatively, we can replace interpolations with a specific "Ignored Token" if we modify the grammar, but whitespace is the standard approach in the LSP ecosystem (e.g., how the HTML server handles PHP tags).3

#### **4.1.3 Handling Escape Sequences in Python**

Python strings interpret backslashes. \\n is a single character (newline, byte 10). However, the LSP operates on the _source text_ view of the document.

-   **Scenario:** User types s.match("\\d+").
-   **File Content:** \\ followed by d.
-   **Python Memory:** Depending on whether it's a raw string r"", Python might see this differently.
-   **Virtual Document Requirement:** The STRling parser expects to see the literal source characters \\ and d. It does _not_ want the evaluated byte for escape sequences.
-   **Solution:** The extraction logic must pull the _raw text_ of the source code, not the evaluated string value from the Python runtime. We access the text buffer of the editor, which gives us the raw source. This simplifies mapping significantly: one character in the editor buffer equals one character in the virtual buffer.11

### **4.2 The JavaScript Challenge: Template Literals**

JavaScript uses template literals delimited by backticks \` which support interpolation via ${...}.13

#### **4.2.1 Tagged Templates**

STRling in JS will likely be used via tagged templates:

JavaScript

const pattern \= s\`match this ${variable}\`;

or via function calls:

JavaScript

const pattern \= s.match(\`match this ${variable}\`);

The scanner must identify both forms.

#### **4.2.2 Masking in JS**

The strategy is identical to Python. We locate the ${...} sequence and replace it with spaces.

-   **Host:** \`Val: ${x}\`
-   **Masked:** \`Val: \`
-   **Offset Integrity:** Preserved.

### **4.3 Scanner Implementation**

To implement the **Extraction** phase, we need a robust scanner. We cannot rely on simple Regex because of nested braces (e.g., f"{ {x:1} }").

-   **Recommendation:** Use **TextMate Grammars** or **Tree-sitter**.
-   **Tree-sitter:** VS Code is moving towards Tree-sitter (via the vscode-anycode or similar initiatives). A WASM-compiled Tree-sitter parser for Python and JS running in the extension host is the most robust way to identify string boundaries and interpolation ranges accurately, handling edge cases like nested strings and comments correctly.8
-   **Fallback:** For the MVP (Minimum Viable Product), a carefully crafted stack-based Lexer (or a recursive regex where supported) can suffice, but Tree-sitter is the "Principled Engineering" choice for long-term scalability.

## ---

**5\. Source Mapping: The Coordinate Transformation Engine**

The **Source Map** is the mathematical bridge between the two documents. It translates every diagnostic, completion item, and hover position.

### **5.1 The Coordinate System**

LSP positions are Line:Character pairs.

-   **Host Position:** Absolute position in app.py.
-   **Virtual Position:** Relative position in the projected .strl file.

### **5.2 The Mapping Algorithm**

We define a SourceMap class that is generated during the Projection phase.

TypeScript

class SourceMap {  
 // List of segments: \[VirtualOffset, HostOffset, Length\]  
 private mappings: \[number, number, number\] \=;

    constructor(hostText: string, virtualText: string) {
        //... build mappings...
    }

    public toHost(virtualPos: Position): Position {... }
    public toVirtual(hostPos: Position): Position {... }

}

#### **5.2.1 Linear Offsets vs. 2D Positions**

It is computationally more efficient to map **Linear Offsets** (character index from start of file) and convert to/from 2D Positions (Line:Char) only at the boundaries of the API.

1. **Input:** Virtual Position (0, 5).
2. **Step 1:** Convert to Virtual Offset 5\.
3. **Step 2:** Look up Offset 5 in the Mapping Table.
    - Since we use **Whitespace Masking** (replacing interpolation with spaces of equal length), the mapping is often a simple linear shift: HostOffset \= VirtualOffset \+ StartIndexOfString.
    - _Correction:_ This assumes the virtual document starts at the beginning of the string content.
    - If the virtual document contains the _entire_ host file content with non-STRling parts masked out (another valid strategy), the offset delta is zero. However, this is inefficient for the STRling parser.
    - **Decision:** The Virtual Document contains _only_ the string content.
    - **Formula:** HostOffset \= VirtualOffset \+ IslandStartOffset.

#### **5.2.2 Handling Multiline Strings**

Python and JS both support multiline strings.

Python

s.match("""  
 Start  
 Middle  
 End  
""")

-   **Virtual Doc:** Must preserve the newlines. The content should be extracted exactly as is.
-   **Indentation:** Often, multiline strings are indented.  
    Python  
    def func():  
     s.match("""  
     pattern  
     """)

    The whitespace before pattern is part of the string content in Python (unless textwrap.dedent is used). The STRling parser handles whitespace (especially in %flags x). Therefore, we should extract the indentation _as is_ into the virtual document. This preserves the column numbers exactly. If the user creates an invalid pattern because of indentation, the error should be shown at that indentation level.

### **5.3 Diagnostic Re-Mapping**

When the STRling Server returns a diagnostic:

-   **Diagnostic:** Error: Invalid range at 0:5 \- 0:10.
-   **Middleware Action:**
    1. Convert 0:5 to Host Position (e.g., 105:12).
    2. Convert 0:10 to Host Position (e.g., 105:17).
    3. Create a VS Code Diagnostic object with the mapped range.
    4. Push to the DiagnosticCollection for app.py.

## ---

**6\. Implementation Strategy: Python F-Strings**

### **6.1 Syntax Specifics & Edge Cases**

Python f-strings are notoriously complex due to nesting and format specifiers.

-   **Nesting:** f"result: {f'nested {x}'}".
-   **Format Specifiers:** f"value: {x:.2f}".
-   **Backslashes:** Prior to Python 3.12, backslashes were not allowed in f-string expressions. In 3.12, they are.4

### **6.2 The Tokenization Requirement**

To correctly mask {expr}, the scanner must understand Python tokenization. It must track opening and closing braces, ignoring braces inside strings or comments within the expression.

-   **Example:** f"pat { {'a':1} } tern". The scanner must identify { {'a':1} } as the interpolation block.
-   **Failure Mode:** A naive regex \\{.\*?\\} will fail on nested braces.
-   **Validation:** The Middleware must implement a bracket-counting scanner or use a parser combinator library to identify the exact span of the interpolation.

### **6.3 Raw String Interaction**

In rf"pattern", the r prefix disables escape processing for the string literal, but _not_ for the interpolation parts.15

-   **Impact:** The virtual document extraction is straightforward—we take the raw source characters. The STRling parser handles the \\ characters.
-   **Note:** If the user does _not_ use r (e.g., f"\\d"), Python treats \\d as a valid escape (or invalid escape warning, depending on version). But importantly, \\d usually remains \\d in the string unless it's a known escape like \\n.
-   **Safety:** We should always project the _source code text_. If the source has \\\\, the virtual doc has \\\\. This maps 1:1 to what the user sees.

## ---

**7\. Implementation Strategy: JavaScript Template Literals**

### **7.1 Template Literal Specifics**

JS template literals support nesting ${ ${ } }.

-   **Scanner:** Needs to handle nested braces, similar to Python.
-   **Tagged Templates:** The s tag (e.g., s...\`\`) is a function call. The browser/node receives an array of strings and an array of values.
-   **Raw Property:** Tagged templates receive a raw property (e.g., strings.raw). This gives the exact source text, including backslashes. This confirms that accessing the raw source is the correct model for the runtime as well.

### **7.2 Semantic Highlighting**

In addition to validation, we can provide semantic highlighting. The STRling Server can return SemanticTokens.

-   **Workflow:**
    1. VS Code requests semantic tokens for app.js.
    2. Middleware calculates the range of the template literal.
    3. Middleware requests tokens from STRling Server for the virtual doc.
    4. Middleware shifts the returned tokens by the start offset of the literal.
    5. Middleware merges these tokens with the tokens provided by the JS language server (if any).

## ---

**8\. Middleware Specification & Logic Flow**

This section provides the pseudo-code logic for the critical middleware components.

### **8.1 The Middleware Class**

The Middleware class intercepts the LSP traffic.

TypeScript

class STRlingMiddleware {  
 async provideCompletionItem(document, position, context, token, next) {  
 // 1\. Check if we are inside an Island  
 const region \= this.scanner.scan(document).findRegionAt(position);

        if (\!region) {
            // Not our business, let the host server handle it
            return next(document, position, context, token);
        }

        // 2\. We are in an Island. Create/Get Virtual Document.
        const virtualUri \= this.virtualDocManager.getUri(document, region);
        await this.virtualDocManager.update(virtualUri, region.content);

        // 3\. Map Position to Virtual Coordinates
        const virtualPos \= region.toVirtual(position);

        // 4\. Forward Request to STRling Server
        const result \= await commands.executeCommand(
            'vscode.executeCompletionItemProvider',
            virtualUri,
            virtualPos,
            context.triggerCharacter
        );

        // 5\. Map Results back to Host Coordinates
        return this.mapper.mapCompletions(result, region);
    }

}

### **8.2 The Scanner Strategy**

To ensure performance, scanning should be incremental or scoped. However, for reliability, scanning the whole file text (which is available in memory) using a fast WASM parser (Tree-sitter) is the most robust solution.

**Table 1: Scanner Capabilities Matrix**

| Host Language  | Scanner Tech           | Complexity | Accuracy               | Performance |
| :------------- | :--------------------- | :--------- | :--------------------- | :---------- |
| **Python**     | Regex (Naive)          | Low        | Low (fails on nesting) | High        |
| **Python**     | **Tree-sitter (WASM)** | **High**   | **High**               | **High**    |
| **JavaScript** | Regex                  | Low        | Medium                 | High        |
| **JavaScript** | **Tree-sitter (WASM)** | **High**   | **High**               | **High**    |

-   **Decision:** The "Principled Engineering" choice is to invest in **Tree-sitter WASM** integration for the middleware. This ensures we correctly handle edge cases like comments inside interpolations or nested strings that would break regex approaches.14

## ---

**9\. Failure Modes and Safety**

### **9.1 Malformed Host Syntax**

If the user types an unclosed string s.match("..., the host syntax tree is broken.

-   **Behavior:** The Tree-sitter parser is error-tolerant. It will likely produce an "ERROR" node but may still identify the string start.
-   **Strategy:** If the scanner cannot definitively find the end of the string, it should **abort** processing for that specific island. Do not attempt to validate incomplete strings, as it leads to noisy, incorrect diagnostics. Wait for the user to close the quote.

### **9.2 Desynchronization**

LSP is asynchronous. The user types a, the document updates, the middleware scans, the virtual doc updates, the server computes.

-   **Risk:** The user types b before the result for a returns.
-   **Mitigation:** VS Code handles cancellation tokens. The middleware must pass the cancellation token to the forwarded request. If the host cancels, the virtual request cancels. Furthermore, we must ensure we rely on document versions. Only update diagnostics if the document version matches the request version.

### **9.3 Performance Overheads**

Creating a virtual document for every keystroke adds overhead.

-   **Optimization:** **Debounce** the onDidChangeTextDocument listener for the Virtual Document update logic. Wait 20-50ms after typing stops before pushing the update to the STRling Server. This prevents thrashing the parser during rapid typing.16

## ---

**10\. Conclusion and Roadmap**

This architecture specification provides a complete blueprint for solving the "Island Grammar" problem for STRling. By implementing the **Request Forwarding** pattern via **Virtual Documents** and **Middleware**, we can fill the Tooling Void without compromising the architectural purity of the core compiler.

### **10.1 Key Deliverables**

1. **STRling Client (VS Code Extension):** A TypeScript extension implementing the Middleware, Scanner (Tree-sitter), and Source Mapper.
2. **STRling Language Server:** A standard LSP server wrapping the existing Python-based parser (already available via parse_strl.py but needs an LSP wrapper like pygls or a Node.js wrapper).17
3. **Test Suite:** Extended E2E tests validating the mapping logic.

### **10.2 Strategic Impact**

Implementing this architecture elevates STRling from a "library" to a "language." It grants developers the confidence of static typing and validation within the dynamic world of regex generation. It embodies "Pragmatic Empathy" by meeting developers where they live—in their editor, assisting every keystroke.

**Action Item:** Begin prototyping the TextDocumentContentProvider for the strling-embedded scheme immediately. This is the foundation upon which the rest of the architecture rests.

**Source Citations:**

-   2 \- VS Code Embedded Languages & Virtual Documents
-   4 \- Python F-strings & Syntax Analysis
-   13 \- JS Template Literals
-   1 \- STRling Codebase & Specs
-   6 \- Island Grammar Theory
-   20 \- LSP Specifications
-   3 \- VS Code Middleware & APIs
-   17 \- pygls & LSP Implementation
-   14 \- Tree-sitter usage

#### **Works cited**

1. strling-lang/strling
2. VS Code API | Visual Studio Code Extension API, accessed December 28, 2025, [https://code.visualstudio.com/api/references/vscode-api](https://code.visualstudio.com/api/references/vscode-api)
3. Embedded Programming Languages | Visual Studio Code Extension API, accessed December 28, 2025, [https://code.visualstudio.com/api/language-extensions/embedded-languages](https://code.visualstudio.com/api/language-extensions/embedded-languages)
4. Python's F-String for String Interpolation and Formatting, accessed December 28, 2025, [https://realpython.com/python-f-strings/](https://realpython.com/python-f-strings/)
5. PEP 701 – Syntactic formalization of f-strings \- Python Enhancement Proposals, accessed December 28, 2025, [https://peps.python.org/pep-0701/](https://peps.python.org/pep-0701/)
6. Island Grammars in ASF+SDF \- CWI, accessed December 28, 2025, [https://homepages.cwi.nl/\~paulk/theses/ErikPost.pdf](https://homepages.cwi.nl/~paulk/theses/ErikPost.pdf)
7. Well-typed Islands Parse Faster \- Khoury College of Computer Sciences, accessed December 28, 2025, [https://www.khoury.northeastern.edu/home/ejs/papers/tfp12-island.pdf](https://www.khoury.northeastern.edu/home/ejs/papers/tfp12-island.pdf)
8. Implementing the LSP server in the good way : r/Compilers \- Reddit, accessed December 28, 2025, [https://www.reddit.com/r/Compilers/comments/1hs6rii/implementing_the_lsp_server_in_the_good_way/](https://www.reddit.com/r/Compilers/comments/1hs6rii/implementing_the_lsp_server_in_the_good_way/)
9. File System API | Visual Studio Code Extension API, accessed December 28, 2025, [https://code.visualstudio.com/api/extension-guides/virtual-documents](https://code.visualstudio.com/api/extension-guides/virtual-documents)
10. PEP 498 – Literal String Interpolation \- Python Enhancement Proposals, accessed December 28, 2025, [https://peps.python.org/pep-0498/](https://peps.python.org/pep-0498/)
11. What Are Python Raw Strings?, accessed December 28, 2025, [https://realpython.com/python-raw-strings/](https://realpython.com/python-raw-strings/)
12. 2\. Lexical analysis — Python 3.14.2 documentation, accessed December 28, 2025, [https://docs.python.org/3/reference/lexical_analysis.html](https://docs.python.org/3/reference/lexical_analysis.html)
13. Template literals (Template strings) \- JavaScript \- MDN Web Docs \- Mozilla, accessed December 28, 2025, [https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Template_literals](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Template_literals)
14. Newest 'treesitter' Questions \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/tagged/treesitter?tab=Newest](https://stackoverflow.com/questions/tagged/treesitter?tab=Newest)
15. Combine f-string and raw string literal \- python \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/58302531/combine-f-string-and-raw-string-literal](https://stackoverflow.com/questions/58302531/combine-f-string-and-raw-string-literal)
16. How does a server-side command in vscode-languageserver-node know which is the current document? \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/43916684/how-does-a-server-side-command-in-vscode-languageserver-node-know-which-is-the-c](https://stackoverflow.com/questions/43916684/how-does-a-server-side-command-in-vscode-languageserver-node-know-which-is-the-c)
17. Advanced Usage — pygls documentation \- Read the Docs, accessed December 28, 2025, [https://pygls.readthedocs.io/en/v0.11.0/pages/advanced_usage.html](https://pygls.readthedocs.io/en/v0.11.0/pages/advanced_usage.html)
18. How to use f-strings to embed expressions in Python strings | LabEx, accessed December 28, 2025, [https://labex.io/tutorials/python-how-to-use-f-strings-to-embed-expressions-in-python-strings-397697](https://labex.io/tutorials/python-how-to-use-f-strings-to-embed-expressions-in-python-strings-397697)
19. ES2015 Template Literals \- Medium, accessed December 28, 2025, [https://medium.com/@photokandy/es2015-template-literals-eddf051ed8ee](https://medium.com/@photokandy/es2015-template-literals-eddf051ed8ee)
20. Official page for Language Server Protocol \- Microsoft Open Source, accessed December 28, 2025, [https://microsoft.github.io/language-server-protocol/](https://microsoft.github.io/language-server-protocol/)
21. Language Server Protocol Specification \- 3.17 \- Microsoft Open Source, accessed December 28, 2025, [https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
22. Syntax Highlight Guide | Visual Studio Code Extension API, accessed December 28, 2025, [https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide)
23. openlawlibrary/pygls: A pythonic generic language server \- GitHub, accessed December 28, 2025, [https://github.com/openlawlibrary/pygls](https://github.com/openlawlibrary/pygls)
24. pygls v2.0.0, accessed December 28, 2025, [https://pygls.readthedocs.io/](https://pygls.readthedocs.io/)
