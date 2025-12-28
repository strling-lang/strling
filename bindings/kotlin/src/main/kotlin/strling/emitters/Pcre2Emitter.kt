package strling.emitters

import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
import strling.core.*

/**
 * STRling PCRE2 Emitter - IR to PCRE2 Pattern String
 *
 * This class implements the emitter that transforms STRling's Intermediate
 * Representation (IR) into PCRE2-compatible regex pattern strings.
 */
object Pcre2Emitter {
    
    /**
     * Escapes PCRE2 metacharacters in literal strings.
     */
    fun escapeLiteral(s: String): String {
        val metaChars = setOf('.', '^', '$', '|', '(', ')', '?', '*', '+', '{', '}', '[', ']', '\\')
        val result = StringBuilder()
        
        for (ch in s) {
            if (ch in metaChars) {
                result.append('\\').append(ch)
            } else {
                result.append(ch)
            }
        }
        
        return result.toString()
    }
    
    /**
     * Escapes a character for use inside [...] per PCRE2 rules.
     */
    fun escapeClassChar(ch: String): String {
        if (ch.length != 1) {
            throw IllegalArgumentException("escapeClassChar expects single character")
        }
        
        val c = ch[0]
        return when (c) {
            '\\', ']' -> "\\$c"
            '[' -> "\\["
            '-' -> "\\-"
            '^' -> "\\^"
            '\n' -> "\\n"
            '\r' -> "\\r"
            '\t' -> "\\t"
            '\u000C' -> "\\f"
            '\u000B' -> "\\v"
            else -> {
                val code = c.code
                when {
                    code < 32 || (code in 127..159) -> String.format("\\x%02x", code)
                    else -> ch
                }
            }
        }
    }
    
    /**
     * Emit a PCRE2 character class.
     */
    private fun emitClass(cc: IRCharClass): String {
        val items = cc.items
        
        // Single-item shorthand optimization
        if (items.size == 1 && items[0] is IRClassEscape) {
            val esc = items[0] as IRClassEscape
            val k = esc.type
            val prop = esc.property
            
            when (k) {
                "d", "w", "s" -> {
                    if (cc.negated) {
                        return when (k) {
                            "d" -> "\\D"
                            "w" -> "\\W"
                            "s" -> "\\S"
                            else -> "\\$k"
                        }
                    }
                    return "\\$k"
                }
                "D", "W", "S" -> {
                    val base = k.lowercase()
                    return if (cc.negated) "\\$base" else "\\$k"
                }
                "p", "P" -> {
                    if (prop != null) {
                        val isUpperP = k == "P"
                        val useUpperP = cc.negated xor isUpperP
                        val use = if (useUpperP) "P" else "p"
                        return "\\$use{$prop}"
                    }
                }
            }
        }
        
        // General case: build a bracket class
        val parts = StringBuilder()
        for (item in items) {
            when (item) {
                is IRClassLiteral -> {
                    parts.append(escapeClassChar(item.char))
                }
                is IRClassRange -> {
                    parts.append(escapeClassChar(item.from))
                    parts.append('-')
                    parts.append(escapeClassChar(item.to))
                }
                is IRClassEscape -> {
                    when {
                        item.type.matches(Regex("[dDwWsS]")) -> {
                            parts.append('\\').append(item.type)
                        }
                        (item.type == "p" || item.type == "P") && item.property != null -> {
                            parts.append('\\').append(item.type).append('{').append(item.property).append('}')
                        }
                        else -> {
                            parts.append('\\').append(item.type)
                        }
                    }
                }
            }
        }
        
        val inner = parts.toString()
        return "[" + (if (cc.negated) "^" else "") + inner + "]"
    }
    
    /**
     * Emit quantifier suffix.
     */
    private fun emitQuantSuffix(minv: Int, maxv: Any, mode: String): String {
        val q = when {
            minv == 0 && maxv == "Inf" -> "*"
            minv == 1 && maxv == "Inf" -> "+"
            minv == 0 && maxv == 1 -> "?"
            minv == maxv -> "{$minv}"
            maxv == "Inf" -> "{$minv,}"
            else -> "{$minv,$maxv}"
        }
        
        return when (mode) {
            "Lazy" -> "$q?"
            "Possessive" -> "$q+"
            else -> q
        }
    }
    
