/// STRling Parser - Recursive Descent Parser for STRling DSL
///
/// Transforms STRling pattern syntax into AST nodes.

import '../nodes.dart';

/// Parse error with position information
class STRlingParseError implements Exception {
  final String message;
  final int position;
  final String source;
  final String? hint;

  STRlingParseError(this.message, this.position, this.source, [this.hint]);

  @override
  String toString() => 'STRlingParseError: $message at position $position';
}

/// Flags container
class Flags {
  bool ignoreCase;
  bool multiline;
  bool dotAll;
  bool unicode;
  bool extended;

  Flags({
    this.ignoreCase = false,
    this.multiline = false,
    this.dotAll = false,
    this.unicode = false,
    this.extended = false,
  });

  static Flags fromLetters(String letters) {
    final f = Flags();
    for (final ch in letters.toLowerCase().split('')) {
      switch (ch) {
        case 'i':
          f.ignoreCase = true;
          break;
        case 'm':
          f.multiline = true;
          break;
        case 's':
          f.dotAll = true;
          break;
        case 'u':
          f.unicode = true;
          break;
        case 'x':
          f.extended = true;
          break;
      }
    }
    return f;
  }

  Map<String, bool> toDict() => {
        'ignoreCase': ignoreCase,
        'multiline': multiline,
        'dotAll': dotAll,
        'unicode': unicode,
        'extended': extended,
      };
}

/// Cursor for tracking position in input
class _Cursor {
  final String text;
  int i = 0;
  bool extendedMode;
  int inClass = 0;

  _Cursor(this.text, {this.extendedMode = false});

  bool get eof => i >= text.length;

  String peek([int offset = 0]) {
    final j = i + offset;
    return j < text.length ? text[j] : '';
  }

  String take() {
    if (eof) return '';
    return text[i++];
  }

  bool match(String s) {
    if (i + s.length > text.length) return false;
    if (text.substring(i, i + s.length) == s) {
      i += s.length;
      return true;
    }
    return false;
  }

  void skipWsAndComments() {
    if (!extendedMode || inClass > 0) return;
    while (!eof) {
      final ch = peek();
      if (' \t\r\n'.contains(ch)) {
        i++;
        continue;
      }
      if (ch == '#') {
        while (!eof && !'\r\n'.contains(peek())) {
          i++;
        }
        continue;
      }
      break;
    }
  }
}

const _controlEscapes = {
  'n': '\n',
  'r': '\r',
  't': '\t',
  'f': '\f',
  'v': '\v',
};

/// Parser class
class Parser {
  late Flags flags;
  late String src;
  late _Cursor _cur;
  int _capCount = 0;
  final Set<String> _capNames = {};

  Parser(String text) {
    final result = _parseDirectives(text);
    flags = result.$1;
    src = result.$2;
    _cur = _Cursor(src, extendedMode: flags.extended);
  }

  (Flags, String) _parseDirectives(String text) {
    var flags = Flags();
    final flagsMatch = RegExp(r'^\s*%flags\s*([imsux,\[\]\s]*)').firstMatch(text);
    
    if (flagsMatch != null) {
      final flagStr = flagsMatch.group(1)!.toLowerCase().replaceAll(RegExp(r'[,\[\]\s]'), '');
      flags = Flags.fromLetters(flagStr);
      
      // Remove directive lines
      final lines = text.split('\n');
      final patternLines = <String>[];
      var inPattern = false;
      
      for (final line in lines) {
        final trimmed = line.trim();
        if (!inPattern && (trimmed.startsWith('%flags') || trimmed.isEmpty || trimmed.startsWith('#'))) {
          continue;
        }
        inPattern = true;
        patternLines.add(line);
      }
      text = patternLines.join('\n');
    }
    
    return (flags, text);
  }

  (Flags, Node) parse() {
    final node = _parseAlt();
    _cur.skipWsAndComments();
    
    if (!_cur.eof) {
      final ch = _cur.peek();
      if (ch == ')') {
        throw STRlingParseError("Unmatched ')'", _cur.i, src);
      }
      throw STRlingParseError('Unexpected trailing input', _cur.i, src);
    }
    
    return (flags, node);
  }

