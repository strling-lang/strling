# **STRling Evolution: First-Class Grammar Architecture**

## **1\. Executive Vision: The Paradigm Shift to Grammar Construction**

The STRling project currently stands at a definitive crossroads in its architectural lifecycle. To date, STRling has functioned primarily as a high-level wrapper—a syntactic sugar layer that makes the existing, underlying regular expression engines of Python (re) and JavaScript (RegExp) more palatable to the developer. While this approach has yielded significant gains in readability and developer ergonomics, it inherently binds the project to the limitations of those underlying engines. We inherit their lack of composability, their inability to natively handle recursive structures, and, most critically, their susceptibility to catastrophic backtracking, commonly known as Regular Expression Denial of Service (ReDoS).

To transcend these limitations and achieve the project’s Prime Directive of becoming a universally accessible pattern-matching framework, STRling must evolve from a wrapper into a **First-Class Grammar Construction Kit**. This is not merely a feature addition; it is a fundamental re-engineering of the project's core identity. We are moving from generating strings for an NFA (Non-Deterministic Finite Automaton) to emitting bytecode for a custom, deterministic Virtual Machine.

This dossier serves as the comprehensive architectural blueprint for this evolution. It is informed by a deep-dive analysis of two "North Star" technologies that define the state-of-the-art in parsing theory: **Raku** (formerly Perl 6), which offers the gold standard for grammar composition and "braiding," and **LPeg** (Lua Parsing Expression Grammars), which provides the execution model for a high-performance, stack-based Parsing Expression Grammar (PEG) Virtual Machine.

By synthesizing the structural elegance of Raku with the execution safety of LPeg, STRling will offer what no standard regex engine can: the ability to define **Island Grammars** (nested languages like SQL within Python strings), the ability to perform **Algebraic Pattern Composition** via operator overloading, and the guarantee of linear-time execution performance regardless of input complexity.

## ---

**2\. The Architectural Pillar of Structure: Raku and the "Braided" Grammar**

The first major deficiency in standard regex engines is their isolation. A regex is typically a standalone string that runs against a target text, returns a result, and exits. It has no memory of previous matches, no awareness of a broader parsing context, and no native ability to hand off control to a sub-parser. Raku addresses this through a revolutionary architecture known as "Grammar Braiding," where a language is defined not as a monolith, but as a woven interaction of multiple distinct sub-languages (slangs).1

### **2.1 The Philosophy of the Cursor**

In the current STRling implementation—and indeed in Python's re module—the concept of "position" is reduced to a simple integer index. This is insufficient for complex grammar construction. Raku redefines the parsing position as a **Cursor**, a rich object that encapsulates the entire state of the parser at a specific moment in time.3

#### **2.1.1 The Immutable State Machine**

The Raku Cursor is not merely a pointer. It is an immutable snapshot of the parsing engine. When a pattern matches, it does not mutate the existing cursor; rather, it returns a _new_ cursor object representing the state after the match. This distinction is critical for implementing backtracking and parallel parsing capabilities.3

The internal anatomy of a Cursor, as implemented in Raku's NQP (Not Quite Perl) layer, includes several vital components that STRling must emulate to support advanced features:

-   **pos (Position):** The current integer offset in the target string. This is the most basic primitive, but in a Grammar engine, it serves as the anchor for all subsequent matching attempts.3
-   **orig (Original String):** A reference to the immutable source string being parsed. By carrying this reference within the cursor, Raku avoids the expensive operation of substring copying. When a sub-rule needs to match against the text, it does not receive a sliced string; it receives a view of the original string bounded by the cursor's coordinates.4
-   **$\!match (The Match State):** Perhaps the most profound divergence from traditional regex is that the Cursor holds the potential result of the match in progress. In Raku, the Match object is actually a subclass of Cursor. This implies that a "result" is simply a specialized state of the parser that has been marked as successful.3

#### **2.1.2 The Shadow Cursor Implementation Strategy**

