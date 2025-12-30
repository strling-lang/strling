# **Regex Backtracking and ReDoS Vulnerabilities: The Architectural Debt of Backtracking**

**Subtitle:** _Catastrophic Performance and the ReDoS Vulnerability_

## **1\. Introduction: The Unmanaged Wilderness of Text Processing**

In the modern software landscape, Regular Expressions (Regex) serve as the ubiquitous glue of data processing. From input validation in web forms to log parsing in security operations centers, regex is the de facto standard for pattern matching. However, this ubiquity masks a profound architectural fragility. The vast majority of production regex engines—including those embedded in the standard libraries of Java, Python, Ruby, and JavaScript—are built upon an architectural decision made decades ago: the use of unbounded Nondeterministic Finite Automaton (NFA) backtracking. This report argues that this decision constitutes a massive "architectural debt" that the industry is currently paying in the form of Regular Expression Denial of Service (ReDoS) vulnerabilities.

The ReDoS threat is not merely a performance annoyance; it is a fundamental failure of algorithmic safety. A single, carefully crafted malicious string can force a server into an exponential search loop, consuming 100% of available CPU resources and causing a total system hang. This vulnerability exists because the abstractions provided to developers—the regex syntax and the runtime engine—fail to communicate the computational cost of the patterns being executed. The engine fails silently until it fails catastrophically.

This report provides a comprehensive analysis of this failure mode to inform the roadmap for the STRling Compiler & Linter. By dissecting the mechanics of backtracking, analyzing the history of engine implementations, and surveying the current landscape of incomplete mitigations in languages like Java and Ruby, we establish the necessity for a new approach. STRling must leverage its compilation phase to bridge the "Optimization Gap," transforming regex safety from a runtime hazard into a compile-time guarantee. Through static analysis, Intermediate Representation (IR) optimization, and Instructional Error Handling, STRling can reject or rewrite dangerous patterns before they ever reach production, effectively retiring the debt that legacy engines have allowed to accumulate.

## ---

**2\. The Theoretical Divide: Automata, Complexity, and the Roots of Failure**

To understand why modern regex engines are vulnerable to ReDoS, we must first examine the theoretical foundations of pattern matching and the divergence between formal theory and practical implementation. This divergence is the root cause of the ReDoS vulnerability.

### **2.1 The Schism: Thompson vs. Spencer**

In the history of computer science, there are two primary lineages of regular expression implementation, each with distinct performance characteristics and capability sets. The choice between these two lineages dictates the security profile of the resulting language.

#### **2.1.1 The Thompson Construction (Safety First)**

The original implementation of regular expressions, pioneered by Ken Thompson in the 1960s (and used in tools like grep and awk), relied on the construction of a Finite Automaton.1

-   **Mechanism:** This approach constructs an NFA (Nondeterministic Finite Automaton) from the regex pattern. Crucially, it simulates the NFA by tracking the _set_ of all possible states the engine could be in at any given character position in the input string.3
-   **Complexity:** Because the number of states in the NFA is proportional to the size of the regex ($m$), and the simulation processes each input character ($n$) exactly once by updating the state set, the worst-case time complexity is $O(mn)$.
-   **Implication:** This guarantees linear time performance relative to the input length. A Thompson NFA engine cannot be forced into exponential backtracking by a malicious input string. It is immune to ReDoS in the classical sense.4

#### **2.1.2 The Spencer Implementation (Features First)**

In the late 1980s and 1990s, as Perl gained popularity, Henry Spencer and others developed a different approach to support "Extended" Regular Expressions. Developers demanded features that technically violated the definition of a Regular Language, specifically **Backreferences** (e.g., (a)\\1 to match "aa") and later **Lookarounds**.5

-   **Mechanism:** To support these features, the engine could not simply track a set of states. It needed to "remember" the specific path taken to reach a state (to capture the group content for the backreference). This necessitated a **Recursive Backtracking** algorithm.7
-   **Complexity:** The backtracking algorithm operates by Depth-First Search (DFS). When it encounters a quantifier (like \* or \+) or an alternation (|), it chooses one path and attempts to match. If that path eventually fails, the engine "backtracks" to the decision point and tries the next path.
-   **The Debt:** While this allowed for powerful text manipulation features, it introduced a worst-case time complexity of $O(2^n)$. The execution time can grow exponentially with the input size if the pattern contains ambiguities.

Most modern programming languages, including Python, Ruby (pre-3.2), Java, and JavaScript, adopted the Spencer-style backtracking engine to maintain compatibility with Perl-compatible Regular Expressions (PCRE).5 This decision prioritized feature richness over algorithmic safety, embedding the ReDoS vulnerability into the foundation of the web stack.

### **2.2 The Mechanics of Catastrophe: Exponential Backtracking**

The mechanism of a ReDoS attack is best understood by analyzing the behavior of the engine when processing a "pathological" regex against a "malicious" input. The canonical example is the pattern (a+)+b.

