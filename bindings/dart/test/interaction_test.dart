import 'package:test/test.dart';
import 'package:strling/strling.dart';

/// Interaction Tests - Parser → Compiler → Emitter handoffs
///
/// This test suite validates the handoff between pipeline stages:
/// - Parser → Compiler: Ensures AST is correctly consumed
/// - Compiler → Emitter: Ensures IR is correctly transformed to regex
void main() {
  group('Parser → Compiler Handoff', () {
    test('SimpleLiteral', () {
      final result = Parser.parse('hello');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Lit'));
    });

    test('Quantifier', () {
      final result = Parser.parse('a+');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Quant'));
    });

    test('CharacterClass', () {
      final result = Parser.parse('[abc]');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('CharClass'));
    });

    test('CapturingGroup', () {
      final result = Parser.parse('(abc)');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Group'));
    });

    test('Alternation', () {
      final result = Parser.parse('a|b');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Alt'));
    });

    test('NamedGroup', () {
      final result = Parser.parse('(?<name>abc)');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Group'));
    });

    test('Lookahead', () {
      final result = Parser.parse('(?=abc)');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Look'));
    });

    test('Lookbehind', () {
      final result = Parser.parse('(?<=abc)');
      final ir = result.node.toIR();
      
      expect(ir['ir'], equals('Look'));
    });
  });

  group('Compiler → Emitter Handoff', () {
    test('SimpleLiteral', () {
      expect(compileToRegex('hello'), equals('hello'));
    });

    test('DigitShorthand', () {
      expect(compileToRegex(r'\d+'), equals(r'\d+'));
    });

    test('CharacterClass', () {
      expect(compileToRegex('[abc]'), equals('[abc]'));
    });

    test('CharacterClassRange', () {
      expect(compileToRegex('[a-z]'), equals('[a-z]'));
    });

    test('NegatedClass', () {
      expect(compileToRegex('[^abc]'), equals('[^abc]'));
    });

    test('QuantifierPlus', () {
      expect(compileToRegex('a+'), equals('a+'));
    });

    test('QuantifierStar', () {
      expect(compileToRegex('a*'), equals('a*'));
    });

    test('QuantifierOptional', () {
      expect(compileToRegex('a?'), equals('a?'));
    });

    test('QuantifierExact', () {
      expect(compileToRegex('a{3}'), equals('a{3}'));
    });

    test('QuantifierRange', () {
      expect(compileToRegex('a{2,5}'), equals('a{2,5}'));
    });

    test('QuantifierLazy', () {
      expect(compileToRegex('a+?'), equals('a+?'));
    });

    test('CapturingGroup', () {
      expect(compileToRegex('(abc)'), equals('(abc)'));
    });

    test('NonCapturingGroup', () {
      expect(compileToRegex('(?:abc)'), equals('(?:abc)'));
    });

    test('NamedGroup', () {
      expect(compileToRegex('(?<name>abc)'), equals('(?<name>abc)'));
    });

    test('Alternation', () {
      expect(compileToRegex('cat|dog'), equals('cat|dog'));
    });

    test('Anchors', () {
      expect(compileToRegex(r'^abc$'), equals(r'^abc$'));
    });

    test('PositiveLookahead', () {
      expect(compileToRegex('foo(?=bar)'), equals('foo(?=bar)'));
    });

    test('NegativeLookahead', () {
      expect(compileToRegex('foo(?!bar)'), equals('foo(?!bar)'));
    });

    test('PositiveLookbehind', () {
      expect(compileToRegex('(?<=foo)bar'), equals('(?<=foo)bar'));
    });

    test('NegativeLookbehind', () {
      expect(compileToRegex('(?<!foo)bar'), equals('(?<!foo)bar'));
    });
  });

  group('Semantic Edge Cases', () {
    test('test_semantic_duplicate_capture_group', () {
      expect(
        () => Parser.parse('(?<name>a)(?<name>b)'),
        throwsA(isA<STRlingParseError>()),
      );
    });

    test('test_semantic_ranges', () {
      // Invalid range [z-a] should produce an error
      expect(
        () => Parser.parse('[z-a]'),
        throwsA(isA<STRlingParseError>()),
      );
    });
  });

  group('Full Pipeline', () {
    test('PhoneNumber', () {
      final regex = compileToRegex(r'(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})');
      expect(regex, equals(r'(\d{3})[-. ]?(\d{3})[-. ]?(\d{4})'));
    });

    test('IPv4', () {
      final regex = compileToRegex(r'(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})');
      expect(regex, equals(r'(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})'));
    });
  });
}

String compileToRegex(String dsl) {
  final result = Parser.parse(dsl);
  final ir = result.node.toIR();
  return Pcre2Emitter.emit(ir, result.flags);
}
