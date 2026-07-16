#!/usr/bin/env python3
import json
import os
import sys


def parse_boolean(value):
    """Parse common boolean string representations."""
    lower = value.lower().strip()
    if lower in ('true', 'yes', '1', 'on'):
        return 'true'
    elif lower in ('false', 'no', '0', 'off'):
        return 'false'
    else:
        raise ValueError(f"unrecognized boolean input: {value!r}")


def parse_integer(value):
    """Parse decimal integer. No scientific notation."""
    value = value.strip()
    if not value:
        raise ValueError("empty integer input")
    # Check for valid decimal integer format
    if value.startswith('-'):
        digits = value[1:]
    elif value.startswith('+'):
        digits = value[1:]
    else:
        digits = value
    if not digits or not digits.isdigit():
        raise ValueError(f"invalid integer input: {value!r}")
    # Ensure no scientific notation or decimal point
    if 'e' in value.lower() or '.' in value:
        raise ValueError(f"invalid integer input: {value!r}")
    return str(int(value))


def parse_float(value):
    """Parse decimal float input."""
    value = value.strip()
    if not value:
        raise ValueError("empty float input")
    try:
        f = float(value)
    except ValueError:
        raise ValueError(f"invalid float input: {value!r}")
    return str(f)


def parse_value(value, typ):
    """Parse a value string according to the given type."""
    if typ == 'string':
        return value
    elif typ == 'integer':
        return parse_integer(value)
    elif typ == 'float':
        return parse_float(value)
    elif typ == 'boolean':
        return parse_boolean(value)
    else:
        raise ValueError(f"unrecognized type: {typ!r}")


def read_file(path):
    """Read file content, return None if absent or invalid."""
    try:
        with open(path, 'r') as f:
            content = f.read()
    except (OSError, IOError):
        return None
    # Check if it's a regular file (not directory, etc.)
    import stat
    try:
        mode = os.stat(path).st_mode
        if not stat.S_ISREG(mode):
            return None
    except (OSError, IOError):
        return None
    trimmed = content.strip()
    if trimmed == '':
        return None
    return trimmed


def resolve_param(name, spec, arg_values):
    """Resolve a single parameter from its sources."""
    typ = spec.get('type')
    if not isinstance(typ, str):
        raise RuntimeError(f"Parameter {name!r}: 'type' must be a string")
    
    # Validate source fields are strings
    for field in ('default', 'env', 'file', 'arg'):
        if field in spec and not isinstance(spec[field], str):
            raise RuntimeError(f"Parameter {name!r}: {field!r} must be a string")
    
    # Priority order: default < env < file < arg
    # Highest priority wins, so check in reverse order
    if 'arg' in spec:
        arg_name = spec['arg']
        if arg_name in arg_values:
            try:
                return parse_value(arg_values[arg_name], typ)
            except ValueError as e:
                print(f"Error: parameter {name!r} from source 'arg': {e}", file=sys.stderr)
                sys.exit(1)
    
    if 'file' in spec:
        file_val = read_file(spec['file'])
        if file_val is not None:
            try:
                return parse_value(file_val, typ)
            except ValueError as e:
                print(f"Error: parameter {name!r} from source 'file': {e}", file=sys.stderr)
                sys.exit(1)
    
    if 'env' in spec:
        env_val = os.environ.get(spec['env'])
        if env_val is not None:
            try:
                return parse_value(env_val, typ)
            except ValueError as e:
                print(f"Error: parameter {name!r} from source 'env': {e}", file=sys.stderr)
                sys.exit(1)
    
    if 'default' in spec:
        try:
            return parse_value(spec['default'], typ)
        except ValueError as e:
            print(f"Error: parameter {name!r} from source 'default': {e}", file=sys.stderr)
            sys.exit(1)
    
    # No source provided a value
    return None


def parse_args(args):
    """Parse CLI arguments after schema file to extract arg values."""
    arg_values = {}
    for arg in args:
        for prefix in ('--', '-'):
            if arg.startswith(prefix):
                rest = arg[len(prefix):]
                if '=' in rest:
                    name, value = rest.split('=', 1)
                    arg_values[name] = value
                    break
    return arg_values


def main():
    if len(sys.argv) < 2:
        print("Usage: python cfgpipe.py <schema-file> [arg-candidates...]", file=sys.stderr)
        sys.exit(1)
    
    schema_path = sys.argv[1]
    arg_candidates = sys.argv[2:]
    
    # Read and parse schema
    try:
        with open(schema_path, 'r') as f:
            schema_content = f.read()
    except (OSError, IOError) as e:
        print(f"Error: cannot read schema file {schema_path!r}: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        schema = json.loads(schema_content)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in schema file: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not isinstance(schema, dict):
        print("Error: schema root must be a JSON object", file=sys.stderr)
        sys.exit(1)
    
    # Validate parameter names are unique (dict keys are naturally unique)
    # Validate each parameter spec
    for name, spec in schema.items():
        if not isinstance(spec, dict):
            print(f"Error: parameter {name!r} must be an object", file=sys.stderr)
            sys.exit(1)
        if 'type' not in spec:
            print(f"Error: parameter {name!r} missing required 'type' field", file=sys.stderr)
            sys.exit(1)
    
    arg_values = parse_args(arg_candidates)
    
    unresolved = []
    result = {}
    
    for name, spec in schema.items():
        try:
            value = resolve_param(name, spec, arg_values)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        
        if value is None:
            unresolved.append(name)
        else:
            result[name] = value
    
    if unresolved:
        print(f"Error: unresolved parameters: {', '.join(unresolved)}", file=sys.stderr)
        sys.exit(1)
    
    print(json.dumps(result, separators=(',', ':')))


if __name__ == '__main__':
    main()
