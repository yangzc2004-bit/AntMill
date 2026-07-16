#!/usr/bin/env python3
"""cfgpipe - Core Resolution: A command-line configuration resolver."""

import json
import os
import sys


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def parse_boolean(value):
    """Parse common boolean string representations."""
    lowered = value.lower()
    if lowered in ('true', 'yes', '1', 'on', 't', 'y'):
        return 'true'
    elif lowered in ('false', 'no', '0', 'off', 'f', 'n'):
        return 'false'
    else:
        raise ValueError(f"unrecognized boolean value: {value!r}")


def parse_integer(value):
    """Parse decimal integer. No scientific notation."""
    if not value:
        raise ValueError("empty integer value")
    # Check for valid decimal integer format
    if value.startswith('-') or value.startswith('+'):
        digits = value[1:]
    else:
        digits = value
    if not digits or not digits.isdigit():
        raise ValueError(f"invalid integer value: {value!r}")
    # Ensure it can be parsed as int
    int(value)
    return str(int(value))


def parse_float(value):
    """Parse decimal float. No exact canonical format required."""
    if not value:
        raise ValueError("empty float value")
    try:
        float(value)
    except ValueError:
        raise ValueError(f"invalid float value: {value!r}")
    # Return as string representation
    return str(float(value))


def parse_value(value, ptype, param_name, source_name):
    """Parse a value according to its type. Returns resolved string."""
    if ptype == 'string':
        return value
    elif ptype == 'integer':
        try:
            return parse_integer(value)
        except ValueError as e:
            fail(f"parameter {param_name}: source {source_name}: {e}")
    elif ptype == 'float':
        try:
            return parse_float(value)
        except ValueError as e:
            fail(f"parameter {param_name}: source {source_name}: {e}")
    elif ptype == 'boolean':
        try:
            return parse_boolean(value)
        except ValueError as e:
            fail(f"parameter {param_name}: source {source_name}: {e}")
    else:
        fail(f"parameter {param_name}: unrecognized type: {ptype!r}")


def resolve_file_source(path):
    """Read file content, trim whitespace. Returns None if absent."""
    try:
        # Must be a regular file
        if not os.path.isfile(path):
            return None
        with open(path, 'r') as f:
            content = f.read()
        content = content.strip()
        if not content:
            return None
        return content
    except (OSError, IOError):
        return None


def parse_args(args):
    """Parse CLI arguments into a dict of arg_name -> value. Last wins."""
    result = {}
    for arg in args:
        # Support --name=value and -name=value
        if arg.startswith('--') and '=' in arg:
            name, value = arg[2:].split('=', 1)
            result[name] = value
        elif arg.startswith('-') and '=' in arg and not arg.startswith('--'):
            name, value = arg[1:].split('=', 1)
            result[name] = value
    return result


def main():
    if len(sys.argv) < 2:
        fail("Usage: python cfgpipe.py <schema-file> [arg-candidates...]")

    schema_path = sys.argv[1]
    arg_candidates = sys.argv[2:]

    # Parse schema
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError:
        fail(f"schema file not found: {schema_path}")
    except json.JSONDecodeError as e:
        fail(f"invalid JSON in schema file: {e}")

    if not isinstance(schema, dict):
        fail("schema must be a JSON object")

    # Validate schema and resolve
    parsed_args = parse_args(arg_candidates)

    resolved = {}
    unresolved = []

    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            fail(f"parameter {param_name}: declaration must be an object")

        # Validate type field
        if 'type' not in decl:
            fail(f"parameter {param_name}: missing required 'type' field")
        ptype = decl['type']
        if not isinstance(ptype, str):
            fail(f"parameter {param_name}: 'type' must be a string")

        # Validate source fields are strings if present
        for source_field in ('default', 'env', 'file', 'arg'):
            if source_field in decl:
                val = decl[source_field]
                if not isinstance(val, str):
                    fail(f"parameter {param_name}: {source_field!r} must be a string")

        # Resolve from sources in priority order: default, env, file, arg
        value = None
        source_used = None

        if 'default' in decl:
            value = decl['default']
            source_used = 'default'

        if 'env' in decl:
            env_val = os.environ.get(decl['env'])
            if env_val is not None:
                value = env_val
                source_used = 'env'

        if 'file' in decl:
            file_val = resolve_file_source(decl['file'])
            if file_val is not None:
                value = file_val
                source_used = 'file'

        if 'arg' in decl:
            arg_name = decl['arg']
            if arg_name in parsed_args:
                value = parsed_args[arg_name]
                source_used = 'arg'

        if value is None:
            unresolved.append(param_name)
        else:
            # Parse and store
            resolved_value = parse_value(value, ptype, param_name, source_used)
            resolved[param_name] = resolved_value

    if unresolved:
        fail(f"unresolved parameters: {', '.join(unresolved)}")

    # Output JSON
    print(json.dumps(resolved))


if __name__ == '__main__':
    main()
