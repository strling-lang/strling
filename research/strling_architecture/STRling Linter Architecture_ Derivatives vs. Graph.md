# **Linter Architecture Spec: Feasibility of Symbolic Derivative-Based Static Analysis for ReDoS Detection**

## **1\. Executive Summary**

### **1.1 The Architectural Imperative**

The evolution of STRling from a syntactic sugar for regular expressions into a robust, "safe-by-default" pattern-matching framework necessitates a fundamental shift in how the compiler approaches safety verification. The core mission of STRling is to democratize rigorous pattern matching, ensuring that developers—regardless of their depth of expertise in automata theory—can deploy patterns that are not only expressive and maintainable but also guaranteed to perform predictably in production environments. The primary threat to this guarantee is Regular Expression Denial of Service (ReDoS), a vulnerability deeply embedded in the backtracking architecture of the engines (PCRE2, Python re, Node.js) that STRling currently targets.

Previous architectural reviews identified "Static Analysis" as the necessary intervention to mitigate ReDoS. However, the constraints of a modern development environment impose a stringent latency budget. A linter that introduces perceptible delays—freezing the Integrated Development Environment (IDE) to construct massive Nondeterministic Finite Automata (NFAs)—violates the principle of "Pragmatic Empathy" by obstructing the developer's flow. The traditional graph-based analysis methods, typified by tools like ReDoSHunter, while effective in offline security audits, entail a computational overhead that renders them unsuitable for the real-time, interactive feedback loop envisioned for the STRling Copilot ecosystem.

This report executes Research Directive 4, evaluating the feasibility of a radical architectural alternative: a **Lightweight Derivative Scanner** based on **Brzozowski Derivatives** and their modern **Symbolic** extensions. This approach shifts the paradigm of static analysis from graph topology inspection to algebraic exploration. By leveraging recent breakthroughs in derivative-based engines, such as the RE\# project 1, and theoretical advancements in ambiguity diagnosis 3, this investigation determines whether the STRling compiler can mathematically prove pattern safety (linear time complexity) or detect vulnerability (exponential ambiguity) at compile time without the prohibitive cost of full NFA construction.

### **1.2 Verdict and Strategic Recommendation**

The comprehensive analysis of the research materials indicates that a **Symbolic Derivative-based linter is not only feasible but architecturally superior** to traditional graph-based methods for the specific use case of the STRling compiler.

The evidence suggests that the "Derivative-Based" approach aligns perfectly with STRling's Intermediate Representation (IR). Unlike graph-based methods that require a lossy and expensive conversion of the IR into an NFA, symbolic derivatives operate directly on the algebraic structure of the pattern. This preserves the semantic richness of the code—such as variable names and group hierarchies—allowing for error messages that are educational and precise rather than opaque and abstract. Furthermore, the ability of symbolic derivatives to handle boolean operations (intersection and complement) natively provides a pathway to verify complex validations that are difficult to model with standard NFAs.

Therefore, we recommend the immediate prioritization of the **Symbolic Ambiguity Inspector (SAI)** architecture. This system will utilize a **Lazy Symbolic Exploration** strategy to detect the root cause of ReDoS—**Exponential Ambiguity**—by exploring the derivative state space on-demand. This avoids the upfront cost of full automata generation, ensuring that the linter remains responsive while providing rigorous safety guarantees. The following report details the theoretical foundations, comparative analysis, and concrete implementation specification for this new architectural component.

## ---

**2\. The ReDoS Threat Landscape**

To engineer a solution that is both effective and efficient, one must first deconstruct the problem of ReDoS with mathematical precision. It is insufficient to categorize ReDoS merely as "slow performance"; it is a specific algorithmic pathology arising from the interaction between ambiguous grammar definitions and depth-first search (DFS) execution strategies.

### **2.1 The Mechanics of Catastrophic Backtracking**

The engines that STRling targets—specifically PCRE2, Python's re module, and the native RegExp engines of JavaScript environments—are fundamentally **backtracking engines**.5 These engines do not implement the theoretical $O(n)$ simulation of an NFA. Instead, they treat the regex pattern as a procedural script for a recursive search.

