#!/usr/bin/env python3
import json
import sys
import re
import argparse

TOKEN_TYPES = [
    ('NUMBER', r'\d+(\.\d+)?'),
    ('STRING', r'"[^"]*"'),
    ('NULL', r'\bnull\b'),
    ('TRUE', r'\btrue\b'),
    ('FALSE', r'\bfalse\b'),
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
    tokens = []
    pos = 0
    while pos < len(expr):
        m = TOKEN_RE.match(expr, pos)
        if not m:
            if expr[pos:pos+2] in ('**', '^^', '&&', '||'):
                raise SyntaxError(f"unsupported operator '{expr[pos:pos+2]}'")
            if expr[pos] in '^&|':
                raise SyntaxError(f"unsupported operator '{expr[pos]}'")
            raise SyntaxError(f"Invalid character at position {pos}")
        kind = m.lastgroup
        val = m.group()
        if kind != 'WS':
            # Check if this OP token followed by same char forms invalid multi-char operator
            if kind == 'OP' and val in ('*', '^', '&', '|') and pos + 1 < len(expr) and expr[pos + 1] == val:
                raise SyntaxError(f"unsupported operator '{val * 2}'")
            tokens.append((kind, val))
        pos = m.end()
    return tokens

def validate_expression(expr):
    tokens = tokenize(expr)
    expect_value = True
    for i, (t, v) in enumerate(tokens):
        if expect_value:
            if t in ('NUMBER', 'STRING', 'IDENT', 'NULL', 'TRUE', 'FALSE'):
                expect_value = False
            elif t == 'NOT':
                pass
            elif t == 'OP' and v == '(':
                pass
            elif t == 'OP' and v in '+-':
                pass
            else:
                raise SyntaxError(f"Unexpected '{v}' at position {i}")
        else:
            if t == 'OP' and v in '+-*/':
                expect_value = True
            elif t == 'COMP':
                expect_value = True
            elif t == 'AND' or t == 'OR':
                expect_value = True
            elif t == 'OP' and v == ')':
                pass
            else:
                raise SyntaxError(f"Unexpected '{v}' at position {i}")
    if expect_value:
        if tokens:
            last_t, last_v = tokens[-1]
            raise SyntaxError(f"Unexpected end of expression after '{last_v}'")
        else:
            raise SyntaxError("Empty expression")
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
    if not isinstance(step, dict):
        return None, make_error("SCHEMA_VALIDATION_FAILED", f"Step must be an object", f"pipeline.steps[{idx}]")
    op = step.get("op")
    if op is None:
        return None, make_error("SCHEMA_VALIDATION_FAILED", "Missing 'op' field", f"pipeline.steps[{idx}].op")
    op = op.strip().lower()
    if not op:
        return None, make_error("SCHEMA_VALIDATION_FAILED", "Empty 'op' field", f"pipeline.steps[{idx}].op")
    if op not in ("select", "filter", "map", "rename", "limit"):
        return None, make_error("UNKNOWN_OP", f"unsupported op '{op}'", f"pipeline.steps[{idx}].op")
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
    sorted_keys = ["op"] + sorted(k for k in normalized if k != "op")
    normalized = {k: normalized[k] for k in sorted_keys}
    return normalized, None


def parse_expr(expr_str):
    try:
        tokens = tokenize(expr_str)
    except SyntaxError as e:
        return None, str(e)
    tokens = list(tokens)
    pos = [0]
    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None
    def consume():
        t = peek()
        if t:
            pos[0] += 1
        return t
    def parse_or():
        left = parse_and()
        while True:
            t = peek()
            if t and t[0] == 'OR':
                consume()
                right = parse_and()
                left = ('or', left, right)
            else:
                break
        return left
    def parse_and():
        left = parse_equality()
        while True:
            t = peek()
            if t and t[0] == 'AND':
                consume()
                right = parse_equality()
                left = ('and', left, right)
            else:
                break
        return left
    def parse_equality():
        left = parse_comparison()
        while True:
            t = peek()
            if t and t[0] == 'COMP' and t[1] in ('==', '!='):
                op = consume()[1]
                right = parse_comparison()
                left = (op, left, right)
            else:
                break
        return left
    def parse_comparison():
        left = parse_additive()
        while True:
            t = peek()
            if t and t[0] == 'COMP' and t[1] in ('<', '<=', '>', '>='):
                op = consume()[1]
                right = parse_additive()
                left = (op, left, right)
            else:
                break
        return left
    def parse_additive():
        left = parse_multiplicative()
        while True:
            t = peek()
            if t and t[0] == 'OP' and t[1] in ('+', '-'):
                op = consume()[1]
                right = parse_multiplicative()
                left = (op, left, right)
            else:
                break
        return left
    def parse_multiplicative():
        left = parse_unary()
        while True:
            t = peek()
            if t and t[0] == 'OP' and t[1] in ('*', '/'):
                op = consume()[1]
                right = parse_unary()
                left = (op, left, right)
            else:
                break
        return left
    def parse_unary():
        t = peek()
        if t and t[0] == 'NOT':
            consume()
            operand = parse_unary()
            return ('not', operand)
        elif t and t[0] == 'OP' and t[1] == '-':
            consume()
            operand = parse_unary()
            return ('neg', operand)
        elif t and t[0] == 'OP' and t[1] == '+':
            consume()
            return parse_unary()
        else:
            return parse_primary()
    def parse_primary():
        t = peek()
        if not t:
            return None
        if t[0] == 'NUMBER':
            consume()
            val = t[1]
            if '.' in val:
                return ('num', float(val))
            else:
                return ('num', int(val))
        if t[0] == 'STRING':
            consume()
            return ('str', t[1][1:-1])
        if t[0] == 'NULL':
            consume()
            return ('null', None)
        if t[0] == 'TRUE':
            consume()
            return ('bool', True)
        if t[0] == 'FALSE':
            consume()
            return ('bool', False)
        if t[0] == 'IDENT':
            consume()
            return ('ident', t[1])
        if t[0] == 'OP' and t[1] == '(':
            consume()
            inner = parse_or()
            t2 = peek()
            if not t2 or not (t2[0] == 'OP' and t2[1] == ')'):
                return None
            consume()
            return inner
        return None
    ast = parse_or()
    if pos[0] != len(tokens):
        return None, f"Unexpected '{tokens[pos[0]][1]}'"
    return ast, None

def eval_expr(ast, row):
    if ast is None:
        return None
    node_type = ast[0]
    if node_type == 'num':
        return ast[1]
    if node_type == 'str':
        return ast[1]
    if node_type == 'null':
        return None
    if node_type == 'bool':
        return ast[1]
    if node_type == 'ident':
        return row.get(ast[1], None)
    if node_type == 'not':
        val = eval_expr(ast[1], row)
        return bool(val) if val is not None else False
    if node_type == 'neg':
        val = eval_expr(ast[1], row)
        if val is None:
            return None
        return -val
    if node_type in ('+', '-', '*', '/'):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        if left is None or right is None:
            return None
        if node_type == '+':
            return left + right
        elif node_type == '-':
            return left - right
        elif node_type == '*':
            return left * right
        elif node_type == '/':
            if right == 0:
                return None
            return left / right
    if node_type in ('==', '!='):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        if type(left) != type(right):
            if left is None or right is None:
                return False
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return (left == right) if node_type == '==' else (left != right)
            return False if node_type == '==' else True
        if left is None or right is None:
            return False
        return (left == right) if node_type == '==' else (left != right)
    if node_type in ('<', '<=', '>', '>='):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        if left is None or right is None:
            return False
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return False
        # Allow int/float comparison
        if node_type == '<':
            return left < right
        elif node_type == '<=':
            return left <= right
        elif node_type == '>':
            return left > right
        elif node_type == '>=':
            return left >= right
    if node_type == 'and':
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        return bool(left) and bool(right)
    if node_type == 'or':
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        return bool(left) or bool(right)
    return None

def execute_select(dataset, step, path):
    cols = step["columns"]
    result = []
    for row in dataset:
        new_row = {}
        for j, col in enumerate(cols):
            if col not in row:
                return None, make_error("MISSING_COLUMN", f"column '{col}' not found in row", f"{path}.columns[{j}]")
            new_row[col] = row[col]
        result.append(new_row)
    return result, None

def execute_map(dataset, step, path):
    as_field = step["as"]
    expr_str = step["expr"]
    ast, err = parse_expr(expr_str)
    if err:
        return None, make_error("BAD_EXPR", err, path)
    result = []
    for row in dataset:
        new_row = dict(row)
        new_row[as_field] = eval_expr(ast, row)
        result.append(new_row)
    return result, None

def execute_filter(dataset, step, path):
    expr_str = step["where"]
    ast, err = parse_expr(expr_str)
    if err:
        return None, make_error("BAD_EXPR", err, path)
    result = []
    for row in dataset:
        val = eval_expr(ast, row)
        if bool(val):
            result.append(row)
    return result, None

def execute_rename(dataset, step, path):
    mapping = step["mapping"]
    result = []
    for row in dataset:
        new_row = dict(row)
        for from_field, to_field in mapping.items():
            if from_field not in new_row:
                return None, make_error("MISSING_COLUMN", f"column '{from_field}' not found in row", path)
            new_row[to_field] = new_row.pop(from_field)
        result.append(new_row)
    return result, None

def execute_limit(dataset, step, path):
    n = step["n"]
    return dataset[:n], None

def execute_pipeline(dataset, steps):
    for i, step in enumerate(steps):
        op = step["op"]
        if op == "select":
            result, err = execute_select(dataset, step, f"pipeline.steps[{i}]")
        elif op == "map":
            result, err = execute_map(dataset, step, f"pipeline.steps[{i}].expr")
        elif op == "filter":
            result, err = execute_filter(dataset, step, f"pipeline.steps[{i}].where")
        elif op == "rename":
            result, err = execute_rename(dataset, step, f"pipeline.steps[{i}].mapping")
        elif op == "limit":
            result, err = execute_limit(dataset, step, f"pipeline.steps[{i}]")
        else:
            return None, make_error("EXECUTION_FAILED", f"unsupported op '{op}'", f"pipeline.steps[{i}]")
        if err:
            return None, err
        dataset = result
    return dataset, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", default=False, help="Execute the pipeline")
    args = parser.parse_args()
    
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
    
    if args.execute:
        result_data, error = execute_pipeline(dataset, normalized_steps)
        if error:
            print(json.dumps(error))
            sys.exit(1)
        output = {
            "status": "ok",
            "data": result_data,
            "metrics": {
                "rows_in": len(dataset),
                "rows_out": len(result_data)
            }
        }
        print(json.dumps(output))
    else:
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
