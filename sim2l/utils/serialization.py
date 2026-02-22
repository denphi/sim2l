# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""JSON serialization utilities"""

import json
import jsonpickle
import numpy as np
from typing import Any


def serialize_for_hashing(value: Any) -> Any:
    """Convert value to a JSON-serializable primitive for hashing/caching.

    Handles:
    - Pint Quantity objects → magnitude (units discarded for hash key)
    - NumPy arrays → nested Python lists
    - NumPy scalars → Python int/float
    - Lists/tuples → lists (recursively processed)
    - Dicts → dicts (recursively processed)
    - All other types returned unchanged
    """
    if hasattr(value, 'magnitude'):
        return serialize_for_hashing(value.magnitude)
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
    """Custom JSON encoder that handles NumPy arrays and other types"""

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

        # Fallback to jsonpickle for complex objects
        try:
            return json.loads(jsonpickle.encode(obj))
        except Exception:
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
    def decode_dict(cls, data: dict) -> dict:
        """Recursively decode a dictionary"""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = cls.decode(cls.decode_dict(value))
            elif isinstance(value, list):
                result[key] = [cls.decode(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result


def serialize_value(value: Any) -> str:
    """Serialize a value to JSON string using custom encoder

    Args:
        value: Value to serialize

    Returns:
        JSON string
    """
    return json.dumps(value, cls=JsonEncoder, sort_keys=True)


def deserialize_value(json_str: str) -> Any:
    """Deserialize a JSON string using custom decoder

    Args:
        json_str: JSON string

    Returns:
        Deserialized value
    """
    return json.loads(json_str, object_hook=JsonDecoder.decode)