When the engine encounters a non-deterministic choice points—such as an alternation operator (|) or a quantifier (\*, \+, ?)—it must select a path to explore. It typically chooses greedily, consuming as much input as possible or selecting the first branch of an alternation. Crucially, the engine remembers this decision point. If the chosen path fails to match the subsequent portion of the input string, the engine _backtracks_: it unwinds its state to the most recent decision point and attempts the next available alternative.

**Vulnerability arises from Ambiguity.** A regular expression $R$ is strictly **ambiguous** if there exists at least one string $s$ in the language $L(R)$ for which there are multiple distinct derivations (parse trees).3 In the context of a backtracking engine, ambiguity translates directly into redundant search paths.

-   **Polynomial ReDoS**: This typically occurs when a pattern contains multiple, linearly arranged quantifiers that overlap in the strings they accept. For example, a\*a\* creates a situation where a string of $N$ 'a's can be partitioned between the first and second star in $N+1$ ways. The engine, upon failure, will try every possible partition, leading to $O(N^2)$ complexity.6
-   **Exponential ReDoS (The "Catastrophic" Case)**: This occurs when ambiguity is cyclic or nested. The canonical example is (a+)+. Here, the inner quantifier \+ and the outer quantifier \+ both operate on the character 'a'. For an input string of 'a's, the number of ways to partition the string into a sequence of non-empty substrings grows exponentially with the input length, specifically $2^{N-1}$ ways. If the matching fails at the end of the string (e.g., due to a mismatching character), the engine is forced to explore this entire exponential state space, resulting in effectively infinite runtime for relatively short inputs.6

Consequently, the core engineering challenge for the STRling linter is **Ambiguity Detection**. If we can statically prove that a pattern is unambiguous, or that its ambiguity is bounded (finite), we can guarantee safety. If the ambiguity is infinite (cyclic), the pattern is a ReDoS candidate.

### **2.2 The Limitations of Current Detection Tools**

The directive highlights a critical gap: existing tools are either too slow for an IDE or require dynamic execution. An analysis of the leading tool, **ReDoSHunter** 5, reveals why it is ill-suited for the STRling compiler.

ReDoSHunter operates through a "Hybrid" methodology:

1. **Static Identification**: It parses the regex and converts it into a generalized NFA. It then analyzes the graph structure to identify five specific vulnerability patterns, such as **Exponential Overlapping Adjacency (EOA)**, **Exponential Overlapping Disjunction (EOD)**, and **Nested Quantifiers (NQ)**.5
2. **Dynamic Validation**: Because the static analysis is conservative and prone to false positives, ReDoSHunter generates candidate "attack strings" based on the detected patterns and runs them against the actual regex engine to confirm the vulnerability.11

**Incompatibility with STRling's Goals:**

-   **Performance Overhead**: The construction of the NFA and the subsequent graph traversals (detecting cycles, checking reachability between cycles) can have high polynomial complexity in the size of the regex ($O(m^3)$ or worse). For large, complex patterns generated by STRling, this creates an unacceptable "stop-the-world" pause.16
-   **Dependency on Runtime**: The reliance on a dynamic validation step is structurally impossible for a pure static linter. We cannot execute code that is in the process of being written.
-   **Loss of Context**: By converting to an NFA, the analysis loses the connection to the high-level STRling constructs. An error pointing to "State 42" is meaningless to a user working with named groups and variables. The linter must report errors in terms of the user's code, e.g., "The group user_input contains a nested repetition."

This necessitates a different approach—one that is faster, purely static, and structure-preserving.

## ---

**3\. Theoretical Foundations of Derivative-Based Analysis**

The proposed solution lies in the realm of **Brzozowski Derivatives**, a concept dating back to 1964 but recently revitalized by advances in symbolic computation. This section establishes the theoretical rigor required to justify this architectural pivot.

### **3.1 The Algebra of Derivatives**

Unlike NFA construction, which is a graph-building process, differentiation is an **algebraic transformation** of the regular expression itself.

