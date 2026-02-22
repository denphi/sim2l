#!/usr/bin/env python3
"""
Interactive Input Validation Example for Sim2l

This example demonstrates how to:
1. Define input schemas with various field types
2. Interactively prompt users for input values
3. Validate inputs against sim2l schema requirements
4. Show helpful error messages and allow retries
5. Display the validated inputs ready for simulation

The example showcases all common field types:
- Integer: with min/max validation
- Number: with units and range validation
- Text: with choices and max length
- Boolean: flexible true/false parsing
- Array: numpy arrays with dtype and shape
- List: lists of items

Usage:
    python examples/interactive_input_example.py
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sim2l.schema import InputSchema, OutputSchema
from sim2l.schema.types import Integer, Number, Text, Boolean, Array, List


def print_header(title: str, char: str = "="):
    """Print a formatted header"""
    width = 70
    print(f"\n{char * width}")
    print(f"{title.center(width)}")
    print(f"{char * width}")


def print_field_info(name: str, field) -> str:
    """Print detailed information about a field and return formatted prompt"""
    field_dict = field.to_dict()
    field_type = field_dict.get('type', type(field).__name__)

    print(f"\n  Field: {name}")
    print(f"  Type: {field_type}")

    if field.description:
        print(f"  Description: {field.description}")

    # Show constraints based on field type
    constraints = []

    if hasattr(field, 'min') and field.min is not None:
        constraints.append(f"min={field.min}")
    if hasattr(field, 'max') and field.max is not None:
        constraints.append(f"max={field.max}")
    if hasattr(field, 'units') and field.units:
        constraints.append(f"units={field.units}")
    if hasattr(field, 'choices') and field.choices:
        constraints.append(f"choices={field.choices}")
    if hasattr(field, 'maxlen') and field.maxlen:
        constraints.append(f"maxlen={field.maxlen}")
    if hasattr(field, 'dtype'):
        constraints.append(f"dtype={field.dtype}")
    if hasattr(field, 'shape') and field.shape:
        constraints.append(f"shape={field.shape}")

    if constraints:
        print(f"  Constraints: {', '.join(constraints)}")

    if field.default is not None:
        print(f"  Default: {field.default}")

    if field.optional:
        print(f"  Optional: Yes (press Enter to skip)")
    else:
        print(f"  Required: Yes")

    # Build the prompt string
    prompt_parts = [name]
    if hasattr(field, 'units') and field.units:
        prompt_parts.append(f"[{field.units}]")
    if field.default is not None:
        prompt_parts.append(f"(default: {field.default})")

    return f"  Enter {' '.join(prompt_parts)}: "


def parse_input_value(raw_value: str, field) -> Any:
    """Parse raw string input into the appropriate type for the field"""
    field_type = type(field).__name__

    if field_type == 'Integer':
        return int(raw_value)

    elif field_type == 'Number':
        return float(raw_value)

    elif field_type == 'Boolean':
        # Let the field's validate method handle boolean parsing
        return raw_value

    elif field_type == 'Text':
        return raw_value

    elif field_type == 'Array':
        # Parse comma-separated values into a list
        import numpy as np
        values = [float(v.strip()) for v in raw_value.split(',')]
        return np.array(values, dtype=field.dtype)

    elif field_type == 'List':
        # Parse comma-separated values
        return [v.strip() for v in raw_value.split(',')]

    else:
        return raw_value


def prompt_for_field(name: str, field) -> Optional[Any]:
    """Interactively prompt for a single field value with validation"""

    prompt_str = print_field_info(name, field)

    while True:
        try:
            raw_value = input(prompt_str).strip()

            # Handle empty input
            if not raw_value:
                if field.default is not None:
                    print(f"    Using default: {field.default}")
                    return field.default
                elif field.optional:
                    print(f"    Skipping optional field")
                    return None
                else:
                    print(f"    Error: This field is required. Please enter a value.")
                    continue

            # Parse the raw value to appropriate type
            parsed_value = parse_input_value(raw_value, field)

            # Validate using the field's validate method
            validated_value = field.validate(parsed_value)

            print(f"    Validated: {validated_value}")
            return validated_value

        except ValueError as e:
            print(f"    Validation Error: {e}")
            print(f"    Please try again.")
        except KeyboardInterrupt:
            print("\n    Input cancelled.")
            return None


def interactive_input_collection(schema: InputSchema) -> Dict[str, Any]:
    """Collect all inputs interactively with validation"""

    print_header("INPUT COLLECTION")
    print("\nPlease provide values for each input parameter.")
    print("Press Ctrl+C at any time to cancel.")

    collected_inputs = {}

    for name, field in schema.items():
        try:
            value = prompt_for_field(name, field)
            if value is not None:
                collected_inputs[name] = value
        except KeyboardInterrupt:
            print("\n\nInput collection cancelled by user.")
            return {}

    return collected_inputs


def validate_all_inputs(schema: InputSchema, inputs: Dict[str, Any]) -> bool:
    """Validate all collected inputs against the schema"""

    print_header("VALIDATION SUMMARY", "-")

    try:
        validated = schema.validate(inputs)
        print("\nAll inputs validated successfully!")

        print("\nValidated values:")
        for name, value in validated.items():
            print(f"  {name}: {value}")

        return True

    except ValueError as e:
        print(f"\nValidation failed: {e}")
        return False


def demo_thermal_simulation_inputs():
    """Demo with thermal simulation schema (matches thermal_simulation.ipynb)"""

    print_header("THERMAL SIMULATION INPUT EXAMPLE")
    print("\nThis example uses the same schema as thermal_simulation.ipynb")

    # Define the input schema matching the thermal simulation
    schema = InputSchema.from_yaml("""
