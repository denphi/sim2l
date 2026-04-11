"""Tests for loading schemas from different input formats: JSON, YAML, dict, DTDL, SOFT7, OWL, and notebooks."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sim2l.schema.schema import InputSchema, OutputSchema, Schema
from sim2l.schema.types import (
    Array,
    Boolean,
    Dict,
    Integer,
    List,
    Number,
    Text,
)


# ---------------------------------------------------------------------------
# Shared schema spec used across format tests
# ---------------------------------------------------------------------------
SCHEMA_SPEC = {
    "temperature": {"type": "Number", "units": "kelvin", "min": 0, "max": 1000, "default": 300},
    "steps": {"type": "Integer", "min": 1, "max": 10000, "default": 100},
    "label": {"type": "Text", "optional": True},
    "enabled": {"type": "Boolean", "default": True},
    "weights": {"type": "Array", "dtype": "float", "optional": True},
    "tags": {"type": "List", "optional": True},
    "metadata": {"type": "Dict", "optional": True},
}

VALID_INPUT = {
    "temperature": 350,
    "steps": 500,
    "label": "run-1",
    "enabled": True,
    "weights": [1.0, 2.0, 3.0],
    "tags": ["physics", "test"],
    "metadata": {"author": "alice"},
}


# ---------------------------------------------------------------------------
# 1. Schema from Python dict
# ---------------------------------------------------------------------------
class TestDictInput(unittest.TestCase):
    def setUp(self):
        self.schema = InputSchema.from_dict(SCHEMA_SPEC)

    def test_fields_created(self):
        for name in SCHEMA_SPEC:
            self.assertIn(name, self.schema)

    def test_field_types(self):
        self.assertIsInstance(self.schema["temperature"], Number)
        self.assertIsInstance(self.schema["steps"], Integer)
        self.assertIsInstance(self.schema["label"], Text)
        self.assertIsInstance(self.schema["enabled"], Boolean)
        self.assertIsInstance(self.schema["weights"], Array)
        self.assertIsInstance(self.schema["tags"], List)
        self.assertIsInstance(self.schema["metadata"], Dict)

    def test_validate_full_input(self):
        validated = self.schema.validate(VALID_INPUT)
        self.assertEqual(validated["steps"], 500)
        self.assertEqual(validated["label"], "run-1")

    def test_required_field_missing_raises(self):
        # Build a schema with no defaults so a missing field truly raises.
        strict = InputSchema.from_dict({
            "x": {"type": "Integer"},
            "y": {"type": "Integer"},
        })
        with self.assertRaises(ValueError):
            strict.validate({"x": 1})  # y missing and has no default

    def test_defaults_applied(self):
        validated = self.schema.validate({"temperature": 300, "steps": 50})
        self.assertEqual(validated["enabled"], True)

    def test_extra_field_raises(self):
        bad = dict(VALID_INPUT)
        bad["unknown_field"] = "surprise"
        with self.assertRaises(ValueError):
            self.schema.validate(bad)


# ---------------------------------------------------------------------------
# 2. Schema from JSON string
# ---------------------------------------------------------------------------
class TestJSONInput(unittest.TestCase):
    def setUp(self):
        self.json_str = json.dumps(SCHEMA_SPEC)
        self.schema = InputSchema.from_dict(json.loads(self.json_str))

    def test_parse_from_json_string(self):
        self.assertIn("temperature", self.schema)
        self.assertIn("steps", self.schema)

    def test_units_preserved(self):
        field = self.schema["temperature"]
        self.assertEqual(field.units, "kelvin")

    def test_bounds_preserved(self):
        field = self.schema["steps"]
        self.assertEqual(field.min, 1)
        self.assertEqual(field.max, 10000)

    def test_validate_json_loaded_values(self):
        raw = json.dumps({"temperature": 273, "steps": 200})
        inputs = json.loads(raw)
        validated = self.schema.validate(inputs)
        self.assertEqual(validated["steps"], 200)

    def test_min_bound_violation(self):
        with self.assertRaises(ValueError):
            self.schema.validate({"temperature": -10, "steps": 1})

    def test_max_bound_violation(self):
        with self.assertRaises(ValueError):
            self.schema.validate({"temperature": 300, "steps": 99999})

    def test_roundtrip_json(self):
        """to_dict → json.dumps → json.loads → from_dict reproduces the same schema."""
        original_dict = self.schema.to_dict()
        json_str = json.dumps(original_dict)
        restored = InputSchema.from_dict(json.loads(json_str))
        self.assertEqual(set(restored.fields.keys()), set(self.schema.fields.keys()))
        self.assertEqual(restored["steps"].min, self.schema["steps"].min)


# ---------------------------------------------------------------------------
# 3. Schema from YAML string
# ---------------------------------------------------------------------------
YAML_SCHEMA = """\
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
steps:
  type: Integer
  min: 1
  max: 10000
  default: 100
