"""Sanitizer into the strict JSON-schema subset, and the investigator output format (011 R1, R2)."""

import copy
from collections.abc import Iterator, Mapping
from functools import cache
from typing import Final, cast

from plant_monitor.domain.proposals import InvestigatorOutput

SUPPORTED_KEYWORDS: Final = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "anyOf",
        "allOf",
        "$ref",
        "$defs",
        "description",
        "minItems",
    }
)
DROPPED_KEYWORDS: Final = frozenset(
    {
        "title",
        "default",
        "examples",
        "discriminator",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "format",
        "pattern",
        "maxItems",
    }
)
LOCAL_REF_PREFIX: Final = "#/$defs/"
MAX_MIN_ITEMS: Final = 1


def _unsupported(feature: str, path: str) -> ValueError:
    return ValueError(f"unsupported schema feature: {feature} at {path}")


def _merge_all_of(node: Mapping[str, object], path: str) -> Mapping[str, object]:
    """Step 1: fold single-item 'allOf' into its node; several items holding a '$ref' raise."""
    while isinstance(items := node.get("allOf"), list):
        if len(items) == 1 and isinstance(items[0], Mapping):
            rest = {k: v for k, v in node.items() if k != "allOf"}
            node = {**rest, **cast("Mapping[str, object]", items[0])}
        elif any(isinstance(i, Mapping) and "$ref" in i for i in items):
            raise _unsupported("allOf with $ref", path)
        else:
            break
    return node


def _sanitize_all(values: object, path: str) -> list[object]:
    if not isinstance(values, list):
        raise _unsupported("non-list combinator", path)
    return [_sanitize(v, f"{path}/{i}", is_root=False) for i, v in enumerate(values)]


def _sanitize_properties(props: object, path: str) -> dict[str, object]:
    if not isinstance(props, Mapping):
        raise _unsupported("non-object properties", path)
    return {str(k): _sanitize(v, f"{path}/{k}", is_root=False) for k, v in props.items()}


def _sanitize_key(key: str, value: object, path: str, is_root: bool) -> object:
    """Step 3 for one supported key: its value sanitized."""
    child = f"{path}/{key}"
    if key == "properties":
        return _sanitize_properties(value, child)
    if key == "items":
        return _sanitize(value, child, is_root=False)
    if key in ("anyOf", "allOf"):
        return _sanitize_all(value, child)
    if key == "$defs":
        if not is_root or not isinstance(value, Mapping):
            raise _unsupported("$defs", path)
        return {str(k): _sanitize(v, f"{path}/$defs/{k}", is_root=False) for k, v in value.items()}
    if key == "additionalProperties" and value is not False:
        raise _unsupported("additionalProperties", path)
    return copy.deepcopy(value)


def _sanitize(node: object, path: str, *, is_root: bool) -> dict[str, object]:
    if not isinstance(node, Mapping):
        raise _unsupported("non-object schema", path)
    node = _merge_all_of(cast("Mapping[str, object]", node), path)
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith(LOCAL_REF_PREFIX):
            raise _unsupported(f"non-local $ref {ref}", path)
        kept: dict[str, object] = {"$ref": ref}
        if "$defs" in node:
            kept["$defs"] = _sanitize_key("$defs", node["$defs"], path, is_root)
        return kept
    out: dict[str, object] = {}
    for key, value in node.items():
        if key in DROPPED_KEYWORDS:
            continue
        name = "anyOf" if key == "oneOf" else key
        if name == "minItems":
            if isinstance(value, int) and value > MAX_MIN_ITEMS:
                continue
        elif name not in SUPPORTED_KEYWORDS:
            raise _unsupported(key, path)
        out[name] = _sanitize_key(name, value, path, is_root)
    if node.get("type") == "object" or "properties" in node:
        _close_object(node, out, path, is_root)
    return out


def _close_object(node: Mapping[str, object], out: dict[str, object], path: str, is_root: bool) -> None:
    """Step 4: every property required, in order, and no additional properties."""
    props = out.get("properties")
    if isinstance(props, dict):
        out["required"] = list(props)
    elif not is_root:
        raise _unsupported("object without properties", path)
    out["additionalProperties"] = False


def _refs(node: object) -> Iterator[str]:
    """Names of the local '$defs' that 'node' refers to."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value.removeprefix(LOCAL_REF_PREFIX)
            elif key in ("properties", "$defs") and isinstance(value, Mapping):
                for child in value.values():
                    yield from _refs(child)
            elif key not in ("enum", "const"):
                yield from _refs(value)
    elif isinstance(node, list):
        for child in node:
            yield from _refs(child)


def _check_cycles(defs: Mapping[str, object]) -> None:
    """A '$ref' cycle among the '$defs' raises."""

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in stack:
            raise ValueError(f"unsupported schema feature: recursive $defs {name}")
        for target in _refs(defs[name]):
            if target in defs:
                visit(target, (*stack, name))

    for name in defs:
        visit(name, ())


def strict_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """A new schema inside the strict subset; the input is untouched and a second pass is a no-op."""
    out = _sanitize(schema, "#", is_root=True)
    defs = out.get("$defs")
    if isinstance(defs, dict):
        _check_cycles(defs)
    return out


@cache
def investigator_output_schema() -> Mapping[str, object]:
    """The sanitized schema of 'InvestigatorOutput', built once; callers never mutate it."""
    return strict_schema(InvestigatorOutput.model_json_schema())
