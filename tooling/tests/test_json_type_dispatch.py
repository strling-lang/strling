from __future__ import annotations

import copy
import itertools
import unittest
from decimal import Decimal
from fractions import Fraction

from jsonschema import Draft202012Validator
from jsonschema.exceptions import UndefinedTypeCheck
from jsonschema.validators import validator_for

from tooling.json_type_dispatch import (
    BuiltinDraft202012Validator,
    BuiltinJSONTypeChecker,
)


class JsonTypeDispatchTests(unittest.TestCase):
    def test_exact_builtins_match_every_canonical_type(self):
        values = [None, False, True, 0, -1, 2**200, [], [0], {}, {"a": 0}, "", "x"]
        values.extend(
            [
                0.0,
                -0.0,
                1.0,
                -1.0,
                0.5,
                1e100,
                float("nan"),
                float("inf"),
                -float("inf"),
            ]
        )
        checker = BuiltinJSONTypeChecker()
        for value, name in itertools.product(
            values,
            ("array", "boolean", "integer", "null", "number", "object", "string"),
        ):
            with self.subTest(value=value, name=name):
                self.assertEqual(
                    Draft202012Validator.TYPE_CHECKER.is_type(value, name),
                    checker.is_type(value, name),
                )

    def test_nonbuiltin_values_use_exact_canonical_fallback(self):
        class Integer(int):
            pass

        class Real(float):
            pass

        class Text(str):
            pass

        class Mapping(dict):
            pass

        class Array(list):
            pass

        values = [
            Integer(3),
            Real(1),
            Real(0.5),
            Text("x"),
            Mapping(a=2),
            Array([1]),
            Decimal("1.5"),
            Fraction(3, 2),
            1 + 2j,
            (),
            set(),
            object(),
        ]
        checker = BuiltinJSONTypeChecker()
        for value, name in itertools.product(
            values,
            ("array", "boolean", "integer", "null", "number", "object", "string"),
        ):
            with self.subTest(value=value, name=name):
                self.assertEqual(
                    Draft202012Validator.TYPE_CHECKER.is_type(value, name),
                    checker.is_type(value, name),
                )

    def test_unknown_type_and_custom_type_name_preserve_errors(self):
        checker = BuiltinJSONTypeChecker()
        for value in (None, 1, [], object()):
            with self.assertRaises(UndefinedTypeCheck):
                checker.is_type(value, "not-a-json-type")

        class Name(str):
            pass

        self.assertTrue(checker.is_type(1, Name("integer")))

    def test_all_public_extensions_return_canonical_not_stale_dispatch(self):
        checker = BuiltinJSONTypeChecker()
        changed = checker.redefine(
            "integer", lambda checker, instance: instance == "new"
        )
        self.assertFalse(changed.is_type(1, "integer"))
        self.assertTrue(changed.is_type("new", "integer"))
        many = checker.redefine_many(
            {"number": lambda checker, instance: instance is None}
        )
        self.assertTrue(many.is_type(None, "number"))
        self.assertFalse(many.is_type(1, "number"))
        removed = checker.remove("integer")
        with self.assertRaises(UndefinedTypeCheck):
            removed.is_type(1, "integer")
        self.assertTrue(checker.is_type(1, "integer"))

    def test_original_registry_and_keywords_are_not_modified(self):
        self.assertIs(
            validator_for({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
            Draft202012Validator,
        )
        self.assertIsNot(BuiltinDraft202012Validator, Draft202012Validator)
        self.assertEqual(
            BuiltinDraft202012Validator.VALIDATORS, Draft202012Validator.VALIDATORS
        )
        self.assertEqual(
            BuiltinDraft202012Validator.META_SCHEMA, Draft202012Validator.META_SCHEMA
        )

    @staticmethod
    def errors(validator, value):
        def serialize(error):
            return (
                list(error.path),
                list(error.schema_path),
                error.validator,
                error.validator_value,
                error.message,
                [serialize(child) for child in error.context],
            )

        return [serialize(error) for error in validator.iter_errors(value)]

    def test_nested_all_keywords_error_order_paths_messages_and_context_match(self):
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": {
                "value": {
                    "oneOf": [
                        {"type": "integer", "minimum": 2, "maximum": 9},
                        {"type": "string", "pattern": "^[a-z]{2}$"},
                    ]
                }
            },
            "type": "object",
            "required": ["values", "flag"],
            "additionalProperties": False,
            "properties": {
                "values": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/value"},
                },
                "flag": {"type": "boolean"},
                "number": {"type": "number", "multipleOf": 2},
            },
        }
        original = copy.deepcopy(schema)
        canonical = Draft202012Validator(schema)
        candidate = BuiltinDraft202012Validator(schema)
        values = [
            None,
            [],
            {},
            {"values": [], "flag": 0},
            {"values": [1, 1.5, None, False, "AA"], "flag": "bad", "extra": 1},
            {"values": [2, "ab"], "flag": True, "number": 4},
            {"values": [3, 3], "flag": False, "number": 3},
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    self.errors(canonical, value), self.errors(candidate, value)
                )
        self.assertEqual(schema, original)

    def test_reused_validator_revalidates_mutated_instances(self):
        validator = BuiltinDraft202012Validator(
            {"type": "object", "properties": {"x": {"type": "integer"}}}
        )
        value = {"x": 1}
        self.assertEqual(list(validator.iter_errors(value)), [])
        value["x"] = False
        self.assertEqual(len(list(validator.iter_errors(value))), 1)
        value["x"] = 2
        self.assertEqual(list(validator.iter_errors(value)), [])


if __name__ == "__main__":
    unittest.main()