  Node _parseAlt() {
    _cur.skipWsAndComments();
    
    if (_cur.peek() == '|') {
      throw STRlingParseError('Alternation lacks left-hand side', _cur.i, src);
    }
    
    final branches = <Node>[_parseSeq()];
    _cur.skipWsAndComments();
    
    while (_cur.peek() == '|') {
      final pipePos = _cur.i;
      _cur.take();
      _cur.skipWsAndComments();
      
      if (_cur.eof || _cur.peek() == '|') {
        throw STRlingParseError('Alternation lacks right-hand side', pipePos, src);
      }
      
      branches.add(_parseSeq());
      _cur.skipWsAndComments();
    }
    
    return branches.length == 1 ? branches[0] : Alternation(branches);
  }

  Node _parseSeq() {
    final parts = <Node>[];
    
    while (true) {
      _cur.skipWsAndComments();
      final ch = _cur.peek();
      
      if ('*+?{'.contains(ch) && parts.isEmpty) {
        throw STRlingParseError('Invalid quantifier \'$ch\'', _cur.i, src);
      }
      
      if (ch.isEmpty || '|)'.contains(ch)) break;
      
      var atom = _parseAtom();
      atom = _parseQuantIfAny(atom);
      parts.add(atom);
    }
    
    if (parts.length == 1) return parts[0];
    return Sequence(parts);
  }

  Node _parseAtom() {
    _cur.skipWsAndComments();
    final ch = _cur.peek();
    
    if (ch == '.') {
      _cur.take();
      return Dot();
    }
    if (ch == '^') {
      _cur.take();
      return Anchor('Start');
    }
    if (ch == '\$') {
      _cur.take();
      return Anchor('End');
    }
    if (ch == '(') {
      return _parseGroupOrLook();
    }
    if (ch == '[') {
      return _parseCharClass();
    }
    if (ch == '\\') {
      return _parseEscapeAtom();
    }
    if (ch == ')') {
      throw STRlingParseError("Unmatched ')'", _cur.i, src);
    }
    
    return Literal(_cur.take());
  }

  Node _parseQuantIfAny(Node child) {
    final ch = _cur.peek();
    int? min;
    dynamic max;
    var greedy = true;
    var lazy = false;
    var possessive = false;
    
    if (ch == '*') {
      min = 0;
      max = null;
      _cur.take();
    } else if (ch == '+') {
      min = 1;
      max = null;
      _cur.take();
    } else if (ch == '?') {
      min = 0;
      max = 1;
      _cur.take();
    } else if (ch == '{') {
      final save = _cur.i;
      _cur.take();
      
      final m = _readIntOptional();
      if (m == null) {
        _cur.i = save;
        return child;
      }
      
      min = m;
      max = m;
      
      if (_cur.peek() == ',') {
        _cur.take();
        max = _readIntOptional();
      }
      
      if (_cur.peek() != '}') {
        throw STRlingParseError('Incomplete quantifier', _cur.i, src);
      }
      _cur.take();
    } else {
      return child;
    }
    
    if (child is Anchor) {
      throw STRlingParseError('Cannot quantify anchor', _cur.i, src);
    }
    
    final nxt = _cur.peek();
    if (nxt == '?') {
      greedy = false;
      lazy = true;
      _cur.take();
    } else if (nxt == '+') {
      greedy = false;
      possessive = true;
      _cur.take();
    }
    
    return Quantifier(
      target: child,
      min: min!,
      max: max,
      greedy: greedy,
      lazy: lazy,
      possessive: possessive,
    );
  }

  int? _readIntOptional() {
    var s = '';
    while (RegExp(r'\d').hasMatch(_cur.peek())) {
      s += _cur.take();
    }
    return s.isNotEmpty ? int.parse(s) : null;
  }

  Node _parseGroupOrLook() {
    _cur.take(); // consume '('
    
    if (_cur.match('?:')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated group', _cur.i, src);
      }
      return Group(capturing: false, body: body);
    }
    
