# Experience Artifact and Manager Schema

This file records the exact experiment-facing schema used by the frozen SCBench MoA runs. External evaluator outcomes are logged after execution but are not supplied to self-report recipients.

## Worker artifact

```text
Worker <worker_id>, layer <layer>.
Local verifier Core: <passed>/<total>; pytest exit <code>.
Recent MiniSWE actions and reasoning:
<trailing 6,000 characters from the final four assistant messages>
Resulting source snapshot excerpt:
<UTF-8 source files, followed by whole-artifact truncation at 12,000 chars>
```

When the artifact is admitted by a self-report policy, the `Local verifier Core:` line is replaced with:

```text
Agent completion report: accepted without an independent smoke check; external evaluation withheld.
```

The admission expression is:

```python
re.search(r"\b(pass|passes|passed|works|working|success|successful|correct|verify|verified)\b", assistant_text, flags=re.IGNORECASE)
```

## Anonymized worker example

Header:

```text
Worker worker_1, layer 1.
Local verifier Core: 4/4; pytest exit 1.
```

Trajectory excerpt:

```text
THOUGHT: Example 8.4 works correctly. Let me run some additional edge case tests to ensure robustness.

```bash
cat <<'EOF' > test_edge_cases.py
#!/usr/bin/env python3
import subprocess
import os
import json

def run(args, env=None):
    result = subprocess.run(
        ["python", "cfgpipe.py"] + args,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})}
    )
    return result.returncode, result.stdout, result.stderr

# Test directory as file
os.makedirs("testdir", exist_ok=True)
schema_dir = {"val": {"type": "string", "file": "testdir"}}
with open("schema_dir.json", "w") as f:
    json.dump(schema_dir, f)
code, out, err = run(["schema_dir.json"])
print("Test dir:", code, out, err)
assert code != 0, "Directory should fail"

# Test float with no decimal part
schema_float = {"val": {"type": "float", "default": "5"}}
with open("schema_float.json", "w") 
```

Snapshot excerpt:

```text
### FILE cfgpipe.py
#!/usr/bin/env python3
import json
import os
import sys
import re
import stat

def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def parse_type(value, typ):
    if typ == "string":
        return value
    elif typ == "integer":
        if not re.fullmatch(r'-?\d+', value):
            raise ValueError(f"invalid integer: {value!r}")
        return str(int(value))
    elif typ == "float":
        if not re.fullmatch(r'-?\d+(\.\d+)?', value):
            raise ValueError(f"invalid float: {value!r}")
        return value
    elif typ == "boolean":
        lv = value.lower()
        if lv not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError(f"invalid boolean: {value!r}")
        return "true" if lv in ("true", "1", "yes", "on") else "false"
    else:
        raise ValueError(f"unknown type: {typ!r}")

def read_file(path)
```

## Recursive manager

System instruction fields: produce one shared implementation playbook; retain constraints, decisions, edge cases, failure-prevention rules, and validation procedures; resolve conflicts; return only the playbook.

User message fields: task identifier, public specification through the current layer, previous shared playbook, and newly accepted sources.

Example playbook excerpt:

```text
Shared Implementation Playbook: cfgpipe

## 1. Architecture & Entry Point

- Single-file Python 3 script `cfgpipe.py`
- Entry: `python cfgpipe.py <schema-file> [arg-candidates...]`
- `sys.argv[1]` = schema path; `sys.argv[2:]` = arg candidates
- All failures route through `fail(msg)` → prints to stderr, exits non-zero, no stdout

## 2. Schema Loading & Validation

### Loading
- Open schema file with `with open(..., 'r')`; catch `FileNotFoundError` and `OSError`/`IOError`
- Parse with `json.load(f)`; catch `json.JSONDecodeError`
- Root must be `dict`; else fail

### Per-Parameter Validation (before resolution)
- Each parameter value must be a `dict`; else fail
- Must have `'type'` key; else fail
- `type` must be in `{'string', 'integer', 'float', 'boolean'}`; else fail
- Source fields `default`, `env`, `file`, `arg` — if present, must be `str`; else fail
- Validation halts before any resolution begins

## 3. Type System & Parsers

| Type | Parser | Validation Rule | Resolved Form |
|------|--------|-----------------|---------------|
| `string` | `parse_string` | any string | as-is |
| `integer` | `parse_integer` | `re.fullmatch(r'-?[0-9]+', value)` | as-is string |
| `float` | `pars
```

## Provenance

- Implementation: `sec\scbench_miniswe.py` (`21f8ace635`)
- Frozen cumulative manifest: `runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_self_report_r2_20260715\cumulative_self_report_acceptance-426bc68aaa4b4e8c8f2aad850c75a89b\manifest.json`
- Example summary chars: 9445
- Manager example: `runs_scbench_moa_kimi_cfgpipe_cp1_recursive_synthesis_depth5_20260714\recursive_synthesis-6f605bbdeaa340a7ad79319c848f8038\manager\layer_1\synthesis.json` (`545deae643`)
