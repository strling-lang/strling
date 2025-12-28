import 'package:test/test.dart';
import 'package:strling/strling.dart';

/// E2E Tests - Black-box testing where DSL input produces a regex
/// that matches expected strings.
void main() {
  group('E2E Phone Number', () {
    test('matches valid formats', () {
      final regex = compileToRegex(r'^(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})$');
      final re = RegExp(regex);

      expect(re.hasMatch('555-123-4567'), isTrue);
      expect(re.hasMatch('555.123.4567'), isTrue);
      expect(re.hasMatch('555 123 4567'), isTrue);
      expect(re.hasMatch('5551234567'), isTrue);
    });

    test('rejects invalid formats', () {
      final regex = compileToRegex(r'^(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})$');
      final re = RegExp(regex);

      expect(re.hasMatch('55-123-4567'), isFalse);
      expect(re.hasMatch('555-12-4567'), isFalse);
      expect(re.hasMatch('555-123-456'), isFalse);
      expect(re.hasMatch('abc-def-ghij'), isFalse);
    });
  });

  group('E2E Email', () {
    test('matches valid formats', () {
      final regex = compileToRegex(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$');
      final re = RegExp(regex);

      expect(re.hasMatch('user@example.com'), isTrue);
      expect(re.hasMatch('test.user@domain.org'), isTrue);
    });

    test('rejects invalid formats', () {
      final regex = compileToRegex(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$');
      final re = RegExp(regex);

      expect(re.hasMatch('@example.com'), isFalse);
      expect(re.hasMatch('user@'), isFalse);
      expect(re.hasMatch('user@.com'), isFalse);
    });
  });

  group('E2E IPv4', () {
    test('matches valid addresses', () {
      final regex = compileToRegex(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$');
      final re = RegExp(regex);

      expect(re.hasMatch('192.168.1.1'), isTrue);
      expect(re.hasMatch('10.0.0.1'), isTrue);
      expect(re.hasMatch('255.255.255.255'), isTrue);
      expect(re.hasMatch('0.0.0.0'), isTrue);
    });

    test('rejects invalid addresses', () {
      final regex = compileToRegex(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$');
      final re = RegExp(regex);

      expect(re.hasMatch('192.168.1'), isFalse);
      expect(re.hasMatch('192.168.1.1.1'), isFalse);
      expect(re.hasMatch('192-168-1-1'), isFalse);
    });
  });

  group('E2E Hex Color', () {
    test('matches valid colors', () {
      final regex = compileToRegex(r'^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$');
      final re = RegExp(regex);

      expect(re.hasMatch('#ffffff'), isTrue);
      expect(re.hasMatch('#000000'), isTrue);
      expect(re.hasMatch('#ABC123'), isTrue);
      expect(re.hasMatch('#fff'), isTrue);
      expect(re.hasMatch('#F00'), isTrue);
    });

    test('rejects invalid colors', () {
      final regex = compileToRegex(r'^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$');
      final re = RegExp(regex);

      expect(re.hasMatch('ffffff'), isFalse);
      expect(re.hasMatch('#ffff'), isFalse);
      expect(re.hasMatch('#GGGGGG'), isFalse);
    });
  });

  group('E2E Date', () {
    test('matches valid dates', () {
      final regex = compileToRegex(r'^(\d{4})-(\d{2})-(\d{2})$');
      final re = RegExp(regex);

      expect(re.hasMatch('2024-01-15'), isTrue);
      expect(re.hasMatch('2000-12-31'), isTrue);
      expect(re.hasMatch('1999-06-30'), isTrue);
    });

    test('rejects invalid dates', () {
      final regex = compileToRegex(r'^(\d{4})-(\d{2})-(\d{2})$');
      final re = RegExp(regex);

      expect(re.hasMatch('24-01-15'), isFalse);
      expect(re.hasMatch('2024/01/15'), isFalse);
      expect(re.hasMatch('2024-1-15'), isFalse);
    });
  });

  group('E2E Lookahead', () {
    test('positive lookahead', () {
      final regex = compileToRegex('foo(?=bar)');
      final re = RegExp(regex);

      expect(re.hasMatch('foobar'), isTrue);
      expect(re.hasMatch('foobaz'), isFalse);
    });

    test('negative lookahead', () {
      final regex = compileToRegex('foo(?!bar)');
      final re = RegExp(regex);

      expect(re.hasMatch('foobaz'), isTrue);
    });
  });

  group('E2E Word Boundary', () {
    test('matches word boundaries', () {
      final regex = compileToRegex(r'\bword\b');
      final re = RegExp(regex);

      expect(re.hasMatch('word'), isTrue);
      expect(re.hasMatch('a word here'), isTrue);
      expect(re.hasMatch('sword'), isFalse);
      expect(re.hasMatch('wording'), isFalse);
    });
  });

  group('E2E Alternation', () {
    test('matches alternatives', () {
      final regex = compileToRegex(r'^(cat|dog|bird)$');
      final re = RegExp(regex);

      expect(re.hasMatch('cat'), isTrue);
      expect(re.hasMatch('dog'), isTrue);
      expect(re.hasMatch('bird'), isTrue);
      expect(re.hasMatch('cats'), isFalse);
      expect(re.hasMatch('fish'), isFalse);
    });
  });

  group('E2E Quantifiers', () {
    test('plus', () {
      final regex = compileToRegex(r'^a+$');
      final re = RegExp(regex);

      expect(re.hasMatch('a'), isTrue);
      expect(re.hasMatch('aa'), isTrue);
      expect(re.hasMatch('aaa'), isTrue);
      expect(re.hasMatch(''), isFalse);
      expect(re.hasMatch('b'), isFalse);
    });

    test('star', () {
      final regex = compileToRegex(r'^a*$');
      final re = RegExp(regex);

      expect(re.hasMatch(''), isTrue);
      expect(re.hasMatch('a'), isTrue);
      expect(re.hasMatch('aaa'), isTrue);
      expect(re.hasMatch('b'), isFalse);
    });

    test('optional', () {
      final regex = compileToRegex(r'^a?$');
      final re = RegExp(regex);

      expect(re.hasMatch(''), isTrue);
      expect(re.hasMatch('a'), isTrue);
      expect(re.hasMatch('aa'), isFalse);
    });

    test('exact', () {
      final regex = compileToRegex(r'^a{3}$');
      final re = RegExp(regex);

      expect(re.hasMatch('aaa'), isTrue);
      expect(re.hasMatch('a'), isFalse);
      expect(re.hasMatch('aa'), isFalse);
      expect(re.hasMatch('aaaa'), isFalse);
    });

    test('range', () {
      final regex = compileToRegex(r'^a{2,4}$');
      final re = RegExp(regex);

      expect(re.hasMatch('aa'), isTrue);
      expect(re.hasMatch('aaa'), isTrue);
      expect(re.hasMatch('aaaa'), isTrue);
      expect(re.hasMatch('a'), isFalse);
      expect(re.hasMatch('aaaaa'), isFalse);
    });

    test('atLeast', () {
      final regex = compileToRegex(r'^a{2,}$');
      final re = RegExp(regex);

      expect(re.hasMatch('aa'), isTrue);
      expect(re.hasMatch('aaa'), isTrue);
      expect(re.hasMatch(''), isFalse);
      expect(re.hasMatch('a'), isFalse);
    });
  });

  group('E2E Capture Groups', () {
    test('extracts captured groups', () {
      final regex = compileToRegex(r'^(\d{4})-(\d{2})-(\d{2})$');
      final re = RegExp(regex);
      final match = re.firstMatch('2024-12-25');

      expect(match, isNotNull);
      expect(match!.group(1), equals('2024'));
      expect(match.group(2), equals('12'));
      expect(match.group(3), equals('25'));
    });
  });
}

String compileToRegex(String dsl) {
  final result = Parser.parse(dsl);
  final ir = result.node.toIR();
  return Pcre2Emitter.emit(ir, result.flags);
}
