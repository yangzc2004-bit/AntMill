#!/usr/bin/env python3
import json
import os
import sys

def parse_boolean(value):
    lower = value.lower()
    if lower in ('true', '1', 'yes', 'on', 't', 'y'):
        return 'true'
    elif lower in ('false', '0', 'no', 'off', 'f', 'n'):
        return 'false'
    else:
        raise ValueError(f"cannot parse '{value}' as boolean")

def parse_integer(value):
    if not value:
        raise ValueError("empty string")
    stripped = value.lstrip('+-')
    if not stripped or not stripped.isdigit():
        raise ValueError(f"cannot parse '{value}' as integer")
    if 'e' in value.lower():
        raise ValueError(f"cannot parse '{value}' as integer")
    return str(int(value))

def parse_float(value):
    if not value:
        raise ValueError("empty string")
    try:
        f = float(value)
    except ValueError:
        raise ValueError(f"cannot parse '{value}' as float")
    return str(f)

def parse_value(value, typ):
    if typ == 'string':
        return value
    elif typ == 'integer':
        return parse_integer(value)
    elif typ == 'float':
        return parse_float(value)
    elif typ == 'boolean':
        return parse_boolean(value)
    else:
        raise ValueError(f"unrecognized type '{typ}'")

def resolve_param(name, spec, arg_values):
    if not isinstance(spec, dict):
        sys.stderr.write(f"Parameter '{name}': spec must be an object\n")
        sys.exit(1)
    
    if 'type' not in spec:
        sys.stderr.write(f"Parameter '{name}': missing required 'type' field\n")
        sys.exit(1)
    
    typ = spec['type']
    if not isinstance(typ, str):
        sys.stderr.write(f"Parameter '{name}': 'type' must be a string\n")
        sys.exit(1)
    
    for field in ['default', 'env', 'file', 'arg']:
        if field in spec and not isinstance(spec[field], str):
            sys.stderr.write(f"Parameter '{name}': '{field}' must be a string\n")
            sys.exit(1)
    
    # Priority: arg > file > env > default (highest to lowest)
    # Check arg first
    if 'arg' in spec:
        arg_name = spec['arg']
        if arg_name in arg_values:
            try:
                return parse_value(arg_values[arg_name], typ)
            except ValueError as e:
                sys.stderr.write(f"Parameter '{name}': source 'arg' parse failure: {e}\n")
                sys.exit(1)
    
    # Check file
    if 'file' in spec:
        filepath = spec['file']
        try:
            if os.path.isfile(filepath):
                with open(filepath, 'r') as f:
                    content = f.read().strip()
                if content:
                    try:
                        return parse_value(content, typ)
                    except ValueError as e:
                        sys.stderr.write(f"Parameter '{name}': source 'file' parse failure: {e}\n")
                        sys.exit(1)
        except (IOError, OSError):
            pass
    
    # Check env
    if 'env' in spec:
        env_val = os.environ.get(spec['env'])
        if env_val is not None:
            try:
                return parse_value(env_val, typ)
            except ValueError as e:
                sys.stderr.write(f"Parameter '{name}': source 'env' parse failure: {e}\n")
                sys.exit(1)
    
    # Check default
    if 'default' in spec:
        try:
            return parse_value(spec['default'], typ)
        except ValueError as e:
            sys.stderr.write(f"Parameter '{name}': source 'default' parse failure: {e}\n")
            sys.exit(1)
    
    return None

def parse_args(args):
    result = {}
    for arg in args:
        if arg.startswith('--'):
            rest = arg[2:]
        elif arg.startswith('-'):
            rest = arg[1:]
        else:
            continue
        if '=' in rest:
            name, value = rest.split('=', 1)
            result[name] = value
    return result

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python cfgpipe.py <schema-file> [arg-candidates...]\n")
        sys.exit(1)
    
    schema_path = sys.argv[1]
    arg_candidates = sys.argv[2:]
    
    if not os.path.isfile(schema_path):
        sys.stderr.write(f"Schema file not found: {schema_path}\n")
        sys.exit(1)
    
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Invalid JSON in schema file: {e}\n")
        sys.exit(1)
    except (IOError, OSError) as e:
        sys.stderr.write(f"Cannot read schema file: {e}\n")
        sys.exit(1)
    
    if not isinstance(schema, dict):
        sys.stderr.write("Schema must be a JSON object\n")
        sys.exit(1)
    
    arg_values = parse_args(arg_candidates)
    
    unresolved = []
    result = {}
    
    for name, spec in schema.items():
        resolved = resolve_param(name, spec, arg_values)
        if resolved is None:
            unresolved.append(name)
        else:
            result[name] = resolved
    
    if unresolved:
        sys.stderr.write(f"Unresolved parameters: {', '.join(unresolved)}\n")
        sys.exit(1)
    
    print(json.dumps(result, separators=(', ', ': ')))
    sys.exit(0)

if __name__ == '__main__':
    main()