#### **2.2.1 The Ambiguity of Nested Quantifiers**

Consider the pattern (a+)+b and the input string aaaaaaaaaaaaaaaaaaaa (20 'a's) followed by a \! (which causes the final b match to fail).

1. **The Pattern Structure:**
    - The inner quantifier a+ is greedy. It matches one or more 'a's.
    - The outer quantifier (...)+ is also greedy. It matches one or more groups of the inner match.
    - The final character b is the anchor that forces the engine to continue searching until the end of the string.
2. The Combinatorial Explosion:  
   Because the input string consists entirely of 'a's, there are multiple valid ways to partition the string to satisfy the (a+)+ portion.
    - **Option 1:** One outer group containing 20 'a's: {aaaaaaaaaaaaaaaaaaaa}.
    - **Option 2:** Two outer groups: {aaaaaaaaaaaaaaaaaaa}{a}.
    - **Option 3:** Two outer groups: {aaaaaaaaaaaaaaaaaa}{aa}.
    - **Option 4:** Twenty outer groups: {a}{a}{a}...{a}.

Mathematically, this is equivalent to the problem of integer composition: finding all sequences of positive integers that sum to $n$. The number of such compositions is $2^{n-1}$.

3. The Execution Trace:  
   When the engine reaches the end of the string and encounters \! instead of b, it must backtrack. It returns to the most recent decision point—the last repetition of the outer quantifier—and attempts to reduce the number of characters consumed by the inner quantifier. It then retries the match.
    - If that fails, it backtracks again.
    - It recursively explores _every single possible partition_ of the string.
    - For an input length of $n=30$, the engine executes roughly $2^{29}$ operations (over 500 million steps). For $n=50$, the number of operations exceeds the number of milliseconds since the Big Bang.3

This is the ReDoS condition. The CPU is pinned at 100% utilization, processing a single request. In a threaded server (like Java or Ruby on Rails), this blocks one worker thread. If an attacker sends $k$ such requests, where $k$ is the size of the thread pool, the entire server becomes unresponsive to legitimate traffic.13

### **2.3 The Taxonomy of Evil Regexes**

Static analysis of ReDoS vulnerabilities relies on identifying specific structural patterns in the regex that lead to this exponential behavior. These patterns are often referred to as "Evil Regexes" or "Vulnerable Patterns."

#### **2.3.1 Nested Quantifiers (NQ)**

This is the most severe and common class of ReDoS vulnerability.

-   **Definition:** A quantifier resides inside another quantifier, and there is a common character that can be matched by both the inner and outer loops.14
-   **Examples:**
    -   (a+)+: The classic case.
    -   (\\w\*)\*: Common in attempts to match optional words.
    -   (x+x+)+y: As highlighted in 11, this pattern is particularly insidious because it involves adjacent repetition inside a loop.

#### **2.3.2 Quantified Overlapping Disjunction (QOD)**

This pattern occurs when an alternation (OR) contains overlapping options, and the alternation itself is repeated.

-   **Definition:** (A|B)+ where the languages defined by A and B have a non-empty intersection.15
-   **Example:** (a|a)+ or (\\w|s)+.
-   **Mechanism:** If the input is "a", the engine can match it via the first branch (a) or the second branch (a). If this decision is inside a loop, the ambiguity multiplies at every iteration, leading to the same $O(2^n)$ complexity as nested quantifiers.

#### **2.3.3 Quantified Overlapping Adjacency (QOA)**

This pattern involves two adjacent parts of a regex that can match the same input.

-   **Definition:** A+B+ where the suffix of A overlaps with the prefix of B.15
-   **Example:** \\d+\\d+.
-   **Mechanism:** While typically "Polynomial" ($O(n^2)$ or $O(n^3)$) rather than exponential, QOA can still be catastrophic on large inputs. If the input is a string of 100,000 digits, an $O(n^2)$ match can take minutes, sufficient to time out a web request and degrade service availability.

**Table 1: Complexity Classes of Regex Patterns**

| Pattern Type          | Complexity       | Example   | Description                  | Vulnerability Level                  |
| :-------------------- | :--------------- | :-------- | :--------------------------- | :----------------------------------- |
| **Linear**            | $O(n)$           | a+b+      | No ambiguity. Deterministic. | Safe                                 |
| **Polynomial**        | $O(n^2), O(n^3)$ | \\d+.\\d+ | Overlapping adjacency.       | Medium (DoS on large payloads)       |
| **Exponential**       | $O(2^n)$         | (a+)+     | Nested quantifiers.          | **Critical** (DoS on small payloads) |
| **Super-Exponential** | $O(2^{2^n})$     | (a\*)\*   | Nested Kleene stars (rare).  | **Critical**                         |

## ---

**3\. The Landscape of Vulnerability: A Language Survey**