    if (_cur.match('?<=')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated lookbehind', _cur.i, src);
      }
      return Lookaround(dir: 'Behind', neg: false, body: body);
    }
    
    if (_cur.match('?<!')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated lookbehind', _cur.i, src);
      }
      return Lookaround(dir: 'Behind', neg: true, body: body);
    }
    
    if (_cur.match('?<')) {
      var name = '';
      while (_cur.peek() != '>' && _cur.peek().isNotEmpty) {
        name += _cur.take();
      }
      if (!_cur.match('>')) {
        throw STRlingParseError('Unterminated group name', _cur.i, src);
      }
      if (_capNames.contains(name)) {
        throw STRlingParseError('Duplicate group name <$name>', _cur.i, src);
      }
      _capCount++;
      _capNames.add(name);
      
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated group', _cur.i, src);
      }
      return Group(capturing: true, body: body, name: name);
    }
    
    if (_cur.match('?>')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated atomic group', _cur.i, src);
      }
      return Group(capturing: false, body: body, atomic: true);
    }
    
    if (_cur.match('?=')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated lookahead', _cur.i, src);
      }
      return Lookaround(dir: 'Ahead', neg: false, body: body);
    }
    
    if (_cur.match('?!')) {
      final body = _parseAlt();
      if (!_cur.match(')')) {
        throw STRlingParseError('Unterminated lookahead', _cur.i, src);
      }
      return Lookaround(dir: 'Ahead', neg: true, body: body);
    }
    
    _capCount++;
    final body = _parseAlt();
    if (!_cur.match(')')) {
      throw STRlingParseError('Unterminated group', _cur.i, src);
    }
    return Group(capturing: true, body: body);
  }

  Node _parseCharClass() {
    _cur.take(); // consume '['
    _cur.inClass++;
    
    var neg = false;
    if (_cur.peek() == '^') {
      neg = true;
      _cur.take();
    }
    
    final members = <Node>[];
    
    while (!_cur.eof && _cur.peek() != ']') {
      if (_cur.peek() == '\\') {
        members.add(_parseClassEscape());
      } else {
        final ch = _cur.take();
        
        if (_cur.peek() == '-' && _cur.peek(1) != ']') {
          _cur.take(); // consume '-'
          final endCh = _cur.take();
          members.add(Range(from: ch, to: endCh));
        } else {
          members.add(Literal(ch));
        }
      }
    }
    
    if (_cur.eof) {
      throw STRlingParseError('Unterminated character class', _cur.i, src);
    }
    
    _cur.take(); // consume ']'
    _cur.inClass--;
    
    return CharacterClass(negated: neg, members: members);
  }

  Node _parseClassEscape() {
    final startPos = _cur.i;
    _cur.take(); // consume '\'
    
    final nxt = _cur.peek();
    
    if ('dDwWsS'.contains(nxt)) {
      final kind = switch (_cur.take()) {
        'd' => 'digit',
        'D' => 'not-digit',
        'w' => 'word',
        'W' => 'not-word',
        's' => 'space',
        'S' => 'not-space',
        _ => throw StateError('Unexpected'),
      };
      return Escape(kind);
    }
    
    if (nxt == 'p' || nxt == 'P') {
      final tp = _cur.take();
      if (!_cur.match('{')) {
        throw STRlingParseError("Expected '{' after \\p/\\P", startPos, src);
      }
      var prop = '';
      while (_cur.peek() != '}' && _cur.peek().isNotEmpty) {
        prop += _cur.take();
      }
      if (!_cur.match('}')) {
        throw STRlingParseError('Unterminated \\p{...}', startPos, src);
      }
      return UnicodeProperty(value: prop, negated: tp == 'P');
    }
    
    if (_controlEscapes.containsKey(nxt)) {
      _cur.take();
      return Literal(_controlEscapes[nxt]!);
    }
    
    if (nxt == 'b') {
      _cur.take();
      return Literal('\x08');
    }
    
    if (nxt == '0') {
      _cur.take();
      return Literal('\x00');
    }
    
    return Literal(_cur.take());
  }

  Node _parseEscapeAtom() {
    final startPos = _cur.i;
    _cur.take(); // consume '\'
    
    final nxt = _cur.peek();
    
    if (RegExp(r'\d').hasMatch(nxt) && nxt != '0') {
      var num = 0;
      while (RegExp(r'\d').hasMatch(_cur.peek())) {
        num = num * 10 + int.parse(_cur.take());
        if (num > _capCount) {
          throw STRlingParseError('Backreference to undefined group \\$num', startPos, src);
        }
      }
      return Backreference(index: num);
    }
    
    if (nxt == 'b') {
      _cur.take();
      return Anchor('WordBoundary');
    }
    if (nxt == 'B') {
      _cur.take();
      return Anchor('NotWordBoundary');
    }
    if (nxt == 'A') {
      _cur.take();
      return Anchor('AbsoluteStart');
    }
    if (nxt == 'Z') {
      _cur.take();
      return Anchor('EndBeforeFinalNewline');
    }
    
    if (nxt == 'k') {
      _cur.take();
      if (!_cur.match('<')) {
        throw STRlingParseError("Expected '<' after \\k", startPos, src);
      }
      var name = '';
      while (_cur.peek() != '>' && _cur.peek().isNotEmpty) {
        name += _cur.take();
      }
      if (!_cur.match('>')) {
        throw STRlingParseError('Unterminated named backref', startPos, src);
      }
      if (!_capNames.contains(name)) {
        throw STRlingParseError('Backreference to undefined group <$name>', startPos, src);
      }
      return Backreference(name: name);
    }
    
    if ('dDwWsS'.contains(nxt)) {
      final kind = switch (_cur.take()) {
        'd' => 'digit',
        'D' => 'not-digit',
        'w' => 'word',
        'W' => 'not-word',
        's' => 'space',
        'S' => 'not-space',
        _ => throw StateError('Unexpected'),
      };
      return CharacterClass(negated: false, members: [Escape(kind)]);
    }
    
    if (nxt == 'p' || nxt == 'P') {
      final tp = _cur.take();
      if (!_cur.match('{')) {
        throw STRlingParseError("Expected '{' after \\p/\\P", startPos, src);
      }
      var prop = '';
      while (_cur.peek() != '}' && _cur.peek().isNotEmpty) {
        prop += _cur.take();
      }
      if (!_cur.match('}')) {
        throw STRlingParseError('Unterminated \\p{...}', startPos, src);
      }
      return CharacterClass(negated: false, members: [UnicodeProperty(value: prop, negated: tp == 'P')]);
    }
    
    if (_controlEscapes.containsKey(nxt)) {
      _cur.take();
      return Literal(_controlEscapes[nxt]!);
    }
    
    if (nxt == 'x') {
      _cur.take();
      return Literal(_parseHexEscape(startPos));
    }
    
    if (nxt == 'u' || nxt == 'U') {
      return Literal(_parseUnicodeEscape(startPos));
    }
    
    if (nxt == '0') {
      _cur.take();
      return Literal('\x00');
    }
    
    return Literal(_cur.take());
  }

  String _parseHexEscape(int startPos) {
    if (_cur.match('{')) {
      var hex = '';
      while (RegExp(r'[0-9A-Fa-f]').hasMatch(_cur.peek())) {
        hex += _cur.take();
      }
      if (!_cur.match('}')) {
        throw STRlingParseError('Unterminated \\x{...}', startPos, src);
      }
      return String.fromCharCode(int.parse(hex.isEmpty ? '0' : hex, radix: 16));
    }
    
    final h1 = _cur.take();
    final h2 = _cur.take();
    if (!RegExp(r'[0-9A-Fa-f]').hasMatch(h1) || !RegExp(r'[0-9A-Fa-f]').hasMatch(h2)) {
      throw STRlingParseError('Invalid \\xHH escape', startPos, src);
    }
    return String.fromCharCode(int.parse(h1 + h2, radix: 16));
  }

  String _parseUnicodeEscape(int startPos) {
    final tp = _cur.take();
    
    if (tp == 'u' && _cur.match('{')) {
      var hex = '';
      while (RegExp(r'[0-9A-Fa-f]').hasMatch(_cur.peek())) {
        hex += _cur.take();
      }
      if (!_cur.match('}')) {
        throw STRlingParseError('Unterminated \\u{...}', startPos, src);
      }
      return String.fromCharCode(int.parse(hex.isEmpty ? '0' : hex, radix: 16));
    }
    
    if (tp == 'u') {
      var hex = '';
      for (var i = 0; i < 4; i++) {
        hex += _cur.take();
      }
      if (!RegExp(r'^[0-9A-Fa-f]{4}$').hasMatch(hex)) {
        throw STRlingParseError('Invalid \\uHHHH escape', startPos, src);
      }
      return String.fromCharCode(int.parse(hex, radix: 16));
    }
    
    if (tp == 'U') {
      var hex = '';
      for (var i = 0; i < 8; i++) {
        hex += _cur.take();
      }
      if (!RegExp(r'^[0-9A-Fa-f]{8}$').hasMatch(hex)) {
        throw STRlingParseError('Invalid \\UHHHHHHHH escape', startPos, src);
      }
      return String.fromCharCode(int.parse(hex, radix: 16));
    }
    
    throw STRlingParseError('Invalid unicode escape', startPos, src);
  }
}

/// Parse a DSL string into flags and AST
(Flags, Node) parse(String src) {
  final parser = Parser(src);
  return parser.parse();
}
