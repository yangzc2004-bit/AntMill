#!/usr/bin/env python3
import json
import sys
import re

# Token types for expression parsing - order matters!
# Keywords must come before IDENT
TOKEN_TYPES = [
    ('NUMBER', r'\d+(\.\d+)?'),
    ('STRING', r'"[^"]*"'),
    ('AND', r'\band\b'),
    ('OR', r'\bor\b'),
    ('NOT', r'\bnot\b'),
    ('IDENT', r'[a-zA-Z_][a-zA-Z0-9_]*'),
    ('OP', r'[+\-*/()]'),
    ('COMP', r'>=|<=|==|!=|>|<'),
    ('WS', r'\s+'),
]

TOKEN_RE = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_TYPES))

def tokenize(expr):
    """Tokenize an expression. Returns list of tokens or raises SyntaxError."""
    tokens = []
    pos = 0
    while pos < len(expr):
        m = TOKEN_RE.match(expr, pos)
        if not m:
            # Check for invalid characters
            if expr[pos] in '^&|':
                raise SyntaxError(f"Invalid character '{expr[pos]}' at position {pos}")
            raise SyntaxError(f"Invalid character at position {pos}")
        kind = m.lastgroup
        val = m.group()
        if kind != 'WS':
            tokens.append((kind, val))
        pos = m.end()
    return tokens

def validate_expression(expr):
    """Validate a filter/map expression for obvious syntax errors."""
    tokens = tokenize(expr)
    
    # A valid expression alternates between values/prefix and infix/postfix
    # After these, we expect a value or prefix operator
    expect_value = True
    
    for i, (t, v) in enumerate(tokens):
        if expect_value:
            # We need a value or prefix operator
            if t in ('NUMBER', 'STRING', 'IDENT'):
                expect_value = False
            elif t == 'NOT':
                pass  # still expect value
            elif t == 'OP' and v == '(':
                pass  # still expect value
            elif t == 'OP' and v in '+-':
                pass  # unary + or -, still expect value
            else:
                raise SyntaxError(f"Unexpected '{v}' at position {i}")
        else:
            # We need an infix or postfix operator
            if t == 'OP' and v in '+-*/':
                expect_value = True
            elif t == 'COMP':
                expect_value = True
            elif t == 'AND' or t == 'OR':
                expect_value = True
            elif t == 'OP' and v == ')':
                pass  # still not expecting value
            else:
                raise SyntaxError(f"Unexpected '{v}' at position {i}")
    
    if expect_value:
        # Expression ended while expecting a value
        if tokens:
            last_t, last_v = tokens[-1]
            raise SyntaxError(f"Unexpected end of expression after '{last_v}'")
        else:
            raise SyntaxError("Empty expression")
    
    # Check parentheses balance
    depth = 0
    for t, v in tokens:
        if t == 'OP' and v == '(':
            depth += 1
        elif t == 'OP' and v == ')':
            depth -= 1
            if depth < 0:
                raise SyntaxError("Unbalanced parentheses")
    if depth != 0:
        raise SyntaxError("Unbalanced parentheses")
    
    return True

def make_error(code, message, path):
    return {
        "status": "error",
        "error_code": code,
        "message": f"ETL_ERROR: {message}",
        "path": path
    }

