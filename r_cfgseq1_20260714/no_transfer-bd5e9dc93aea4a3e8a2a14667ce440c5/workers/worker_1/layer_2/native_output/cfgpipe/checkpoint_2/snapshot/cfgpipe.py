#!/usr/bin/env python3
import json
import os
import sys
try:
    from urllib import request, parse, error
except ImportError:
    import urllib2 as request
    import urllib as parse
    import urllib2 as error

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

def lookup_primary_store(base_url, key):
    """Lookup a key in the primary store. Returns (found, value) or raises exception on failure."""
    import urllib.request
    import urllib.parse
    import urllib.error
    
    encoded_key = urllib.parse.quote(key, safe='')
    url = f"{base_url}/v1/primary/kv?key={encoded_key}"
    
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"malformed response from primary store: {e}")
            
            if status == 200:
                if isinstance(data, dict) and data.get('found') is True:
                    if 'value' not in data:
                        raise RuntimeError("malformed response from primary store: missing 'value' field")
                    return (True, data['value'])
                else:
                    raise RuntimeError("malformed response from primary store")
            elif status == 404:
                if isinstance(data, dict) and data.get('found') is False:
                    return (False, None)
                else:
                    raise RuntimeError("malformed response from primary store")
            else:
                raise RuntimeError(f"primary store returned status {status}")
    except urllib.error.HTTPError as e:
        # HTTPError is raised for non-2xx status codes
        status = e.code
        try:
            body = e.read().decode('utf-8')
            data = json.loads(body)
        except (IOError, OSError, json.JSONDecodeError):
            data = None
        
        if status == 404:
            if isinstance(data, dict) and data.get('found') is False:
                return (False, None)
            else:
                raise RuntimeError("malformed response from primary store")
        else:
            raise RuntimeError(f"primary store returned status {status}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"primary store network error: {e.reason}")
    except (IOError, OSError) as e:
        raise RuntimeError(f"primary store network error: {e}")

def resolve_param(name, spec, arg_values, primary_store_url):
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
    
    for field in ['default', 'env', 'file', 'arg', 'primary-store']:
        if field in spec and not isinstance(spec[field], str):
            sys.stderr.write(f"Parameter '{name}': '{field}' must be a string\n")
            sys.exit(1)
    
    # Priority: arg > primary-store > file > env > default (highest to lowest)
    
    # Check arg first
    if 'arg' in spec:
        arg_name = spec['arg']
        if arg_name in arg_values:
            try:
                return parse_value(arg_values[arg_name], typ)
            except ValueError as e:
                sys.stderr.write(f"Parameter '{name}': source 'arg' parse failure: {e}\n")
                sys.exit(1)
    
    # Check primary-store
    if 'primary-store' in spec and primary_store_url is not None:
        key = spec['primary-store']
        try:
            found, value = lookup_primary_store(primary_store_url, key)
            if found:
                try:
                    return parse_value(value, typ)
                except ValueError as e:
                    sys.stderr.write(f"Parameter '{name}': source 'primary-store' parse failure: {e}\n")
                    sys.exit(1)
        except RuntimeError as e:
            sys.stderr.write(f"Parameter '{name}': source 'primary-store' lookup failure: {e}\n")
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
        sys.stderr.write("Usage: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]\n")
        sys.exit(1)
    
    # Parse global flags before schema path
    args = sys.argv[1:]
    primary_store_url = None
    
    # Find schema path (first non-flag argument)
    schema_path = None
    schema_idx = 0
    for i, arg in enumerate(args):
        if arg.startswith('--'):
            if arg.startswith('--primary-store='):
                primary_store_url = arg.split('=', 1)[1]
            elif arg == '--primary-store':
                if i + 1 < len(args):
                    primary_store_url = args[i + 1]
                    # Skip the next argument as it's the value
                    # But we need to be careful - the next arg might be the schema path
                    # Actually, if --primary-store is followed by another flag, that's an error
                    # For now, let's just consume it
        elif arg.startswith('-'):
            pass  # Other flags
        else:
            schema_path = arg
            schema_idx = i
            break
    
    if schema_path is None:
        sys.stderr.write("Usage: python cfgpipe.py [global-flags...] <schema-file> [arg-candidates...]\n")
        sys.exit(1)
    
    # Collect arg candidates after schema path
    arg_candidates = []
    # Skip past the schema path and any consumed --primary-store value
    i = schema_idx + 1
    # Also need to skip the value of --primary-store if it was before schema_path
    # Let's re-process more carefully
    arg_candidates = args[schema_idx + 1:]
    
    # Re-parse global flags more carefully
    primary_store_url = None
    skip_next = False
    for i, arg in enumerate(args[:schema_idx]):
        if skip_next:
            skip_next = False
            continue
        if arg == '--primary-store':
            if i + 1 < schema_idx:
                primary_store_url = args[i + 1]
                skip_next = True
            else:
                sys.stderr.write("Missing value for --primary-store\n")
                sys.exit(1)
        elif arg.startswith('--primary-store='):
            primary_store_url = arg.split('=', 1)[1]
    
    arg_values = parse_args(arg_candidates)
    
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
    
    # Validate primary-store: check for duplicate keys and missing --primary-store
    primary_store_keys = {}
    for name, spec in schema.items():
        if isinstance(spec, dict) and 'primary-store' in spec:
            key = spec['primary-store']
            if not isinstance(key, str):
                sys.stderr.write(f"Parameter '{name}': 'primary-store' must be a string\n")
                sys.exit(1)
            if key in primary_store_keys:
                other_param = primary_store_keys[key]
                sys.stderr.write(f"Schema error: parameters '{other_param}' and '{name}' share primary-store key '{key}'\n")
                sys.exit(1)
            primary_store_keys[key] = name
    
    # Check if any parameter declares primary-store but --primary-store is absent
    if primary_store_keys and primary_store_url is None:
        # Name the first affected parameter
        first_param = list(primary_store_keys.values())[0]
        sys.stderr.write(f"Parameter '{first_param}': primary-store is declared but --primary-store is not configured\n")
        sys.exit(1)
    
    unresolved = []
    result = {}
    
    for name, spec in schema.items():
        resolved = resolve_param(name, spec, arg_values, primary_store_url)
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
