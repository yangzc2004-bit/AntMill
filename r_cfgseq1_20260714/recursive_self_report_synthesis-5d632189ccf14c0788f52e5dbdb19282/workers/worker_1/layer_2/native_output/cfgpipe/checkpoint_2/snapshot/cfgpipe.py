import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def parse_global_flags_and_args(argv):
    # Global flags may precede the schema path.
    # Format: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]
    primary_store = None
    i = 1
    while i < len(argv):
        if argv[i] == '--primary-store':
            if i + 1 >= len(argv):
                fail("missing value for --primary-store")
            primary_store = argv[i + 1]
            i += 2
        else:
            # Not a global flag we recognize; assume it's the schema file
            break
    
    if i >= len(argv):
        fail("usage: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]")
    
    schema_path = argv[i]
    arg_candidates = argv[i + 1:]
    
    # Parse arg candidates
    args = {}
    for arg in arg_candidates:
        m = re.fullmatch(r'--?([^=]+)=(.*)', arg)
        if m:
            name = m.group(1)
            value = m.group(2)
            args[name] = value
    
    return primary_store, schema_path, args


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


def lookup_primary_store(base_url, key):
    # Seed lookup: GET <base-url>/v1/primary/kv?key=<url-encoded-key>
    encoded_key = urllib.parse.quote(key, safe='')
    url = f"{base_url}/v1/primary/kv?key={encoded_key}"
    
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read().decode('utf-8')
        except Exception:
            body = ''
    except Exception as e:
        fail(f"primary-store connector failure: {e}")
        return None  # unreachable
    
    # Parse response body as JSON
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        fail(f"primary-store connector failure: malformed response for key '{key}'")
        return None  # unreachable
    
    if status == 200:
        if isinstance(data, dict) and data.get('found') is True and 'value' in data:
            return data['value']
        else:
            fail(f"primary-store connector failure: malformed response for key '{key}'")
            return None  # unreachable
    elif status == 404:
        if isinstance(data, dict) and data.get('found') is False:
            return None  # missing key
        else:
            fail(f"primary-store connector failure: malformed response for key '{key}'")
            return None  # unreachable
    else:
        fail(f"primary-store connector failure: unexpected status {status} for key '{key}'")
        return None  # unreachable


def parse_value(param_name, source_name, raw_value, typ):
    if typ == 'string':
        return raw_value

    if typ == 'integer':
        if re.fullmatch(r'-?\d+', raw_value) is None:
            fail(f"parse failure: parameter '{param_name}' from source '{source_name}': '{raw_value}' is not a valid integer")
        int(raw_value)  # Validate it's a valid int
        return raw_value

    if typ == 'float':
        if re.fullmatch(r'-?\d+(?:\.\d+)?', raw_value) is None:
            fail(f"parse failure: parameter '{param_name}' from source '{source_name}': '{raw_value}' is not a valid float")
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
    primary_store, schema_path, args = parse_global_flags_and_args(sys.argv)

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
    primary_keys = {}  # key -> param_name for duplicate detection
    has_primary_store_decl = False
    
    for param_name, decl in schema.items():
        if not isinstance(decl, dict):
            fail(f"schema validation failure: parameter '{param_name}' declaration must be an object")
        if 'type' not in decl:
            fail(f"schema validation failure: parameter '{param_name}' missing required 'type' field")
        if not isinstance(decl['type'], str):
            fail(f"schema validation failure: parameter '{param_name}' 'type' must be a string")
        for field in ('default', 'env', 'file', 'arg', 'primary-store'):
            if field in decl and not isinstance(decl[field], str):
                fail(f"schema validation failure: parameter '{param_name}' '{field}' must be a string")
        
        if 'primary-store' in decl:
            has_primary_store_decl = True
            ps_key = decl['primary-store']
            if ps_key in primary_keys:
                other_param = primary_keys[ps_key]
                fail(f"schema validation failure: parameters '{other_param}' and '{param_name}' share primary-store key '{ps_key}'")
            primary_keys[ps_key] = param_name

    # If any parameter declares primary-store but --primary-store is absent, fail
    if has_primary_store_decl and primary_store is None:
        # Find the first parameter that declares it to name in error
        for param_name, decl in schema.items():
            if 'primary-store' in decl:
                fail(f"primary-store not configured but parameter '{param_name}' declares primary-store")

    result = {}
    unresolved = []

    for param_name, decl in schema.items():
        typ = decl['type']
        raw_value = None
        source_name = None

        # Priority: arg > primary-store > file > env > default
        # Check arg first
        if 'arg' in decl:
            arg_name = decl['arg']
            if arg_name in args:
                raw_value = args[arg_name]
                source_name = 'arg'

        # Check primary-store
        if raw_value is None and 'primary-store' in decl and primary_store is not None:
            ps_key = decl['primary-store']
            ps_value = lookup_primary_store(primary_store, ps_key)
            if ps_value is not None:
                raw_value = ps_value
                source_name = 'primary-store'

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