Definition: Let $R$ be a regular expression over an alphabet $\\Sigma$. The derivative of $R$ with respect to a symbol $a \\in \\Sigma$, denoted $\\partial\_a(R)$ (or $D\_a(R)$), is the set of suffixes of strings in $L(R)$ that start with $a$.

$$\\partial\_a(R) \= \\{ s \\mid as \\in L(R) \\}$$  
Crucially, this derivative can be computed symbolically using recursive rules, without enumerating strings 19:

-   $\\partial\_a(a) \= \\epsilon$ (The empty string, representing a successful match of the character).
-   $\\partial\_a(b) \= \\emptyset$ (where $a \\neq b$).
-   $\\partial\_a(R\_1 \\cdot R\_2) \= \\partial\_a(R\_1) \\cdot R\_2 \\cup \\nu(R\_1) \\cdot \\partial\_a(R\_2)$ (where $\\nu(R)$ is the "nullable" function, returning $\\epsilon$ if $R$ matches the empty string, else $\\emptyset$).
-   $\\partial\_a(R^\*) \= \\partial\_a(R) \\cdot R^\*$.
-   $\\partial\_a(R\_1 \\cup R\_2) \= \\partial\_a(R\_1) \\cup \\partial\_a(R\_2)$.
-   $\\partial\_a(R\_1 \\cap R\_2) \= \\partial\_a(R\_1) \\cap \\partial\_a(R\_2)$ (Intersection is handled naturally).
-   $\\partial\_a(\\neg R) \= \\neg \\partial\_a(R)$ (Complement is handled naturally).

The power of this approach lies in the fact that **the set of all unique derivatives of a regular expression corresponds to the states of its minimal Deterministic Finite Automaton (DFA)**.21

### **3.2 The Symbolic Breakthrough**

A historical limitation of Brzozowski derivatives was the handling of large alphabets (like Unicode). Computing $\\partial\_a(R)$ for every $a \\in \\Sigma$ is infeasible when $|\\Sigma| \= 1,114,112$ (Unicode).

Recent research, particularly the Symbolic Regex Matcher (SRM) and RE\# engine developed by Microsoft Research 1, introduced Symbolic Derivatives. instead of deriving with respect to concrete characters, we derive with respect to character predicates (sets).  
If a regex contains the character classes \[0-9\] and \[a-z\], we partition the alphabet into disjoint sets: $P\_1 \= \\{0..9\\}$, $P\_2 \= \\{a..z\\}$, and $P\_{rest} \= \\Sigma \\setminus (P\_1 \\cup P\_2)$. We then compute only three derivatives: $\\partial\_{P\_1}(R)$, $\\partial\_{P\_2}(R)$, and $\\partial\_{P\_{rest}}(R)$.  
This optimization is critical for STRling. It allows the linter to reason about broad classes of inputs (e.g., "any digit", "any whitespace") as single atomic units, keeping the branching factor of the analysis extremely low even for Unicode-heavy patterns.

### **3.3 Ambiguity Diagnosis via Derivatives**

The most significant theoretical alignment for ReDoS detection comes from the work of Sulzmann and Lu (2016) on **"Derivative-Based Diagnosis of Regular Expression Ambiguity"**.3 They demonstrated that derivatives can be used to explicitly track ambiguity.

Standard derivative construction simplifies expressions to avoid state explosion (e.g., $R \\cup R \\equiv R$). However, to detect ambiguity, we can disable this specific simplification.  
If we compute $\\partial\_a(R)$ and arrive at a term that looks like $E \\cup E$ (a union of identical terms), it implies that there are two distinct paths through the regex that match the character $a$ and lead to the same remaining requirement $E$.

-   If this $E \\cup E$ structure persists or grows as we continue to take derivatives (e.g., matching a loop), we have identified **infinite ambiguity**.
-   If the multiplicity of the terms grows exponentially (e.g., $E, E \\cup E, E \\cup E \\cup E \\cup E \\dots$), we have identified **Exponential Ambiguity**, the exact condition for Catastrophic Backtracking.

This provides a direct, algebraic method to detect ReDoS without building a graph. We simply explore the "derivative space" and watch for the accumulation of identical terms in the union operator.

## ---

