# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""JSON serialization utilities"""

# Keep `X | None` annotations evaluatable on Python 3.9 — sim2l is imported by
# arc inside the legacy-FEniCS/DOLFIN conda env, which ships py39-only builds.
from __future__ import annotations

import json
import jsonpickle
import numpy as np
from typing import Any


def serialize_for_hashing(value: Any) -> Any:
    """Convert value to a JSON-serializable primitive for hashing/caching.

    Handles:
    - Pint Quantity objects → {"__magnitude__": ..., "__units__": str} (units preserved)
    - NumPy arrays → nested Python lists
    - NumPy scalars → Python int/float
    - Lists/tuples → lists (recursively processed)
    - Dicts → dicts (recursively processed)
    - All other types returned unchanged
    """
    if hasattr(value, 'magnitude') and hasattr(value, 'units'):
        return {
            "__magnitude__": serialize_for_hashing(value.magnitude),
            "__units__": str(value.units),
        }
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [serialize_for_hashing(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_for_hashing(v) for k, v in value.items()}
    return value


def serialize_output_value(value: Any) -> Any:
    """Convert a simulation output value to a JSON-serializable form.

    Used when serializing outputs for storage or API transmission.
    Handles Pint quantities, NumPy types, and falls back to str().
    """
    if hasattr(value, 'magnitude'):
        value = value.magnitude
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


class JsonEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles NumPy arrays and other types.

    By default this encoder does NOT use ``jsonpickle`` for unknown objects:
    jsonpickle's decoder can deserialize arbitrary classes, which is RCE-prone
    when consumed by anything that round-trips untrusted data. Callers that
    need the legacy behaviour (e.g. for in-process artifact round-tripping
    where the source is trusted) can opt back in via ``allow_pickle=True``.
    """

    # Class-level default. Construct with ``allow_pickle=True`` to override.
    allow_pickle: bool = False

    def __init__(self, *args, allow_pickle: bool | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if allow_pickle is not None:
            self.allow_pickle = allow_pickle

    def default(self, obj):
        """Encode object to JSON-serializable format"""
        # NumPy arrays
        if isinstance(obj, np.ndarray):
            return {
                "__type__": "ndarray",
                "data": obj.tolist(),
                "dtype": str(obj.dtype),
                "shape": obj.shape,
            }

        # NumPy scalars
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()

        # Pint Quantity (if has units)
        if hasattr(obj, 'magnitude') and hasattr(obj, 'units'):
            return {
                "__type__": "quantity",
                "magnitude": float(obj.magnitude),
                "units": str(obj.units),
            }

        # PIL Image
        if hasattr(obj, 'mode') and hasattr(obj, 'size') and hasattr(obj, 'tobytes'):
            import base64
            import io
            buffer = io.BytesIO()
            obj.save(buffer, format='PNG')
            return {
                "__type__": "image",
                "data": base64.b64encode(buffer.getvalue()).decode(),
                "mode": obj.mode,
                "size": obj.size,
            }

        if self.allow_pickle:
            # Last-resort path for trusted inputs only. jsonpickle's output
            # embeds class names that the decoder would later resolve and
            # instantiate — so do not use this with data crossing trust
            # boundaries (REST APIs, untrusted disk, etc.).
            try:
                return json.loads(jsonpickle.encode(obj))
            except Exception:
                pass
        return super().default(obj)


class JsonDecoder:
    """Custom JSON decoder that handles custom types"""

    @staticmethod
    def decode(obj: Any) -> Any:
        """Decode JSON object to Python object"""
        if isinstance(obj, dict) and "__type__" in obj:
            obj_type = obj["__type__"]

            if obj_type == "ndarray":
                return np.array(obj["data"], dtype=obj["dtype"]).reshape(obj["shape"])

            elif obj_type == "quantity":
                from ..utils.units import get_unit_registry
                ureg = get_unit_registry()
                return obj["magnitude"] * ureg(obj["units"])

            elif obj_type == "image":
                from PIL import Image
                import base64
                import io
                image_data = base64.b64decode(obj["data"])
                return Image.open(io.BytesIO(image_data))

        return obj

    @classmethod
    def _decode_list(cls, items: list) -> list:
        """Recurse into a list, handling nested dicts/lists symmetrically."""
        result: list = []
        for item in items:
            if isinstance(item, dict):
                result.append(cls.decode(cls.decode_dict(item)))
            elif isinstance(item, list):
                result.append(cls._decode_list(item))
            else:
                result.append(item)
        return result

    @classmethod
    def decode_dict(cls, data: dict) -> dict:
        """Recursively decode a dictionary.

        Review item #S9: lists of lists now recurse into the inner list
        rather than passing it through unchanged.
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = cls.decode(cls.decode_dict(value))
            elif isinstance(value, list):
                result[key] = cls._decode_list(value)
            else:
                result[key] = value
        return result


def serialize_value(value: Any, *, allow_pickle: bool = False) -> str:
    """Serialize a value to JSON string using custom encoder.

    Args:
        value: Value to serialize.
        allow_pickle: When True, the encoder falls back to ``jsonpickle`` for
            objects it doesn't know how to handle. Off by default — the
            decoded form embeds class names and is RCE-prone when fed back
            through a class-aware decoder. Review item #S10.

    Returns:
        JSON string
    """
    encoder_cls = JsonEncoder
    if allow_pickle:
        class _PickleEncoder(JsonEncoder):
            pass
        _PickleEncoder.allow_pickle = True
        encoder_cls = _PickleEncoder
    return json.dumps(value, cls=encoder_cls, sort_keys=True)


def deserialize_value(json_str: str) -> Any:
    """Deserialize a JSON string using custom decoder

    Args:
        json_str: JSON string

    Returns:
        Deserialized value
    """
    return json.loads(json_str, object_hook=JsonDecoder.decode)
