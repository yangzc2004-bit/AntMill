#!/usr/bin/env python3
"""cfgpipe - Core Resolution: A command-line configuration resolver."""

import json
import os
import sys
import re
import urllib.parse

import requests


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


def parse_global_flags(argv):
    """Parse global flags from argv. Returns (primary_store_url, remaining_args)."""
    primary_store_url = None
    i = 0
    while i < len(argv):
        if argv[i] == '--primary-store':
            if i + 1 >= len(argv):
                print("Flag --primary-store requires a value", file=sys.stderr)
                sys.exit(1)
            primary_store_url = argv[i + 1]
            i += 2
        elif argv[i].startswith('--primary-store='):
            primary_store_url = argv[i].split('=', 1)[1]
            i += 1
        else:
            break
    return primary_store_url, argv[i:]


def lookup_primary_store(base_url, key):
    """Lookup a key in the primary store. Returns the value string if found, None if not found.
    Raises RuntimeError on connector failures."""
    encoded_key = urllib.parse.quote(key, safe='')
    url = f"{base_url}/v1/primary/kv?key={encoded_key}"
    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"primary store request failed: {e}")

    if response.status_code == 404:
        try:
            body = response.json()
            if isinstance(body, dict) and body.get('found') is False:
                return None
        except (ValueError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"primary store returned 404 with unexpected body: {response.text}")

    if response.status_code != 200:
        raise RuntimeError(f"primary store returned {response.status_code}: {response.text}")

    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"primary store returned malformed JSON: {e}")

    if not isinstance(body, dict):
        raise RuntimeError(f"primary store returned malformed response")

    if body.get('found') is not True:
        raise RuntimeError(f"primary store returned unexpected response")

    if 'value' not in body:
        raise RuntimeError(f"primary store returned response without 'value' field")

    return body['value']


def resolve(schema_path, arg_candidates, primary_store_url):
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
        for field in ('default', 'env', 'file', 'arg', 'primary-store'):
            if field in param_decl and not isinstance(param_decl[field], str):
                print(f"Parameter '{param_name}' field '{field}' must be a string", file=sys.stderr)
                sys.exit(1)

    # Check for duplicate primary-store keys
    primary_store_keys = {}
    for param_name, param_decl in schema.items():
        if 'primary-store' in param_decl:
            key = param_decl['primary-store']
            if key in primary_store_keys:
                other_param = primary_store_keys[key]
                print(f"Parameters '{other_param}' and '{param_name}' share primary-store key '{key}'", file=sys.stderr)
                sys.exit(1)
            primary_store_keys[key] = param_name

    # Check if any parameter declares primary-store but --primary-store is absent
    if primary_store_url is None:
        for param_name, param_decl in schema.items():
            if 'primary-store' in param_decl:
                print(f"Parameter '{param_name}' declares primary-store but --primary-store is not configured", file=sys.stderr)
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

        # Check sources in priority order: default, env, file, primary-store, arg
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

        if 'primary-store' in param_decl and primary_store_url is not None:
            try:
                ps_val = lookup_primary_store(primary_store_url, param_decl['primary-store'])
                if ps_val is not None:
                    value = ps_val
                    source = 'primary-store'
            except RuntimeError as e:
                print(f"Parameter '{param_name}' from source 'primary-store': {e}", file=sys.stderr)
                sys.exit(1)

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
        print("Usage: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]", file=sys.stderr)
        sys.exit(1)

    primary_store_url, remaining = parse_global_flags(sys.argv[1:])

    if len(remaining) < 1:
        print("Usage: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]", file=sys.stderr)
        sys.exit(1)

    schema_path = remaining[0]
    arg_candidates = remaining[1:]
    resolve(schema_path, arg_candidates, primary_store_url)


if __name__ == '__main__':
    main()