**4\. Architectural Feasibility Study for STRling**

Having established the theory, we must now assess the practical engineering reality. Can this theoretical model be implemented within the constraints of the STRling compiler?

### **4.1 Structural Alignment with STRling IR**

The STRling Intermediate Representation (IR), as defined in core/ir.ts 27 and core/ir.py 28, is a hierarchical tree of nodes: IRSeq (sequence), IRAlt (alternation), IRQuant (quantifier), IRLit (literal), and IRClass (character class).

This structure is **isomorphic** to the algebraic terms used in derivative calculus.

-   IRAlt maps directly to the $\\cup$ operator.
-   IRSeq maps to concatenation $\\cdot$.
-   IRQuant maps to the Kleene star $^\*$.

This isomorphism means the "Derivative Scanner" does not need a complex translation layer. It can operate directly on the IR objects produced by the Compiler phase. This is a massive advantage over ReDoSHunter, which would require a dedicated "IR to NFA Graph" compiler, effectively duplicating the logic of the entire regex engine. The Derivative Scanner can reuse the existing IR classes, simply adding a derive(char_set) method to the base IROp class or implementing it as a visitor pattern.

### **4.2 Performance Analysis: The "Freezing" Constraint**

The core directive constraint is avoiding "freezing the IDE."

-   **Graph Analysis (ReDoSHunter)**: Worst-case complexity for NFA construction is linear in regex size, but the subsequent cycle analysis is super-linear. For large, nested patterns, the graph can become dense with $\\epsilon$-transitions, making cycle detection expensive ($O(V+E)$ for simple cycles, but path counting is harder).
-   **Derivative Analysis**: The worst-case complexity for constructing a full DFA via derivatives is exponential $O(2^m)$. **However**, for the purpose of _linting_, we do not need to construct the full DFA. We only need to explore the state space until we find a **cycle with ambiguity**.
    -   ReDoS cycles typically manifest very quickly (short loop bodies).
    -   We can impose a **Depth Limit** (e.g., 50 transitions) and a **State Limit** (e.g., 200 unique states).
    -   Research on RE\# shows that for real-world patterns, the derivative graph is surprisingly small.1

**Conclusion**: With strict resource budgets (state count limits), the derivative approach is **guaranteed to be fast**. Even if it aborts due to complexity limits, it fails gracefully ("Complexity Unknown") rather than hanging the process. The "Lazy" nature of derivative computation means we pay only for the states we visit, unlike graph analysis which pays for the whole graph upfront.

### **4.3 Handling The "Hard" Features**

Previous reports flagged Backreferences and Lookarounds as major hurdles.

Lookarounds ((?=...), (?\!...)):  
The derivative framework excels here. As shown in the RE\# papers 1, lookarounds are handled as Boolean constraints on the nullability of the derivative.

$$\\partial\_a(R\_1 (?= R\_2)) \= \\partial\_a(R\_1) \\cdot (?= \\partial\_a(R\_2))$$

This allows the linter to precisely analyze patterns with lookarounds, a notorious weak spot for NFA-based tools which often treat them as opaque or ignore them, leading to false negatives.  
Backreferences (\\1, \\k\<name\>):  
Backreferences render the language non-regular, theoretically breaking the DFA model. However, for a linter focusing on safety, we can use Abstract Interpretation.

-   **Strategy**: When the derivative scanner encounters a backreference \\1, it does not know the exact string matched. However, it knows the **structure** of Group 1\.
-   **Approximation**: We replace \\1 with the _underlying IR_ of Group 1\. If Group 1 is (a|b), we treat \\1 as (a|b).
-   **Implication**: This is an over-approximation. It effectively treats the backreference as a macro expansion. If (a+)\\1 is analyzed as (a+)(a+), and we detect ReDoS in the expanded form, it is a valid warning. While this might flag some safe patterns (false positives), it adheres to the "Safe-by-Default" principle. A pattern that relies on the specific runtime binding of a backreference to avoid ReDoS is likely fragile and arguably bad practice. The linter's advice to refactor it is sound guidance.

## ---

**5\. Specification: The Symbolic Ambiguity Inspector (SAI)**

