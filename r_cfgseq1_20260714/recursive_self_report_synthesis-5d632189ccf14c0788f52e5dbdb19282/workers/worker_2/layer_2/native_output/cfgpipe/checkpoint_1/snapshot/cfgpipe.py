#!/usr/bin/env python3
import json
import os
import re
import sys


def error_exit(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def parse_boolean(raw):
    lowered = raw.lower()
    if lowered in ("true", "yes", "1", "on"):
        return "true"
    if lowered in ("false", "no", "0", "off"):
        return "false"
    return None


def parse_integer(raw):
    if re.fullmatch(r'-?\d+', raw):
        return raw
    return None


def parse_float(raw):
    if re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
        return raw
    return None


def parse_value(raw, typ):
    if typ == "string":
        return raw
    if typ == "integer":
        return parse_integer(raw)
    if typ == "float":
        return parse_float(raw)
    if typ == "boolean":
        return parse_boolean(raw)
    return None


def main():
    args = sys.argv[1:]
    if not args:
        error_exit("missing schema file")
    schema_path = args[0]
    arg_candidates = args[1:]

    # Load schema
    if not os.path.exists(schema_path):
        error_exit(f"schema file not found: {schema_path}")
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        error_exit(f"invalid JSON in schema: {e}")
    except Exception as e:
        error_exit(f"cannot read schema file: {e}")

    if not isinstance(schema, dict):
        error_exit("schema root must be a JSON object")

    # Validate schema: each parameter must be a dict with required 'type' string,
    # and source fields must be strings if present.
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            error_exit(f"parameter '{param_name}' declaration must be an object")
        if "type" not in decl:
            error_exit(f"parameter '{param_name}' missing required 'type' field")
        if not isinstance(decl["type"], str):
            error_exit(f"parameter '{param_name}' 'type' must be a string")
        for field in ("default", "env", "file", "arg"):
            if field in decl and not isinstance(decl[field], str):
                error_exit(f"parameter '{param_name}' '{field}' must be a string")

    # Parse arg candidates
    arg_values = {}
    for candidate in arg_candidates:
        m = re.fullmatch(r'--?([^=]+)=(.*)', candidate)
        if m:
            name = m.group(1)
            value = m.group(2)
            arg_values[name] = value

    # Resolve parameters
    result = {}
    unresolved = []

    for param_name, decl in schema.items():
        typ = decl["type"]
        raw_value = None
        source = None

        # Priority: arg > file > env > default
        if "arg" in decl:
            arg_name = decl["arg"]
            if arg_name in arg_values:
                raw_value = arg_values[arg_name]
                source = "arg"

        if raw_value is None and "file" in decl:
            file_path = decl["file"]
            try:
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    stripped = content.strip()
                    if stripped:
                        raw_value = stripped
                        source = "file"
            except Exception:
                pass

        if raw_value is None and "env" in decl:
            env_name = decl["env"]
            env_val = os.environ.get(env_name)
            if env_val is not None and env_val != "":
                raw_value = env_val
                source = "env"

        if raw_value is None and "default" in decl:
            raw_value = decl["default"]
            source = "default"

        if raw_value is None:
            unresolved.append(param_name)
            continue

        parsed = parse_value(raw_value, typ)
        if parsed is None:
            error_exit(f"parameter '{param_name}' source '{source}' parse failure: cannot parse '{raw_value}' as {typ}")

        result[param_name] = parsed

    if unresolved:
        error_exit("unresolved parameters: " + ", ".join(unresolved))

    sys.stdout.write(json.dumps(result, separators=(',', ':')) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
