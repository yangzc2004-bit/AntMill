#!/usr/bin/env python3
import json
import os
import sys
import re

def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)

def parse_boolean(val):
    v = val.strip().lower()
    if v in ("true", "yes", "1", "on"):
        return "true"
    if v in ("false", "no", "0", "off"):
        return "false"
    raise ValueError(f"invalid boolean value: {val!r}")

def parse_integer(val):
    val = val.strip()
    if not re.fullmatch(r'-?\d+', val):
        raise ValueError(f"invalid integer value: {val!r}")
    # Remove leading zeros but keep sign
    if val.startswith('-'):
        return '-' + val[1:].lstrip('0') or '0'
    return val.lstrip('0') or '0'

def parse_float(val):
    val = val.strip()
    # Accept decimal floats, no scientific notation required
    if not re.fullmatch(r'-?\d+(\.\d+)?', val):
        raise ValueError(f"invalid float value: {val!r}")
    # Just return as-is, no exact canonical format required
    return val

def parse_string(val):
    return val

def parse_value(param_name, source, val, typ):
    try:
        if typ == "string":
            return parse_string(val)
        elif typ == "integer":
            return parse_integer(val)
        elif typ == "float":
            return parse_float(val)
        elif typ == "boolean":
            return parse_boolean(val)
        else:
            raise ValueError(f"unknown type {typ!r}")
    except ValueError as e:
        fail(f"parse failure for parameter {param_name!r} from source {source!r}: {e}")

def resolve_param(param_name, decl, args):
    typ = decl.get("type")
    if not isinstance(typ, str):
        fail(f"schema validation failure: parameter {param_name!r} has non-string type field")
    
    # Priority: arg > file > env > default (highest to lowest)
    # Check arg first
    if "arg" in decl:
        arg_val = args.get(decl["arg"])
        if arg_val is not None:
            return parse_value(param_name, "arg", arg_val, typ)
    
    # Check file
    if "file" in decl:
        file_path = decl["file"]
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            if content.strip() != "":
                return parse_value(param_name, "file", content, typ)
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
            pass
    
    # Check env
    if "env" in decl:
        env_val = os.environ.get(decl["env"])
        if env_val is not None and env_val != "":
            return parse_value(param_name, "env", env_val, typ)
    
    # Check default
    if "default" in decl:
        default_val = decl["default"]
        if default_val is not None:
            return parse_value(param_name, "default", default_val, typ)
    
    return None

def main():
    if len(sys.argv) < 2:
        fail("usage: python cfgpipe.py <schema-file> [arg-candidates...]")
    
    schema_path = sys.argv[1]
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError:
        fail(f"schema file not found: {schema_path}")
    except json.JSONDecodeError as e:
        fail(f"invalid JSON in schema file: {e}")
    
    if not isinstance(schema, dict):
        fail("schema validation failure: root must be an object")
    
    # Parse arg candidates
    args = {}
    for arg in sys.argv[2:]:
        for prefix in ("--", "-"):
            if arg.startswith(prefix):
                rest = arg[len(prefix):]
                if "=" in rest:
                    key, val = rest.split("=", 1)
                    args[key] = val
                    break
    
    # Validate schema and resolve
    unresolved = []
    result = {}
    
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            fail(f"schema validation failure: parameter {param_name!r} declaration is not an object")
        
        # Validate source fields are strings
        for field in ("default", "env", "file", "arg"):
            if field in decl and not isinstance(decl[field], str):
                fail(f"schema validation failure: parameter {param_name!r} field {field!r} is not a string")
        
        # type is required
        if "type" not in decl:
            fail(f"schema validation failure: parameter {param_name!r} missing required field 'type'")
        
        val = resolve_param(param_name, decl, args)
        if val is None:
            unresolved.append(param_name)
        else:
            result[param_name] = val
    
    if unresolved:
        fail(f"unresolved parameters: {', '.join(unresolved)}")
    
    sys.stdout.write(json.dumps(result, separators=(',', ':')))
    sys.stdout.write("\n")

if __name__ == "__main__":
    main()
