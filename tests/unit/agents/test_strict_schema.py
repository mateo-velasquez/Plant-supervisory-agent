"""011 T10: schema sanitizer and the investigator output format (R1, R2, R3, E1, E2)."""

import copy
import re
from collections.abc import Iterator, Mapping
from typing import cast

import pytest
from judgment_builders import incident_tool_context

from plant_monitor.agents.output import (
    DROPPED_KEYWORDS,
    SUPPORTED_KEYWORDS,
    investigator_output_schema,
    strict_schema,
)
from plant_monitor.domain.proposals import InvestigatorOutput
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import READ_TOOLS, WRITE_TOOLS, build_server

pytestmark = pytest.mark.anyio

GC: dict[str, object] = {
    "type": "object",
    "properties": {"case_id": {"type": "string"}},
    "required": ["case_id"],
    "additionalProperties": False,
}
NAME_MAPS = ("properties", "$defs")


def _nodes(node: object) -> Iterator[Mapping[str, object]]:
    """Every schema node under 'node'; 'properties' and '$defs' are name maps, not keywords."""
    if isinstance(node, Mapping):
        yield node
        for key, value in node.items():
            if key in NAME_MAPS and isinstance(value, Mapping):
                for child in value.values():
                    yield from _nodes(child)
            else:
                yield from _nodes(value)
    elif isinstance(node, list):
        for child in node:
            yield from _nodes(child)


async def _tool_schemas() -> dict[str, Mapping[str, object]]:
    ctx, frames = incident_tool_context()
    async with ToolClient(build_server(ctx, frames, tools=(*READ_TOOLS, *WRITE_TOOLS))) as client:
        return {spec.name: spec.input_schema for spec in await client.list_tools()}


def test_e1a_the_investigator_output_schema_is_strict() -> None:
    """E1 (a): shape of 'InvestigatorOutput' after sanitizing; idempotent; input untouched."""
    raw = InvestigatorOutput.model_json_schema()
    before = copy.deepcopy(raw)
    out = strict_schema(raw)
    assert raw == before
    assert out["required"] == ["propuestas"]
    assert out["additionalProperties"] is False
    props = out["properties"]
    assert isinstance(props, dict)
    assert props["propuestas"] == {
        "type": "array",
        "items": {
            "anyOf": [
                {"$ref": "#/$defs/SetCauseProposal"},
                {"$ref": "#/$defs/RaiseProposal"},
                {"$ref": "#/$defs/LiftProposal"},
            ]
        },
    }
    defs = out["$defs"]
    assert isinstance(defs, dict)
    assert set(defs) == {
        "CauseCategory",
        "CauseState",
        "LiftProposal",
        "Market",
        "Model",
        "RaiseProposal",
        "SetCauseProposal",
        "Stage",
    }
    raise_def = defs["RaiseProposal"]
    assert raise_def["required"] == [
        "tipo",
        "categoria",
        "etapa",
        "modelo",
        "mercado",
        "bitacora",
        "fragmento",
        "estado_causa",
    ]
    assert raise_def["properties"]["mercado"] == {"anyOf": [{"$ref": "#/$defs/Market"}, {"type": "null"}]}
    assert raise_def["properties"]["tipo"] == {"const": "raise", "type": "string"}
    assert raise_def["additionalProperties"] is False
    assert "no_declarada" in defs["CauseCategory"]["enum"]
    for node in _nodes(out):
        assert not {"title", "default", "discriminator", "oneOf"} & set(node)
    assert strict_schema(out) == out


async def test_e1b_valid_schemas_and_minitems() -> None:
    """E1 (b): 'get_case' as listed by the server, a root object without properties, 'minItems' 2 and 1."""
    assert strict_schema((await _tool_schemas())["get_case"]) == GC
    assert strict_schema({"type": "object"}) == {"type": "object", "additionalProperties": False}
    array: dict[str, object] = {"type": "array", "items": {"type": "string"}}
    assert strict_schema({**array, "minItems": 2}) == array
    assert strict_schema({**array, "minItems": 1}) == {**array, "minItems": 1}


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        pytest.param(
            {"type": "object", "additionalProperties": {"type": "string"}},
            "unsupported schema feature: additionalProperties at #",
            id="additional_properties",
        ),
        pytest.param(
            {"$ref": "https://x/s.json"},
            "unsupported schema feature: non-local $ref https://x/s.json at #",
            id="non_local_ref",
        ),
        pytest.param(
            {
                "type": "object",
                "properties": {"n": {"$ref": "#/$defs/N"}},
                "$defs": {"N": {"type": "object", "properties": {"next": {"$ref": "#/$defs/N"}}}},
            },
            "unsupported schema feature: recursive $defs N",
            id="recursive_defs",
        ),
        pytest.param(
            {"type": "string", "contentEncoding": "base64"},
            "unsupported schema feature: contentEncoding at #",
            id="unknown_keyword",
        ),
        pytest.param(
            {"type": "object", "properties": {"m": {"type": "object"}}},
            "unsupported schema feature: object without properties at #/properties/m",
            id="object_without_properties",
        ),
    ],
)
def test_e1c_unsupported_features_raise(schema: dict[str, object], message: str) -> None:
    """E1 (c): each unsupported feature raises 'ValueError' naming the feature and the path."""
    with pytest.raises(ValueError, match=re.escape(message)):
        strict_schema(schema)