Based on the feasibility findings, this section provides the architectural specification for the new linter component.

### **5.1 Architecture Overview**

The SAI is a standalone module within the core package. It is invoked by the Compiler after IR normalization but before Emission.

\[Parser\] \--\> \--\> \[Compiler\] \--\> \--+--\> \[Emitter\] \--\> \[Output\]  
|

|

### **5.2 Core Components**

#### **A. The Symbolic CharSet Engine**

A robust module for handling set algebra on Unicode characters.

-   **Responsibility**: To manage disjoint sets of characters efficiently.
-   **Implementation**: Use **Interval Trees** or **Binary Decision Diagrams (BDDs)** to represent sets like \[\\u0041-\\u005A\] or \\p{L}.
-   **API**:
    -   intersect(Set A, Set B) \-\> Set
    -   union(Set A, Set B) \-\> Set
    -   complement(Set A) \-\> Set
    -   is_empty(Set A) \-\> bool
    -   partition(List) \-\> List (Takes a list of interesting character classes from the regex and returns a list of disjoint basic sets that cover the alphabet).

#### **B. The Derivative Computer**

The engine that implements the algebraic rules.

-   **Input**: IRNode (current regex), CharSet (symbol to derive by).
-   **Output**: IRNode (the derivative).
-   **Normalization**: A critical sub-component. It must simplify the resulting IR to prevent state explosion.
    -   $R \\cdot \\epsilon \\to R$
    -   $R \\cdot \\emptyset \\to \\emptyset$
    -   $\\emptyset \\cdot R \\to \\emptyset$
    -   $(A \\cdot B) \\cdot C \\to A \\cdot (B \\cdot C)$ (Associativity normalization is vital for cycle detection).
-   **Ambiguity Preservation**: Unlike a standard matcher, the normalization **MUST NOT** simplify $A \\cup A \\to A$ if we are in "Ambiguity Detection Mode". Instead, it should tag the node as potentially ambiguous or maintain a multiplicity counter.

#### **C. The State Explorer (The "Linter")**

The driver loop that searches for ReDoS.

-   **Algorithm**: Breadth-First Search (BFS) over the derivative states.
-   **State Definition**: A State is defined by the normalized IRNode.
-   **Cycle Detection**: A hash map visited: Map\<IRNode, Metadata\>. If we encounter a node already in visited, we check the path.
-   **Heuristic**:
    -   If we traverse a loop $S\_1 \\to \\dots \\to S\_1$, and the "ambiguity counter" (multiplicity of terms) has increased, we flag **Exponential ReDoS**.
    -   If we traverse a loop and ambiguity exists but is constant, we flag **Polynomial ReDoS**.

### **5.3 Pseudocode Specification**

Python

class SAI:  
 def analyze(self, ir_root: IRNode) \-\> Report:  
 \# 1\. Extract all character classes mentioned in the pattern  
 relevant_sets \= self.extract_char_sets(ir_root)  
 \# 2\. Partition into disjoint sets (the "Symbolic Alphabet")  
 alphabet \= self.partition_sets(relevant_sets)

        worklist \= \[(ir\_root, 0)\] \# (Node, Depth)
        history \= {} \# Node \-\> (Depth, Multiplicity)

        while worklist:
            current\_node, depth \= worklist.pop(0)

            if depth \> MAX\_DEPTH: return Report.incomplete()
            if current\_node in history:
                \# Cycle found\! Check for ambiguity growth
                prev\_mult \= history\[current\_node\].multiplicity
                curr\_mult \= self.measure\_ambiguity(current\_node)

                if curr\_mult \> prev\_mult:
                    return Report.vulnerable("Exponential Ambiguity")
                elif curr\_mult \> 1:
                    return Report.warning("Polynomial Ambiguity")
                continue

            history\[current\_node\] \= Metadata(depth, self.measure\_ambiguity(current\_node))

            \# Explore transitions for each symbolic character set
            for char\_set in alphabet:
                next\_node \= self.derive(current\_node, char\_set)
                next\_node \= self.normalize(next\_node)

                if not next\_node.is\_empty():
                    worklist.append((next\_node, depth \+ 1))

        return Report.safe()