The severity of the ReDoS threat depends entirely on the regex engine implementation used by the host programming language. A survey of the current landscape reveals a fragmented ecosystem where "safety" is often an afterthought or a recent, incomplete patch.

### **3.1 Java: The Bounded Memoization Defense**

For nearly two decades, Java's java.util.regex package was a pure backtracking engine with no defenses against ReDoS. It was, and remains, a primary vector for ReDoS attacks in enterprise applications.

#### **3.1.1 The Java 9 Patch**

In 2016, with the release of JDK 9, the OpenJDK team introduced a significant mitigation strategy.5 The patch, comprising approximately 1,712 lines of code, added a **Bounded Memoization Cache** to the engine.

-   **Concept:** The core idea is to prune the backtracking search tree. If the engine backtracks to a specific state (current node in the regex compiled graph) at a specific position (index in the input string) that it has already visited, it knows that exploring this path again is futile. It can immediately return failure for that branch.19
-   **Impact:** For simple exponential patterns like (a+)+, this optimization effectively collapses the search tree from exponential to polynomial (or even linear) time, as redundant paths are cut off.

#### **3.1.2 The Failure of the Defense (Bypasses)**

Despite this improvement, Java 9+ is not immune to ReDoS. The defense is "bounded" to preventing memory exhaustion.

-   **Cache Eviction:** The memoization cache has a fixed size. If a pattern and input string are sufficiently complex to generate more unique (state, index) pairs than the cache can hold, the engine must evict entries or stop caching. Once this limit is reached, the engine falls back to raw, exponential backtracking.5
-   **Complex Interaction:** Patterns using advanced features like backreferences or certain types of lookarounds interact poorly with the simple node-index caching key. Research indicates that constructing specific "attack strings" can still trigger catastrophic backtracking in Java 9+ runtimes.18 The vulnerability remains an active concern, evidenced by ongoing CVEs such as CVE-2023-39663.5

### **3.2 Ruby: Partial Mitigation in Version 3.2**

The Ruby ecosystem, particularly the Ruby on Rails framework, has been historically plagued by ReDoS vulnerabilities (e.g., CVE-2023-28755 in the URI gem).21 Ruby 3.2 (released December 2022\) introduced two major defenses.23

#### **3.2.1 Memoization-Based Matching**

Similar to Java, Ruby introduced a memoization technique into its Onigmo regex engine.

-   **Claim:** The release notes state that this allows "most regex matches to be completed in linear time".25
-   **Limitation:** This optimization is heuristic. It does not apply to all regexes. Specifically, patterns using backreferences, atomic groups, or "too large" fixed repetitions fall back to the slow path. This creates a false sense of security; developers may assume the engine is safe when it is only conditionally safe.25

#### **3.2.2 The Timeout Mechanism**

Ruby 3.2 also introduced Regexp.timeout, a global configuration to interrupt long-running matches.23

-   **Analysis:** While practical, a timeout is a mitigation, not a solution. It converts an "infinite hang" into a "1-second stall." In a high-throughput system processing thousands of requests per second, allowing an attacker to stall threads for 1 second each is still a potent Denial of Service vector.26 Furthermore, relying on timeouts forces developers to handle Regexp::TimeoutError exceptions everywhere, effectively treating regex matching as an I/O operation that can fail, which complicates codebases.25

### **3.3 Python and JavaScript: The Unprotected Frontier**

-   **Python:** The re module in Python is a standard backtracking engine with **no built-in ReDoS defenses**. It has no timeout mechanism and no memoization. It is fully vulnerable to (a+)+ and similar patterns. The Python community relies on third-party libraries (like google-re2) or strict code review to mitigate this, but the standard library remains unsafe.5
-   **JavaScript (V8/Node.js):** Historically, V8 used a backtracking engine. While recent versions have introduced an experimental non-backtracking engine, it is opt-in or used only for simple patterns. The ubiquity of JavaScript on both client (browser) and server (Node.js) makes this a massive attack surface. A ReDoS on the client freezes the browser UI; on the server, it crashes the application.8

### **3.4 The Safe Alternatives: Rust, Go, and RE2**

Languages like Go and Rust (via the regex crate) have taken a hard stance against backtracking.

-   **Architecture:** They utilize Thompson's construction to build NFA/DFA engines that guarantee $O(mn)$ execution time.27
-   **Trade-off:** To achieve this safety, they explicitly **drop support** for backreferences and arbitrary lookarounds. This "Feature Gap" means that many valid PCRE regexes cannot be ported to Rust or Go.
-   **Nuance:** Even these engines are not perfectly immune to all resource attacks. They can suffer from **DFA State Blowup** (exponential memory usage during compilation) or **Polynomial Slowness** (quadratic time) if not carefully implemented.3 However, they effectively eliminate the existential threat of Exponential ReDoS.

## ---

**4\. Instructional Failure: The Silent Crash and the Invisible Cost**