    /**
     * Return true if 'child' needs a non-capturing group when quantifying.
     */
    private fun needsGroupForQuant(child: IROp): Boolean {
        return when (child) {
            is IRCharClass, is IRDot, is IRGroup, is IRBackref, is IRAnchor -> false
            is IRLit -> {
                // Single escape sequences don't need grouping
                if (child.value.length == 2 && child.value[0] == '\\') false
                else child.value.length > 1
            }
            is IRAlt, is IRLook -> true
            is IRSeq -> child.parts.size > 1
            else -> false
        }
    }
    
    /**
     * Generate opening for group based on type.
     */
    private fun emitGroupOpen(g: IRGroup): String {
        return when {
            g.atomic == true -> "(?>"
            g.capturing -> {
                if (g.name != null) "(?<${g.name}>"
                else "("
            }
            else -> "(?:"
        }
    }
    
    /**
     * Emit a single IR node to PCRE2 syntax.
     */
    private fun emitNode(node: IROp, parentKind: String): String {
        return when (node) {
            is IRLit -> escapeLiteral(node.value)
            is IRDot -> "."
            is IRAnchor -> {
                val at = if (node.at == "NonWordBoundary") "NotWordBoundary" else node.at
                when (at) {
                    "Start" -> "^"
                    "End" -> "$"
                    "WordBoundary" -> "\\b"
                    "NotWordBoundary" -> "\\B"
                    "AbsoluteStart" -> "\\A"
                    "EndBeforeFinalNewline" -> "\\Z"
                    "AbsoluteEnd" -> "\\z"
                    else -> ""
                }
            }
            is IRBackref -> {
                when {
                    node.byName != null -> "\\k<${node.byName}>"
                    node.byIndex != null -> "\\${node.byIndex}"
                    else -> ""
                }
            }
            is IRCharClass -> emitClass(node)
            is IRSeq -> {
                node.parts.joinToString("") { emitNode(it, "Seq") }
            }
            is IRAlt -> {
                val body = node.branches.joinToString("|") { emitNode(it, "Alt") }
                if (parentKind in listOf("Seq", "Quant")) "(?:$body)" else body
            }
            is IRQuant -> {
                var childStr = emitNode(node.child, "Quant")
                if (needsGroupForQuant(node.child) && node.child !is IRGroup) {
                    childStr = "(?:$childStr)"
                }
                
                // Parse max value from JsonElement
                val maxVal: Any = when {
                    node.max.toString() == "\"Inf\"" -> "Inf"
                    node.max is JsonPrimitive -> {
                        val jp = node.max as JsonPrimitive
                        jp.intOrNull ?: jp.content
                    }
                    else -> node.max.toString().replace("\"", "")
                }
                
                childStr + emitQuantSuffix(node.min, maxVal, node.mode)
            }
            is IRGroup -> {
                emitGroupOpen(node) + emitNode(node.body, "Group") + ")"
            }
            is IRLook -> {
                val op = when {
                    node.dir == "Ahead" && !node.neg -> "?="
                    node.dir == "Ahead" && node.neg -> "?!"
                    node.dir == "Behind" && !node.neg -> "?<="
                    node.dir == "Behind" && node.neg -> "?<!"
                    else -> "?="
                }
                "($op${emitNode(node.body, "Look")})"
            }
        }
    }
    
    /**
     * Build the inline prefix form for flags.
     */
    private fun emitPrefixFromFlags(flags: Flags): String {
        val letters = StringBuilder()
        if (flags.ignoreCase) letters.append('i')
        if (flags.multiline) letters.append('m')
        if (flags.dotAll) letters.append('s')
        if (flags.unicode) letters.append('u')
        if (flags.extended) letters.append('x')
        
        return if (letters.isNotEmpty()) "(?$letters)" else ""
    }
    
    /**
     * Emit a PCRE2 pattern string from IR.
     */
    fun emit(irRoot: IROp, flags: Flags? = null): String {
        val prefix = if (flags != null) emitPrefixFromFlags(flags) else ""
        val body = emitNode(irRoot, "")
        return prefix + body
    }
}