## ---

**6\. Comparative Analysis: Graph vs. Derivative**

The following comparison matrix summarizes the findings of this research directive, highlighting why the Derivative approach is the correct strategic choice for STRling.

| Feature                 | Graph Analysis (ReDoSHunter)                                    | Symbolic Derivatives (SAI)                                          |
| :---------------------- | :-------------------------------------------------------------- | :------------------------------------------------------------------ |
| **Primary Mechanism**   | Topological analysis of NFA graph                               | Algebraic transformation of IR tree                                 |
| **Analysis Latency**    | High (High upfront cost to build NFA)                           | **Low** (Lazy, on-demand exploration)                               |
| **Complexity Class**    | $O(V^3)$ or worse for cycle overlap analysis                    | Analysis is bounded by MAX_STATES budget                            |
| **Ambiguity Detection** | Inferential (deduced from graph cycles)                         | **Direct** (explicit redundant terms in algebra)                    |
| **Feature Support**     | Poor for Lookarounds/Backrefs (requires complex NFA extensions) | **Native** support for Lookarounds; safe approximation for Backrefs |
| **Code Structure**      | Destructive (NFA loses variable names)                          | **Preservative** (IR keeps variable names)                          |
| **Implementation Risk** | High (Complex graph algorithms, NFA conversion logic)           | Medium (Recursive functions, algebraic rules)                       |
| **Strategic Fit**       | Low (Legacy approach)                                           | **High** (Cutting-edge, "Principled Engineering")                   |

## ---

**7\. Implementation Roadmap**

To integrate the SAI without disrupting the current development velocity, we propose a phased implementation plan:

### **Phase 1: The Core Derivative Engine (Sprint 8\)**

-   **Goal**: Implement the mathematical machinery.
-   **Tasks**:
    -   Create core/derivative.ts.
    -   Implement derive(node, char_set) for all basic IROp types.
    -   Implement normalize(node) with basic simplifications ($R \\cdot \\epsilon$, etc.).
    -   **Deliverable**: A unit-tested module that can correctly compute the derivative of a regex like a\*b with respect to a.

### **Phase 2: Symbolic Sets & Ambiguity Tracking (Sprint 9\)**

-   **Goal**: Enable symbolic reasoning and ambiguity detection.
-   **Tasks**:
    -   Implement the CharSet engine (initially using simple range logic).
    -   Implement the BFS explorer with loop detection.
    -   Implement the "Ambiguity Counter" logic (detecting $R \\cup R$).
    -   **Deliverable**: A CLI flag \--check-redos that correctly flags (a+)+ as dangerous.

### **Phase 3: Integration & Tuning (Sprint 10\)**

-   **Goal**: Production readiness.
-   **Tasks**:
    -   Integrate SAI into the main Compiler pipeline (optional warning mode).
    -   Benchmark against the ReDoSHunter corpus to tune MAX_DEPTH and MAX_STATES for the sweet spot between performance and recall.
    -   Refine error messages to be user-centric (e.g., highlighting the specific variable causing the loop).
    -   **Deliverable**: A fully functional, "safe-by-default" linter enabled in the CI pipeline.

## **8\. Conclusion**

Research Directive 4 asked for a solution to detect ReDoS in milliseconds. The **Symbolic Ambiguity Inspector (SAI)**, built on the foundation of Brzozowski Derivatives, is that solution.

By rejecting the heavy, opaque legacy of graph-based NFA analysis and embracing the elegant, structured power of algebraic differentiation, STRling can provide developers with instant, high-fidelity feedback on the safety of their patterns. This approach is not merely an optimization; it is a declaration of intent. It signals that STRling is committed to **Principled Engineering**—solving hard problems not by throwing raw compute at them, but by applying the right mathematical abstractions.

**Recommendation**: Proceed immediately with Phase 1\. The implementation of the derivative engine will yield benefits beyond just linting, potentially opening doors for future features like pattern optimization and equivalence checking.

---

**Citations used in this report:**

-   19  
    : Brzozowski Derivatives definition and foundational theory.
