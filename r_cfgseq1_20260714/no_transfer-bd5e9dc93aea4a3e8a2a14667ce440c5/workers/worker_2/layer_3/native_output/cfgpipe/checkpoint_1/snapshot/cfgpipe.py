#!/usr/bin/env python3
import json
import os
import sys


VALID_TYPES = {"string", "integer", "float", "boolean"}


def parse_boolean(value):
    """Parse common boolean string representations."""
    lower = value.lower()
    if lower in ("true", "1", "yes", "on", "y"):
        return "true"
    elif lower in ("false", "0", "no", "off", "n"):
        return "false"
    else:
        raise ValueError(f"unrecognized boolean value: {value!r}")


def parse_value(param_name, source_name, raw_value, param_type):
    """Parse raw value according to type. Returns string representation."""
    if param_type == "string":
        return raw_value
    elif param_type == "integer":
        try:
            int(raw_value)
        except ValueError:
            raise ValueError(f"parameter {param_name!r} from source {source_name!r}: cannot parse {raw_value!r} as integer")
        # Reject scientific notation or float-like inputs
        if "." in raw_value or "e" in raw_value.lower():
            raise ValueError(f"parameter {param_name!r} from source {source_name!r}: cannot parse {raw_value!r} as integer")
        return str(int(raw_value))
    elif param_type == "float":
        try:
            float(raw_value)
        except ValueError:
            raise ValueError(f"parameter {param_name!r} from source {source_name!r}: cannot parse {raw_value!r} as float")
        return raw_value
    elif param_type == "boolean":
        try:
            return parse_boolean(raw_value)
        except ValueError as e:
            raise ValueError(f"parameter {param_name!r} from source {source_name!r}: {e}")
    else:
        raise ValueError(f"parameter {param_name!r}: unrecognized type {param_type!r}")


def resolve_param(param_name, decl, cli_args):
    """Resolve a single parameter. Returns (value_string, error_string or None)."""
    param_type = decl["type"]

    # Validate source fields are strings if present
    for field in ("default", "env", "file", "arg"):
        if field in decl and not isinstance(decl[field], str):
            return None, f"parameter {param_name!r}: {field!r} must be a string"

    # Priority order (highest to lowest): arg, file, env, default
    # Check arg first
    if "arg" in decl:
        arg_name = decl["arg"]
        arg_val = None
        for arg in cli_args:
            for prefix in (f"--{arg_name}=", f"-{arg_name}="):
                if arg.startswith(prefix):
                    arg_val = arg[len(prefix):]
                    break
            if arg_val is not None:
                break
        if arg_val is not None:
            try:
                return parse_value(param_name, "arg", arg_val, param_type), None
            except ValueError as e:
                return None, str(e)

    # Check file
    if "file" in decl:
        file_path = decl["file"]
        try:
            if os.path.isfile(file_path):
                with open(file_path, "r") as f:
                    content = f.read()
                stripped = content.strip()
                if stripped:
                    try:
                        return parse_value(param_name, "file", stripped, param_type), None
                    except ValueError as e:
                        return None, str(e)
        except (OSError, IOError):
            pass

    # Check env
    if "env" in decl:
        env_val = os.environ.get(decl["env"])
        if env_val is not None:
            try:
                return parse_value(param_name, "env", env_val, param_type), None
            except ValueError as e:
                return None, str(e)

    # Check default
    if "default" in decl:
        try:
            return parse_value(param_name, "default", decl["default"], param_type), None
        except ValueError as e:
            return None, str(e)

    # No source provided a value
    return None, None


def main():
    if len(sys.argv) < 2:
        print("Usage: python cfgpipe.py <schema-file> [arg-candidates...]", file=sys.stderr)
        sys.exit(1)

    schema_path = sys.argv[1]
    cli_args = sys.argv[2:]

    # Read and parse schema
    try:
        with open(schema_path, "r") as f:
            schema_text = f.read()
    except FileNotFoundError:
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Cannot read schema file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in schema: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(schema, dict):
        print("Schema must be a JSON object", file=sys.stderr)
        sys.exit(1)

    # Validate each parameter declaration
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            print(f"Parameter {param_name!r} declaration must be an object", file=sys.stderr)
            sys.exit(1)
        if "type" not in decl:
            print(f"Parameter {param_name!r} missing required 'type' field", file=sys.stderr)
            sys.exit(1)
        if decl["type"] not in VALID_TYPES:
            print(f"Parameter {param_name!r}: unrecognized type {decl['type']!r}", file=sys.stderr)
            sys.exit(1)
        for field in ("default", "env", "file", "arg"):
            if field in decl and not isinstance(decl[field], str):
                print(f"Parameter {param_name!r}: {field!r} must be a string", file=sys.stderr)
                sys.exit(1)

    # Resolve parameters
    result = {}
    unresolved = []
    for param_name, decl in schema.items():
        value, error = resolve_param(param_name, decl, cli_args)
        if error:
            print(error, file=sys.stderr)
            sys.exit(1)
        if value is None:
            unresolved.append(param_name)
        else:
            result[param_name] = value

    if unresolved:
        print(f"Unresolved parameters: {', '.join(unresolved)}", file=sys.stderr)
        sys.exit(1)

    # Output JSON
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
