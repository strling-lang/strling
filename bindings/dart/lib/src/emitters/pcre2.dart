/// STRling PCRE2 Emitter
///
/// Transforms STRling IR into PCRE2-compatible regex strings.
/// Iron Law: Emitters are pure functions with signature emit(ir, flags) → string.

import '../core/parser.dart' show Flags;

/// Special characters that need escaping in PCRE2
const _literalSpecial = r'[\]^$.|?*+(){}';

/// Special characters inside character class
const _classSpecial = r'[\]^-';

/// Escape a literal string for use outside character classes
String _escapeLiteral(String s) {
  final buf = StringBuffer();
  for (final ch in s.split('')) {
    if (_literalSpecial.contains(ch)) {
      buf.write('\\');
    }
    buf.write(ch);
  }
  return buf.toString();
}

/// Escape a character for use inside character classes
String _escapeClassChar(String ch) {
  if (_classSpecial.contains(ch)) {
    return '\\$ch';
  }
  return ch;
}

/// PCRE2 Emitter class
class Pcre2Emitter {
  /// Emit PCRE2 pattern from IR
  ///
  /// [ir] is a Map representation of the STRling IR
  /// [flags] optional compilation flags
  /// Returns the compiled PCRE2 regex string
  String emit(Map<String, dynamic> ir, [Flags? flags]) {
    final irType = ir['ir'] as String;

    switch (irType) {
      case 'Lit':
        return _emitLit(ir);
      case 'Seq':
        return _emitSeq(ir);
      case 'Alt':
        return _emitAlt(ir);
      case 'Group':
        return _emitGroup(ir);
      case 'Quant':
        return _emitQuant(ir);
      case 'CharClass':
        return _emitCharClass(ir);
      case 'Anchor':
        return _emitAnchor(ir);
      case 'Dot':
        return '.';
      case 'Backref':
        return _emitBackref(ir);
      case 'Look':
        return _emitLook(ir);
      case 'Esc':
        return _emitEsc(ir);
      default:
        throw FormatException('Unknown IR type: $irType');
    }
  }

  String _emitLit(Map<String, dynamic> ir) {
    final value = ir['value'] as String;
    return _escapeLiteral(value);
  }

  String _emitSeq(Map<String, dynamic> ir) {
    final parts = ir['parts'] as List;
    return parts.map((p) => emit(p as Map<String, dynamic>)).join();
  }

  String _emitAlt(Map<String, dynamic> ir) {
    final branches = ir['branches'] as List;
    return branches.map((b) => emit(b as Map<String, dynamic>)).join('|');
  }

  String _emitGroup(Map<String, dynamic> ir) {
    final body = emit(ir['body'] as Map<String, dynamic>);
    final capturing = ir['capturing'] as bool? ?? false;
    final name = ir['name'] as String?;
    final atomic = ir['atomic'] as bool? ?? false;

    if (atomic) {
      return '(?>$body)';
    }
    if (name != null) {
      return '(?<$name>$body)';
    }
    if (capturing) {
      return '($body)';
    }
    return '(?:$body)';
  }

  String _emitQuant(Map<String, dynamic> ir) {
    final child = ir['child'] as Map<String, dynamic>;
    final min = ir['min'] as int;
    final max = ir['max'];
    final mode = ir['mode'] as String? ?? 'Greedy';

    var childStr = emit(child);

    // Wrap if needed (sequences, alternations, multi-char literals)
    final needsParens = _needsQuantifierParens(child, childStr);
    if (needsParens) {
      childStr = '(?:$childStr)';
    }

    // Build quantifier suffix
    String quantStr;
    if (max == 'Inf' || max == null) {
      if (min == 0) {
        quantStr = '*';
      } else if (min == 1) {
        quantStr = '+';
      } else {
        quantStr = '{$min,}';
      }
    } else if (min == max) {
      if (min == 0) {
        return ''; // Matches nothing, effectively empty
      } else if (min == 1) {
        quantStr = '';
      } else {
        quantStr = '{$min}';
      }
    } else if (min == 0 && max == 1) {
      quantStr = '?';
    } else {
      quantStr = '{$min,$max}';
    }

    // Add mode suffix
    if (mode == 'Lazy') {
      quantStr += '?';
    } else if (mode == 'Possessive') {
      quantStr += '+';
    }

    return '$childStr$quantStr';
  }

