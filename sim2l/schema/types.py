# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Concrete field type implementations"""

from typing import Any, Optional, List as ListType, Union
import numpy as np

from .field import Field
from ..utils.units import get_unit_registry
from pint import Quantity


class Integer(Field):
    """Integer field with min/max validation"""

    def __init__(
        self,
        *,
        min: Optional[int] = None,
        max: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.min = min
        self.max = max

    def validate(self, value: Any) -> int:
        """Validate integer"""
        try:
            val = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Cannot convert {value} to integer")

        if self.min is not None and val < self.min:
            raise ValueError(f"Value {val} < minimum {self.min}")
        if self.max is not None and val > self.max:
            raise ValueError(f"Value {val} > maximum {self.max}")

        return val

    def serialize(self) -> int:
        return self.value

    def deserialize(self, data: int):
        self.value = data

    @classmethod
    def from_dict(cls, data: dict) -> 'Integer':
        return cls(
            min=data.get('min'),
            max=data.get('max'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.min is not None:
            result['min'] = self.min
        if self.max is not None:
            result['max'] = self.max
        return result


class Number(Field):
    """Numeric field with units support"""

    def __init__(
        self,
        *,
        units: Optional[str] = None,
        min: Optional[float] = None,
        max: Optional[float] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.units = units
        self.min = min
        self.max = max

    def validate(self, value: Any) -> Union[float, Quantity]:
        """Validate number with optional units"""
        ureg = get_unit_registry()

        # If value already has units (Pint Quantity)
        if hasattr(value, 'magnitude'):
            if self.units:
                # Convert to target units
                try:
                    value = value.to(self.units)
                except Exception as e:
                    raise ValueError(f"Cannot convert units: {e}")
            magnitude = value.magnitude
        else:
            # Plain number
            try:
                magnitude = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert {value} to number")

            # Attach units if specified
            if self.units:
                value = magnitude * ureg(self.units)

        # Validate range
        if self.min is not None and magnitude < self.min:
            raise ValueError(f"Value {magnitude} < minimum {self.min}")
        if self.max is not None and magnitude > self.max:
            raise ValueError(f"Value {magnitude} > maximum {self.max}")

        return value

    def serialize(self) -> Union[dict, float]:
        """Serialize with units"""
        val = self.value
        if val is None:
            return None

        if hasattr(val, 'magnitude'):
            return {
                'magnitude': float(val.magnitude),
                'units': str(val.units)
            }
        return float(val)

    def deserialize(self, data: Union[dict, float]):
        """Deserialize number with units"""
        if data is None:
            self.value = None
        elif isinstance(data, dict):
            magnitude = data['magnitude']
            units = data.get('units')
            if units:
                ureg = get_unit_registry()
                self.value = magnitude * ureg(units)
            else:
                self.value = magnitude
        else:
            self.value = float(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'Number':
        return cls(
            units=data.get('units'),
            min=data.get('min'),
            max=data.get('max'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.units:
            result['units'] = self.units
        if self.min is not None:
            result['min'] = self.min
        if self.max is not None:
            result['max'] = self.max
        return result


class Text(Field):
    """Text field with optional choices and max length"""

    def __init__(
        self,
        *,
        choices: Optional[ListType[str]] = None,
        maxlen: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.choices = choices
        self.maxlen = maxlen

    def validate(self, value: Any) -> str:
        """Validate text"""
        val = str(value)

        if self.maxlen and len(val) > self.maxlen:
            raise ValueError(f"Text length {len(val)} > maximum {self.maxlen}")

        if self.choices and val not in self.choices:
            raise ValueError(f"Value '{val}' not in allowed choices: {self.choices}")

        return val

    def serialize(self) -> str:
        return self.value

    def deserialize(self, data: str):
        self.value = data

    @classmethod
    def from_dict(cls, data: dict) -> 'Text':
        return cls(
            choices=data.get('choices'),
            maxlen=data.get('maxlen'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.choices:
            result['choices'] = self.choices
        if self.maxlen:
            result['maxlen'] = self.maxlen
        return result


class Array(Field):
    """NumPy array field"""

    def __init__(
        self,
        *,
        dtype: str = 'float',
        shape: Optional[tuple] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.dtype = dtype
        self.shape = shape

    def validate(self, value: Any) -> np.ndarray:
        """Validate array"""
        arr = np.asarray(value, dtype=self.dtype)

        if self.shape:
            # Check shape (None means any size for that dimension)
            if len(arr.shape) != len(self.shape):
                raise ValueError(f"Array rank {len(arr.shape)} != expected {len(self.shape)}")

            for i, (actual, expected) in enumerate(zip(arr.shape, self.shape)):
                if expected is not None and actual != expected:
                    raise ValueError(f"Array dimension {i}: {actual} != expected {expected}")

        return arr

    def serialize(self) -> dict:
        """Serialize array"""
        arr = self.value
        if arr is None:
            return None
        return {
            'data': arr.tolist(),
            'dtype': str(arr.dtype),
            'shape': list(arr.shape)
        }

    def deserialize(self, data: Union[dict, list]):
        """Deserialize array"""
        if data is None:
            self.value = None
        elif isinstance(data, dict):
            arr = np.array(data['data'], dtype=data['dtype'])
            self.value = arr.reshape(data['shape'])
        else:
            self.value = np.array(data, dtype=self.dtype)

    @classmethod
    def from_dict(cls, data: dict) -> 'Array':
        shape = data.get('shape')
        if shape:
            # Convert None strings back to None
            shape = tuple(None if s == 'null' or s is None else s for s in shape)
        return cls(
            dtype=data.get('dtype', 'float'),
            shape=shape,
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        result['dtype'] = self.dtype
        if self.shape:
            result['shape'] = list(self.shape)
        return result


class Boolean(Field):
    """Boolean field"""

    def validate(self, value: Any) -> bool:
        """Validate boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ('true', 'yes', '1'):
                return True
            if value.lower() in ('false', 'no', '0'):
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError(f"Cannot convert {value} to boolean")

    def serialize(self) -> bool:
        return self.value

    def deserialize(self, data: bool):
        self.value = data

    @classmethod
    def from_dict(cls, data: dict) -> 'Boolean':
        return cls(
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )


class Image(Field):
    """PIL Image field"""

    def validate(self, value: Any):
        """Validate image"""
        from PIL import Image as PILImage

        if isinstance(value, str):
            # Load from file path
            return PILImage.open(value)
        elif isinstance(value, PILImage.Image):
            return value
        else:
            raise ValueError(f"Cannot convert {type(value)} to Image")

    def serialize(self) -> dict:
        """Serialize image"""
        import base64
        import io

        if self.value is None:
            return None

        buffer = io.BytesIO()
        self.value.save(buffer, format='PNG')
        return {
            'data': base64.b64encode(buffer.getvalue()).decode(),
            'mode': self.value.mode,
            'size': self.value.size,
        }

    def deserialize(self, data: dict):
        """Deserialize image"""
        from PIL import Image as PILImage
        import base64
        import io

        if data is None:
            self.value = None
        else:
            image_data = base64.b64decode(data['data'])
            self.value = PILImage.open(io.BytesIO(image_data))

    @classmethod
    def from_dict(cls, data: dict) -> 'Image':
        return cls(
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )


class Element(Field):
    """Chemical element field using mendeleev"""

    def __init__(
        self,
        *,
        choices: Optional[ListType[str]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.choices = choices

    def validate(self, value: Any):
        """Validate element"""
        import mendeleev

        # Already a mendeleev element object (e.g. re-validation via value setter)
        if hasattr(value, 'symbol'):
            symbol = value.symbol
            element = value
        elif isinstance(value, str):
            symbol = value
            try:
                element = mendeleev.element(symbol)
            except Exception:
                raise ValueError(f"Unknown element: {symbol}")
        else:
            raise ValueError(f"Cannot convert {type(value)} to element")

        if self.choices and symbol not in self.choices:
            raise ValueError(f"Element '{symbol}' not in allowed choices: {self.choices}")

        return element

    def serialize(self) -> str:
        """Serialize element as symbol"""
        if self.value is None:
            return None
        return self.value.symbol

    def deserialize(self, data: str):
        """Deserialize element from symbol"""
        import mendeleev

        if data is None:
            self.value = None
        else:
            self.value = mendeleev.element(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'Element':
        return cls(
            choices=data.get('choices'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.choices:
            result['choices'] = self.choices
        return result


class List(Field):
    """List field"""

    def __init__(
        self,
        *,
        item_type: str = 'Text',
        **kwargs
    ):
        super().__init__(**kwargs)
        self.item_type = item_type

    def validate(self, value: Any) -> list:
        """Validate list"""
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"Expected list, got {type(value)}")
        return list(value)

    def serialize(self) -> list:
        return self.value if self.value is not None else []

    def deserialize(self, data: list):
        self.value = data

    @classmethod
    def from_dict(cls, data: dict) -> 'List':
        return cls(
            item_type=data.get('item_type', 'Text'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        result['item_type'] = self.item_type
        return result


class Dict(Field):
    """Dictionary field with optional nested schema"""

    def __init__(
        self,
        *,
        schema: Optional[dict] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.schema = schema

    def validate(self, value: Any) -> dict:
        """Validate dictionary"""
        if not isinstance(value, dict):
            raise ValueError(f"Expected dict, got {type(value)}")

        # TODO: Validate against nested schema if provided
        return value

    def serialize(self) -> dict:
        return self.value if self.value is not None else {}

    def deserialize(self, data: dict):
        self.value = data

    @classmethod
    def from_dict(cls, data: dict) -> 'Dict':
        return cls(
            schema=data.get('schema'),
            default=data.get('default'),
            optional=data.get('optional', False),
            description=data.get('description', ''),
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.schema:
            result['schema'] = self.schema
        return result
