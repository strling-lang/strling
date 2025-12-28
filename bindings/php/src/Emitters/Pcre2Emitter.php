<?php

declare(strict_types=1);

namespace STRling\Emitters;

use STRling\Core\Nodes\{
    Node, Alternation, Sequence, Literal, Dot, Anchor, CharacterClass, Quantifier, Group, Backreference,
    Lookahead, NegativeLookahead, Lookbehind, NegativeLookbehind,
    ClassItem, Escape, Range, Flags
};

/**
 * STRling PCRE2 Emitter - IR to PCRE2 Pattern String
 *
 * Transforms STRling AST nodes into PCRE2-compatible regex pattern strings.
 */
class Pcre2Emitter
{
    /**
     * Emit a PCRE2 pattern string from an AST node.
     */
    public static function emit(Node $node, ?Flags $flags = null): string
    {
        $prefix = $flags ? self::emitFlagsPrefix($flags) : '';
        return $prefix . self::emitNode($node, '');
    }

    /**
     * Build the inline prefix form from flags, e.g. "(?imx)"
     */
    private static function emitFlagsPrefix(Flags $flags): string
    {
        $letters = '';
        if ($flags->ignoreCase) $letters .= 'i';
        if ($flags->multiline) $letters .= 'm';
        if ($flags->dotAll) $letters .= 's';
        if ($flags->unicode) $letters .= 'u';
        if ($flags->extended) $letters .= 'x';
        return $letters ? "(?{$letters})" : '';
    }

    private static function emitNode(Node $node, string $parentKind): string
    {
        if ($node instanceof Literal) {
            return self::escapeLiteral($node->value);
        }

        if ($node instanceof Dot) {
            return '.';
        }

        if ($node instanceof Anchor) {
            return match ($node->at) {
                'Start' => '^',
                'End' => '$',
                'WordBoundary' => '\\b',
                'NotWordBoundary' => '\\B',
                'AbsoluteStart' => '\\A',
                'EndBeforeFinalNewline' => '\\Z',
                'AbsoluteEnd' => '\\z',
                default => '',
            };
        }

        if ($node instanceof Backreference) {
            if ($node->name !== null) {
                return "\\k<{$node->name}>";
            }
            if ($node->index !== null) {
                return "\\{$node->index}";
            }
            return '';
        }

        if ($node instanceof CharacterClass) {
            return self::emitClass($node);
        }

        if ($node instanceof Sequence) {
            $parts = array_map(fn($p) => self::emitNode($p, 'Seq'), $node->parts);
            return implode('', $parts);
        }

        if ($node instanceof Alternation) {
            $branches = array_map(fn($b) => self::emitNode($b, 'Alt'), $node->alternatives);
            $body = implode('|', $branches);
            return in_array($parentKind, ['Seq', 'Quant'], true) ? "(?:{$body})" : $body;
        }

        if ($node instanceof Quantifier) {
            $childStr = self::emitNode($node->target, 'Quant');
            if (self::needsGroupForQuant($node->target)) {
                $childStr = "(?:{$childStr})";
            }
            return $childStr . self::emitQuantSuffix($node);
        }

        if ($node instanceof Group) {
            $open = self::emitGroupOpen($node);
            return $open . self::emitNode($node->body, 'Group') . ')';
        }

        if ($node instanceof Lookahead) {
            return '(?=' . self::emitNode($node->body, 'Look') . ')';
        }

        if ($node instanceof NegativeLookahead) {
            return '(?!' . self::emitNode($node->body, 'Look') . ')';
        }

        if ($node instanceof Lookbehind) {
            return '(?<=' . self::emitNode($node->body, 'Look') . ')';
        }

        if ($node instanceof NegativeLookbehind) {
            return '(?<!' . self::emitNode($node->body, 'Look') . ')';
        }

        throw new \RuntimeException('Emitter missing for ' . get_class($node));
    }

    private static function escapeLiteral(string $s): string
    {
        $toEscape = [' ', '#', '$', '&', '(', ')', '*', '+', '-', '.', '?', '[', '\\', ']', '^', '{', '|', '}', '~'];
        $result = '';
        
        for ($i = 0; $i < strlen($s); $i++) {
            $ch = $s[$i];
            if (in_array($ch, $toEscape, true) && $ch !== '-') {
                $result .= '\\' . $ch;
            } else {
                $result .= $ch;
            }
        }
        
        return $result;
    }