def test_e1b_a_one_item_all_of_with_a_ref_folds_into_the_node_and_siblings_go() -> None:
    """E1 (b), R1 step 1: the '$ref' node stays and its sibling 'description' is stripped."""
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"x": {"allOf": [{"$ref": "#/$defs/N"}], "description": "d"}},
        "$defs": {"N": {"type": "string"}},
    }
    out = strict_schema(schema)
    props = out["properties"]
    assert isinstance(props, dict)
    assert props["x"] == {"$ref": "#/$defs/N"}


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        pytest.param(
            {
                "type": "object",
                "properties": {"x": {"allOf": [{"$ref": "#/$defs/N"}, {"type": "string"}]}},
                "$defs": {"N": {"type": "string"}},
            },
            "unsupported schema feature: allOf with $ref at #/properties/x",
            id="two-item-all-of-with-ref",
        ),
        pytest.param(
            {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "object",
                        "properties": {"s": {"type": "string"}},
                        "$defs": {"N": {"type": "string"}},
                    }
                },
            },
            "unsupported schema feature: $defs at #/properties/x",
            id="nested-defs-below-the-root",
        ),
        pytest.param(
            {
                "type": "object",
                "properties": {"x": {"$ref": "#/$defs/N", "$defs": {"M": {"type": "string"}}}},
                "$defs": {"N": {"type": "string"}},
            },
            "unsupported schema feature: $defs at #/properties/x",
            id="non-root-node-with-ref-and-defs",
        ),
    ],
)
def test_e1c_all_of_with_a_ref_and_nested_defs_raise(schema: dict[str, object], message: str) -> None:
    """E1 (c), R1: a multi-item 'allOf' with '$ref' raises; so does a '$defs' below the root."""
    with pytest.raises(ValueError, match=re.escape(message)):
        strict_schema(schema)


async def test_e1d_sanitizing_twice_keeps_the_input_key_order() -> None:
    """E1 (d): FastMCP's key order survives, and a second pass gives the same keys."""
    original = (await _tool_schemas())["get_case"]
    assert "additionalProperties" not in original
    once = strict_schema(original)
    assert list(once) == [key for key in original if key != "title"] + ["additionalProperties"]
    assert list(strict_schema(once)) == list(once)
    raw = InvestigatorOutput.model_json_schema()
    kept = [key for key in raw if key != "title"]
    assert list(strict_schema(raw)) == kept + (
        [] if "additionalProperties" in raw else ["additionalProperties"]
    )


def test_r2_the_investigator_output_schema_is_built_once() -> None:
    """R2: 'investigator_output_schema' equals the sanitized model schema and is the same object each call."""
    assert investigator_output_schema() == strict_schema(InvestigatorOutput.model_json_schema())
    assert investigator_output_schema() is investigator_output_schema()


async def test_e2_risk_every_registered_schema_is_within_the_strict_subset() -> None:
    """Risk: a 400 from an unsupported feature or a non-nullable optional parameter (R1, R2, R3)."""
    originals = await _tool_schemas()
    sanitized = {name: strict_schema(schema) for name, schema in originals.items()}
    sanitized["<investigator output>"] = dict(investigator_output_schema())
    for schema in sanitized.values():
        defs = schema.get("$defs", {})
        assert isinstance(defs, Mapping)
        for node in _nodes(schema):
            assert set(node) <= SUPPORTED_KEYWORDS
            assert not set(node) & DROPPED_KEYWORDS
            props = node.get("properties")
            if props is not None or node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert isinstance(props, Mapping)
                assert node["required"] == list(props)
            if "minItems" in node:
                assert node["minItems"] in (0, 1)
            ref = node.get("$ref")
            if isinstance(ref, str):
                assert ref.removeprefix("#/$defs/") in defs
    optional = {
        (name, prop)
        for name, original in originals.items()
        for prop in cast("Mapping[str, object]", original.get("properties", {}))
        if prop not in cast("list[str]", original.get("required", []))
    }
    assert optional == {("raise_severity", "mercado")}
    for name, prop in optional:
        props = cast("Mapping[str, Mapping[str, list[object]]]", sanitized[name]["properties"])
        assert {"type": "null"} in props[prop]["anyOf"]