Current regex engines used by STRling (Python re, JS RegExp) do not expose this rich cursor object. They are "black boxes" that consume a string and spit out a match object or null. To achieve Raku-like capabilities, STRling cannot rely on the host language's tracking.

We must implement a **Shadow Cursor**. This architectural component will sit between the host language's regex engine and the STRling API.

**Specification for the STRling Cursor:**

1. **State Encapsulation:** The Shadow Cursor must track line numbers and column numbers, not just character offsets. This allows for human-readable error reporting ("Syntax Error at Line 14, Col 5"), a requirement for any grammar parsing tool.5
2. **Context Awareness:** The cursor must maintain a reference to the GrammarStack. As we enter nested structures (e.g., parsing a JSON object), the cursor pushes the current grammar context onto a stack. When the structure closes, the stack is popped. This is the mechanism that allows for recursive parsing, which is impossible in standard regex.5
3. **Lazy Evaluation:** Following Raku's design, the creation of these cursor objects should be lazy where possible. We generate the full state object only when a complex match (like a grammar switch) is requested, otherwise using lightweight integer tracking for simple token matching.6

### **2.2 Grammar Braiding and Island Resolution**

The most ambitious goal of STRling's evolution is to support **Island Grammars**. An Island Grammar occurs when one language is embedded inside another. A classic example is an f-string in Python that contains a SQL query. To parse this correctly, one cannot simply use a "Python" parser or a "SQL" parser. One needs a parser that starts in Python mode, detects the SQL string literal, switches context to a SQL grammar, and then switches back upon hitting the closing quote.

Raku handles this via **Braiding**, using the subparse method to handle the coordinate handover.2

#### **2.2.1 The subparse Coordinate System**

Raku's subparse method allows a grammar to be invoked on a string starting at an arbitrary position, without requiring the match to consume the entire remainder of the string.8

**Mechanism of Action:**