The persistence of ReDoS is not solely a technical problem; it is a user interface (UI) problem of the compiler and runtime. The tools provided to developers fail to communicate the risks inherent in the code they write.

### **4.1 The "Silent Failure" Paradigm**

When a developer writes a dangerous pattern like ^(\[a-zA-Z0-9\]+\\s?)+$, the compiler (or interpreter) accepts it without complaint.

-   **Validity vs. Safety:** The pattern is syntactically valid. It compiles into a bytecode or state machine. The runtime executes it.
-   **The Feedback Loop:** For 99.9% of inputs (valid inputs), the regex performs efficiently. The developer receives positive reinforcement that the code is correct.
-   **The Crash:** The failure only occurs under specific, often adversarial conditions. When the ReDoS is triggered, the symptoms are opaque: the application stops responding, CPU usage spikes, and health checks fail. There is no exception thrown (until a timeout kills the process), and no error message pointing to the specific regex line number or the specific backtracking flaw.29
-   **Diagnosis Cost:** Debugging a ReDoS often involves capturing thread dumps, analyzing stack traces to find java.util.regex calls, and then manually isolating the offending pattern. This process requires high-level expertise that many generalist developers lack.

### **4.2 Visualizing the Invisible: The Role of Debuggers**

The opacity of the backtracking process has led to the rise of third-party visualization tools like **Regex101** and **RegexBuddy**. These tools are essential because they make the invisible visible.

-   **The Step Counter:** The critical metric exposed by these tools is the "Step Count." A match might take 20 steps. A mismatch on a safe regex might take 25 steps. A mismatch on a ReDoS regex might take 50,000 steps for a short string.30
-   **The Visualization:** These debuggers show the engine's cursor moving forward, entering a group, failing, moving back, changing the group capture, moving forward again, and repeating. This visualizes the recursive descent of the algorithm.12
-   **STRling's Opportunity:** STRling's "Instructional Error Handling" must bridge this gap. The compiler should perform this "step count simulation" (or a static analysis equivalent) during compilation and present the result to the user _before_ the code runs.

### **4.3 Instructional Error Messages**

STRling's mission is to replace "Silent Failure" with **Instructional Errors**. This draws inspiration from the Rust compiler's philosophy of helpful error messages.33

**Contrast of Experience:**

-   **Current State (Java/Python):**
    -   _Input:_ (a+)+
    -   _Output:_ None (Compiles successfully).
    -   _Runtime:_ System hang.
-   **STRling Target State:**
    -   _Input:_ (a+)+
    -   Output:  
        Error\[E042\]: Catastrophic Backtracking Detected  
        \--\> src/validation.strl:12:15  
        |  
        12 | let pattern \= "(a+)+";

| ^^^^^^ Nested quantifier detected here.  
|  
\= Explanation: The group (a+) is repeated by the outer quantifier (+).  
This creates exponential complexity O(2^n). A string of 30 'a's  
followed by a mismatch will cause the engine to hang.  
\= Recommendation: Remove the nested quantifier if possible.  
\= Fix: Use an atomic group to disable backtracking: "(?\>a+)+"  
This approach fulfills the requirement of teaching the user why the pattern is dangerous, turning a potential vulnerability into an educational moment.35

## ---

**5\. The Optimization Gap: A Compiler-First Approach**

The "Optimization Gap" refers to the missed opportunity in current regex engines. Because most engines parse and compile at runtime (or JIT at the instruction level), they lack the global view required to perform high-level algorithmic optimizations. STRling's architecture, based on a rigorous compilation pipeline, can close this gap.

### **5.1 STRling Compiler Architecture**

To enable deep static analysis and optimization, STRling requires a multi-stage compiler architecture, similar to that of Rust or LLVM.36

#### **5.1.1 The Compilation Pipeline**

1. **Lexical Analysis:** Tokenize the regex string.
2. **Parsing:** Construct an Abstract Syntax Tree (AST). This represents the syntactic structure (groups, quantifiers, characters).38
3. **Lowering to HIR (High-Level Intermediate Representation):** Transform the AST into a semantic graph. This is the crucial step for ReDoS detection.
    - **HIR Design:** The HIR must explicitly represent the _topology_ of the automata. It needs to distinguish between "loops" (quantifiers) and "branches" (alternations) and track their nesting relationships.39
    - _Reference:_ Rust's regex crate uses an HIR to perform analysis before compiling to the NFA.40
4. **Static Analysis (The Linter):** Run safety passes on the HIR.
5. **Optimization (The Rewriter):** Transform the HIR to improve safety and performance.
6. **Code Generation (MIR/LIR):** Emit the final executable code (Thompson NFA instructions or a backtracking bytecode with safeguards).

### **5.2 Static Analysis Algorithms**

The Linter phase utilizes algorithms derived from academic research to detect ReDoS patterns mathematically.

#### **5.2.1 Brzozowski Derivatives**

