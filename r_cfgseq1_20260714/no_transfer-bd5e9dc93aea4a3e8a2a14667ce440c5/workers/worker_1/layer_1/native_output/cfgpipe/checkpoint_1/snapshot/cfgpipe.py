#!/usr/bin/env python3
import json
import os
import sys
import re


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def parse_boolean(value):
    lower = value.lower()
    if lower in ("true", "1", "yes", "on"):
        return "true"
    if lower in ("false", "0", "no", "off"):
        return "false"
    raise ValueError(f"invalid boolean value: {value!r}")


def parse_integer(value):
    # Decimal integers only, no scientific notation
    if re.fullmatch(r"-?[0-9]+", value):
        return value
    raise ValueError(f"invalid integer value: {value!r}")


def parse_float(value):
    # Decimal inputs, no exact canonical format required
    # Scientific notation not required (and treated as invalid here)
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
        return value
    raise ValueError(f"invalid float value: {value!r}")


def parse_string(value):
    return value


TYPE_PARSERS = {
    "string": parse_string,
    "integer": parse_integer,
    "float": parse_float,
    "boolean": parse_boolean,
}


def resolve_arg(args, arg_name):
    # args are the remaining positional arguments after schema file
    # Support --name=value and -name=value, last wins
    value = None
    for arg in args:
        for prefix in (f"--{arg_name}=", f"-{arg_name}="):
            if arg.startswith(prefix):
                value = arg[len(prefix):]
                break
    return value


def main():
    if len(sys.argv) < 2:
        fail("Usage: python cfgpipe.py <schema-file> [arg-candidates...]")

    schema_path = sys.argv[1]
    arg_candidates = sys.argv[2:]

    # Read schema file
    if not os.path.exists(schema_path):
        fail(f"Schema file not found: {schema_path}")

    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"Invalid JSON in schema file: {e}")
    except Exception as e:
        fail(f"Error reading schema file: {e}")

    if not isinstance(schema, dict):
        fail("Schema must be a JSON object")

    # Validate schema structure
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            fail(f"Parameter {param_name!r} declaration must be an object")
        if "type" not in decl:
            fail(f"Parameter {param_name!r} missing required 'type' field")
        for field in ("default", "env", "file", "arg"):
            if field in decl and not isinstance(decl[field], str):
                fail(f"Parameter {param_name!r} field {field!r} must be a string")

    # Resolve each parameter
    resolved = {}
    unresolved = []
    parse_errors = []

    for param_name, decl in schema.items():
        ptype = decl["type"]
        if ptype not in TYPE_PARSERS:
            fail(f"Parameter {param_name!r} has unrecognized type {ptype!r}")

        parser = TYPE_PARSERS[ptype]
        value = None
        source_used = None

        # Priority order: arg > file > env > default (highest first)
        # Try arg first
        if "arg" in decl:
            arg_val = resolve_arg(arg_candidates, decl["arg"])
            if arg_val is not None:
                try:
                    value = parser(arg_val)
                    source_used = "arg"
                except ValueError as e:
                    parse_errors.append((param_name, "arg", str(e)))

        # Try file
        if value is None and "file" in decl:
            file_path = decl["file"]
            if os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as f:
                        content = f.read()
                    stripped = content.strip()
                    if stripped:
                        try:
                            value = parser(stripped)
                            source_used = "file"
                        except ValueError as e:
                            parse_errors.append((param_name, "file", str(e)))
                except Exception:
                    pass

        # Try env
        if value is None and "env" in decl:
            env_val = os.environ.get(decl["env"])
            if env_val is not None:
                try:
                    value = parser(env_val)
                    source_used = "env"
                except ValueError as e:
                    parse_errors.append((param_name, "env", str(e)))

        # Try default
        if value is None and "default" in decl:
            try:
                value = parser(decl["default"])
                source_used = "default"
            except ValueError as e:
                parse_errors.append((param_name, "default", str(e)))

        if value is not None:
            resolved[param_name] = value
        else:
            unresolved.append(param_name)

    if parse_errors:
        param_name, source_name, reason = parse_errors[0]
        fail(f"Parameter {param_name!r} source {source_name!r} parse error: {reason}")

    if unresolved:
        fail(f"Unresolved parameters: {', '.join(unresolved)}")

    # Output resolved configuration
    print(json.dumps(resolved))


if __name__ == "__main__":
    main()