1. **Trigger Detection:** The parent grammar (e.g., Main) identifies a token that signals a language shift. For example, sql".
2. **State Handover:** The parent grammar captures the current cursor position pos.
3. **Sub-Grammar Invocation:** The parent calls SQLGrammar.subparse(target, :pos(pos)). Crucially, it passes the _original_ string and the _offset_, not a substring.8
4. **Island Parsing:** The SQLGrammar parses as much as it can. It does not need to know it is inside a larger file; it simply consumes tokens starting at pos.9
5. **Termination and Return:** When the SQL grammar hits a token it cannot parse (like the closing quote "), it succeeds and returns a Match object.
6. **Resumption:** The parent grammar receives the Match object, inspects its .to (end position), and updates its own cursor to resume parsing from that exact point.2

Implications for STRling:  
To support this, STRling must introduce a Delegate pattern. We cannot implement this using a single regex string, because regex engines are monolithic. We must break the pattern into "chunks" separated by delegation points.

-   **Proposed API:**  
    Python  
    \# Conceptual Python API for Grammar Braiding  
    python_grammar \= s.Grammar("Python")  
    sql_grammar \= s.Grammar("SQL")

    \# Define the "Island"  
    python_grammar.rule("sql_query",  
     s.literal('sql"') \+  
     s.delegate(target=sql_grammar, terminator=s.literal('"'))  
    )

In this architecture, STRling compiles the "Python" grammar up to the sql" literal. It then emits a specialized instruction (discussed in Section 3\) to pause the VM, invoke the sql_grammar, and wait for the return signal. This effectively "braids" the execution of two distinct state machines.

### **2.3 The Fractal Nature of the Match Object**

In Raku, the result of a parse is not a flat list of captured groups, but a hierarchical tree. This is the **Concrete Syntax Tree (CST)**. Raku's variable $/ represents the current match object, which can be indexed like a hash or an array to retrieve sub-matches.4

#### **2.3.1 From Groups to Trees**

Standard regex engines return "groups" (Group 1, Group 2). This is fragile; if a developer adds a new capturing group early in the pattern, all subsequent indices shift, breaking downstream code. Raku solves this by treating named captures as hash keys in the Match object.10

The STRling MatchTree:  
We must move away from re.MatchObject. STRling should return a custom MatchTree object.

-   **Named Access:** match\['uuid'\] should return the specific sub-match for the UUID rule, regardless of where it appeared in the sequence.
-   **Hierarchical Navigation:** If a pattern defines a Person containing an Address containing a ZipCode, the result object should allow traversal: match\['Person'\]\['Address'\]\['ZipCode'\].
-   **Self-Describing:** The MatchTree should carry metadata about which rule generated it, allowing for introspection and debugging.3

This hierarchy is constructed automatically during the parsing phase. In the Raku model, every time a sub-rule (like token word) succeeds, its resulting Match object is attached to the parent's Match object.10 STRling's new VM must replicate this "attach-on-success" behavior to build the CST dynamically.

### **2.4 Dynamic Dispatch and Proto-Regexes**

A powerful feature in Raku is the proto regex, which allows for dynamic dispatch of pattern matching—essentially polymorphism for grammars. A proto defines a category of tokens (e.g., "operators"), and individual implementations (multi token) handle the specifics.4

#### **2.4.1 Longest Token Matching (LTM)**

When multiple rules could apply (e.g., matching \+ vs \+=), standard regex engines are order-dependent (the first one defined wins). Raku employs **Longest Token Matching (LTM)**, constructing a graph of all possible alternatives and selecting the one that consumes the most characters.12

Strategic Decision for STRling:  
While LTM is theoretically superior for extensibility, it adds significant complexity to the compiler (requiring NFA-to-DFA conversion). Given our pragmatic constraints, we will initially adopt Ordered Choice (PEG style) rather than LTM. However, we can simulate LTM by strictly enforcing that "longer" patterns are registered before "shorter" ones in the STRling registry.  
The proto concept, however, is valuable. STRling should support a **Pattern Registry** that acts as a dispatch table.

-   **Registry:** A central store where users can register patterns like s.register("ipv4",...) and s.register("ipv6",...).
-   **Polymorphic Reference:** A user can then write s.ref("ip_address"), and STRling can resolve this to an ordered choice of all registered IP patterns. This decouples the definition of the grammar from its usage, allowing for plugin-based extensions.

## ---

**3\. The Execution Pillar: LPeg and the Virtual Machine**

While Raku provides the structural inspiration for _how_ to organize our grammars, **LPeg** (Lua Parsing Expression Grammars) provides the blueprint for _how_ to execute them safely and efficiently. The shift from NFA (Regex) to PEG (Parsing Expression Grammar) is the key to solving the ReDoS vulnerability that plagues modern web applications.

### **3.1 The ReDoS Cure: Ordered Choice**

The fundamental flaw in standard Regular Expressions is the ambiguity of the Alternation operator (|). In a standard regex A|B, if A matches partially but then fails later in the string, the engine backtracks and tries B. When combined with nested quantifiers, this leads to exponential execution time—ReDoS.13

PEG replaces Alternation (|) with **Ordered Choice** (/).

-   **Mechanism:** In PEG, the expression A / B means "Try A. If A matches, **commit to it**. Do not ever backtrack to try B, even if the subsequent parts of the grammar fail." 13
-   **Safety Guarantee:** This "greedy" commitment behavior ensures that for any given input position, a rule either succeeds or fails in a deterministic manner. It eliminates the possibility of "catastrophic backtracking" loops.

STRling Mandate:  
The STRling "Atomic Emitter" (Task 8.2) must compile patterns into a format that enforces Ordered Choice. We are effectively building a "ReDoS-immune" engine by design.

### **3.2 The LPeg Virtual Machine Architecture**

LPeg does not interpret the grammar tree directly; it compiles it into bytecode for a specialized Virtual Machine. This VM is stack-based and optimized for character consumption.15

#### **3.2.1 The Instruction Set Architecture (ISA)**

We have analyzed the LPeg source code (lpvm.c) to identify the core instruction set required for the STRling VM. We must implement the following opcodes 17:

| Opcode            | Arguments  | Description                                                                                                                                                                                                           |
| :---------------- | :--------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Char**          | char c     | Asserts that the character at the current cursor matches c. Advances cursor on success; triggers failure handling on mismatch.                                                                                        |
| **Set**           | bitmap map | Checks if the current character exists in the provided character class bitmap. Essential for performance with ranges \[a-z\].                                                                                         |
| **Any**           | None       | Matches any single character (dot). Advances cursor. Fails only at End of String (EOS).                                                                                                                               |
| **Choice**        | label L    | Pushes a **Choice Entry** onto the stack. This entry contains the current cursor position and the address L. If the current path fails, the VM pops this entry and jumps to L.                                        |
| **Commit**        | label L    | The "Cut" operator. It discards the top Choice Entry from the stack and jumps to L. This signifies that the current alternative has succeeded and we should not backtrack to the other options.                       |
| **PartialCommit** | label L    | Used for loops (A\*). It updates the top Choice Entry with the _new_ cursor position and jumps to L (start of loop). This allows backtracking to the previous iteration state without growing the stack infinitely.19 |
| **BackCommit**    | label L    | Used for Lookahead. It pops the Choice Entry (restoring the cursor to the saved state) and jumps to L. This allows checking if a pattern matches without consuming it.16                                              |
| **Fail**          | None       | Signals a match failure. The VM enters "Recovery Mode," popping the stack until it finds a Choice Entry to resume from.                                                                                               |
| **Span**          | set s      | An optimization instruction. It consumes a sequence of characters belonging to s in a tight loop. Replaces OneOrMore(Set) constructs.16                                                                               |

#### **3.2.2 The "Head-Fail" Optimization**

One of LPeg's key performance secrets is the **Head-Fail** analysis. Before compiling a complex pattern, the engine checks if the pattern must start with a specific character.

-   **Example:** For the pattern ( "foo" / "bar" ), the engine knows it must start with f or b.
-   **Optimization:** The compiler emits a TestChar instruction _before_ the Choice. If the current character is z, it fails immediately without the overhead of pushing the Choice state onto the stack.16

**Implementation Detail:** STRling's compiler must perform a "First Set" analysis on the AST to identify these optimization opportunities. This ensures that the generated bytecode is not just safe, but performant.

### **3.3 Stack-Based Captures and the Return Stack**

Unlike Regex engines which often use a fixed number of registers for groups, the LPeg VM uses the stack to manage captures. This is what enables recursive parsing.

#### **3.3.1 The Capture Protocol**

When the VM encounters a capture definition (s.group(...)), it emits:

1. **OpenCapture**: Pushes a marker onto the stack recording the start position.
2. **\[Pattern Code\]**: Executes the pattern.
3. **CloseCapture**: Pushes a marker recording the end position.

Upon successful completion of the entire match, the VM post-processes the stack. It walks from bottom to top, pairing Open and Close markers to construct the MatchTree. Nested captures appear as nested pairs on the stack, naturally forming a hierarchy.17

The Recursion Limit:  
Because captures live on the stack, the depth of recursion is limited only by available memory (or a configured limit). This allows STRling to parse deeply nested structures like JSON or XML which break standard regex engines. To ensure robustness, STRling should expose a max_stack_depth configuration to prevent stack overflow attacks.17

### **3.4 The Emitter Specification**

Task 8.2 requires an "Emitter Specification." The STRling compilation pipeline will follow these stages:

1. **DSL Parsing:** Convert the user's Python/JS calls (s.literal('a') \+ s.digits()) into a high-level Internal Representation (IR) tree.
2. **Analysis Phase:**
    - **Nullable Check:** Verify which nodes can match the empty string (to prevent infinite loops).
    - **First-Set Calculation:** Determine starting characters for Head-Fail optimization.
3. **Emission Phase:** Traverse the IR and generate the opcode list.
    - _Sequence A \+ B:_ Emit code for A, followed immediately by code for B.
    - _Ordered Choice A | B:_ Emit Choice L1, code for A, Commit L2, label L1, code for B, label L2.
    - _Repetition A\*:_ Emit Choice L_End, label L_Start, code for A, PartialCommit L_Start, label L_End.
4. **Bytecode Serialization:** The resulting list of integers/structs is the "compiled" pattern, ready for execution by the VM.

## ---

**4\. The Ergonomic Pillar: Algebraic Pattern Composition**

The final piece of the puzzle is the developer interface. How do we expose this raw power in a way that feels elegant? We look to LPeg's use of **Operator Overloading**, treating patterns as algebraic values that can be added, multiplied, and divided.15

### **4.1 The Algebra of Patterns**

In formal language theory, concatenation is a product (Cartesian product of strings), and union is a sum. LPeg maps language operators to these concepts:

-   \* (Multiplication) $\\rightarrow$ Sequence
-   \+ (Addition) $\\rightarrow$ Ordered Choice
-   \- (Subtraction) $\\rightarrow$ Difference (Match A but not B)
-   / (Division) $\\rightarrow$ Capture Transformation (Apply function to result)

This algebraic approach allows for extremely concise grammar definitions. However, we must adapt this to the idioms of our target host languages: Python and JavaScript.

### **4.2 Python: The Ideal Host for Algebra**

Python's data model supports rich operator overloading via "magic methods" (\_\_add\_\_, \_\_mul\_\_, \_\_or\_\_, etc.). This makes it an ideal host for the STRling DSL.21

#### **4.2.1 The Operator Mapping Strategy**

While LPeg uses \+ for choice, the Python ecosystem (influenced by re and standard set theory) strongly associates the pipe | with alternation. To respect the "Principle of Least Astonishment," STRling should deviate from LPeg here.

**Recommended Python Mapping:**

| Operator | Magic Method    | Semantic Meaning                                | Example                                   |
| :------- | :-------------- | :---------------------------------------------- | :---------------------------------------- |
| **\+**   | \_\_add\_\_     | **Sequence.** Concatenation of patterns.        | s.literal("a") \+ s.digits()              |
| \*\*\`   | \`\*\*          | \_\_or\_\_                                      | **Ordered Choice.** Try Left, then Right. |
| **/**    | \_\_truediv\_\_ | **Action/Transform.** Apply function to result. | s.digits() / int                          |
| **\>\>** | \_\_rshift\_\_  | **Pipe/Braid.** Handover to sub-grammar.        | s.start \>\> sub_grammar                  |
| **&**    | \_\_and\_\_     | **Lookahead.** Ensure match without consuming.  | s.word & s.literal(";")                   |
| **\-**   | \_\_sub\_\_     | **Difference.** Match A if not B.               | s.any \- s.literal('"')                   |

#### **4.2.2 The Semantic Power of Division (/)**

The use of the division operator for semantic actions is a specific ergonomic breakthrough we must adopt. In standard parsers, attaching a transformation function often involves verbose method chaining (pattern.map(lambda x:...)).  
Using division allows for a syntax that reads like a pipeline:

Python

\# Parse a comma-separated list of integers  
integer \= s.digits() / int  
int_list \= (integer \+ (s.literal(",") \+ integer).star()) / list

This conciseness transforms the code from a "parsing script" into a declarative "grammar definition".23

### **4.3 JavaScript: The "Proxy" Challenge**

JavaScript presents a significant hurdle: it **does not support operator overloading**.24 The \+ operator, for instance, will always attempt string concatenation or numeric addition via valueOf, which is destructive to our Pattern objects.24

#### **4.3.1 The Failure of valueOf Hacks**

Research into "fake" overloading in JS using valueOf reveals it to be fragile and limited. It typically forces the object to be coerced to a primitive, losing its internal structure.25 We cannot return a new Pattern object from p1 \+ p2 in JS; the runtime forces a primitive result.

#### **4.3.2 The Proxy Solution and Fluent Interface**

While we cannot overload operators, we can use the ES6 Proxy object to improve the _creation_ API, creating a "Magic Builder".26

-   **Dynamic Properties:** s.uuid or s.ipv4 can be intercepted by a Proxy to lazily load patterns from the registry.

For composition, however, we must accept the platform constraints and offer a **Fluent Interface** (Method Chaining) that mirrors the algebraic structure semantically, if not syntactically.27

**JavaScript API Mapping:**

-   Python a \+ b $\\rightarrow$ JS a.then(b)
-   Python a | b $\\rightarrow$ JS a.or(b)
-   Python a / f $\\rightarrow$ JS a.map(f)

While less concise, the Fluent Interface preserves the _order of operations_ clarity that is often lost in nested function calls (or(then(a, b), c)). The use of Proxy can be reserved for DSL-like property accessors, e.g., s.digits.oneOrMore, to reduce parentheses noise.29

## ---

**5\. Comparative Analysis: Raku vs. LPeg for STRling**

It is crucial to explicitly articulate why we are mixing these two technologies. Why not just copy Raku entirely? Or just LPeg?

### **5.1 Raku's Strength: The "Meta" Layer**

Raku excels at the **Management** of grammars. Its class-based structure (grammar MyGrammar {... }), its inheritance model, and its ability to mix-in roles are superior for organizing large, complex parsing logic.7 STRling needs this "Grammar as Class" structure to allow developers to build reusable libraries of patterns.

### **5.2 LPeg's Strength: The "Micro" Layer**

Raku's execution model is complex, involving NFAs, DFAs, and LTM graphs. It is powerful but heavy. LPeg's PEG VM is lightweight, fast, and mathematically provable.15 For STRling, which needs to be embeddable and performant in Python and JS environments, the LPeg VM is the correct **Execution Engine**.

### **5.3 The Synthesis**

STRling v2.0 will essentially be:

-   **The Skin of Raku:** A class-based API, method interpolation, and grammar braiding for structure.
-   **The Muscle of LPeg:** A stack-based PEG VM for the actual bytecode execution.
-   **The Dress of Python:** An algebraic, operator-overloaded DSL for definition.

## ---

**6\. Implementation Roadmap and Future Outlook**

The transition to this new architecture is a significant undertaking. We advocate a phased "Strangler Fig" approach, where the new Grammar engine is introduced alongside the existing Regex wrapper.

### **6.1 Phase 1: The Atomic Core**

-   **Action:** Implement the VM class in Python and a JS equivalent.
-   **Deliverable:** A unit-tested engine capable of executing manually constructed bytecode instructions (Char, Choice, Commit).
-   **Verification:** Validate that simple patterns execute in linear time, specifically testing against known ReDoS vectors.

### **6.2 Phase 2: The Emitter and Algebra**

-   **Action:** Build the Compiler that transforms the existing STRling AST into VM bytecode.
-   **Action:** Implement the Python \_\_magic\_\_ methods to output this AST.
-   **Deliverable:** The ability to write s.literal("a") \+ s.literal("b") and have it execute on the VM.

### **6.3 Phase 3: The Shadow Cursor and Braiding**

-   **Action:** Implement the Cursor and MatchTree objects.
-   **Action:** Implement the subparse logic and the Delegate instruction in the VM.
-   **Deliverable:** A working demonstration of parsing a SQL string embedded in a Python variable using two distinct grammar definitions.

### **6.4 Phase 4: The Registry and LSP Integration**

-   **Action:** Build the PatternRegistry for proto-like dispatch.
-   **Action:** Expose the MatchTree coordinates to the Language Server Protocol (LSP).
-   **Outcome:** Because we track line/col in our Shadow Cursor, STRling can now power syntax highlighters and linters with character-perfect accuracy, opening a new market for the tool beyond simple data extraction.

### **6.5 Conclusion**

The evolution outlined in this dossier moves STRling from a utility library to a foundational infrastructure component. By adopting the **First-Class Grammar** architecture, we do not just "improve" regex; we replace it with something safer, more powerful, and significantly more maintainable.

The "Braided" nature of the architecture acknowledges the reality of modern computing: languages are rarely isolated; they are embedded, nested, and mixed. The **PEG VM** acknowledges the reality of modern security: we cannot trust backtracking engines with user input.

This is the path to excellence. This is the future of STRling.

**STRling Copilot // End Report**

#### **Works cited**

1. Is it possible to run a sub-grammar inside a grammar nqp? \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/61726883/is-it-possible-to-run-a-sub-grammar-inside-a-grammar-nqp](https://stackoverflow.com/questions/61726883/is-it-possible-to-run-a-sub-grammar-inside-a-grammar-nqp)
2. Multiple Co-operating Grammars in Raku \- Mike Clarke : r/rakulang \- Reddit, accessed December 30, 2025, [https://www.reddit.com/r/rakulang/comments/ssd1lf/multiple_cooperating_grammars_in_raku_mike_clarke/](https://www.reddit.com/r/rakulang/comments/ssd1lf/multiple_cooperating_grammars_in_raku_mike_clarke/)
3. class Match \- Raku Documentation, accessed December 30, 2025, [https://docs.raku.org/type/Match](https://docs.raku.org/type/Match)
4. old-design-docs/S05-regex.pod at master \- GitHub, accessed December 30, 2025, [https://github.com/Raku/old-design-docs/blob/master/S05-regex.pod](https://github.com/Raku/old-design-docs/blob/master/S05-regex.pod)
5. Rakudo and NQP Internals \- GitHub Pages, accessed December 30, 2025, [https://edumentab.github.io/rakudo-and-nqp-internals-course/slides-day2.pdf](https://edumentab.github.io/rakudo-and-nqp-internals-course/slides-day2.pdf)
6. NQP gets MoarVM support, cursor reduction, and other news | 6guts \- WordPress.com, accessed December 30, 2025, [https://6guts.wordpress.com/2013/10/11/nqp-gets-moarvm-support-cursor-reduction-and-other-news/](https://6guts.wordpress.com/2013/10/11/nqp-gets-moarvm-support-cursor-reduction-and-other-news/)
7. Grammars \- Raku Documentation, accessed December 30, 2025, [https://docs.raku.org/language/grammars](https://docs.raku.org/language/grammars)
8. subparse \- Raku Documentation, accessed December 30, 2025, [https://docs.raku.org/routine/subparse](https://docs.raku.org/routine/subparse)
9. Using 'after' as lookbehind in a grammar in raku \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/62686065/using-after-as-lookbehind-in-a-grammar-in-raku](https://stackoverflow.com/questions/62686065/using-after-as-lookbehind-in-a-grammar-in-raku)
10. Matching things with Raku grammars \- DEV Community, accessed December 30, 2025, [https://dev.to/jj/matching-things-with-perl-6-grammars-ao9](https://dev.to/jj/matching-things-with-perl-6-grammars-ao9)
11. perl6 Need help to understand more about proto regex/token/rule \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/42291598/perl6-need-help-to-understand-more-about-proto-regex-token-rule](https://stackoverflow.com/questions/42291598/perl6-need-help-to-understand-more-about-proto-regex-token-rule)
12. Parsing Expression Grammars and the Structure of Languages \- Reddit, accessed December 30, 2025, [https://www.reddit.com/r/ProgrammingLanguages/comments/no0qdc/parsing_expression_grammars_and_the_structure_of/](https://www.reddit.com/r/ProgrammingLanguages/comments/no0qdc/parsing_expression_grammars_and_the_structure_of/)
13. What are the differences between PEGs and CFGs? \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/5501074/what-are-the-differences-between-pegs-and-cfgs](https://stackoverflow.com/questions/5501074/what-are-the-differences-between-pegs-and-cfgs)
14. Parsing expression grammar \- Wikipedia, accessed December 30, 2025, [https://en.wikipedia.org/wiki/Parsing_expression_grammar](https://en.wikipedia.org/wiki/Parsing_expression_grammar)
15. LPeg \- Parsing Expression Grammars For Lua \- INF/PUC-Rio, accessed December 30, 2025, [https://www.inf.puc-rio.br/\~roberto/lpeg/](https://www.inf.puc-rio.br/~roberto/lpeg/)
16. A Parsing Machine for PEGs \- INF/PUC-Rio, accessed December 30, 2025, [https://www.inf.puc-rio.br/\~roberto/docs/ry08-4.pdf](https://www.inf.puc-rio.br/~roberto/docs/ry08-4.pdf)
17. lpeg/lpvm.c at master · luvit/lpeg \- GitHub, accessed December 30, 2025, [https://github.com/luvit/lpeg/blob/master/lpvm.c](https://github.com/luvit/lpeg/blob/master/lpvm.c)
18. lpeg/lpcode.c at master · luvit/lpeg \- GitHub, accessed December 30, 2025, [https://github.com/luvit/lpeg/blob/master/lpcode.c](https://github.com/luvit/lpeg/blob/master/lpcode.c)
19. A Text Pattern-Matching Tool based on Parsing Expression Grammars \- INF/PUC-Rio, accessed December 30, 2025, [https://www.inf.puc-rio.br/\~roberto/docs/peg.pdf](https://www.inf.puc-rio.br/~roberto/docs/peg.pdf)
20. I know of at least one other use of operator overloading which is quite pleasant... | Hacker News, accessed December 30, 2025, [https://news.ycombinator.com/item?id=26684562](https://news.ycombinator.com/item?id=26684562)
21. Operator Overloading In Python \- Flexiple, accessed December 30, 2025, [https://flexiple.com/python/operator-overloading-python](https://flexiple.com/python/operator-overloading-python)
22. Can someone explain Operator Overloading in most simple way? : r/learnpython \- Reddit, accessed December 30, 2025, [https://www.reddit.com/r/learnpython/comments/b4j04y/can_someone_explain_operator_overloading_in_most/](https://www.reddit.com/r/learnpython/comments/b4j04y/can_someone_explain_operator_overloading_in_most/)
23. An introduction to Parsing Expression Grammars with LPeg \- leafo.net, accessed December 30, 2025, [https://leafo.net/guides/parsing-expression-grammars.html](https://leafo.net/guides/parsing-expression-grammars.html)
24. Javascript: operator overloading \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/19620667/javascript-operator-overloading](https://stackoverflow.com/questions/19620667/javascript-operator-overloading)
25. Fake operator overloading in JavaScript \- 2ality, accessed December 30, 2025, [https://2ality.com/2011/12/fake-operator-overloading.html](https://2ality.com/2011/12/fake-operator-overloading.html)
26. Proxy and Reflect \- The Modern JavaScript Tutorial, accessed December 30, 2025, [https://javascript.info/proxy](https://javascript.info/proxy)
27. Fluent interface \- Wikipedia, accessed December 30, 2025, [https://en.wikipedia.org/wiki/Fluent_interface](https://en.wikipedia.org/wiki/Fluent_interface)
28. What's the point of DSLs / fluent interfaces \- Stack Overflow, accessed December 30, 2025, [https://stackoverflow.com/questions/587995/whats-the-point-of-dsls-fluent-interfaces](https://stackoverflow.com/questions/587995/whats-the-point-of-dsls-fluent-interfaces)
29. A practical guide to Javascript Proxy | by Thomas Barrasso \- Bits and Pieces, accessed December 30, 2025, [https://blog.bitsrc.io/a-practical-guide-to-es6-proxy-229079c3c2f0](https://blog.bitsrc.io/a-practical-guide-to-es6-proxy-229079c3c2f0)
30. Grammar tutorial \- Raku Documentation, accessed December 30, 2025, [https://docs.raku.org/language/grammar_tutorial](https://docs.raku.org/language/grammar_tutorial)