One powerful method for analyzing regex behavior is the use of **Brzozowski Derivatives**.5

-   **Concept:** The derivative of a regular expression $R$ with respect to a symbol $a$ (denoted $D\_a(R)$) is the set of strings $S$ such that $aS$ matches $R$.
-   **Application:** Derivatives allow the compiler to explore the state space of the regex without generating the full NFA. By calculating derivatives, the compiler can detect:
    -   **Nullability:** Can a loop match the empty string? (A common cause of infinite loops).
    -   **Ambiguity:** If $D\_a(R)$ results in a set of regexes that have significant overlap, it indicates potential backtracking issues.
    -   **Cycle Detection:** By building a graph of derivatives, the compiler can detect "pumpable" cycles that lead to exponential blowup.2

#### **5.2.2 Automata Graph Analysis (ReDoSHunter Approach)**

Another approach, used by tools like ReDoSHunter and REVEALER, involves analyzing the topology of the NFA graph.13

-   **Algorithm:**
    1. Convert the regex HIR to a generalized NFA graph.
    2. Identify all "Pivot Nodes" (nodes involved in loops/quantifiers).
    3. Check for **Strongly Connected Components (SCCs)** that contain overlapping paths.
    4. If a path exists where the engine can cycle through an SCC in two different ways while consuming the same input, the pattern is vulnerable.44
-   **Integration:** STRling can implement a simplified version of this logic to flag QOD and NQ patterns during compilation.

### **5.3 Optimization Strategies: The Rewrite System**

STRling's value proposition extends beyond detection to **Auto-Remediation**. The compiler can automatically rewrite dangerous patterns into safe equivalents using formal logic rules.45

#### **5.3.1 Kleene Algebra Rewrite Rules**

Using the axioms of Kleene Algebra, STRling can mathematically prove that two regexes are equivalent and replace the slow one with the fast one.

-   **Idempotence of Kleene Star:**
    -   _Rule:_ $(a^\*)^\* \\equiv a^\*$
    -   _Application:_ Automatically flatten nested stars. This eliminates the $O(2^n)$ risk entirely for this class of patterns.45
-   **Unrolling Alternations:**
    -   _Rule:_ $(a|b)^\* \\equiv \[ab\]^\*$ (where a and b are single characters).
    -   _Application:_ Replace costly alternation backtracking with efficient bit-set character class matching.47

#### **5.3.2 Atomic Group Injection**

For patterns that cannot be mathematically simplified but are detected as risky, STRling can inject **Atomic Groups** (also known as "Possessive Quantifiers" or "Independent Sub-expressions").11

-   **Transformation:** (a+)+ $\\rightarrow$ (?\>(a+)+)
-   **Mechanism:** An atomic group (?\>...) acts as a firewall for backtracking. Once the engine exits the group, it discards all backtracking positions saved within it.
-   **Impact:** This reduces the complexity from exponential to linear.
-   **Warning:** This optimization changes semantics (it prohibits backtracking that might be necessary for a match in rare cases). Therefore, STRling must perform this **optimistically** but issue a **Warning** to the developer: _"Compiler optimized potential ReDoS pattern by adding atomic grouping. Verify behavior on complex inputs."_

**Table 2: STRling Compiler Optimization Rules**

