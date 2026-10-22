"""Lossless builtin JSON type dispatch; all other values use jsonschema.

This is not a replacement schema validator: every keyword, traversal, reference,
and error still belongs to the canonical Draft 2020-12 implementation. No
instance, validation result, or evidence is cached. Extensions deliberately
return the canonical checker so custom type definitions cannot hit this path.
"""

from __future__ import annotations

import builtins

from jsonschema import Draft202012Validator
from jsonschema.validators import extend


_CANONICAL = Draft202012Validator.TYPE_CHECKER
_NAMES = frozenset(
    ("array", "boolean", "integer", "null", "number", "object", "string")
)
_BUILTINS = {
    list: frozenset(("array",)),
    bool: frozenset(("boolean",)),
    int: frozenset(("integer", "number")),
    builtins.type(None): frozenset(("null",)),
    dict: frozenset(("object",)),
    str: frozenset(("string",)),
}


class BuiltinJSONTypeChecker:
    """Preserve exact builtin semantics and canonical fallback/extension APIs."""

    __slots__ = ()

    def is_type(self, instance, type):
        if builtins.type(type) is str and type in _NAMES:
            instance_type = builtins.type(instance)
            accepted = _BUILTINS.get(instance_type)
            if accepted is not None:
                return type in accepted
            if instance_type is float:
                return type == "number" or (type == "integer" and instance.is_integer())
        return _CANONICAL.is_type(instance, type)

    def redefine(self, type, fn):
        return _CANONICAL.redefine(type, fn)

    def redefine_many(self, definitions=()):
        return _CANONICAL.redefine_many(definitions)

    def remove(self, *types):
        return _CANONICAL.remove(*types)


# No version registration, global monkeypatch, meta-schema mutation or keyword
# replacement. Production call sites must explicitly select this class.
BuiltinDraft202012Validator = extend(
    Draft202012Validator, type_checker=BuiltinJSONTypeChecker()
)
