#!/usr/bin/env python3
"""
Comprehensive tests for the sim2l schema system.

Covers all layers of the schema pipeline:
- Field base class behaviour
- Every concrete field type (validation, coercion, serialize/deserialize, to_dict/from_dict)
- Registry registration and lookup
- Schema container (validate, set/get, serialize/deserialize, from_dict/from_yaml)
- InputSchema / OutputSchema subclasses
- Realistic end-to-end roundtrip mimicking a real simulation contract
"""

import unittest
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from sim2l.schema.field import Field
from sim2l.schema.types import (
    Integer, Number, Text, Array, Boolean, List, Dict, Image, Element
)
from sim2l.schema.schema import Schema, InputSchema, OutputSchema
from sim2l.schema.registry import (
    register_field_type, get_field_class, _FIELD_REGISTRY
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _PassthroughField(Field):
    """Minimal concrete Field for testing the ABC surface."""

    def validate(self, value):
        return value

    def serialize(self):
        return self.value

    def deserialize(self, data):
        self.value = data

    @classmethod
    def from_dict(cls, data):
        return cls(
            default=data.get("default"),
            optional=data.get("optional", False),
            description=data.get("description", ""),
            metadata=data.get("metadata"),
        )


# ---------------------------------------------------------------------------
# Field base class
# ---------------------------------------------------------------------------

class TestFieldBase(unittest.TestCase):
    """Tests for the abstract Field base class."""

    def _make(self, **kwargs):
        return _PassthroughField(**kwargs)

    def test_default_returned_when_no_value_set(self):
        field = self._make(default=42)
        self.assertEqual(field.value, 42)

    def test_assigned_value_overrides_default(self):
        field = self._make(default=42)
        field.value = 99
        self.assertEqual(field.value, 99)

    def test_none_assignment_falls_back_to_default(self):
        field = self._make(default=7)
        field.value = None
        self.assertEqual(field.value, 7)

    def test_optional_flag_stored(self):
        field = self._make(optional=True)
        self.assertTrue(field.optional)

    def test_description_stored(self):
        field = self._make(description="My field")
        self.assertEqual(field.description, "My field")

    def test_metadata_stored(self):
        field = self._make(metadata={"unit": "K"})
        self.assertEqual(field.metadata["unit"], "K")

    def test_metadata_defaults_to_empty_dict(self):
        field = self._make()
        self.assertEqual(field.metadata, {})

    def test_required_if_stored(self):
        field = self._make(required_if="other_field == True")
        self.assertEqual(field.required_if, "other_field == True")

    def test_type_name_is_class_name(self):
        field = self._make()
        self.assertEqual(field.type_name, "_PassthroughField")

    def test_name_set_by_schema(self):
        field = self._make()
        field._name = "temperature"
        self.assertIn("temperature", repr(field))

    def test_to_dict_contains_required_keys(self):
        field = self._make(optional=True, description="desc")
        d = field.to_dict()
        self.assertIn("type", d)
        self.assertIn("optional", d)
        self.assertIn("description", d)

    def test_to_dict_excludes_none_default(self):
        field = self._make()
        d = field.to_dict()
        self.assertNotIn("default", d)

    def test_to_dict_includes_non_none_default(self):
        field = self._make(default=5)
        d = field.to_dict()
        self.assertEqual(d["default"], 5)

    def test_to_dict_includes_required_if(self):
        field = self._make(required_if="flag")
        d = field.to_dict()
        self.assertEqual(d["required_if"], "flag")

    def test_metadata_merged_into_to_dict(self):
        field = self._make(metadata={"extra": "yes"})
        d = field.to_dict()
        self.assertEqual(d["extra"], "yes")


# ---------------------------------------------------------------------------
# Integer
# ---------------------------------------------------------------------------

class TestIntegerField(unittest.TestCase):
    """Tests for the Integer field type."""

    def test_plain_int_accepted(self):
        f = Integer()
        self.assertEqual(f.validate(3), 3)

    def test_float_coerced_to_int(self):
        f = Integer()
        self.assertEqual(f.validate(3.9), 3)

    def test_string_digit_coerced(self):
        f = Integer()
        self.assertEqual(f.validate("5"), 5)

    def test_non_numeric_string_raises(self):
        f = Integer()
        with self.assertRaises(ValueError):
            f.validate("abc")

    def test_min_boundary_accepted(self):
        f = Integer(min=0)
        self.assertEqual(f.validate(0), 0)

    def test_below_min_raises(self):
        f = Integer(min=0)
        with self.assertRaises(ValueError):
            f.validate(-1)

    def test_max_boundary_accepted(self):
        f = Integer(max=10)
        self.assertEqual(f.validate(10), 10)

    def test_above_max_raises(self):
        f = Integer(max=10)
        with self.assertRaises(ValueError):
            f.validate(11)

    def test_serialize_returns_value(self):
        f = Integer()
        f.value = 7
        self.assertEqual(f.serialize(), 7)

    def test_deserialize_sets_value(self):
        f = Integer()
        f.deserialize(4)
        self.assertEqual(f.value, 4)

    def test_to_dict_includes_min_max(self):
        f = Integer(min=1, max=100)
        d = f.to_dict()
        self.assertEqual(d["min"], 1)
        self.assertEqual(d["max"], 100)

    def test_to_dict_omits_absent_min_max(self):
        f = Integer()
        d = f.to_dict()
        self.assertNotIn("min", d)
        self.assertNotIn("max", d)

    def test_from_dict_roundtrip(self):
        original = Integer(min=2, max=50, default=10, optional=True, description="count")
        d = original.to_dict()
        d["type"] = "Integer"
        restored = Integer.from_dict(d)
        self.assertEqual(restored.min, 2)
        self.assertEqual(restored.max, 50)
        self.assertEqual(restored.default, 10)
        self.assertTrue(restored.optional)
        self.assertEqual(restored.description, "count")


# ---------------------------------------------------------------------------
# Number
# ---------------------------------------------------------------------------

class TestNumberField(unittest.TestCase):
    """Tests for the Number field type (including pint units)."""

    def test_plain_float_accepted(self):
        f = Number()
        result = f.validate(3.14)
        self.assertAlmostEqual(float(result), 3.14)

    def test_int_coerced_to_float(self):
        f = Number()
        result = f.validate(5)
        self.assertAlmostEqual(float(result), 5.0)

    def test_non_numeric_raises(self):
        f = Number()
        with self.assertRaises(ValueError):
            f.validate("not-a-number")

    def test_min_boundary(self):
        f = Number(min=0.0)
        self.assertAlmostEqual(float(f.validate(0.0)), 0.0)

    def test_below_min_raises(self):
        f = Number(min=0.0)
        with self.assertRaises(ValueError):
            f.validate(-0.001)

    def test_max_boundary(self):
        f = Number(max=1.0)
        self.assertAlmostEqual(float(f.validate(1.0)), 1.0)

    def test_above_max_raises(self):
        f = Number(max=1.0)
        with self.assertRaises(ValueError):
            f.validate(1.001)

    def test_serialize_plain_float(self):
        f = Number()
        f.value = 2.5
        self.assertAlmostEqual(f.serialize(), 2.5)

    def test_serialize_none_returns_none(self):
        f = Number()
        self.assertIsNone(f.serialize())

    def test_deserialize_plain_float(self):
        f = Number()
        f.deserialize(9.9)
        self.assertAlmostEqual(float(f.value), 9.9)

    def test_deserialize_none(self):
        f = Number()
        f.deserialize(None)
        self.assertIsNone(f.value)

    def test_to_dict_includes_units(self):
        f = Number(units="kelvin")
        d = f.to_dict()
        self.assertEqual(d["units"], "kelvin")

    def test_from_dict_roundtrip(self):
        original = Number(min=0.0, max=1000.0, default=300.0, description="temp")
        d = original.to_dict()
        restored = Number.from_dict(d)
        self.assertEqual(restored.min, 0.0)
        self.assertEqual(restored.max, 1000.0)
        self.assertEqual(restored.default, 300.0)

    def test_pint_quantity_validate(self):
        try:
            from sim2l.utils.units import get_unit_registry
        except ImportError:
            self.skipTest("pint not available")
        ureg = get_unit_registry()
        f = Number(units="kelvin")
        qty = 350 * ureg("kelvin")
        result = f.validate(qty)
        self.assertAlmostEqual(float(result.magnitude), 350.0)

    def test_pint_quantity_serialize_deserialize(self):
        try:
            from sim2l.utils.units import get_unit_registry
        except ImportError:
            self.skipTest("pint not available")
        ureg = get_unit_registry()
        f = Number(units="kelvin")
        f.value = 400 * ureg("kelvin")
        serialized = f.serialize()
        self.assertIsInstance(serialized, dict)
        self.assertIn("magnitude", serialized)
        self.assertIn("units", serialized)

        f2 = Number(units="kelvin")
        f2.deserialize(serialized)
        self.assertAlmostEqual(float(f2.value.magnitude), 400.0)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

class TestTextField(unittest.TestCase):
    """Tests for the Text field type."""

    def test_plain_string_accepted(self):
        f = Text()
        self.assertEqual(f.validate("hello"), "hello")

    def test_non_string_coerced(self):
        f = Text()
        self.assertEqual(f.validate(123), "123")

    def test_choices_accepted(self):
        f = Text(choices=["a", "b", "c"])
        self.assertEqual(f.validate("b"), "b")

    def test_invalid_choice_raises(self):
        f = Text(choices=["x", "y"])
        with self.assertRaises(ValueError):
            f.validate("z")

    def test_maxlen_at_boundary(self):
        f = Text(maxlen=5)
        self.assertEqual(f.validate("hello"), "hello")

    def test_maxlen_exceeded_raises(self):
        f = Text(maxlen=3)
        with self.assertRaises(ValueError):
            f.validate("toolong")

    def test_serialize_returns_value(self):
        f = Text()
        f.value = "sim2l"
        self.assertEqual(f.serialize(), "sim2l")

    def test_deserialize_sets_value(self):
        f = Text()
        f.deserialize("restored")
        self.assertEqual(f.value, "restored")

    def test_to_dict_includes_choices(self):
        f = Text(choices=["a", "b"])
        d = f.to_dict()
        self.assertEqual(d["choices"], ["a", "b"])

    def test_to_dict_includes_maxlen(self):
        f = Text(maxlen=20)
        d = f.to_dict()
        self.assertEqual(d["maxlen"], 20)

    def test_from_dict_roundtrip(self):
        original = Text(choices=["low", "high"], default="low", description="level")
        d = original.to_dict()
        restored = Text.from_dict(d)
        self.assertEqual(restored.choices, ["low", "high"])
        self.assertEqual(restored.default, "low")


# ---------------------------------------------------------------------------
# Boolean
# ---------------------------------------------------------------------------

class TestBooleanField(unittest.TestCase):
    """Tests for the Boolean field type."""

    def test_true_bool(self):
        f = Boolean()
        self.assertTrue(f.validate(True))

    def test_false_bool(self):
        f = Boolean()
        self.assertFalse(f.validate(False))

    def test_string_true_variants(self):
        f = Boolean()
        for s in ("true", "True", "TRUE", "yes", "Yes", "1"):
            with self.subTest(s=s):
                self.assertTrue(f.validate(s))

    def test_string_false_variants(self):
        f = Boolean()
        for s in ("false", "False", "FALSE", "no", "No", "0"):
            with self.subTest(s=s):
                self.assertFalse(f.validate(s))

    def test_int_truthy(self):
        f = Boolean()
        self.assertTrue(f.validate(1))
        self.assertFalse(f.validate(0))

    def test_invalid_raises(self):
        f = Boolean()
        with self.assertRaises(ValueError):
            f.validate("maybe")

    def test_serialize_deserialize(self):
        f = Boolean()
        f.value = True
        self.assertTrue(f.serialize())
        f.deserialize(False)
        self.assertFalse(f.value)

    def test_from_dict(self):
        f = Boolean.from_dict({"default": True, "optional": False})
        self.assertTrue(f.default)


# ---------------------------------------------------------------------------
# Array
# ---------------------------------------------------------------------------

class TestArrayField(unittest.TestCase):
    """Tests for the Array (numpy) field type."""

    def test_list_converted_to_ndarray(self):
        f = Array()
        result = f.validate([1, 2, 3])
        self.assertIsInstance(result, np.ndarray)

    def test_dtype_enforced(self):
        f = Array(dtype="int32")
        result = f.validate([1.9, 2.1])
        self.assertEqual(result.dtype, np.int32)

    def test_shape_accepted(self):
        f = Array(shape=(2, 3))
        result = f.validate([[1, 2, 3], [4, 5, 6]])
        self.assertEqual(result.shape, (2, 3))

    def test_wrong_rank_raises(self):
        f = Array(shape=(2, 2))
        with self.assertRaises(ValueError):
            f.validate([1, 2, 3, 4])

    def test_wrong_dimension_size_raises(self):
        f = Array(shape=(2, 2))
        with self.assertRaises(ValueError):
            f.validate([[1, 2, 3], [4, 5, 6]])

    def test_none_dimension_allows_any_size(self):
        f = Array(shape=(None, 3))
        result = f.validate([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        self.assertEqual(result.shape, (3, 3))

    def test_serialize_returns_dict(self):
        f = Array()
        f.value = np.array([1.0, 2.0, 3.0])
        s = f.serialize()
        self.assertIn("data", s)
        self.assertIn("dtype", s)
        self.assertIn("shape", s)

    def test_serialize_none_returns_none(self):
        f = Array()
        self.assertIsNone(f.serialize())

    def test_deserialize_from_dict(self):
        f = Array()
        f.value = np.array([[1, 2], [3, 4]], dtype="float64")
        serialized = f.serialize()

        f2 = Array()
        f2.deserialize(serialized)
        np.testing.assert_array_equal(f2.value, np.array([[1, 2], [3, 4]]))

    def test_deserialize_from_plain_list(self):
        f = Array(dtype="float")
        f.deserialize([5.0, 6.0])
        self.assertIsInstance(f.value, np.ndarray)
        self.assertAlmostEqual(f.value[0], 5.0)

    def test_to_dict_includes_dtype_and_shape(self):
        f = Array(dtype="float32", shape=(3, 3))
        d = f.to_dict()
        self.assertEqual(d["dtype"], "float32")
        self.assertEqual(d["shape"], [3, 3])

    def test_from_dict_roundtrip(self):
        original = Array(dtype="float64", shape=(None, 2))
        d = original.to_dict()
        restored = Array.from_dict(d)
        self.assertEqual(restored.dtype, "float64")
        self.assertIsNone(restored.shape[0])
        self.assertEqual(restored.shape[1], 2)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListField(unittest.TestCase):
    """Tests for the List field type."""

    def test_list_accepted(self):
        f = List()
        self.assertEqual(f.validate([1, 2, 3]), [1, 2, 3])

    def test_tuple_coerced_to_list(self):
        f = List()
        result = f.validate((1, 2))
        self.assertIsInstance(result, list)

    def test_non_list_raises(self):
        f = List()
        with self.assertRaises(ValueError):
            f.validate("not a list")

    def test_serialize_returns_list(self):
        f = List()
        f.value = ["a", "b"]
        self.assertEqual(f.serialize(), ["a", "b"])

    def test_serialize_none_returns_empty_list(self):
        f = List()
        self.assertEqual(f.serialize(), [])

    def test_deserialize_sets_value(self):
        f = List()
        f.deserialize([10, 20])
        self.assertEqual(f.value, [10, 20])

    def test_to_dict_includes_item_type(self):
        f = List(item_type="Integer")
        d = f.to_dict()
        self.assertEqual(d["item_type"], "Integer")

    def test_from_dict_roundtrip(self):
        original = List(item_type="Number", optional=True)
        d = original.to_dict()
        restored = List.from_dict(d)
        self.assertEqual(restored.item_type, "Number")
        self.assertTrue(restored.optional)


# ---------------------------------------------------------------------------
# Dict
# ---------------------------------------------------------------------------

class TestDictField(unittest.TestCase):
    """Tests for the Dict field type."""

    def test_dict_accepted(self):
        f = Dict()
        self.assertEqual(f.validate({"a": 1}), {"a": 1})

    def test_non_dict_raises(self):
        f = Dict()
        with self.assertRaises(ValueError):
            f.validate([1, 2])

    def test_serialize_returns_dict(self):
        f = Dict()
        f.value = {"x": 1}
        self.assertEqual(f.serialize(), {"x": 1})

    def test_serialize_none_returns_empty_dict(self):
        f = Dict()
        self.assertEqual(f.serialize(), {})

    def test_deserialize_sets_value(self):
        f = Dict()
        f.deserialize({"key": "val"})
        self.assertEqual(f.value, {"key": "val"})

    def test_to_dict_includes_schema_when_set(self):
        f = Dict(schema={"x": {"type": "Integer"}})
        d = f.to_dict()
        self.assertIn("schema", d)

    def test_from_dict_roundtrip(self):
        original = Dict(optional=True, description="config blob")
        d = original.to_dict()
        restored = Dict.from_dict(d)
        self.assertTrue(restored.optional)


# ---------------------------------------------------------------------------
# Image (optional — skipped when PIL unavailable)
# ---------------------------------------------------------------------------

class TestImageField(unittest.TestCase):
    """Tests for the Image field type (requires PIL)."""

    def setUp(self):
        try:
            from PIL import Image as PILImage
            self.PILImage = PILImage
        except ImportError:
            self.skipTest("PIL not available")

    def test_pil_image_accepted(self):
        from sim2l.schema.types import Image
        f = Image()
        img = self.PILImage.new("RGB", (10, 10))
        result = f.validate(img)
        self.assertIsInstance(result, self.PILImage.Image)

    def test_invalid_type_raises(self):
        from sim2l.schema.types import Image
        f = Image()
        with self.assertRaises(ValueError):
            f.validate(12345)

    def test_serialize_deserialize_roundtrip(self):
        from sim2l.schema.types import Image
        f = Image()
        img = self.PILImage.new("RGB", (4, 4))
        f.value = img
        serialized = f.serialize()
        self.assertIn("data", serialized)
        self.assertIn("mode", serialized)

        f2 = Image()
        f2.deserialize(serialized)
        self.assertIsInstance(f2.value, self.PILImage.Image)
        self.assertEqual(f2.value.size, (4, 4))

    def test_serialize_none_returns_none(self):
        from sim2l.schema.types import Image
        f = Image()
        self.assertIsNone(f.serialize())


# ---------------------------------------------------------------------------
# Element (optional — skipped when mendeleev unavailable)
# ---------------------------------------------------------------------------

class TestElementField(unittest.TestCase):
    """Tests for the Element field type (requires mendeleev)."""

    def setUp(self):
        try:
            import mendeleev  # noqa: F401
        except ImportError:
            self.skipTest("mendeleev not available")

    def test_valid_symbol_accepted(self):
        f = Element()
        result = f.validate("Fe")
        self.assertEqual(result.symbol, "Fe")

    def test_invalid_symbol_raises(self):
        f = Element()
        with self.assertRaises(ValueError):
            f.validate("Xx")

    def test_choices_enforced(self):
        f = Element(choices=["Si", "Ge"])
        with self.assertRaises(ValueError):
            f.validate("Fe")

    def test_serialize_returns_symbol(self):
        f = Element()
        f.value = f.validate("Au")
        self.assertEqual(f.serialize(), "Au")

    def test_serialize_none_returns_none(self):
        f = Element()
        self.assertIsNone(f.serialize())

    def test_deserialize_sets_element(self):
        f = Element()
        f.deserialize("Cu")
        self.assertEqual(f.value.symbol, "Cu")

    def test_from_dict_roundtrip(self):
        original = Element(choices=["Si", "Ge"], description="semiconductor")
        d = original.to_dict()
        restored = Element.from_dict(d)
        self.assertEqual(restored.choices, ["Si", "Ge"])


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry(unittest.TestCase):
    """Tests for the field type registry."""

    def test_all_builtin_types_registered(self):
        for name in ("Integer", "Number", "Text", "Array", "Image",
                     "Element", "Boolean", "List", "Dict"):
            with self.subTest(name=name):
                cls = get_field_class(name)
                self.assertIsNotNone(cls)

    def test_lookup_returns_correct_class(self):
        self.assertIs(get_field_class("Integer"), Integer)
        self.assertIs(get_field_class("Number"), Number)
        self.assertIs(get_field_class("Text"), Text)
        self.assertIs(get_field_class("Boolean"), Boolean)
        self.assertIs(get_field_class("Array"), Array)
        self.assertIs(get_field_class("List"), List)
        self.assertIs(get_field_class("Dict"), Dict)

    def test_unknown_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_field_class("NonExistentType")

    def test_custom_type_can_be_registered_and_retrieved(self):
        register_field_type("_TestPassthrough", _PassthroughField)
        cls = get_field_class("_TestPassthrough")
        self.assertIs(cls, _PassthroughField)

    def test_reregistering_overwrites_previous(self):
        register_field_type("_Overwrite", Integer)
        register_field_type("_Overwrite", Text)
        self.assertIs(get_field_class("_Overwrite"), Text)


# ---------------------------------------------------------------------------
# Schema container
# ---------------------------------------------------------------------------

class TestSchemaContainer(unittest.TestCase):
    """Tests for the Schema class container mechanics."""

    def _make_schema(self):
        return Schema({
            "count": Integer(min=0, default=1),
            "label": Text(optional=True),
            "active": Boolean(default=False),
        })

    def test_field_access_by_attribute(self):
        s = self._make_schema()
        self.assertIsInstance(s.count, Integer)

    def test_attribute_access_missing_raises(self):
        s = self._make_schema()
        with self.assertRaises(AttributeError):
            _ = s.nonexistent

    def test_field_access_by_item(self):
        s = self._make_schema()
        self.assertIsInstance(s["count"], Integer)

    def test_contains_existing_field(self):
        s = self._make_schema()
        self.assertIn("count", s)

    def test_contains_missing_field(self):
        s = self._make_schema()
        self.assertNotIn("missing", s)

    def test_iter_yields_field_names(self):
        s = self._make_schema()
        names = list(s)
        self.assertIn("count", names)
        self.assertIn("label", names)
        self.assertIn("active", names)

    def test_keys(self):
        s = self._make_schema()
        self.assertIn("count", s.keys())

    def test_values_are_field_instances(self):
        s = self._make_schema()
        for field in s.values():
            self.assertIsInstance(field, Field)

    def test_items_yields_name_field_pairs(self):
        s = self._make_schema()
        for name, field in s.items():
            self.assertIsInstance(name, str)
            self.assertIsInstance(field, Field)

    def test_field_name_set_on_init(self):
        s = self._make_schema()
        self.assertEqual(s.count._name, "count")

    def test_set_attribute_sets_field_value(self):
        s = self._make_schema()
        s.count = 5
        self.assertEqual(s.count.value, 5)

    def test_validate_required_field_present(self):
        s = self._make_schema()
        validated = s.validate({"count": 3})
        self.assertEqual(validated["count"], 3)

    def test_validate_uses_default_for_missing_optional_field(self):
        s = self._make_schema()
        validated = s.validate({"count": 1})
        # label is optional and has no default — should not appear
        self.assertNotIn("label", validated)

    def test_validate_missing_required_raises(self):
        # Use a schema with a field that has no default and is not optional
        s = Schema({"required_field": Integer()})
        with self.assertRaises(ValueError):
            s.validate({})

    def test_validate_unexpected_field_raises(self):
        s = self._make_schema()
        with self.assertRaises(ValueError):
            s.validate({"count": 1, "unknown": "x"})

    def test_set_values_and_get_values(self):
        s = self._make_schema()
        s.set_values({"count": 7, "active": True})
        values = s.get_values()
        self.assertEqual(values["count"], 7)
        self.assertTrue(values["active"])

    def test_get_values_excludes_none_fields(self):
        s = self._make_schema()
        values = s.get_values()
        # label was never set, has no default — absent from get_values
        self.assertNotIn("label", values)

    def test_serialize_and_deserialize_roundtrip(self):
        s = self._make_schema()
        s.set_values({"count": 9, "active": False})
        serialized = s.serialize()

        s2 = Schema({
            "count": Integer(min=0),
            "label": Text(optional=True),
            "active": Boolean(),
        })
        s2.deserialize(serialized)
        self.assertEqual(s2.count.value, 9)
        self.assertFalse(s2.active.value)

    def test_to_dict_returns_field_specs(self):
        s = self._make_schema()
        d = s.to_dict()
        self.assertIn("count", d)
        self.assertEqual(d["count"]["type"], "Integer")

    def test_from_dict_constructs_schema(self):
        spec = {
            "temperature": {"type": "Number", "min": 0.0, "description": "K"},
            "mode": {"type": "Text", "choices": ["fast", "slow"], "optional": True},
        }
        s = Schema.from_dict(spec)
        self.assertIn("temperature", s)
        self.assertIn("mode", s)
        self.assertIsInstance(s["temperature"], Number)
        self.assertIsInstance(s["mode"], Text)

    def test_from_yaml_constructs_schema(self):
        yaml_str = """
temperature:
  type: Number
  min: 0.0
  description: Temperature in K
iterations:
  type: Integer
  min: 1
  default: 100
"""
        s = Schema.from_yaml(yaml_str)
        self.assertIn("temperature", s)
        self.assertIn("iterations", s)
        self.assertIsInstance(s["temperature"], Number)
        self.assertEqual(s["iterations"].default, 100)

    def test_from_yaml_empty_string_returns_empty_schema(self):
        s = Schema.from_yaml("")
        self.assertEqual(list(s.keys()), [])

    def test_repr_includes_field_names(self):
        s = self._make_schema()
        r = repr(s)
        self.assertIn("count", r)


# ---------------------------------------------------------------------------
# InputSchema / OutputSchema subclasses
# ---------------------------------------------------------------------------

class TestInputOutputSchemaSubclasses(unittest.TestCase):
    """Tests that InputSchema and OutputSchema are proper Schema subclasses."""

    def test_input_schema_is_schema(self):
        s = InputSchema({"n": Integer()})
        self.assertIsInstance(s, Schema)

    def test_output_schema_is_schema(self):
        s = OutputSchema({"result": Number()})
        self.assertIsInstance(s, Schema)

    def test_input_schema_validate(self):
        s = InputSchema({"n": Integer(min=1)})
        validated = s.validate({"n": 5})
        self.assertEqual(validated["n"], 5)

    def test_output_schema_serialize(self):
        s = OutputSchema({"result": Number()})
        s.result = 3.14
        serialized = s.serialize()
        self.assertAlmostEqual(serialized["result"], 3.14)


# ---------------------------------------------------------------------------
# End-to-end roundtrip — realistic simulation contract
# ---------------------------------------------------------------------------

class TestSchemaEndToEnd(unittest.TestCase):
    """
    Simulates the full schema lifecycle used by sim2l:
    - Define InputSchema and OutputSchema
    - Validate raw user-supplied inputs
    - Serialize inputs for storage
    - Deserialize inputs from storage
    - Set output values and serialize for persistence
    - Deserialize outputs and verify typed access
    """

    @classmethod
    def setUpClass(cls):
        cls.input_schema = InputSchema({
            "temperature": Number(min=0.0, max=5000.0, description="K"),
            "power":       Number(min=0.0, description="W"),
            "iterations":  Integer(min=1, max=10000, default=100),
            "mode":        Text(choices=["fast", "accurate"], default="accurate"),
            "grid":        Array(dtype="float64", shape=(None, None)),
        })

        cls.output_schema = OutputSchema({
            "max_temperature": Number(description="K"),
            "converged":       Boolean(),
            "heat_map":        Array(dtype="float64"),
            "summary":         Dict(optional=True),
        })

    def _raw_inputs(self):
        return {
            "temperature": 350.0,
            "power": 20.0,
            "iterations": 200,
            "mode": "fast",
            "grid": [[1.0, 2.0], [3.0, 4.0]],
        }

    def _raw_outputs(self):
        return {
            "max_temperature": 412.7,
            "converged": True,
            "heat_map": [100.0, 200.0, 300.0],
        }

    def test_input_validation_succeeds(self):
        validated = self.input_schema.validate(self._raw_inputs())
        self.assertAlmostEqual(float(validated["temperature"]), 350.0)
        self.assertEqual(validated["iterations"], 200)
        self.assertEqual(validated["mode"], "fast")

    def test_input_default_applied(self):
        data = dict(self._raw_inputs())
        del data["iterations"]
        del data["mode"]
        validated = self.input_schema.validate(data)
        self.assertEqual(validated["iterations"], 100)
        self.assertEqual(validated["mode"], "accurate")

    def test_invalid_mode_rejected(self):
        data = dict(self._raw_inputs())
        data["mode"] = "turbo"
        with self.assertRaises(ValueError):
            self.input_schema.validate(data)

    def test_temperature_below_min_rejected(self):
        data = dict(self._raw_inputs())
        data["temperature"] = -1.0
        with self.assertRaises(ValueError):
            self.input_schema.validate(data)

    def test_input_serialize_deserialize_roundtrip(self):
        self.input_schema.set_values(self._raw_inputs())
        serialized = self.input_schema.serialize()

        restored = InputSchema({
            "temperature": Number(min=0.0),
            "power":       Number(min=0.0),
            "iterations":  Integer(min=1, default=100),
            "mode":        Text(choices=["fast", "accurate"], default="accurate"),
            "grid":        Array(dtype="float64", shape=(None, None)),
        })
        restored.deserialize(serialized)

        self.assertAlmostEqual(float(restored.temperature.value), 350.0)
        self.assertEqual(restored.mode.value, "fast")
        self.assertEqual(restored.iterations.value, 200)

    def test_output_set_and_serialize(self):
        self.output_schema.set_values(self._raw_outputs())
        serialized = self.output_schema.serialize()

        self.assertIn("max_temperature", serialized)
        self.assertIn("converged", serialized)
        self.assertIn("heat_map", serialized)

    def test_output_deserialize_and_access(self):
        self.output_schema.set_values(self._raw_outputs())
        serialized = self.output_schema.serialize()

        restored = OutputSchema({
            "max_temperature": Number(),
            "converged":       Boolean(),
            "heat_map":        Array(dtype="float64"),
            "summary":         Dict(optional=True),
        })
        restored.deserialize(serialized)

        self.assertAlmostEqual(float(restored.max_temperature.value), 412.7)
        self.assertTrue(restored.converged.value)
        self.assertIsInstance(restored.heat_map.value, np.ndarray)
        self.assertAlmostEqual(restored.heat_map.value[1], 200.0)

    def test_optional_output_absent_is_fine(self):
        # summary is optional and not in raw outputs
        self.output_schema.set_values(self._raw_outputs())
        values = self.output_schema.get_values()
        self.assertNotIn("summary", values)

    def test_schema_to_dict_and_from_dict_roundtrip(self):
        spec = self.input_schema.to_dict()
        restored = Schema.from_dict(spec)

        self.assertIn("temperature", restored)
        self.assertIn("iterations", restored)
        self.assertIsInstance(restored["temperature"], Number)
        self.assertIsInstance(restored["iterations"], Integer)


# ---------------------------------------------------------------------------
# Gap coverage tests
# ---------------------------------------------------------------------------

class TestImageFieldGaps(unittest.TestCase):
    """Gap tests for Image field: file path loading and from_dict."""

    def setUp(self):
        try:
            from PIL import Image as PILImage
            self.PILImage = PILImage
        except ImportError:
            self.skipTest("PIL not available")

    def test_validate_from_file_path(self):
        """Image.validate should open a file path string."""
        import tempfile, os
        from sim2l.schema.types import Image
        img = self.PILImage.new("RGB", (8, 8))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
            img.save(tmp_path)
        try:
            f_field = Image()
            result = f_field.validate(tmp_path)
            self.assertIsInstance(result, self.PILImage.Image)
            size = result.size  # read before closing
            result.close()      # release file handle (required on Windows)
            self.assertEqual(size, (8, 8))
        finally:
            os.unlink(tmp_path)

    def test_from_dict_roundtrip(self):
        """Image.from_dict should restore optional and description."""
        from sim2l.schema.types import Image
        original = Image(optional=True, description="output image")
        d = original.to_dict()
        restored = Image.from_dict(d)
        self.assertTrue(restored.optional)
        self.assertEqual(restored.description, "output image")


class TestNumberDeserializeGaps(unittest.TestCase):
    """Gap tests for Number.deserialize with dict missing 'units' key."""

    def test_deserialize_dict_without_units_gives_plain_float(self):
        f = Number()
        f.deserialize({"magnitude": 42.0})
        self.assertAlmostEqual(float(f.value), 42.0)
        # Should be a plain float, not a pint Quantity
        self.assertFalse(hasattr(f.value, "magnitude"))


class TestArrayDeserializeGaps(unittest.TestCase):
    """Gap tests for Array.deserialize(None)."""

    def test_deserialize_none_sets_value_to_none(self):
        f = Array()
        f.value = np.array([1.0, 2.0])
        f.deserialize(None)
        self.assertIsNone(f._value)


class TestBooleanToDictGaps(unittest.TestCase):
    """Gap tests for Boolean.to_dict (inherited, no override)."""

    def test_to_dict_contains_required_keys(self):
        f = Boolean(optional=True, description="flag")
        d = f.to_dict()
        self.assertEqual(d["type"], "Boolean")
        self.assertTrue(d["optional"])
        self.assertEqual(d["description"], "flag")

    def test_to_dict_with_default(self):
        f = Boolean(default=True)
        d = f.to_dict()
        self.assertTrue(d["default"])


class TestRequiredIfGaps(unittest.TestCase):
    """
    Gap tests documenting that required_if is stored and serialised
    but NOT enforced by Schema.validate.

    The tests below verify current behaviour. If required_if enforcement
    is ever implemented, update these tests accordingly.
    """

    def test_required_if_stored_on_field(self):
        f = Integer(required_if="use_advanced == True")
        self.assertEqual(f.required_if, "use_advanced == True")

    def test_required_if_appears_in_to_dict(self):
        f = Integer(required_if="flag")
        d = f.to_dict()
        self.assertEqual(d["required_if"], "flag")

    def test_required_if_field_not_enforced_by_schema_validate(self):
        """Schema.validate currently ignores required_if — field is treated as
        optional regardless of the condition value."""
        s = Schema({
            "use_advanced": Boolean(default=False),
            "advanced_param": Integer(optional=True, required_if="use_advanced == True"),
        })
        # Even though use_advanced=True, advanced_param absence raises no error.
        validated = s.validate({"use_advanced": True})
        self.assertNotIn("advanced_param", validated)


class TestDictNestedSchemaGaps(unittest.TestCase):
    """
    Gap tests documenting that Dict.validate ignores nested schema (TODO).

    Verifies current passthrough behaviour so regressions are caught when
    the TODO is eventually implemented.
    """

    def test_nested_schema_stored_in_field(self):
        schema_spec = {"x": {"type": "Integer"}}
        f = Dict(schema=schema_spec)
        self.assertEqual(f.schema, schema_spec)

    def test_validate_does_not_enforce_nested_schema(self):
        """Dict.validate currently accepts any dict regardless of nested schema."""
        f = Dict(schema={"x": {"type": "Integer"}})
        # 'x' should be Integer but passing a string is accepted (no enforcement)
        result = f.validate({"x": "not-an-integer", "extra_key": True})
        self.assertEqual(result["x"], "not-an-integer")

    def test_nested_schema_survives_to_dict_from_dict_roundtrip(self):
        schema_spec = {"count": {"type": "Integer", "min": 0}}
        original = Dict(schema=schema_spec)
        d = original.to_dict()
        restored = Dict.from_dict(d)
        self.assertEqual(restored.schema, schema_spec)


class TestListItemTypeGaps(unittest.TestCase):
    """
    Gap tests documenting that List.item_type is stored and serialised
    but NOT enforced during validation.
    """

    def test_item_type_stored(self):
        f = List(item_type="Integer")
        self.assertEqual(f.item_type, "Integer")

    def test_item_type_not_enforced_on_validate(self):
        """List.validate accepts any element regardless of item_type."""
        f = List(item_type="Integer")
        result = f.validate(["not", "integers", True, 3.14])
        self.assertEqual(result, ["not", "integers", True, 3.14])

    def test_item_type_survives_roundtrip(self):
        original = List(item_type="Number", optional=True)
        d = original.to_dict()
        restored = List.from_dict(d)
        self.assertEqual(restored.item_type, "Number")


class TestSchemaDeserializeGaps(unittest.TestCase):
    """
    Gap tests for Schema.deserialize behaviour on unknown keys.

    Schema.validate raises on extra fields, but Schema.deserialize silently
    ignores keys that are not in the schema.  These tests document that
    inconsistency so it is not accidentally changed without notice.
    """

    def test_deserialize_unknown_key_is_silently_ignored(self):
        s = Schema({"count": Integer()})
        s.deserialize({"count": 5, "rogue_key": "surprise"})
        self.assertEqual(s.count.value, 5)
        # rogue_key was silently dropped — no AttributeError or ValueError
        self.assertNotIn("rogue_key", s)

    def test_validate_raises_on_same_extra_key(self):
        """Contrast: validate() raises where deserialize() does not."""
        s = Schema({"count": Integer()})
        with self.assertRaises(ValueError):
            s.validate({"count": 5, "rogue_key": "surprise"})

    def test_deserialize_empty_dict_leaves_schema_unchanged(self):
        s = Schema({"count": Integer(default=3)})
        s.deserialize({})
        self.assertEqual(s.count.value, 3)


class TestNumberUnitConversionGaps(unittest.TestCase):
    """Gap tests for Number.validate unit-conversion error path."""

    def setUp(self):
        try:
            from sim2l.utils.units import get_unit_registry
            self.ureg = get_unit_registry()
        except ImportError:
            self.skipTest("pint not available")

    def test_incompatible_units_raises_value_error(self):
        """Passing a Quantity with incompatible dimensions should raise ValueError."""
        f = Number(units="kelvin")
        with self.assertRaises(ValueError):
            f.validate(5.0 * self.ureg.meter)

    def test_compatible_units_converted(self):
        """A Quantity in compatible units is auto-converted (e.g. degC → K)."""
        f = Number(units="kelvin")
        qty = self.ureg.Quantity(0.0, "degC")
        result = f.validate(qty)
        self.assertAlmostEqual(float(result.magnitude), 273.15, places=1)


class TestArrayValidateGaps(unittest.TestCase):
    """Gap tests for Array.validate with non-array-convertible input."""

    def test_empty_list_produces_empty_array(self):
        f = Array(dtype="float")
        result = f.validate([])
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.size, 0)

    def test_nested_ragged_list_raises(self):
        """A ragged list cannot be turned into a fixed-shape ndarray."""
        f = Array(dtype="float", shape=(2, 2))
        with self.assertRaises((ValueError, Exception)):
            f.validate([[1, 2], [3]])  # ragged — numpy raises on shape check

    def test_non_numeric_list_raises(self):
        """Passing strings to a float-dtype Array should raise during np.asarray."""
        f = Array(dtype="float")
        with self.assertRaises((ValueError, TypeError)):
            f.validate(["a", "b", "c"])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestFieldBase,
        TestIntegerField,
        TestNumberField,
        TestTextField,
        TestBooleanField,
        TestArrayField,
        TestListField,
        TestDictField,
        TestImageField,
        TestElementField,
        TestRegistry,
        TestSchemaContainer,
        TestInputOutputSchemaSubclasses,
        TestSchemaEndToEnd,
        TestImageFieldGaps,
        TestNumberDeserializeGaps,
        TestArrayDeserializeGaps,
        TestBooleanToDictGaps,
        TestRequiredIfGaps,
        TestDictNestedSchemaGaps,
        TestListItemTypeGaps,
        TestSchemaDeserializeGaps,
        TestNumberUnitConversionGaps,
        TestArrayValidateGaps,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
