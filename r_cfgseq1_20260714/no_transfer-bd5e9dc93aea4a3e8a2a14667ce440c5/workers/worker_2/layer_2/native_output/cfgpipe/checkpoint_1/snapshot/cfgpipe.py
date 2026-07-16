#!/usr/bin/env python3
"""cfgpipe - Core Resolution: A command-line configuration resolver."""

import json
import os
import sys
import re


def parse_boolean(value):
    """Parse a boolean string. Returns 'true' or 'false' on success, raises ValueError on failure."""
    lower = value.lower()
    if lower in ('true', 'yes', '1', 'on'):
        return 'true'
    elif lower in ('false', 'no', '0', 'off'):
        return 'false'
    else:
        raise ValueError(f"cannot parse '{value}' as boolean")


def parse_integer(value):
    """Parse an integer string. Returns plain decimal string on success, raises ValueError on failure."""
    # Match optional sign followed by digits only (no scientific notation)
    if not re.fullmatch(r'-?\d+', value):
        raise ValueError(f"cannot parse '{value}' as integer")
    # Validate it's a valid integer
    int(value)
    return value


def parse_float(value):
    """Parse a float string. Returns string representation on success, raises ValueError on failure."""
    # Match optional sign, digits, optional decimal point and digits
    # Or optional sign, digits, decimal point, digits
    # No scientific notation required
    if not re.fullmatch(r'-?\d+(\.\d+)?', value):
        raise ValueError(f"cannot parse '{value}' as float")
    # Validate it's a valid float
    float(value)
    return value


def parse_value(value, param_type):
    """Parse a value according to its type. Returns the resolved string form."""
    if param_type == 'string':
        return value
    elif param_type == 'integer':
        return parse_integer(value)
    elif param_type == 'float':
        return parse_float(value)
    elif param_type == 'boolean':
        return parse_boolean(value)
    else:
        raise ValueError(f"unrecognized type '{param_type}'")


def read_file(path):
    """Read file content. Returns stripped content or None if absent/empty."""
    try:
        if not os.path.isfile(path):
            return None
        with open(path, 'r') as f:
            content = f.read().strip()
        if content == '':
            return None
        return content
    except (OSError, IOError):
        return None


def parse_args(arg_candidates):
    """Parse CLI arguments into a dict of name -> value. Supports --name=value and -name=value. Last wins."""
    args = {}
    for arg in arg_candidates:
        # Match --name=value or -name=value
        m = re.fullmatch(r'--([^=]+)=(.*)', arg)
        if m:
            name, value = m.group(1), m.group(2)
            args[name] = value
            continue
        m = re.fullmatch(r'-([^=]+)=(.*)', arg)
        if m:
            name, value = m.group(1), m.group(2)
            args[name] = value
            continue
    return args


def resolve(schema_path, arg_candidates):
    """Resolve configuration from schema and sources."""
    # Read and parse schema
    try:
        with open(schema_path, 'r') as f:
            schema_content = f.read()
    except FileNotFoundError:
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)
    except (OSError, IOError) as e:
        print(f"Cannot read schema file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        schema = json.loads(schema_content)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in schema: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(schema, dict):
        print("Schema must be a JSON object", file=sys.stderr)
        sys.exit(1)

    # Validate schema
    for param_name, param_decl in schema.items():
        if not isinstance(param_decl, dict):
            print(f"Parameter '{param_name}' declaration must be an object", file=sys.stderr)
            sys.exit(1)
        if 'type' not in param_decl:
            print(f"Parameter '{param_name}' missing required 'type' field", file=sys.stderr)
            sys.exit(1)
        for field in ('default', 'env', 'file', 'arg'):
            if field in param_decl and not isinstance(param_decl[field], str):
                print(f"Parameter '{param_name}' field '{field}' must be a string", file=sys.stderr)
                sys.exit(1)

    # Parse CLI args
    cli_args = parse_args(arg_candidates)

    # Resolve each parameter
    resolved = {}
    unresolved = []

    for param_name, param_decl in schema.items():
        param_type = param_decl['type']
        value = None
        source = None

        # Check sources in priority order: default, env, file, arg
        # The first source that provides a value wins
        if 'default' in param_decl:
            value = param_decl['default']
            source = 'default'

        if 'env' in param_decl:
            env_val = os.environ.get(param_decl['env'])
            if env_val is not None:
                value = env_val
                source = 'env'

        if 'file' in param_decl:
            file_val = read_file(param_decl['file'])
            if file_val is not None:
                value = file_val
                source = 'file'

        if 'arg' in param_decl:
            if param_decl['arg'] in cli_args:
                value = cli_args[param_decl['arg']]
                source = 'arg'

        if value is None:
            unresolved.append(param_name)
            continue

        # Parse the value
        try:
            parsed = parse_value(value, param_type)
        except ValueError as e:
            print(f"Parameter '{param_name}' from source '{source}': {e}", file=sys.stderr)
            sys.exit(1)

        resolved[param_name] = parsed

    if unresolved:
        print(f"Unresolved parameters: {', '.join(unresolved)}", file=sys.stderr)
        sys.exit(1)

    # Output resolved config as JSON
    print(json.dumps(resolved, indent=2))


def main():
    if len(sys.argv) < 2:
        print("Usage: python cfgpipe.py <schema-file> [arg-candidates...]", file=sys.stderr)
        sys.exit(1)

    schema_path = sys.argv[1]
    arg_candidates = sys.argv[2:]
    resolve(schema_path, arg_candidates)


if __name__ == '__main__':
    main()