    private static function escapeClassChar(string $ch): string
    {
        if ($ch === '\\' || $ch === ']') {
            return '\\' . $ch;
        }
        if ($ch === '-') {
            return '\\-';
        }
        if ($ch === '^') {
            return '\\^';
        }
        if ($ch === "\n") return '\\n';
        if ($ch === "\r") return '\\r';
        if ($ch === "\t") return '\\t';
        if ($ch === "\f") return '\\f';
        if ($ch === "\v") return '\\v';

        $code = ord($ch);
        if ($code < 32 || ($code >= 127 && $code <= 159)) {
            return sprintf('\\x%02x', $code);
        }

        return $ch;
    }

    private static function emitClass(CharacterClass $cc): string
    {
        $items = $cc->members;

        // Single-item shorthand optimization
        if (count($items) === 1 && $items[0] instanceof Escape) {
            $esc = $items[0];
            $k = match ($esc->kind) {
                'digit' => 'd',
                'not-digit' => 'D',
                'word' => 'w',
                'not-word' => 'W',
                'space' => 's',
                'not-space' => 'S',
                default => null,
            };
            
            if ($k !== null) {
                if (in_array($k, ['d', 'w', 's'], true)) {
                    if ($cc->negated) {
                        return '\\' . strtoupper($k);
                    }
                    return '\\' . $k;
                }
                if (in_array($k, ['D', 'W', 'S'], true)) {
                    $base = strtolower($k);
                    return $cc->negated ? '\\' . $base : '\\' . $k;
                }
            }
        }

        // General case: build bracket class
        $parts = [];
        foreach ($items as $item) {
            if ($item instanceof Literal) {
                $parts[] = self::escapeClassChar($item->value);
            } elseif ($item instanceof Range) {
                $parts[] = self::escapeClassChar($item->from) . '-' . self::escapeClassChar($item->to);
            } elseif ($item instanceof Escape) {
                $k = match ($item->kind) {
                    'digit' => 'd',
                    'not-digit' => 'D',
                    'word' => 'w',
                    'not-word' => 'W',
                    'space' => 's',
                    'not-space' => 'S',
                    'property' => 'p',
                    'not-property' => 'P',
                    default => null,
                };
                if ($k !== null) {
                    $parts[] = '\\' . $k;
                }
            }
        }

        $inner = implode('', $parts);
        return '[' . ($cc->negated ? '^' : '') . $inner . ']';
    }

    private static function emitQuantSuffix(Quantifier $q): string
    {
        $min = $q->min;
        $max = $q->max;
        
        if ($min === 0 && $max === null) {
            $suffix = '*';
        } elseif ($min === 1 && $max === null) {
            $suffix = '+';
        } elseif ($min === 0 && $max === 1) {
            $suffix = '?';
        } elseif ($min === $max) {
            $suffix = "{{$min}}";
        } elseif ($max === null) {
            $suffix = "{{$min},}";
        } else {
            $suffix = "{{$min},{$max}}";
        }

        if ($q->lazy) {
            $suffix .= '?';
        } elseif ($q->possessive) {
            $suffix .= '+';
        }

        return $suffix;
    }

    private static function needsGroupForQuant(Node $child): bool
    {
        if ($child instanceof CharacterClass || $child instanceof Dot ||
            $child instanceof Group || $child instanceof Backreference ||
            $child instanceof Anchor) {
            return false;
        }
        if ($child instanceof Literal) {
            return strlen($child->value) > 1;
        }
        if ($child instanceof Alternation) {
            return true;
        }
        if ($child instanceof Sequence) {
            return count($child->parts) > 1;
        }
        return false;
    }

    private static function emitGroupOpen(Group $group): string
    {
        if ($group->atomic === true) {
            return '(?>';
        }
        if ($group->capturing) {
            if ($group->name !== null) {
                return "(?<{$group->name}>";
            }
            return '(';
        }
        return '(?:';
    }
}
