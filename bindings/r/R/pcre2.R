#' STRling PCRE2 Emitter - R Implementation
#'
#' Transforms STRling IR into PCRE2-compatible regex strings.
#' Iron Law: Emitters are pure functions with signature emit(ir, flags) → string.

# Special characters that need escaping in PCRE2 literals
LITERAL_SPECIAL <- "[\\]^$.|?*+(){}"

# Special characters inside character class
CLASS_SPECIAL <- "[\\]^-"

#' Check if character is in special set
contains_char <- function(str, ch) {
  grepl(ch, str, fixed = TRUE)
}

#' Escape a literal string for use outside character classes
escape_literal <- function(s) {
  chars <- strsplit(s, "")[[1]]
  result <- character(length(chars))
  for (i in seq_along(chars)) {
    ch <- chars[i]
    if (contains_char(LITERAL_SPECIAL, ch)) {
      result[i] <- paste0("\\", ch)
    } else {
      result[i] <- ch
    }
  }
  paste0(result, collapse = "")
}

#' Escape a character for use inside character classes
escape_class_char <- function(ch) {
  if (contains_char(CLASS_SPECIAL, ch)) {
    return(paste0("\\", ch))
  }
  ch
}

#' Emit PCRE2 pattern from IR
#'
#' @param ir IR representation (list from compile_ast)
#' @param flags Optional flags
#' @return Compiled PCRE2 regex string
#' @export
emit_pcre2 <- function(ir, flags = NULL) {
  ir_type <- ir$ir
  
  if (ir_type == "Lit") {
    return(emit_lit(ir))
  } else if (ir_type == "Seq") {
    return(emit_seq(ir))
  } else if (ir_type == "Alt") {
    return(emit_alt(ir))
  } else if (ir_type == "Group") {
    return(emit_group(ir))
  } else if (ir_type == "Quant") {
    return(emit_quant(ir))
  } else if (ir_type == "CharClass") {
    return(emit_char_class(ir))
  } else if (ir_type == "Anchor") {
    return(emit_anchor(ir))
  } else if (ir_type == "Dot") {
    return(".")
  } else if (ir_type == "Backref") {
    return(emit_backref(ir))
  } else if (ir_type == "Look") {
    return(emit_look(ir))
  } else if (ir_type == "Esc") {
    return(emit_esc(ir))
  } else {
    stop(paste("Unknown IR type:", ir_type))
  }
}

emit_lit <- function(ir) {
  escape_literal(ir$value)
}

emit_seq <- function(ir) {
  parts <- sapply(ir$parts, emit_pcre2)
  paste0(parts, collapse = "")
}

emit_alt <- function(ir) {
  branches <- sapply(ir$branches, emit_pcre2)
  paste0(branches, collapse = "|")
}

emit_group <- function(ir) {
  body <- emit_pcre2(ir$body)
  capturing <- isTRUE(ir$capturing)
  name <- ir$name
  atomic <- isTRUE(ir$atomic)
  
  if (atomic) {
    return(paste0("(?>", body, ")"))
  }
  if (!is.null(name)) {
    return(paste0("(?<", name, ">", body, ")"))
  }
  if (capturing) {
    return(paste0("(", body, ")"))
  }
  paste0("(?:", body, ")")
}

emit_quant <- function(ir) {
  child <- ir$child
  min_val <- ir$min
  max_val <- ir$max
  mode <- if (is.null(ir$mode)) "Greedy" else ir$mode
  
  child_str <- emit_pcre2(child)
  
  # Check if we need parentheses
  needs_parens <- needs_quantifier_parens(child, child_str)
  if (needs_parens) {
    child_str <- paste0("(?:", child_str, ")")
  }
  
  # Build quantifier suffix
  quant_str <- ""
  if (identical(max_val, "Inf") || is.null(max_val)) {
    if (min_val == 0) {
      quant_str <- "*"
    } else if (min_val == 1) {
      quant_str <- "+"
    } else {
      quant_str <- paste0("{", min_val, ",}")
    }
  } else if (min_val == max_val) {
    if (min_val == 0) {
      return("")  # Matches nothing
    } else if (min_val == 1) {
      quant_str <- ""
    } else {
      quant_str <- paste0("{", min_val, "}")
    }
  } else if (min_val == 0 && max_val == 1) {
    quant_str <- "?"
  } else {
    quant_str <- paste0("{", min_val, ",", max_val, "}")
  }
  
  # Add mode suffix
  if (mode == "Lazy") {
    quant_str <- paste0(quant_str, "?")
  } else if (mode == "Possessive") {
    quant_str <- paste0(quant_str, "+")
  }
  
  paste0(child_str, quant_str)
}