  bool _needsQuantifierParens(Map<String, dynamic> child, String childStr) {
    final irType = child['ir'] as String;
    switch (irType) {
      case 'Seq':
        return true;
      case 'Alt':
        return true;
      case 'Lit':
        return childStr.length > 1 && !childStr.startsWith('\\');
      case 'Quant':
        return true;
      default:
        return false;
    }
  }

  String _emitCharClass(Map<String, dynamic> ir) {
    final negated = ir['negated'] as bool? ?? false;
    final items = ir['items'] as List;

    // Single-item shorthand optimization
    if (items.length == 1) {
      final item = items[0] as Map<String, dynamic>;
      final itemIr = item['ir'] as String;
      
      if (itemIr == 'Esc') {
        final type = item['type'] as String;
        
        // Handle d, w, s with negation flipping
        if ('dws'.contains(type)) {
          if (negated) {
            return '\\${type.toUpperCase()}';
          }
          return '\\$type';
        }
        
        // Handle D, W, S
        if ('DWS'.contains(type)) {
          if (negated) {
            return '\\${type.toLowerCase()}';
          }
          return '\\$type';
        }
        
        // Handle \p{...} and \P{...}
        if (type == 'p' || type == 'P') {
          final prop = item['property'] as String?;
          if (prop != null) {
            final shouldNegate = negated != (type == 'P');
            final use = shouldNegate ? 'P' : 'p';
            return '\\$use{$prop}';
          }
        }
      }
    }

    // Build bracket class
    final parts = <String>[];
    var hasHyphen = false;

    for (final item in items) {
      final itemMap = item as Map<String, dynamic>;
      final itemIr = itemMap['ir'] as String;

      switch (itemIr) {
        case 'Char':
          final ch = itemMap['char'] as String;
          if (ch == '-') {
            hasHyphen = true;
          } else {
            parts.add(_escapeClassChar(ch));
          }
          break;
        case 'Range':
          final from = itemMap['from'] as String;
          final to = itemMap['to'] as String;
          parts.add('${_escapeClassChar(from)}-${_escapeClassChar(to)}');
          break;
        case 'Esc':
          final type = itemMap['type'] as String;
          final prop = itemMap['property'] as String?;
          if (prop != null) {
            parts.add('\\$type{$prop}');
          } else {
            parts.add('\\$type');
          }
          break;
      }
    }

    // Hyphen at start to avoid ambiguity
    final inner = hasHyphen ? '-${parts.join()}' : parts.join();
    return '[${negated ? '^' : ''}$inner]';
  }

  String _emitAnchor(Map<String, dynamic> ir) {
    final at = ir['at'] as String;
    switch (at) {
      case 'Start':
        return '^';
      case 'End':
        return r'$';
      case 'WordBoundary':
        return r'\b';
      case 'NotWordBoundary':
        return r'\B';
      case 'AbsoluteStart':
        return r'\A';
      case 'AbsoluteEnd':
        return r'\z';
      case 'EndBeforeFinalNewline':
        return r'\Z';
      default:
        throw FormatException('Unknown anchor type: $at');
    }
  }

  String _emitBackref(Map<String, dynamic> ir) {
    final byIndex = ir['byIndex'] as int?;
    final byName = ir['byName'] as String?;

    if (byName != null) {
      return '\\k<$byName>';
    }
    if (byIndex != null) {
      return '\\$byIndex';
    }
    throw FormatException('Backref must have byIndex or byName');
  }

  String _emitLook(Map<String, dynamic> ir) {
    final dir = ir['dir'] as String;
    final neg = ir['neg'] as bool? ?? false;
    final body = emit(ir['body'] as Map<String, dynamic>);

    if (dir == 'Ahead') {
      return neg ? '(?!$body)' : '(?=$body)';
    } else {
      return neg ? '(?<!$body)' : '(?<=$body)';
    }
  }

  String _emitEsc(Map<String, dynamic> ir) {
    final type = ir['type'] as String;
    final prop = ir['property'] as String?;

    if (prop != null) {
      return '\\$type{$prop}';
    }
    return '\\$type';
  }
}

/// Convenience function to emit PCRE2 from IR
String emitPcre2(Map<String, dynamic> ir, [Flags? flags]) {
  return Pcre2Emitter().emit(ir, flags);
}