temperature:
  type: Number
  units: kelvin
  min: 0
  max: 1000
  default: 300
  description: "Initial temperature of the system"

power:
  type: Number
  units: watt
  min: 0
  max: 100
  default: 10
  description: "Applied power to the system"

iterations:
  type: Integer
  min: 1
  max: 10000
  default: 100
  description: "Number of simulation iterations"

grid_size:
  type: Integer
  min: 10
  max: 200
  default: 50
  description: "Size of the simulation grid (NxN)"
""")

    # Collect inputs interactively
    inputs = interactive_input_collection(schema)

    if inputs:
        # Validate all inputs
        if validate_all_inputs(schema, inputs):
            print_header("READY TO RUN SIMULATION")
            print("\nYou can now run the thermal simulation with these inputs:")
            print("\n  from sim2l import load_simulation")
            print("  sim = load_simulation('thermal_analysis')")
            print(f"  result = sim.run(")
            for name, value in inputs.items():
                print(f"      {name}={repr(value)},")
            print("  )")


def demo_all_field_types():
    """Demo showcasing all available field types"""

    print_header("ALL FIELD TYPES DEMO")
    print("\nThis example demonstrates all sim2l input field types.")

    # Define schema with all field types
    schema = InputSchema.from_yaml("""
integer_field:
  type: Integer
  min: 1
  max: 100
  default: 10
  description: "An integer between 1 and 100"

number_field:
  type: Number
  units: meter
  min: 0
  max: 1000
  description: "A number with units (meter)"

text_choice:
  type: Text
  choices: ["option_a", "option_b", "option_c"]
  default: "option_a"
  description: "Select one of the available options"

text_free:
  type: Text
  maxlen: 50
  description: "Free text (max 50 characters)"
  optional: true

boolean_field:
  type: Boolean
  default: true
  description: "A yes/no flag (accepts: true/false, yes/no, 1/0)"

list_field:
  type: List
  item_type: Text
  description: "A comma-separated list of items"
  optional: true
""")

    # Collect inputs interactively
    inputs = interactive_input_collection(schema)

    if inputs:
        validate_all_inputs(schema, inputs)


def demo_custom_schema():
    """Allow user to define a custom schema"""

    print_header("CUSTOM SCHEMA DEMO")
    print("\nDefine your own input schema in YAML format.")
    print("Example schema:")
    print("""
my_parameter:
  type: Number
  min: 0
  max: 100
  description: "My custom parameter"
""")

    print("\nEnter your YAML schema (end with an empty line):")

    lines = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    if not lines:
        print("No schema provided.")
        return

    yaml_str = "\n".join(lines)

    try:
        schema = InputSchema.from_yaml(yaml_str)
        print(f"\nSchema parsed successfully with {len(schema.fields)} field(s).")

        inputs = interactive_input_collection(schema)
        if inputs:
            validate_all_inputs(schema, inputs)

    except Exception as e:
        print(f"\nError parsing schema: {e}")


def main():
    """Main entry point with menu selection"""

    print_header("SIM2L INTERACTIVE INPUT VALIDATION EXAMPLE")
    print("\nThis example demonstrates interactive input collection")
    print("with real-time validation against sim2l schemas.")

    while True:
        print("\n" + "-" * 70)
        print("\nSelect a demo:")
        print("  1. Thermal Simulation Inputs (matches thermal_simulation.ipynb)")
        print("  2. All Field Types Demo (Integer, Number, Text, Boolean, List)")
        print("  3. Custom Schema Demo (define your own)")
        print("  4. Exit")

        try:
            choice = input("\nEnter your choice (1-4): ").strip()

            if choice == "1":
                demo_thermal_simulation_inputs()
            elif choice == "2":
                demo_all_field_types()
            elif choice == "3":
                demo_custom_schema()
            elif choice == "4":
                print("\nGoodbye!")
                break
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break


if __name__ == "__main__":
    main()