needs_quantifier_parens <- function(child, child_str) {
  ir_type <- child$ir
  if (ir_type == "Seq") return(TRUE)
  if (ir_type == "Alt") return(TRUE)
  if (ir_type == "Lit") {
    return(nchar(child_str) > 1 && !startsWith(child_str, "\\"))
  }
  if (ir_type == "Quant") return(TRUE)
  FALSE
}

emit_char_class <- function(ir) {
  negated <- isTRUE(ir$negated)
  items <- ir$items
  
  # Single-item shorthand optimization
  if (length(items) == 1) {
    item <- items[[1]]
    item_ir <- item$ir
    
    if (item_ir == "Esc") {
      type_val <- item$type
      
      # Handle d, w, s with negation flipping
      if (type_val %in% c("d", "w", "s")) {
        if (negated) {
          return(paste0("\\", toupper(type_val)))
        }
        return(paste0("\\", type_val))
      }
      
      # Handle D, W, S
      if (type_val %in% c("D", "W", "S")) {
        if (negated) {
          return(paste0("\\", tolower(type_val)))
        }
        return(paste0("\\", type_val))
      }
      
      # Handle \p{...} and \P{...}
      if (type_val %in% c("p", "P")) {
        prop <- item$property
        if (!is.null(prop)) {
          should_negate <- negated != (type_val == "P")
          use <- if (should_negate) "P" else "p"
          return(paste0("\\", use, "{", prop, "}"))
        }
      }
    }
  }
  
  # Build bracket class
  parts <- character(0)
  has_hyphen <- FALSE
  
  for (item in items) {
    item_ir <- item$ir
    
    if (item_ir == "Char") {
      ch <- item$char
      if (ch == "-") {
        has_hyphen <- TRUE
      } else {
        parts <- c(parts, escape_class_char(ch))
      }
    } else if (item_ir == "Range") {
      from <- item$from
      to <- item$to
      parts <- c(parts, paste0(escape_class_char(from), "-", escape_class_char(to)))
    } else if (item_ir == "Esc") {
      type_val <- item$type
      prop <- item$property
      if (!is.null(prop)) {
        parts <- c(parts, paste0("\\", type_val, "{", prop, "}"))
      } else {
        parts <- c(parts, paste0("\\", type_val))
      }
    }
  }
  
  # Hyphen at start to avoid ambiguity
  inner <- if (has_hyphen) paste0("-", paste0(parts, collapse = "")) else paste0(parts, collapse = "")
  neg <- if (negated) "^" else ""
  paste0("[", neg, inner, "]")
}

emit_anchor <- function(ir) {
  at <- ir$at
  if (at == "Start") return("^")
  if (at == "End") return("$")
  if (at == "WordBoundary") return("\\b")
  if (at == "NotWordBoundary") return("\\B")
  if (at == "AbsoluteStart") return("\\A")
  if (at == "AbsoluteEnd") return("\\z")
  if (at == "EndBeforeFinalNewline") return("\\Z")
  stop(paste("Unknown anchor type:", at))
}

emit_backref <- function(ir) {
  by_index <- ir$byIndex
  by_name <- ir$byName
  
  if (!is.null(by_name)) {
    return(paste0("\\k<", by_name, ">"))
  }
  if (!is.null(by_index)) {
    return(paste0("\\", by_index))
  }
  stop("Backref must have byIndex or byName")
}

emit_look <- function(ir) {
  dir <- ir$dir
  neg <- isTRUE(ir$neg)
  body <- emit_pcre2(ir$body)
  
  if (dir == "Ahead") {
    if (neg) {
      return(paste0("(?!", body, ")"))
    } else {
      return(paste0("(?=", body, ")"))
    }
  } else {
    if (neg) {
      return(paste0("(?<!", body, ")"))
    } else {
      return(paste0("(?<=", body, ")"))
    }
  }
}

emit_esc <- function(ir) {
  type_val <- ir$type
  prop <- ir$property
  
  if (!is.null(prop)) {
    return(paste0("\\", type_val, "{", prop, "}"))
  }
  paste0("\\", type_val)
}
