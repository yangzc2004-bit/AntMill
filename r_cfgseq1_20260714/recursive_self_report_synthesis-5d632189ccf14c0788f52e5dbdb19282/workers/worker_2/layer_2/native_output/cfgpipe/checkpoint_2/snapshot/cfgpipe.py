#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
import urllib.error


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


def lookup_primary_store(base_url, key):
    """Lookup a key in the primary store. Returns (found, value) or raises on error."""
    import urllib.parse
    encoded_key = urllib.parse.quote(key, safe='')
    url = f"{base_url}/v1/primary/kv?key={encoded_key}"
    req = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode('utf-8')
            data = json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            try:
                body = e.read().decode('utf-8')
                data = json.loads(body)
            except Exception:
                raise Exception(f"primary-store lookup for key '{key}': 404 with malformed response")
            if isinstance(data, dict) and data.get("found") is False:
                return (False, None)
            raise Exception(f"primary-store lookup for key '{key}': 404 with unexpected response")
        raise Exception(f"primary-store lookup for key '{key}': HTTP {e.code}")
    except json.JSONDecodeError:
        raise Exception(f"primary-store lookup for key '{key}': malformed JSON response")
    except Exception as e:
        raise Exception(f"primary-store lookup for key '{key}': network error: {e}")

    if not isinstance(data, dict):
        raise Exception(f"primary-store lookup for key '{key}': malformed response")
    if data.get("found") is not True:
        raise Exception(f"primary-store lookup for key '{key}': unexpected response")
    if "value" not in data:
        raise Exception(f"primary-store lookup for key '{key}': missing value in response")
    return (True, str(data["value"]))


def main():
    args = sys.argv[1:]
    if not args:
        error_exit("missing schema file")

    # Parse global flags before schema file
    primary_store_url = None
    schema_path = None
    arg_candidates = []
    i = 0
    while i < len(args):
        if args[i] == "--primary-store":
            if i + 1 >= len(args):
                error_exit("missing value for --primary-store")
            primary_store_url = args[i + 1]
            i += 2
        else:
            # This is the schema path (first non-global-flag argument)
            schema_path = args[i]
            arg_candidates = args[i + 1:]
            break

    if schema_path is None:
        error_exit("missing schema file")

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

    # Validate schema
    # Check for duplicate primary-store keys
    primary_store_keys = {}
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            error_exit(f"parameter '{param_name}' declaration must be an object")
        if "type" not in decl:
            error_exit(f"parameter '{param_name}' missing required 'type' field")
        if not isinstance(decl["type"], str):
            error_exit(f"parameter '{param_name}' 'type' must be a string")
        for field in ("default", "env", "file", "arg", "primary-store"):
            if field in decl and not isinstance(decl[field], str):
                error_exit(f"parameter '{param_name}' '{field}' must be a string")
        if "primary-store" in decl:
            key = decl["primary-store"]
            if key in primary_store_keys:
                other_param = primary_store_keys[key]
                error_exit(f"parameters '{other_param}' and '{param_name}' share primary-store key '{key}'")
            primary_store_keys[key] = param_name

    # Check: if any parameter declares primary-store but --primary-store is absent
    params_with_primary_store = [name for name, decl in schema.items() if "primary-store" in decl]
    if params_with_primary_store and primary_store_url is None:
        error_exit(f"parameter '{params_with_primary_store[0]}' declares primary-store but --primary-store is not configured")

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

        # Priority: arg > primary-store > file > env > default
        if "arg" in decl:
            arg_name = decl["arg"]
            if arg_name in arg_values:
                raw_value = arg_values[arg_name]
                source = "arg"

        if raw_value is None and "primary-store" in decl:
            key = decl["primary-store"]
            try:
                found, ps_value = lookup_primary_store(primary_store_url, key)
                if found:
                    raw_value = ps_value
                    source = "primary-store"
            except Exception as e:
                error_exit(str(e))

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