-   1  
    : RE\# and the performance/correctness of Symbolic Derivatives.
-   3  
    : Sulzmann & Lu's work on "Derivative-Based Diagnosis of Regular Expression Ambiguity".
-   5  
    : ReDoSHunter mechanics and limitations.
-   16  
    : Complexity analysis of automata and regex.
-   27  
    : STRling IR structure files.

#### **Works cited**

1. RE\#: High Performance Derivative-Based Regex Matching with Intersection, Complement, and Restricted Lookarounds \- Microsoft Research, accessed December 28, 2025, [https://www.microsoft.com/en-us/research/publication/re-high-performance-derivative-based-regex-matching-with-intersection-complement-and-restricted-lookarounds/?locale=ko-kr](https://www.microsoft.com/en-us/research/publication/re-high-performance-derivative-based-regex-matching-with-intersection-complement-and-restricted-lookarounds/?locale=ko-kr)
2. RE\#: High Performance Derivative-Based Regex Matching with Intersection, Complement and Lookarounds \- arXiv, accessed December 28, 2025, [https://arxiv.org/html/2407.20479v1](https://arxiv.org/html/2407.20479v1)
3. Derivative-Based Diagnosis of Regular Expression Ambiguity | International Journal of Foundations of Computer Science \- World Scientific Publishing, accessed December 28, 2025, [https://www.worldscientific.com/doi/full/10.1142/S0129054117400068](https://www.worldscientific.com/doi/full/10.1142/S0129054117400068)
4. \[1604.06644\] Derivative-Based Diagnosis of Regular Expression Ambiguity \- arXiv, accessed December 28, 2025, [https://arxiv.org/abs/1604.06644](https://arxiv.org/abs/1604.06644)
5. ReDoSHunter: A Combined Static and Dynamic Approach for Regular Expression DoS Detection \- USENIX, accessed December 28, 2025, [https://www.usenix.org/system/files/sec21-li-yeting.pdf](https://www.usenix.org/system/files/sec21-li-yeting.pdf)
6. Regex Denial of Service (ReDoS): The Pattern That Freezes Your Server | by InstaTunnel, accessed December 28, 2025, [https://medium.com/@instatunnel/regex-denial-of-service-redos-the-pattern-that-freezes-your-server-843e6c035deb](https://medium.com/@instatunnel/regex-denial-of-service-redos-the-pattern-that-freezes-your-server-843e6c035deb)
7. Preventing Regular Expression Denial of Service (ReDoS), accessed December 28, 2025, [https://www.regular-expressions.info/redos.html](https://www.regular-expressions.info/redos.html)
8. Check if a regex is ambiguous \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/20604670/check-if-a-regex-is-ambiguous](https://stackoverflow.com/questions/20604670/check-if-a-regex-is-ambiguous)
9. Regular expression attack technique on ReDoS vulnerability, accessed December 28, 2025, [https://isj.vn/index.php/journal_STIS/article/view/1030](https://isj.vn/index.php/journal_STIS/article/view/1030)
10. Performance of Regular Expressions | by Maciek Rząsa | TextMaster Engineering \- Medium, accessed December 28, 2025, [https://medium.com/textmaster-engineering/performance-of-regular-expressions-81371f569698](https://medium.com/textmaster-engineering/performance-of-regular-expressions-81371f569698)
11. ReDoSHunter: A Combined Static and Dynamic Approach for Regular Expression DoS Detection | USENIX, accessed December 28, 2025, [https://www.usenix.org/conference/usenixsecurity21/presentation/li-yeting](https://www.usenix.org/conference/usenixsecurity21/presentation/li-yeting)
12. ReDoSHunter: A Combined Static and Dynamic Approach for Regular Expression DoS Detection \- GitHub, accessed December 28, 2025, [https://github.com/yetingli/ReDoSHunter](https://github.com/yetingli/ReDoSHunter)
13. Effective ReDoS Detection by Principled Vulnerability Modeling and Exploit Generation \- Cen Zhang, accessed December 28, 2025, [https://cenzhang.github.io/files/pubs/2023-ieeesp-rengar.pdf](https://cenzhang.github.io/files/pubs/2023-ieeesp-rengar.pdf)
14. ReDoSHunter: A Combined Static and Dynamic Approach for Regular Expression DoS Detection \- USENIX, accessed December 28, 2025, [https://www.usenix.org/system/files/sec21_slides_li-yeting.pdf](https://www.usenix.org/system/files/sec21_slides_li-yeting.pdf)
15. A Combined Static and Dynamic Approach for Regular Expression DoS Detection ReDoSHunter:一种动静态结合的 ReDoS 检测算法, accessed December 28, 2025, [http://www.is.cas.cn/ztzl2016/2021xsnh/2021hbzs/202108/W020210831373787012349.pdf](http://www.is.cas.cn/ztzl2016/2021xsnh/2021hbzs/202108/W020210831373787012349.pdf)
16. regular expressions \- Time complexity of derivative-based regex matchers, accessed December 28, 2025, [https://cstheory.stackexchange.com/questions/41939/time-complexity-of-derivative-based-regex-matchers](https://cstheory.stackexchange.com/questions/41939/time-complexity-of-derivative-based-regex-matchers)
17. What's the Time Complexity of Average Regex algorithms? \- Stack Overflow, accessed December 28, 2025, [https://stackoverflow.com/questions/5892115/whats-the-time-complexity-of-average-regex-algorithms](https://stackoverflow.com/questions/5892115/whats-the-time-complexity-of-average-regex-algorithms)
18. Repairing DoS Vulnerability of Real-World Regexes \- Tachio Terauchi, accessed December 28, 2025, [https://terauchi.w.waseda.jp/papers/sp22-remedy.pdf](https://terauchi.w.waseda.jp/papers/sp22-remedy.pdf)
19. Towards an Effective Method of ReDoS Detection for Non-backtracking Engines \- USENIX, accessed December 28, 2025, [https://www.usenix.org/system/files/usenixsecurity24-su-weihao.pdf](https://www.usenix.org/system/files/usenixsecurity24-su-weihao.pdf)
20. Brzozowski derivative \- Wikipedia, accessed December 28, 2025, [https://en.wikipedia.org/wiki/Brzozowski_derivative](https://en.wikipedia.org/wiki/Brzozowski_derivative)
21. Brzozowski Derivatives (aka WTF is a regex derivative?\!) \- YouTube, accessed December 28, 2025, [https://www.youtube.com/watch?v=s9EPoy9r-ok](https://www.youtube.com/watch?v=s9EPoy9r-ok)
22. Regular-expression derivatives reexamined \- Khoury College of Computer Sciences, accessed December 28, 2025, [https://www.khoury.northeastern.edu/home/turon/re-deriv.pdf](https://www.khoury.northeastern.edu/home/turon/re-deriv.pdf)
23. rockysnow7/rzozowski: A regex crate using Brzozowski derivatives. \- GitHub, accessed December 28, 2025, [https://github.com/rockysnow7/rzozowski](https://github.com/rockysnow7/rzozowski)
24. Using Brzozowski's derivatives method to construct a minimal DFA, accessed December 28, 2025, [https://cs.stackexchange.com/questions/66620/using-brzozowskis-derivatives-method-to-construct-a-minimal-dfa](https://cs.stackexchange.com/questions/66620/using-brzozowskis-derivatives-method-to-construct-a-minimal-dfa)
25. Symbolic Boolean Derivatives for Efficiently Solving Extended Regular Expression Constraints \- Microsoft, accessed December 28, 2025, [https://www.microsoft.com/en-us/research/wp-content/uploads/2020/08/MSR-TR-2020-25.pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2020/08/MSR-TR-2020-25.pdf)
26. arXiv:1604.06644v2 \[cs.FL\] 13 Jul 2016, accessed December 28, 2025, [https://arxiv.org/pdf/1604.06644](https://arxiv.org/pdf/1604.06644)
27. accessed December 31, 1969, uploaded:bindings/javascript/src/STRling/core/ir.ts
28. accessed December 31, 1969, uploaded:bindings/python/src/STRling/core/ir.py