| Original Pattern (Risky) | Optimized Pattern (Safe) | Technique            | Safety Level               |
| :----------------------- | :----------------------- | :------------------- | :------------------------- |
| (a+)+                    | a+                       | Quantifier Reduction | Safe (Equivalent)          |
| (?:a\*)\*                | a\*                      | Idempotence          | Safe (Equivalent)          |
| \`(a                     | b)+\`                    | \[ab\]+              | Character Class Conversion |
| \`(A                     | B)\*\` (Complex A, B)    | \`(?\>(A             | B)\*)\`                    |
| \\d+\\d+                 | \\d{2,}                  | Adjacency Coalescing | Safe (Equivalent)          |

## ---

**6\. Strategic Outcomes: Defining the Roadmap**

The analysis of the ReDoS threat and the capabilities of static analysis informs the strategic roadmap for the STRling project. The goal is to position STRling as the "Safe-By-Design" alternative in the text processing market.

### **6.1 The "Security Wedge"**

STRling can use ReDoS as a wedge to enter markets dominated by Java and Python.

-   **Pitch:** "Your WAF uses Regex. Your Input Validation uses Regex. Are you sure they are safe? STRling guarantees they are."
-   **Compliance:** Position STRling as a tool for meeting security compliance standards (like OWASP Top 10, which lists ReDoS under "Vulnerable and Outdated Components" or "Security Misconfiguration").16

### **6.2 The Compiler & Linter Roadmap**

The development of the STRling compiler should follow a phased approach:

**Phase 1: The Scanner (Static Analysis MVP)**

-   Implement parsing to HIR.
-   Implement detection of basic "Evil Regex" patterns: Nested Quantifiers (a+)+ and simple Overlapping Disjunctions (a|a)+.
-   Output: Compile-time Warnings.

**Phase 2: The Teacher (Instructional Error Handling)**

-   Enhance error messages. Connect the detected pattern to the concept of backtracking.
-   Integrate a "complexity score" into the output (e.g., "This regex has a complexity score of 50\. Limit is 10.").

**Phase 3: The Optimizer (Auto-Rewrite)**

-   Implement Kleene Algebra rewrite rules.
-   Implement the "Atomic Group Injection" with safety warnings.
-   Goal: Automatically fix 80% of common ReDoS patterns without user intervention.

**Phase 4: The Guardian (Strict Mode)**

-   Introduce a \--safe-regex flag.
-   In this mode, any pattern that cannot be proven linear-time (via Thompson construction or derivative analysis) is rejected.
-   This positions STRling as a direct competitor to Rust's regex crate but with better developer ergonomics (instructional errors).

## **7\. Conclusion: Retiring the Debt**

The "Architectural Debt of Backtracking" has accumulated for over thirty years. It began with the desire for extended features in Perl and was cemented by the adoption of Spencer-style engines in Java, Python, and Ruby. The industry has paid the price in the form of fragile infrastructure, unexpected outages, and a constant stream of security vulnerabilities.

Current mitigations—timeouts, bounded memoization—are merely servicing the interest on this debt. They do not resolve the underlying structural flaw. STRling represents an opportunity to retire the debt entirely.

By shifting the responsibility of complexity analysis from the runtime to the compiler, STRling fundamentally changes the relationship between the developer and the regex engine. It moves regex from an interpreted, opaque "magic string" to a compiled, analyzed, and optimized code artifact. Through **Instructional Error Handling**, STRling empowers developers to understand the cost of their abstractions. Through **Static Analysis and IR Optimization**, it safeguards applications against the mathematical inevitability of exponential backtracking. In doing so, STRling does not just build a better regex engine; it builds a more secure and reliable foundation for the future of text processing.

#### **Works cited**

1. Regular expression \- Wikipedia, accessed December 28, 2025, [https://en.wikipedia.org/wiki/Regular_expression](https://en.wikipedia.org/wiki/Regular_expression)
2. RE\#: High Performance Derivative-Based Regex Matching with Intersection, Complement and Lookarounds \- arXiv, accessed December 28, 2025, [https://arxiv.org/html/2407.20479v1](https://arxiv.org/html/2407.20479v1)
3. ReDoS \- Wikipedia, accessed December 28, 2025, [https://en.wikipedia.org/wiki/ReDoS](https://en.wikipedia.org/wiki/ReDoS)
4. Regular Expression Matching Can Be Simple And Fast, accessed December 28, 2025, [https://swtch.com/\~rsc/regexp/regexp1.html](https://swtch.com/~rsc/regexp/regexp1.html)
5. SoK: Demystifying Regular Expression Denial of Service \- arXiv, accessed December 28, 2025, [https://arxiv.org/html/2406.11618v1](https://arxiv.org/html/2406.11618v1)
6. Regular expressions: Basic notions \- School of Mathematical and Computer Sciences, accessed December 28, 2025, [http://www.macs.hw.ac.uk/\~hwloidl/Events/ISS-AiPL-2014/materials/Henglein/slides1.pdf](http://www.macs.hw.ac.uk/~hwloidl/Events/ISS-AiPL-2014/materials/Henglein/slides1.pdf)
7. To sum it up: The NFA and the DFA have exactly the same Big O complexity. The NF... | Hacker News, accessed December 28, 2025, [https://news.ycombinator.com/item?id=10211337](https://news.ycombinator.com/item?id=10211337)
8. SoK: A Literature and Engineering Review of Regular Expression Denial of Service (ReDoS) | by James Davis, accessed December 28, 2025, [https://davisjam.medium.com/sok-a-literature-and-engineering-review-of-regular-expression-denial-of-service-redos-e6b10ef547c7](https://davisjam.medium.com/sok-a-literature-and-engineering-review-of-regular-expression-denial-of-service-redos-e6b10ef547c7)
9. RE\#: High performance derivative-based regular expression matching (2024) | Hacker News, accessed December 28, 2025, [https://news.ycombinator.com/item?id=44633024](https://news.ycombinator.com/item?id=44633024)
10. Comparison of time complexity for NFA and backtracking implementations of regex search, accessed December 28, 2025, [https://cs.stackexchange.com/questions/171696/comparison-of-time-complexity-for-nfa-and-backtracking-implementations-of-regex](https://cs.stackexchange.com/questions/171696/comparison-of-time-complexity-for-nfa-and-backtracking-implementations-of-regex)
11. Regex Performance \- Coding Horror, accessed December 28, 2025, [https://blog.codinghorror.com/regex-performance/](https://blog.codinghorror.com/regex-performance/)
12. Catastrophic Backtracking \- Runaway Regular Expressions, accessed December 28, 2025, [https://www.regular-expressions.info/catastrophic.html](https://www.regular-expressions.info/catastrophic.html)
13. REVEALER: Detecting and Exploiting Regular Expression Denial-of-Service Vulnerabilities \- CUHK Computer Security Lab, accessed December 28, 2025, [https://seclab.cse.cuhk.edu.hk/papers/sp21_redos.pdf](https://seclab.cse.cuhk.edu.hk/papers/sp21_redos.pdf)
14. What is Regular Expression Denial of Service (ReDoS)? \- Imperva, accessed December 28, 2025, [https://www.imperva.com/learn/ddos/regular-expression-denial-of-service-redos/](https://www.imperva.com/learn/ddos/regular-expression-denial-of-service-redos/)
15. RegexScalpel: Regular Expression Denial of Service (ReDoS) Defense by Localize-and-Fix \- USENIX, accessed December 28, 2025, [https://www.usenix.org/system/files/sec22_slides-li_yeting.pdf](https://www.usenix.org/system/files/sec22_slides-li_yeting.pdf)
16. Regular expression Denial of Service \- ReDoS \- OWASP Foundation, accessed December 28, 2025, [https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service\_-_ReDoS](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS)
17. ReDoS | Tutorial & Examples \- Snyk Learn, accessed December 28, 2025, [https://learn.snyk.io/lesson/redos/](https://learn.snyk.io/lesson/redos/)
18. Is Java ReDos vulnerable? \- regex \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/53048859/is-java-redos-vulnerable](https://stackoverflow.com/questions/53048859/is-java-redos-vulnerable)
19. Towards an Effective Method of ReDoS Detection for Non ... \- USENIX, accessed December 28, 2025, [https://www.usenix.org/system/files/usenixsecurity24-su-weihao.pdf](https://www.usenix.org/system/files/usenixsecurity24-su-weihao.pdf)
20. Regex Denial of Service (ReDoS): The Pattern That Freezes Your Server | by InstaTunnel, accessed December 28, 2025, [https://medium.com/@instatunnel/regex-denial-of-service-redos-the-pattern-that-freezes-your-server-843e6c035deb](https://medium.com/@instatunnel/regex-denial-of-service-redos-the-pattern-that-freezes-your-server-843e6c035deb)
21. Regular Expression Denial of Service (ReDoS) in actionpack | CVE-2024-41128 | Snyk, accessed December 28, 2025, [https://security.snyk.io/vuln/SNYK-RUBY-ACTIONPACK-8220162](https://security.snyk.io/vuln/SNYK-RUBY-ACTIONPACK-8220162)
22. CVE-2023-36617: ReDoS vulnerability in URI \- Ruby, accessed December 28, 2025, [https://www.ruby-lang.org/en/news/2023/06/29/redos-in-uri-CVE-2023-36617/](https://www.ruby-lang.org/en/news/2023/06/29/redos-in-uri-CVE-2023-36617/)
23. Ruby 3.2.0 enhances Regexp performance and security with ReDoS protections, accessed December 28, 2025, [https://blog.kiprosh.com/ruby-3-2-0-introduce/](https://blog.kiprosh.com/ruby-3-2-0-introduce/)
24. Changes/Ruby 3.2 \- Fedora Project Wiki, accessed December 28, 2025, [https://fedoraproject.org/wiki/Changes/Ruby_3.2](https://fedoraproject.org/wiki/Changes/Ruby_3.2)
25. Regex Improvements in the New Ruby 3.2 \- reinteractive, accessed December 28, 2025, [https://reinteractive.com/articles/tutorial-series-new-to-rails/regex-improvements-in-the-new-ruby-3-2](https://reinteractive.com/articles/tutorial-series-new-to-rails/regex-improvements-in-the-new-ruby-3-2)
26. Feature \#17837: Add support for Regexp timeouts \- Ruby Issue Tracking System, accessed December 28, 2025, [https://bugs.ruby-lang.org/issues/17837](https://bugs.ruby-lang.org/issues/17837)
27. How to fix a ReDoS \- The GitHub Blog, accessed December 28, 2025, [https://github.blog/security/how-to-fix-a-redos/](https://github.blog/security/how-to-fix-a-redos/)
28. regex \- Rust \- Docs.rs, accessed December 28, 2025, [https://docs.rs/regex/latest/regex/](https://docs.rs/regex/latest/regex/)
29. Catastrophic Backtracking — The Dark Side of Regular Expressions | by Ohad Yakovskind | BigPanda Engineering | Medium, accessed December 28, 2025, [https://medium.com/bigpanda-engineering/catastrophic-backtracking-the-dark-side-of-regular-expressions-80cab9c443f6](https://medium.com/bigpanda-engineering/catastrophic-backtracking-the-dark-side-of-regular-expressions-80cab9c443f6)
30. Regular Expression Denial of Service (ReDoS) and Catastrophic Backtracking | Snyk, accessed December 28, 2025, [https://snyk.io/blog/redos-and-catastrophic-backtracking/](https://snyk.io/blog/redos-and-catastrophic-backtracking/)
31. Regex Debugger \- Catastrophic backtracking example \- Regex101, accessed December 28, 2025, [https://regex101.com/r/iXSKTs/1/debugger](https://regex101.com/r/iXSKTs/1/debugger)
32. Debugging Catastrophic Backtracking for Regular Expressions in Python, accessed December 28, 2025, [https://krishnanchandra.com/posts/regex-catastrophic-backtracking/](https://krishnanchandra.com/posts/regex-catastrophic-backtracking/)
33. Are very explanatory compiler error messages worth the effort needed to implement them?, accessed December 28, 2025, [https://langdev.stackexchange.com/questions/544/are-very-explanatory-compiler-error-messages-worth-the-effort-needed-to-implemen](https://langdev.stackexchange.com/questions/544/are-very-explanatory-compiler-error-messages-worth-the-effort-needed-to-implemen)
34. Writing Good Compiler Error Messages | Code → Software, accessed December 28, 2025, [https://calebmer.com/2019/07/01/writing-good-compiler-error-messages.html](https://calebmer.com/2019/07/01/writing-good-compiler-error-messages.html)
35. Error Handling in Compiler Design \- GeeksforGeeks, accessed December 28, 2025, [https://www.geeksforgeeks.org/compiler-design/error-handling-compiler-design/](https://www.geeksforgeeks.org/compiler-design/error-handling-compiler-design/)
36. Compiler Design Best Practices \- Meegle, accessed December 28, 2025, [https://www.meegle.com/en_us/topics/compiler-design/compiler-design-best-practices](https://www.meegle.com/en_us/topics/compiler-design/compiler-design-best-practices)
37. HIR vs MIR vs LIR : r/rust \- Reddit, accessed December 28, 2025, [https://www.reddit.com/r/rust/comments/8d9i32/hir_vs_mir_vs_lir/](https://www.reddit.com/r/rust/comments/8d9i32/hir_vs_mir_vs_lir/)
38. How to build an optimal AST of a regular expression? \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/37878198/how-to-build-an-optimal-ast-of-a-regular-expression](https://stackoverflow.com/questions/37878198/how-to-build-an-optimal-ast-of-a-regular-expression)
39. Crate hir \- Rust, accessed December 28, 2025, [https://rust-lang.github.io/rust-analyzer/hir/index.html](https://rust-lang.github.io/rust-analyzer/hir/index.html)
40. Regex engine internals as a library \- Andrew Gallant's Blog, accessed December 28, 2025, [https://blog.burntsushi.net/regex-internals/](https://blog.burntsushi.net/regex-internals/)
41. guidance-ai/derivre: Derivative-based regular expression engine for Rust \- GitHub, accessed December 28, 2025, [https://github.com/guidance-ai/derivre](https://github.com/guidance-ai/derivre)
42. Derivatives of Regular Expressions \- Harrison Goldstein, accessed December 28, 2025, [https://harrisongoldste.in/languages/2017/09/30/derivatives-of-regular-expressions.html](https://harrisongoldste.in/languages/2017/09/30/derivatives-of-regular-expressions.html)
43. ReDoSHunter: A Combined Static and Dynamic Approach for Regular Expression DoS Detection | USENIX, accessed December 28, 2025, [https://www.usenix.org/conference/usenixsecurity21/presentation/li-yeting](https://www.usenix.org/conference/usenixsecurity21/presentation/li-yeting)
44. Static Detection of DoS Vulnerabilities in Programs that use Regular Expressions \- UT Austin Computer Science, accessed December 28, 2025, [https://www.cs.utexas.edu/\~isil/redos.pdf](https://www.cs.utexas.edu/~isil/redos.pdf)
45. Optimizing Regular Expressions via Rewrite-Guided Synthesis \- arXiv, accessed December 28, 2025, [https://arxiv.org/pdf/2104.12039](https://arxiv.org/pdf/2104.12039)
46. Simplifying Regular Expression Quantifiers \- regex \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/24109176/simplifying-regular-expression-quantifiers](https://stackoverflow.com/questions/24109176/simplifying-regular-expression-quantifiers)
47. Five Invaluable Techniques to Improve Regex Performance \- Loggly, accessed December 28, 2025, [https://www.loggly.com/blog/five-invaluable-techniques-to-improve-regex-performance/](https://www.loggly.com/blog/five-invaluable-techniques-to-improve-regex-performance/)
48. Catastrophic Backtracking regular expression example in Java 9+ \[closed\] \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/64280370/catastrophic-backtracking-regular-expression-example-in-java-9](https://stackoverflow.com/questions/64280370/catastrophic-backtracking-regular-expression-example-in-java-9)
