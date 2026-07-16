import json
import os
import re
import sys


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def parse_args(argv):
    # argv[0] is script name, argv[1] is schema file, argv[2:] are arg candidates
    result = {}
    for arg in argv[2:]:
        m = re.fullmatch(r'--?([^=]+)=(.*)', arg)
        if m:
            name = m.group(1)
            value = m.group(2)
            result[name] = value
    return result


def read_file(path):
    try:
        if not os.path.exists(path) or not os.path.isfile(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.strip()
        if content == '':
            return None
        return content
    except (OSError, IOError):
        return None


def parse_value(param_name, source_name, raw_value, typ):
    if typ == 'string':
        return raw_value

    if typ == 'integer':
        if re.fullmatch(r'-?\d+', raw_value) is None:
            fail(f"parse failure: parameter '{param_name}' from source '{source_name}': '{raw_value}' is not a valid integer")
        # Return plain decimal, no scientific notation
        # Validate it's a valid int
        int(raw_value)  # This will raise if somehow invalid, but regex should catch
        return raw_value

    if typ == 'float':
        if re.fullmatch(r'-?\d+(?:\.\d+)?', raw_value) is None:
            fail(f"parse failure: parameter '{param_name}' from source '{source_name}': '{raw_value}' is not a valid float")
        # Return as-is; no exact canonical format required
        return raw_value

    if typ == 'boolean':
        lowered = raw_value.lower()
        if lowered in ('true', 'yes', '1', 'on'):
            return 'true'
        elif lowered in ('false', 'no', '0', 'off'):
            return 'false'
        else:
            fail(f"parse failure: parameter '{param_name}' from source '{source_name}': '{raw_value}' is not a valid boolean")

    fail(f"parse failure: parameter '{param_name}' has unrecognized type '{typ}'")


def main():
    if len(sys.argv) < 2:
        fail("usage: python cfgpipe.py <schema-file> [arg-candidates...]")

    schema_path = sys.argv[1]

    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except FileNotFoundError:
        fail(f"schema file not found: {schema_path}")
    except json.JSONDecodeError as e:
        fail(f"invalid JSON in schema file: {e}")

    if not isinstance(schema, dict):
        fail("schema root must be a JSON object")

    # Validate schema
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            fail(f"schema validation failure: parameter '{param_name}' declaration must be an object")
        if 'type' not in decl:
            fail(f"schema validation failure: parameter '{param_name}' missing required 'type' field")
        if not isinstance(decl['type'], str):
            fail(f"schema validation failure: parameter '{param_name}' 'type' must be a string")
        for field in ('default', 'env', 'file', 'arg'):
            if field in decl and not isinstance(decl[field], str):
                fail(f"schema validation failure: parameter '{param_name}' '{field}' must be a string")

    args = parse_args(sys.argv)

    result = {}
    unresolved = []

    for param_name, decl in schema.items():
        typ = decl['type']
        raw_value = None
        source_name = None

        # Priority: arg > file > env > default
        # Check arg first
        if 'arg' in decl:
            arg_name = decl['arg']
            if arg_name in args:
                raw_value = args[arg_name]
                source_name = 'arg'

        # Check file
        if raw_value is None and 'file' in decl:
            file_val = read_file(decl['file'])
            if file_val is not None:
                raw_value = file_val
                source_name = 'file'

        # Check env
        if raw_value is None and 'env' in decl:
            env_val = os.environ.get(decl['env'])
            if env_val is not None and env_val != '':
                raw_value = env_val
                source_name = 'env'

        # Check default
        if raw_value is None and 'default' in decl:
            raw_value = decl['default']
            source_name = 'default'

        if raw_value is None:
            unresolved.append(param_name)
        else:
            parsed = parse_value(param_name, source_name, raw_value, typ)
            result[param_name] = parsed

    if unresolved:
        fail(f"unresolved parameters: {', '.join(unresolved)}")

    sys.stdout.write(json.dumps(result, separators=(',', ':')) + "\n")


if __name__ == '__main__':
    main()
