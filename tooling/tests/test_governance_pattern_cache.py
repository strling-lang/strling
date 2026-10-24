"""A compiled-pattern cache must never cache governance decisions or files."""

import unittest
from unittest.mock import patch

from tooling import governance as g


class PatternCacheTests(unittest.TestCase):
    def setUp(self):
        if hasattr(g.compile_path_pattern, "cache_clear"):
            g.compile_path_pattern.cache_clear()

    tearDown = setUp

    def test_repeated_pattern_compiles_once_but_validates_each_concrete_path(self):
        with patch.object(g.re, "compile", wraps=g.re.compile) as compile_regex:
            with patch.object(
                g, "normalize_repository_path", wraps=g.normalize_repository_path
            ) as normalize:
                self.assertTrue(g.path_matches("docs/a.md", "docs/**"))
                self.assertTrue(g.path_matches("docs/b.md", "docs/**"))
                self.assertEqual(compile_regex.call_count, 1)
                self.assertEqual(
                    normalize.call_args_list.count(unittest.mock.call("docs/a.md")), 1
                )
                self.assertEqual(
                    normalize.call_args_list.count(unittest.mock.call("docs/b.md")), 1
                )
                for path in ("/docs/a.md", "docs/../a.md", "docs\\a.md"):
                    with self.subTest(path=path), self.assertRaises(g.GovernanceError):
                        g.path_matches(path, "docs/**")

    def test_matching_examples_are_unchanged_on_cold_and_warm_entries(self):
        cases = [
            ("a.md", "**/*.md", True),
            ("docs/deep/a.md", "**/*.md", True),
            ("docs/deep/a.md", "docs/*.md", False),
            ("Docs/a.md", "docs/**", False),
            ("v7/x", "v[0-9]/*", True),
            ("va/x", "v[!0-9]/*", True),
            ("v7/x", "v[!0-9]/*", False),
            ("ab/x", "a?/*", True),
            ("a/b/x", "a?/*", False),
            ("a+b.txt", "a+b.txt", True),
            ("ab.txt", "a+b.txt", False),
        ]
        for _ in range(2):
            for path, pattern, expected in cases:
                with self.subTest(path=path, pattern=pattern):
                    self.assertEqual(g.path_matches(path, pattern), expected)

    def test_failed_patterns_are_never_cached_as_success(self):
        for pattern in ("", "../x", "/x", "x\\y", "a[", "a[]", "a[.]", "a//b"):
            for _ in range(2):
                with (
                    self.subTest(pattern=pattern),
                    self.assertRaises(g.GovernanceError),
                ):
                    g.compile_path_pattern(pattern)
        self.assertEqual(g.compile_path_pattern.cache_info().currsize, 0)

    def test_bounded_eviction_recompiles_without_changing_matching(self):
        with patch.object(g.re, "compile", wraps=g.re.compile) as compile_regex:
            for index in range(513):
                self.assertTrue(g.path_matches(f"d{index}/a", f"d{index}/*"))
            info = g.compile_path_pattern.cache_info()
            self.assertEqual((info.maxsize, info.currsize), (512, 512))
            self.assertTrue(g.path_matches("d0/b", "d0/*"))
            self.assertEqual(compile_regex.call_count, 514)
            self.assertFalse(g.path_matches("d0/deep/b", "d0/*"))
            self.assertEqual(compile_regex.call_count, 514)
        g.compile_path_pattern.cache_clear()
        self.assertEqual(g.compile_path_pattern.cache_info().currsize, 0)
        self.assertTrue(g.path_matches("d0/b", "d0/*"))


if __name__ == "__main__":
    unittest.main()
