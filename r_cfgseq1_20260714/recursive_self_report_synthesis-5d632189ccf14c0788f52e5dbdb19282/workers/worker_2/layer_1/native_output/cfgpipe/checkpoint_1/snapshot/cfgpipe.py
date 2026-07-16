#!/usr/bin/env python3
import json
import os
import sys
import re


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def parse_args(argv):
    if len(argv) < 2:
        fail("Usage: python cfgpipe.py <schema-file> [arg-candidates...]")
    schema_path = argv[1]
    arg_candidates = argv[2:]
    return schema_path, arg_candidates


def load_schema(path):
    if not os.path.exists(path):
        fail(f"Schema file missing: {path}")
    try:
        with open(path, 'r') as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        fail(f"Invalid JSON in schema: {e}")
    except Exception as e:
        fail(f"Cannot read schema file: {e}")
    
    if not isinstance(schema, dict):
        fail("Schema root must be a JSON object")
    
    for param_name, param_decl in schema.items():
        if not isinstance(param_decl, dict):
            fail(f"Parameter '{param_name}' declaration must be an object")
        if 'type' not in param_decl:
            fail(f"Parameter '{param_name}' missing required 'type' field")
        for field in ('default', 'env', 'file', 'arg'):
            if field in param_decl and not isinstance(param_decl[field], str):
                fail(f"Parameter '{param_name}' field '{field}' must be a string")
    
    return schema


def parse_arg_candidates(arg_candidates):
    args = {}
    for arg in arg_candidates:
        m = re.match(r'^--?([^=]+)=(.*)$', arg)
        if m:
            name = m.group(1)
            value = m.group(2)
            args[name] = value
    return args


def read_file(path):
    if not os.path.exists(path):
        return None
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r') as f:
            content = f.read()
    except Exception:
        return None
    content = content.strip()
    if content == '':
        return None
    return content


def parse_value(param_name, source_name, raw_value, typ):
    if typ == 'string':
        return raw_value
    elif typ == 'integer':
        if not re.fullmatch(r'-?[0-9]+', raw_value):
            fail(f"Parameter '{param_name}' from source '{source_name}': cannot parse '{raw_value}' as integer")
        return raw_value
    elif typ == 'float':
        try:
            float(raw_value)
        except ValueError:
            fail(f"Parameter '{param_name}' from source '{source_name}': cannot parse '{raw_value}' as float")
        return raw_value
    elif typ == 'boolean':
        lowered = raw_value.lower()
        if lowered == 'true':
            return 'true'
        elif lowered == 'false':
            return 'false'
        else:
            fail(f"Parameter '{param_name}' from source '{source_name}': cannot parse '{raw_value}' as boolean")
    else:
        fail(f"Parameter '{param_name}' has unrecognized type '{typ}'")


def resolve_param(param_name, param_decl, args):
    typ = param_decl['type']
    
    # Priority order: arg > file > env > default
    # The first source that provides a value wins.
    
    if 'arg' in param_decl:
        arg_name = param_decl['arg']
        if arg_name in args:
            return parse_value(param_name, 'arg', args[arg_name], typ)
    
    if 'file' in param_decl:
        file_val = read_file(param_decl['file'])
        if file_val is not None:
            return parse_value(param_name, 'file', file_val, typ)
    
    if 'env' in param_decl:
        env_val = os.environ.get(param_decl['env'])
        if env_val is not None:
            return parse_value(param_name, 'env', env_val, typ)
    
    if 'default' in param_decl:
        return parse_value(param_name, 'default', param_decl['default'], typ)
    
    return None


def main():
    schema_path, arg_candidates = parse_args(sys.argv)
    schema = load_schema(schema_path)
    args = parse_arg_candidates(arg_candidates)
    
    unresolved = []
    result = {}
    
    for param_name, param_decl in schema.items():
        resolved = resolve_param(param_name, param_decl, args)
        if resolved is None:
            unresolved.append(param_name)
        else:
            result[param_name] = resolved
    
    if unresolved:
        fail(f"Unresolved parameters: {', '.join(unresolved)}")
    
    print(json.dumps(result, separators=(',', ':')))


if __name__ == '__main__':
    main()