def normalize_step(step, idx):
    """Normalize and validate a single step. Returns (normalized_step, error)."""
    if not isinstance(step, dict):
        return None, make_error("SCHEMA_VALIDATION_FAILED", f"Step must be an object", f"pipeline.steps[{idx}]")
    
    # Get op, normalize it
    op = step.get("op")
    if op is None:
        return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'op' field", f"pipeline.steps[{idx}].op")
    
    op = op.strip().lower()
    if not op:
        return None, make_error("SCHEMA_VALIDATION_FAILED", "Empty 'op' field", f"pipeline.steps[{idx}].op")
    
    if op not in ("select", "filter", "map", "rename", "limit"):
        return None, make_error("UNKNOWN_OP", f"unsupported op '{op}'", f"pipeline.steps[{idx}].op")
    
    # Build normalized step with known keys only
    known_keys = {"op"}
    normalized = {"op": op}
    
    if op == "select":
        known_keys.add("columns")
        cols = step.get("columns")
        if cols is None:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'columns' field", f"pipeline.steps[{idx}].columns")
        if not isinstance(cols, list):
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'columns' must be an array", f"pipeline.steps[{idx}].columns")
        if len(cols) == 0:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'columns' must not be empty", f"pipeline.steps[{idx}].columns")
        for c in cols:
            if not isinstance(c, str):
                return None, make_error("SCHEMA_VALIDATION_FAILED", "All columns must be strings", f"pipeline.steps[{idx}].columns")
        normalized["columns"] = cols
    
    elif op == "filter":
        known_keys.add("where")
        where = step.get("where")
        if where is None:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'where' field", f"pipeline.steps[{idx}].where")
        if not isinstance(where, str):
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'where' must be a string", f"pipeline.steps[{idx}].where")
        where = where.strip()
        if not where:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'where' must not be empty", f"pipeline.steps[{idx}].where")
        try:
            validate_expression(where)
        except SyntaxError as e:
            return None, make_error("BAD_EXPR", str(e), f"pipeline.steps[{idx}].where")
        normalized["where"] = where
    
    elif op == "map":
        known_keys.add("as")
        known_keys.add("expr")
        as_field = step.get("as")
        expr = step.get("expr")
        if as_field is None:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'as' field", f"pipeline.steps[{idx}].as")
        if expr is None:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'expr' field", f"pipeline.steps[{idx}].expr")
        if not isinstance(as_field, str):
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'as' must be a string", f"pipeline.steps[{idx}].as")
        if not isinstance(expr, str):
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'expr' must be a string", f"pipeline.steps[{idx}].expr")
        as_field = as_field.strip()
        expr = expr.strip()
        if not as_field:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'as' must not be empty", f"pipeline.steps[{idx}].as")
        if not expr:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'expr' must not be empty", f"pipeline.steps[{idx}].expr")
        try:
            validate_expression(expr)
        except SyntaxError as e:
            return None, make_error("BAD_EXPR", str(e), f"pipeline.steps[{idx}].expr")
        normalized["as"] = as_field
        normalized["expr"] = expr
    
    elif op == "rename":
        # Check for from/to
        from_field = step.get("from")
        to_field = step.get("to")
        mapping = step.get("mapping")
        
        if from_field is not None or to_field is not None:
            known_keys.add("from")
            known_keys.add("to")
            if from_field is None:
                return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'from' field", f"pipeline.steps[{idx}].from")
            if to_field is None:
                return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'to' field", f"pipeline.steps[{idx}].to")
            if not isinstance(from_field, str):
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'from' must be a string", f"pipeline.steps[{idx}].from")
            if not isinstance(to_field, str):
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'to' must be a string", f"pipeline.steps[{idx}].to")
            from_field = from_field.strip()
            to_field = to_field.strip()
            if not from_field:
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'from' must not be empty", f"pipeline.steps[{idx}].from")
            if not to_field:
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'to' must not be empty", f"pipeline.steps[{idx}].to")
            normalized["mapping"] = {from_field: to_field}
        elif mapping is not None:
            known_keys.add("mapping")
            if not isinstance(mapping, dict):
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'mapping' must be an object", f"pipeline.steps[{idx}].mapping")
            if len(mapping) == 0:
                return None, make_error("SCHEMA_VALIDATION_FAILED", "'mapping' must not be empty", f"pipeline.steps[{idx}].mapping")
            for k, v in mapping.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    return None, make_error("SCHEMA_VALIDATION_FAILED", "Mapping keys and values must be strings", f"pipeline.steps[{idx}].mapping")
            normalized["mapping"] = mapping
        else:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'from'/'to' or 'mapping' field", f"pipeline.steps[{idx}]")
    
    elif op == "limit":
        known_keys.add("n")
        n = step.get("n")
        if n is None:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'n' field", f"pipeline.steps[{idx}].n")
        if not isinstance(n, int) or isinstance(n, bool):
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'n' must be an integer", f"pipeline.steps[{idx}].n")
        if n < 0:
            return None, make_error("SCHEMA_VALIDATION_FAILED", "'n' must be >= 0", f"pipeline.steps[{idx}].n")
        normalized["n"] = n
    
    # Sort keys alphabetically with op first
    sorted_keys = ["op"] + sorted(k for k in normalized if k != "op")
    normalized = {k: normalized[k] for k in sorted_keys}
    
    return normalized, None

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", f"Invalid JSON: {e}", "")))
        sys.exit(1)
    except Exception as e:
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", str(e), "")))
        sys.exit(1)
    
    if not isinstance(data, dict):
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "Input must be a JSON object", "")))
        sys.exit(1)
    
    # Validate pipeline exists
    pipeline = data.get("pipeline")
    if pipeline is None:
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "Missing 'pipeline' field", "pipeline")))
        sys.exit(1)
    
    if not isinstance(pipeline, dict):
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "'pipeline' must be an object", "pipeline")))
        sys.exit(1)
    
    steps = pipeline.get("steps")
    if steps is None:
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "Missing 'steps' field", "pipeline.steps")))
        sys.exit(1)
    
    if not isinstance(steps, list):
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "'steps' must be an array", "pipeline.steps")))
        sys.exit(1)
    
    # Validate dataset
    dataset = data.get("dataset")
    if dataset is None:
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "Missing 'dataset' field", "dataset")))
        sys.exit(1)
    
    if not isinstance(dataset, list):
        print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", "'dataset' must be an array", "dataset")))
        sys.exit(1)
    
    for i, item in enumerate(dataset):
        if not isinstance(item, dict):
            print(json.dumps(make_error("SCHEMA_VALIDATION_FAILED", f"dataset[{i}] must be an object", f"dataset[{i}]")))
            sys.exit(1)
    
    normalized_steps = []
    for i, step in enumerate(steps):
        norm_step, error = normalize_step(step, i)
        if error:
            print(json.dumps(error))
            sys.exit(1)
        normalized_steps.append(norm_step)
    
    output = {
        "status": "ok",
        "normalized": {
            "steps": normalized_steps
        }
    }
    print(json.dumps(output))
    sys.exit(0)

if __name__ == "__main__":
    main()