label:
  type: Text
  optional: true
enabled:
  type: Boolean
  default: true
weights:
  type: Array
  dtype: float
  optional: true
tags:
  type: List
  optional: true
metadata:
  type: Dict
  optional: true
"""


class TestYAMLInput(unittest.TestCase):
    def setUp(self):
        self.schema = InputSchema.from_yaml(YAML_SCHEMA)

    def test_parse_from_yaml(self):
        for name in ("temperature", "steps", "label", "enabled", "weights", "tags", "metadata"):
            self.assertIn(name, self.schema)

    def test_number_units(self):
        self.assertEqual(self.schema["temperature"].units, "kelvin")

    def test_integer_bounds(self):
        field = self.schema["steps"]
        self.assertEqual(field.min, 1)
        self.assertEqual(field.max, 10000)

    def test_optional_flags(self):
        self.assertTrue(self.schema["label"].optional)
        self.assertFalse(self.schema["temperature"].optional)

    def test_validate_valid_input(self):
        validated = self.schema.validate(VALID_INPUT)
        self.assertIsInstance(validated["weights"], np.ndarray)

    def test_empty_yaml_produces_empty_schema(self):
        schema = InputSchema.from_yaml("")
        self.assertEqual(len(schema.fields), 0)

    def test_roundtrip_yaml(self):
        """from_yaml → to_dict → from_dict preserves field names and constraints."""
        import yaml
        restored = InputSchema.from_dict(self.schema.to_dict())
        self.assertEqual(set(restored.fields.keys()), set(self.schema.fields.keys()))
        self.assertEqual(restored["temperature"].units, "kelvin")


# ---------------------------------------------------------------------------
# 4. DTDL-structured JSON input
# ---------------------------------------------------------------------------
DTDL_INTERFACE = {
    "@id": "dtmi:com:example:sensor;1",
    "@type": "Interface",
    "@context": "dtmi:dtdl:context;3",
    "displayName": "Temperature Sensor",
    "description": "A simple temperature sensor twin",
    "contents": [
        {
            "@type": "Property",
            "name": "temperature",
            "schema": "double",
            "unit": "degreeCelsius",
        },
        {
            "@type": "Property",
            "name": "humidity",
            "schema": "double",
            "unit": "percent",
        },
        {
            "@type": "Telemetry",
            "name": "alert",
            "schema": "boolean",
        },
        {
            "@type": "Relationship",
            "@id": "dtmi:com:example:sensor:rel_in_room;1",
            "name": "rel_in_room",
            "target": "dtmi:com:example:room;1",
        },
    ],
}


class TestDTDLInput(unittest.TestCase):
    """Validate DTDL Interface JSON against a sim2l schema using Dict/List fields."""

    def setUp(self):
        self.schema = Schema(
            {
                "@id": Text(),
                "@type": Text(),
                "@context": Text(),
                "displayName": Text(optional=True),
                "description": Text(optional=True),
                "contents": List(optional=True),
            }
        )

    def test_validate_full_dtdl_interface(self):
        validated = self.schema.validate(DTDL_INTERFACE)
        self.assertEqual(validated["@type"], "Interface")
        self.assertEqual(len(validated["contents"]), 4)

    def test_contents_items_preserved(self):
        validated = self.schema.validate(DTDL_INTERFACE)
        types = [item["@type"] for item in validated["contents"]]
        self.assertIn("Property", types)
        self.assertIn("Telemetry", types)
        self.assertIn("Relationship", types)

    def test_missing_required_context(self):
        bad = dict(DTDL_INTERFACE)
        del bad["@context"]
        with self.assertRaises(ValueError):
            self.schema.validate(bad)

    def test_contents_not_list_raises(self):
        bad = dict(DTDL_INTERFACE)
        bad["contents"] = "not-a-list"
        with self.assertRaises(ValueError):
            self.schema.validate(bad)

    def test_load_dtdl_from_json_string(self):
        """Simulate loading DTDL from a JSON file or API response."""
        json_str = json.dumps(DTDL_INTERFACE)
        data = json.loads(json_str)
        validated = self.schema.validate(data)
        self.assertEqual(validated["@id"], "dtmi:com:example:sensor;1")

    def test_set_and_get_values(self):
        self.schema.set_values(DTDL_INTERFACE)
        values = self.schema.get_values()
        self.assertEqual(values["@id"], DTDL_INTERFACE["@id"])
        self.assertEqual(len(values["contents"]), 4)

    def test_serialize_deserialize_roundtrip(self):
        self.schema.set_values(DTDL_INTERFACE)
        serialized = self.schema.serialize()

        new_schema = Schema(
            {
                "@id": Text(),
                "@type": Text(),
                "@context": Text(),
                "displayName": Text(optional=True),
                "description": Text(optional=True),
                "contents": List(optional=True),
            }
        )
        new_schema.deserialize(serialized)
        self.assertEqual(new_schema["@id"].value, DTDL_INTERFACE["@id"])
        self.assertEqual(len(new_schema["contents"].value), 4)

    def test_multiple_interfaces_from_json_array(self):
        """A JSON array of DTDL interfaces can each be validated individually."""
        interfaces = [DTDL_INTERFACE, {**DTDL_INTERFACE, "@id": "dtmi:com:example:sensor;2"}]
        for iface in interfaces:
            validated = self.schema.validate(iface)
            self.assertEqual(validated["@type"], "Interface")


# ---------------------------------------------------------------------------
# 5. Notebook input parsing
# ---------------------------------------------------------------------------
class TestNotebookInput(unittest.TestCase):
    """Test parse_notebook() against a real .ipynb file."""

    NOTEBOOK_PATH = Path(__file__).parent.parent / "examples" / "thermal_simulation.ipynb"

    def setUp(self):
        if not self.NOTEBOOK_PATH.exists():
            self.skipTest(f"Notebook not found: {self.NOTEBOOK_PATH}")

        from sim2l.definition.parser import parse_notebook
        self.inputs, self.outputs, self.notebook_bytes = parse_notebook(self.NOTEBOOK_PATH)

    def test_inputs_schema_extracted(self):
        self.assertIsInstance(self.inputs, InputSchema)

    def test_outputs_schema_extracted(self):
        self.assertIsInstance(self.outputs, OutputSchema)

    def test_expected_input_fields(self):
        for name in ("temperature", "power", "iterations", "grid_size"):
            self.assertIn(name, self.inputs)

    def test_expected_output_fields(self):
        for name in ("max_temperature", "min_temperature", "avg_temperature",
                     "temperature_distribution", "thermal_plot", "converged",
                     "iterations_to_convergence"):
            self.assertIn(name, self.outputs)

    def test_input_field_types(self):
        self.assertIsInstance(self.inputs["temperature"], Number)
        self.assertIsInstance(self.inputs["iterations"], Integer)

    def test_notebook_bytes_returned(self):
        self.assertIsInstance(self.notebook_bytes, bytes)
        self.assertGreater(len(self.notebook_bytes), 0)

    def test_validate_valid_inputs(self):
        validated = self.inputs.validate(
            {"temperature": 350, "power": 20, "iterations": 200, "grid_size": 50}
        )
        self.assertEqual(validated["iterations"], 200)

    def test_validate_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            self.inputs.validate(
                {"temperature": -100, "power": 10, "iterations": 100, "grid_size": 50}
            )


class TestNotebookInputFromTempFile(unittest.TestCase):
    """Test parse_notebook() with both sim2l magic formats using a temp notebook."""

    def _make_notebook(self, inputs_magic: str, outputs_magic: str) -> Path:
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "source": [inputs_magic],
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
                {
                    "cell_type": "code",
                    "source": [outputs_magic],
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                },
            ],
        }
        tmp = tempfile.NamedTemporaryFile(
            suffix=".ipynb", mode="w", delete=False, encoding="utf-8"
        )
        json.dump(notebook, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_sim2l_magic_format(self):
        from sim2l.definition.parser import parse_notebook

        nb = self._make_notebook(
            "%%sim2l_inputs\nvalue:\n  type: Integer\n",
            "%%sim2l_outputs\nresult:\n  type: Number\n",
        )
        try:
            inputs, outputs, _ = parse_notebook(nb)
            self.assertIn("value", inputs)
            self.assertIn("result", outputs)
        finally:
            nb.unlink()

    def test_legacy_yaml_magic_format(self):
        from sim2l.definition.parser import parse_notebook

        nb = self._make_notebook(
            "%%yaml INPUTS\nvalue:\n  type: Integer\n",
            "%%yaml OUTPUTS\nresult:\n  type: Number\n",
        )
        try:
            inputs, outputs, _ = parse_notebook(nb)
            self.assertIn("value", inputs)
            self.assertIn("result", outputs)
        finally:
            nb.unlink()

    def test_missing_inputs_cell_raises(self):
        from sim2l.definition.parser import parse_notebook

        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["%%sim2l_outputs\nresult:\n  type: Number\n"],
                    "metadata": {},
                    "outputs": [],
                    "execution_count": None,
                }
            ],
        }
        tmp = tempfile.NamedTemporaryFile(
            suffix=".ipynb", mode="w", delete=False, encoding="utf-8"
        )
        json.dump(notebook, tmp)
        tmp.close()
        nb = Path(tmp.name)
        try:
            with self.assertRaises(ValueError):
                parse_notebook(nb)
        finally:
            nb.unlink()


# ---------------------------------------------------------------------------
# 6. Field-level type coercion from different Python value types
# ---------------------------------------------------------------------------
class TestFieldValueCoercion(unittest.TestCase):
    """Verify that each field type accepts the Python values users naturally pass."""

    def test_integer_from_string(self):
        f = Integer()
        self.assertEqual(f.validate("42"), 42)

    def test_integer_from_float(self):
        f = Integer()
        self.assertEqual(f.validate(3.9), 3)

    def test_number_plain_float(self):
        f = Number()
        result = f.validate(3.14)
        self.assertAlmostEqual(float(result), 3.14)

    def test_number_with_units(self):
        f = Number(units="kelvin")
        result = f.validate(300)
        self.assertAlmostEqual(float(result.magnitude), 300)

    def test_number_from_pint_quantity(self):
        from sim2l.utils.units import get_unit_registry
        ureg = get_unit_registry()
        f = Number(units="kelvin")
        result = f.validate(300 * ureg.kelvin)
        self.assertAlmostEqual(float(result.magnitude), 300)

    def test_text_from_int(self):
        f = Text()
        self.assertEqual(f.validate(99), "99")

    def test_text_choices(self):
        f = Text(choices=["a", "b", "c"])
        self.assertEqual(f.validate("b"), "b")
        with self.assertRaises(ValueError):
            f.validate("d")

    def test_boolean_from_string_true(self):
        f = Boolean()
        self.assertTrue(f.validate("true"))
        self.assertTrue(f.validate("yes"))
        self.assertTrue(f.validate("1"))

    def test_boolean_from_string_false(self):
        f = Boolean()
        self.assertFalse(f.validate("false"))
        self.assertFalse(f.validate("no"))
        self.assertFalse(f.validate("0"))

    def test_boolean_invalid_raises(self):
        f = Boolean()
        with self.assertRaises(ValueError):
            f.validate("maybe")

    def test_array_from_list(self):
        f = Array(dtype="float")
        arr = f.validate([1, 2, 3])
        self.assertIsInstance(arr, np.ndarray)
        np.testing.assert_array_equal(arr, [1.0, 2.0, 3.0])

    def test_array_from_numpy(self):
        f = Array(dtype="int32")
        arr = f.validate(np.array([10, 20, 30]))
        self.assertEqual(arr.dtype, np.dtype("int32"))

    def test_array_shape_mismatch_raises(self):
        f = Array(dtype="float", shape=(3, 3))
        with self.assertRaises(ValueError):
            f.validate([[1, 2], [3, 4]])

    def test_list_from_tuple(self):
        f = List()
        self.assertEqual(f.validate((1, 2, 3)), [1, 2, 3])

    def test_list_non_sequence_raises(self):
        f = List()
        with self.assertRaises(ValueError):
            f.validate("not-a-list")

    def test_dict_from_dict(self):
        f = Dict()
        result = f.validate({"key": "value"})
        self.assertEqual(result["key"], "value")

    def test_dict_non_dict_raises(self):
        f = Dict()
        with self.assertRaises(ValueError):
            f.validate(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# 7. SOFT7 entity input
# ---------------------------------------------------------------------------

# SOFT7 entity definition (onto-ns.com style)
SOFT7_ENTITY = {
    "uri": "http://onto-ns.com/meta/0.3/ThermalSensor",
    "description": "A thermal sensor measuring temperature and power",
    "dimensions": {
        "n_readings": "Number of historical temperature readings"
    },
    "properties": {
        "temperature": {"type": "float64", "unit": "K", "description": "Current temperature"},
        "power":       {"type": "float64", "unit": "W", "description": "Applied power"},
        "active":      {"type": "bool",                 "description": "Whether sensor is active"},
        "label":       {"type": "string",               "description": "Sensor identifier"},
        "readings":    {"type": "float64", "dims": ["n_readings"], "description": "Historical readings"},
    },
}

# Map SOFT7 primitive types to sim2l field types
_SOFT7_TYPE_MAP = {
    "float64": "Number", "float32": "Number", "double": "Number", "float": "Number",
    "int32": "Integer",  "int64": "Integer",  "integer": "Integer", "int": "Integer",
    "string": "Text",    "str": "Text",
    "bool": "Boolean",   "boolean": "Boolean",
}


def soft7_props_to_schema_spec(entity: dict) -> dict:
    """Convert SOFT7 entity ``properties`` block to a sim2l ``from_dict``-compatible spec."""
    spec = {}
    for name, prop in entity.get("properties", {}).items():
        raw_type = prop.get("type", "string")
        if "dims" in prop:
            # Property with dimensions → NumPy array
            field_spec = {"type": "Array", "dtype": "float", "optional": True}
        else:
            field_spec = {"type": _SOFT7_TYPE_MAP.get(raw_type, "Text")}
        if "unit" in prop and field_spec["type"] == "Number":
            field_spec["units"] = prop["unit"]
        spec[name] = field_spec
    return spec


class TestSOFT7Input(unittest.TestCase):
    """Validate SOFT7 entity definitions and instance data through sim2l schemas."""

    def setUp(self):
        # Schema that validates the SOFT7 entity *definition* itself
        self.entity_schema = Schema({
            "uri":         Text(),
            "description": Text(optional=True),
            "dimensions":  Dict(optional=True),
            "properties":  Dict(),
        })

        # InputSchema derived from the SOFT7 entity's properties
        spec = soft7_props_to_schema_spec(SOFT7_ENTITY)
        self.data_schema = InputSchema.from_dict(spec)

    # --- entity definition validation ---

    def test_validate_soft7_entity_structure(self):
        validated = self.entity_schema.validate(SOFT7_ENTITY)
        self.assertEqual(validated["uri"], SOFT7_ENTITY["uri"])
        self.assertIn("temperature", validated["properties"])

    def test_missing_uri_raises(self):
        bad = dict(SOFT7_ENTITY)
        del bad["uri"]
        with self.assertRaises(ValueError):
            self.entity_schema.validate(bad)

    def test_load_entity_from_json_string(self):
        json_str = json.dumps(SOFT7_ENTITY)
        data = json.loads(json_str)
        validated = self.entity_schema.validate(data)
        self.assertEqual(validated["uri"], SOFT7_ENTITY["uri"])

    # --- type mapping ---

    def test_type_mapping_number(self):
        self.assertIsInstance(self.data_schema["temperature"], Number)
        self.assertIsInstance(self.data_schema["power"], Number)

    def test_type_mapping_boolean(self):
        self.assertIsInstance(self.data_schema["active"], Boolean)

    def test_type_mapping_text(self):
        self.assertIsInstance(self.data_schema["label"], Text)

    def test_type_mapping_array_for_dimensioned_property(self):
        self.assertIsInstance(self.data_schema["readings"], Array)

    def test_units_carried_over(self):
        self.assertEqual(self.data_schema["temperature"].units, "K")
        self.assertEqual(self.data_schema["power"].units, "W")

    # --- instance data validation ---

    def test_validate_instance_data(self):
        validated = self.data_schema.validate({
            "temperature": 298.15,
            "power": 5.0,
            "active": True,
            "label": "sensor-001",
            "readings": [295.0, 296.5, 298.15],
        })
        self.assertAlmostEqual(float(validated["temperature"].magnitude), 298.15)
        self.assertIsInstance(validated["readings"], np.ndarray)

    def test_boolean_coercion_from_string(self):
        validated = self.data_schema.validate({
            "temperature": 300.0,
            "power": 10.0,
            "active": "true",
            "label": "s2",
        })
        self.assertTrue(validated["active"])

    def test_invalid_boolean_raises(self):
        with self.assertRaises(ValueError):
            self.data_schema.validate({
                "temperature": 300.0,
                "power": 10.0,
                "active": "maybe",
                "label": "s3",
            })

    # --- round-trip ---

    def test_roundtrip_soft7_entity_via_json(self):
        spec = soft7_props_to_schema_spec(SOFT7_ENTITY)
        json_str = json.dumps(spec)
        restored = InputSchema.from_dict(json.loads(json_str))
        self.assertEqual(set(restored.fields.keys()), set(self.data_schema.fields.keys()))

    def test_schema_spec_round_trip_preserves_units(self):
        spec = soft7_props_to_schema_spec(SOFT7_ENTITY)
        restored = InputSchema.from_dict(spec)
        self.assertEqual(restored["temperature"].units, "K")

    def test_type_mapping_unknown_falls_back_to_text(self):
        """An unmapped SOFT7 primitive type should fall back to Text."""
        entity = {
            "properties": {
                "mystery": {"type": "complex128", "description": "unknown type"},
                "also_unknown": {"type": "uuid", "description": "another unknown"},
            }
        }
        spec = soft7_props_to_schema_spec(entity)
        schema = InputSchema.from_dict(spec)
        self.assertIsInstance(schema["mystery"], Text)
        self.assertIsInstance(schema["also_unknown"], Text)


# ---------------------------------------------------------------------------
# 8. OWL ontology input (JSON-LD)
# ---------------------------------------------------------------------------

OWL_CLASS = {
    "@context": {
        "owl":  "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd":  "http://www.w3.org/2001/XMLSchema#",
    },
    "@id":              "http://example.org/ThermalSensor",
    "@type":            "owl:Class",
    "rdfs:label":       "ThermalSensor",
    "rdfs:subClassOf":  "http://example.org/Sensor",
    "rdfs:comment":     "A device that measures temperature",
}

OWL_INDIVIDUAL = {
    "@context": {
        "owl":  "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "ex":   "http://example.org/",
    },
    "@id":            "http://example.org/sensor_001",
    "@type":          "ex:ThermalSensor",
    "rdfs:label":     "Sensor 001",
    "ex:temperature": 298.15,
    "ex:power":       5.0,
    "ex:active":      True,
}

OWL_OBJECT_PROPERTY = {
    "@context": {
        "owl":  "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    },
    "@id":            "http://example.org/hasReading",
    "@type":          "owl:ObjectProperty",
    "rdfs:label":     "hasReading",
    "rdfs:domain":    "http://example.org/ThermalSensor",
    "rdfs:range":     "http://example.org/Reading",
    "rdfs:comment":   "Links a sensor to its readings",
}

OWL_DATATYPE_PROPERTY = {
    "@context": {
        "owl":  "http://www.w3.org/2002/07/owl#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd":  "http://www.w3.org/2001/XMLSchema#",
    },
    "@id":           "http://example.org/temperature",
    "@type":         "owl:DatatypeProperty",
    "rdfs:label":    "temperature",
    "rdfs:domain":   "http://example.org/ThermalSensor",
    "rdfs:range":    "xsd:double",
    "rdfs:comment":  "Temperature value in Kelvin",
}


class TestOWLInput(unittest.TestCase):
    """Validate OWL JSON-LD structures against sim2l schemas."""

    def setUp(self):
        # Schema for an OWL Class description
        self.class_schema = Schema({
            "@context":         Dict(),
            "@id":              Text(),
            "@type":            Text(),
            "rdfs:label":       Text(optional=True),
            "rdfs:subClassOf":  Text(optional=True),
            "rdfs:comment":     Text(optional=True),
        })

        # Schema for an OWL Individual (open-world: extra keys allowed via Dict)
        self.individual_schema = Schema({
            "@context": Dict(),
            "@id":      Text(),
            "@type":    Text(),
            "rdfs:label": Text(optional=True),
        })

        # Schema for OWL Object/Datatype Property
        self.property_schema = Schema({
            "@context":      Dict(),
            "@id":           Text(),
            "@type":         Text(),
            "rdfs:label":    Text(optional=True),
            "rdfs:domain":   Text(optional=True),
            "rdfs:range":    Text(optional=True),
            "rdfs:comment":  Text(optional=True),
        })

    # --- OWL Class ---

    def test_validate_owl_class(self):
        validated = self.class_schema.validate(OWL_CLASS)
        self.assertEqual(validated["@type"], "owl:Class")
        self.assertEqual(validated["rdfs:label"], "ThermalSensor")

    def test_missing_class_id_raises(self):
        bad = dict(OWL_CLASS)
        del bad["@id"]
        with self.assertRaises(ValueError):
            self.class_schema.validate(bad)

    def test_class_subclass_of_preserved(self):
        validated = self.class_schema.validate(OWL_CLASS)
        self.assertEqual(validated["rdfs:subClassOf"], "http://example.org/Sensor")

    def test_load_class_from_json_string(self):
        json_str = json.dumps(OWL_CLASS)
        validated = self.class_schema.validate(json.loads(json_str))
        self.assertEqual(validated["@id"], "http://example.org/ThermalSensor")

    # --- OWL Individual ---

    def test_validate_owl_individual(self):
        validated = self.individual_schema.validate({
            k: v for k, v in OWL_INDIVIDUAL.items()
            if k in ("@context", "@id", "@type", "rdfs:label")
        })
        self.assertEqual(validated["@type"], "ex:ThermalSensor")

    def test_individual_missing_type_raises(self):
        bad = {"@context": {}, "@id": "http://example.org/sensor_002"}
        with self.assertRaises(ValueError):
            self.individual_schema.validate(bad)

    def test_individual_extra_keys_raise_with_strict_schema(self):
        """OWL individuals carry arbitrary properties; Schema.validate raises on
        extra fields because it is strict.  Tests that consume OWL_INDIVIDUAL
        directly must pre-filter keys or use a schema that covers all fields."""
        with self.assertRaises(ValueError):
            # OWL_INDIVIDUAL contains ex:temperature, ex:power, ex:active
            # which are not declared in individual_schema → strict rejection
            self.individual_schema.validate(OWL_INDIVIDUAL)

    # --- OWL Property ---

    def test_validate_object_property(self):
        validated = self.property_schema.validate(OWL_OBJECT_PROPERTY)
        self.assertEqual(validated["@type"], "owl:ObjectProperty")
        self.assertEqual(validated["rdfs:domain"], "http://example.org/ThermalSensor")

    def test_validate_datatype_property(self):
        validated = self.property_schema.validate(OWL_DATATYPE_PROPERTY)
        self.assertEqual(validated["@type"], "owl:DatatypeProperty")
        self.assertEqual(validated["rdfs:range"], "xsd:double")

    def test_property_range_preserved(self):
        validated = self.property_schema.validate(OWL_DATATYPE_PROPERTY)
        self.assertIn("xsd:double", validated["rdfs:range"])

    # --- context is always a dict ---

    def test_context_not_dict_raises(self):
        bad = dict(OWL_CLASS)
        bad["@context"] = "http://schema.org/"  # string instead of dict
        with self.assertRaises(ValueError):
            self.class_schema.validate(bad)

    # --- round-trip ---

    def test_serialize_deserialize_owl_class(self):
        schema = Schema({
            "@context":        Dict(),
            "@id":             Text(),
            "@type":           Text(),
            "rdfs:label":      Text(optional=True),
            "rdfs:subClassOf": Text(optional=True),
            "rdfs:comment":    Text(optional=True),
        })
        schema.set_values(OWL_CLASS)
        serialized = schema.serialize()

        restored = Schema({
            "@context":        Dict(),
            "@id":             Text(),
            "@type":           Text(),
            "rdfs:label":      Text(optional=True),
            "rdfs:subClassOf": Text(optional=True),
            "rdfs:comment":    Text(optional=True),
        })
        restored.deserialize(serialized)
        self.assertEqual(restored["@id"].value, OWL_CLASS["@id"])
        self.assertEqual(restored["@type"].value, "owl:Class")


# ---------------------------------------------------------------------------
# 9. Loading schemas from actual files on disk
# ---------------------------------------------------------------------------
class TestFileLoading(unittest.TestCase):
    """Verify that schemas can be loaded from real JSON and YAML files."""

    def test_load_schema_from_json_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(SCHEMA_SPEC, f)
            tmp_path = Path(f.name)
        try:
            with open(tmp_path, encoding="utf-8") as fh:
                schema = InputSchema.from_dict(json.load(fh))
            for name in SCHEMA_SPEC:
                self.assertIn(name, schema)
            self.assertEqual(schema["temperature"].units, "kelvin")
        finally:
            tmp_path.unlink()

    def test_load_schema_from_yaml_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(YAML_SCHEMA)
            tmp_path = Path(f.name)
        try:
            with open(tmp_path, encoding="utf-8") as fh:
                schema = InputSchema.from_yaml(fh.read())
            for name in ("temperature", "steps", "label", "enabled", "weights", "tags", "metadata"):
                self.assertIn(name, schema)
            self.assertEqual(schema["steps"].min, 1)
        finally:
            tmp_path.unlink()

    def test_validate_after_json_file_roundtrip(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(SCHEMA_SPEC, f)
            tmp_path = Path(f.name)
        try:
            with open(tmp_path, encoding="utf-8") as fh:
                schema = InputSchema.from_dict(json.load(fh))
            validated = schema.validate(VALID_INPUT)
            self.assertEqual(validated["steps"], 500)
        finally:
            tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
