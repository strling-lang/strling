"""Resolve shared certification membership from repository-owned policy data.

This module is also used by the immutable verifier. It contains no candidate
imports, execution, or filesystem access; candidate toolchain documents are data.
Profiles without a shared prefix retain their exact historical definition.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping


class ProfileCompositionError(ValueError):
    """Raised when canonical profile composition is malformed."""


def profile_prefix(policy: Mapping[str, object]) -> list[dict[str, object]]:
    """Return an independent copy of the mandatory repository-operation prefix."""

    if not isinstance(policy, Mapping):
        raise ProfileCompositionError("toolchain policy must be an object")
    prefix = policy.get("profile_prefix", [])
    if not isinstance(prefix, list) or any(
        not isinstance(member, dict)
        or set(member) != {"operation"}
        or not isinstance(member.get("operation"), str)
        or not member["operation"]
        for member in prefix
    ):
        raise ProfileCompositionError(
            "policy.profile_prefix must contain repository-operation memberships"
        )
    return deepcopy(prefix)


def resolve_profile(policy: Mapping[str, object], name: str) -> dict[str, object]:
    """Expand the shared prefix exactly once, without altering source policy."""

    if not isinstance(policy, Mapping):
        raise ProfileCompositionError("toolchain policy must be an object")
    profiles = policy.get("profiles")
    if not isinstance(profiles, dict) or not isinstance(profiles.get(name), dict):
        raise ProfileCompositionError(f"missing certification profile {name!r}")
    definition = deepcopy(profiles[name])
    members = definition.get("operations")
    if not isinstance(members, list):
        raise ProfileCompositionError(f"profile {name} must declare ordered operations")
    definition["operations"] = [*profile_prefix(policy), *members]
    return definition


def resolve_profiles(policy: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Resolve the full registry for deterministic membership and fingerprints."""

    if not isinstance(policy, Mapping):
        raise ProfileCompositionError("toolchain policy must be an object")
    profiles = policy.get("profiles")
    if not isinstance(profiles, dict):
        raise ProfileCompositionError("policy.profiles must be an object")
    return {name: resolve_profile(policy, name) for name in profiles}
