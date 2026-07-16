#!/usr/bin/env python3
import json
import sys
import re
import argparse

class ExprError(Exception):
    pass

class ExprParser:
    def __init__(self, text):
        self.text = text
        self.tokens = self.tokenize()
        self.tok_pos = 0

    def tokenize(self):
        text = self.text.strip()
        tokens = []
        i = 0
        while i < len(text):
            if text[i].isspace():
                i += 1
                continue
            if text[i:i+2] in ('**', '^^'):
                raise ExprError(f"unsupported operator '{text[i:i+2]}'")
            if text[i:i+2] in ('==', '!=', '>=', '<=', '&&', '||'):
                tokens.append(text[i:i+2])
                i += 2
                continue
            if text[i] in '+-*/()><!':
                tokens.append(text[i])
                i += 1
                continue
            if text[i] == '"':
                j = i + 1
                while j < len(text) and text[j] != '"':
                    if text[j] == '\\' and j + 1 < len(text):
                        j += 2
                    else:
                        j += 1
                if j >= len(text):
                    raise ExprError("unterminated string")
                tokens.append(text[i:j+1])
                i = j + 1
                continue
            m = re.match(r'[a-zA-Z_][a-zA-Z0-9_]*', text[i:])
            if m:
                word = m.group(0)
                tokens.append(word)
                i += len(word)
                continue
            m = re.match(r'\d+(\.\d+)?', text[i:])
            if m:
                tokens.append(m.group(0))
                i += len(m.group(0))
                continue
            raise ExprError(f"invalid character: {text[i]}")
        return tokens

    def current(self):
        if self.tok_pos < len(self.tokens):
            return self.tokens[self.tok_pos]
        return None

    def consume(self):
        tok = self.current()
        self.tok_pos += 1
        return tok

    def expect(self, expected):
        tok = self.current()
        if tok != expected:
            raise ExprError(f"expected '{expected}', got '{tok}'")
        self.tok_pos += 1

    def parse(self):
        if not self.tokens:
            raise ExprError("empty expression")
        result = self.parse_or()
        if self.current() is not None:
            raise ExprError(f"unexpected token: {self.current()}")
        return result

    def parse_or(self):
        left = self.parse_and()
        while self.current() == '||':
            self.consume()
            right = self.parse_and()
            left = ('||', left, right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.current() == '&&':
            self.consume()
            right = self.parse_not()
            left = ('&&', left, right)
        return left

    def parse_not(self):
        if self.current() == '!':
            self.consume()
            operand = self.parse_not()
            return ('!', operand)
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_add()
        if self.current() in ('>', '>=', '<', '<=', '==', '!='):
            op = self.consume()
            right = self.parse_add()
            return (op, left, right)
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.current() in ('+', '-'):
            op = self.consume()
            right = self.parse_mul()
            left = (op, left, right)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.current() in ('*', '/'):
            op = self.consume()
            right = self.parse_unary()
            left = (op, left, right)
        return left

    def parse_unary(self):
        if self.current() in ('+', '-'):
            op = self.consume()
            operand = self.parse_unary()
            return ('u' + op, operand)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current()
        if tok is None:
            raise ExprError("unexpected end of expression")
        if tok == '(':
            self.consume()
            expr = self.parse_or()
            self.expect(')')
            return expr
        if re.match(r'^\d+(\.\d+)?$', tok):
            self.consume()
            return ('num', float(tok) if '.' in tok else int(tok))
        if tok == 'true':
            self.consume()
            return ('bool', True)
        if tok == 'false':
            self.consume()
            return ('bool', False)
        if tok == 'null':
            self.consume()
            return ('null', None)
        if re.match(r'^".*"$', tok):
            self.consume()
            return ('str', tok[1:-1])
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tok):
            self.consume()
            return ('var', tok)
        raise ExprError(f"unexpected token: {tok}")

def parse_expr(expr_str):
    try:
        parser = ExprParser(expr_str)
        return parser.parse()
    except ExprError as e:
        raise e

def validate_expr(expr_str):
    try:
        parse_expr(expr_str)
        return True
    except ExprError:
        return False

def eval_expr(ast, row):
    if ast[0] == 'num':
        return ast[1]
    if ast[0] == 'bool':
        return ast[1]
    if ast[0] == 'null':
        return None
    if ast[0] == 'str':
        return ast[1]
    if ast[0] == 'var':
        return row.get(ast[1], None)
    if ast[0] == '!':
        val = eval_expr(ast[1], row)
        return not is_truthy(val)
    if ast[0] == '&&':
        left = eval_expr(ast[1], row)
        if not is_truthy(left):
            return False
        right = eval_expr(ast[2], row)
        return is_truthy(right)
    if ast[0] == '||':
        left = eval_expr(ast[1], row)
        if is_truthy(left):
            return True
        right = eval_expr(ast[2], row)
        return is_truthy(right)
    if ast[0] in ('+', '-', '*', '/'):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        return eval_arith(ast[0], left, right)
    if ast[0] in ('==', '!='):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        return eval_eq(ast[0], left, right)
    if ast[0] in ('>', '>=', '<', '<='):
        left = eval_expr(ast[1], row)
        right = eval_expr(ast[2], row)
        return eval_cmp(ast[0], left, right)
    if ast[0] in ('u+', 'u-'):
        val = eval_expr(ast[1], row)
        if val is None:
            return None
        if ast[0] == 'u+':
            return val
        if ast[0] == 'u-':
            return -val
    return None

def is_truthy(val):
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return True

def eval_arith(op, left, right):
    if left is None or right is None:
        return None
    if op == '+':
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left + right
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        return None
    if op == '-':
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left - right
        return None
    if op == '*':
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left * right
        return None
    if op == '/':
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if right == 0:
                return None
            return left / right
        return None

def eval_eq(op, left, right):
    if left is None or right is None:
        return False
    if type(left) != type(right):
        return False
    if op == '==':
        return left == right
    if op == '!=':
        return left != right
    return False

def eval_cmp(op, left, right):
    if left is None or right is None:
        return False
    # Allow int/float cross-type comparisons
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if op == '>':
            return left > right
        if op == '>=':
            return left >= right
        if op == '<':
            return left < right
        if op == '<=':
            return left <= right
        return False
    if type(left) != type(right):
        return False
    if not isinstance(left, (int, float, str)):
        return False
    if op == '>':
        return left > right
    if op == '>=':
        return left >= right
    if op == '<':
        return left < right
    if op == '<=':
        return left <= right
    return False

def error_response(error_code, message, path):
    return {
        "status": "error",
        "error_code": error_code,
        "message": f"ETL_ERROR: {message}",
        "path": path
    }

def ok_response_normalized(steps):
    return {
        "status": "ok",
        "normalized": {
            "steps": steps
        }
    }

def ok_response_executed(data, rows_in, rows_out):
    return {
        "status": "ok",
        "data": data,
        "metrics": {
            "rows_in": rows_in,
            "rows_out": rows_out
        }
    }

def validate_step(step, idx):
    if not isinstance(step, dict):
        return error_response("SCHEMA_VALIDATION_FAILED", "step must be an object", f"pipeline.steps[{idx}]")
    
    if "op" not in step:
        return error_response("SCHEMA_VALIDATION_FAILED", "missing op field", f"pipeline.steps[{idx}]")
    
    op = step["op"]
    if not isinstance(op, str):
        return error_response("SCHEMA_VALIDATION_FAILED", "op must be a string", f"pipeline.steps[{idx}].op")
    
    op = op.strip().lower()
    
    if op not in ("select", "filter", "map", "rename", "limit"):
        return error_response("UNKNOWN_OP", f"unsupported op '{op}'", f"pipeline.steps[{idx}].op")
    
    if op == "select":
        if "columns" not in step:
            return error_response("SCHEMA_VALIDATION_FAILED", "missing required field 'columns'", f"pipeline.steps[{idx}]")
        cols = step["columns"]
        if not isinstance(cols, list):
            return error_response("SCHEMA_VALIDATION_FAILED", "columns must be an array", f"pipeline.steps[{idx}].columns")
        for i, c in enumerate(cols):
            if not isinstance(c, str):
                return error_response("SCHEMA_VALIDATION_FAILED", "column name must be a string", f"pipeline.steps[{idx}].columns[{i}]")
    
    elif op == "filter":
        if "where" not in step:
            return error_response("SCHEMA_VALIDATION_FAILED", "missing required field 'where'", f"pipeline.steps[{idx}]")
        where = step["where"]
        if not isinstance(where, str):
            return error_response("SCHEMA_VALIDATION_FAILED", "where must be a string", f"pipeline.steps[{idx}].where")
        where = where.strip()
        if not where:
            return error_response("SCHEMA_VALIDATION_FAILED", "where cannot be empty", f"pipeline.steps[{idx}].where")
        try:
            parse_expr(where)
        except ExprError as e:
            return error_response("BAD_EXPR", str(e), f"pipeline.steps[{idx}].where")
    
    elif op == "map":
        if "as" not in step:
            return error_response("SCHEMA_VALIDATION_FAILED", "missing required field 'as'", f"pipeline.steps[{idx}]")
        if "expr" not in step:
            return error_response("SCHEMA_VALIDATION_FAILED", "missing required field 'expr'", f"pipeline.steps[{idx}]")
        as_field = step["as"]
        expr = step["expr"]
        if not isinstance(as_field, str):
            return error_response("SCHEMA_VALIDATION_FAILED", "as must be a string", f"pipeline.steps[{idx}].as")
        if not isinstance(expr, str):
            return error_response("SCHEMA_VALIDATION_FAILED", "expr must be a string", f"pipeline.steps[{idx}].expr")
        as_field = as_field.strip()
        expr = expr.strip()
        if not as_field:
            return error_response("SCHEMA_VALIDATION_FAILED", "as cannot be empty", f"pipeline.steps[{idx}].as")
        if not expr:
            return error_response("SCHEMA_VALIDATION_FAILED", "expr cannot be empty", f"pipeline.steps[{idx}].expr")
        try:
            parse_expr(expr)
        except ExprError as e:
            return error_response("BAD_EXPR", str(e), f"pipeline.steps[{idx}].expr")
    
    elif op == "rename":
        has_from = "from" in step
        has_to = "to" in step
        has_mapping = "mapping" in step
        
        if has_from and not has_to:
            return error_response("SCHEMA_VALIDATION_FAILED", "rename with from requires to", f"pipeline.steps[{idx}]")
        if has_to and not has_from:
            return error_response("SCHEMA_VALIDATION_FAILED", "rename with to requires from", f"pipeline.steps[{idx}]")
        
        has_from_to = has_from and has_to
        if not has_from_to and not has_mapping:
            return error_response("SCHEMA_VALIDATION_FAILED", "rename requires from/to or mapping", f"pipeline.steps[{idx}]")
        
        if has_from_to:
            from_val = step["from"]
            to_val = step["to"]
            if not isinstance(from_val, str) or not isinstance(to_val, str):
                return error_response("SCHEMA_VALIDATION_FAILED", "from and to must be strings", f"pipeline.steps[{idx}]")
            from_val = from_val.strip()
            to_val = to_val.strip()
            if not from_val:
                return error_response("SCHEMA_VALIDATION_FAILED", "from cannot be empty", f"pipeline.steps[{idx}].from")
            if not to_val:
                return error_response("SCHEMA_VALIDATION_FAILED", "to cannot be empty", f"pipeline.steps[{idx}].to")
        if has_mapping:
            mapping = step["mapping"]
            if not isinstance(mapping, dict):
                return error_response("SCHEMA_VALIDATION_FAILED", "mapping must be an object", f"pipeline.steps[{idx}].mapping")
            for k, v in mapping.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    return error_response("SCHEMA_VALIDATION_FAILED", "mapping keys and values must be strings", f"pipeline.steps[{idx}].mapping")
    
    elif op == "limit":
        if "n" not in step:
            return error_response("SCHEMA_VALIDATION_FAILED", "missing required field 'n'", f"pipeline.steps[{idx}]")
        n = step["n"]
        if not isinstance(n, int) or isinstance(n, bool):
            return error_response("SCHEMA_VALIDATION_FAILED", "n must be an integer", f"pipeline.steps[{idx}].n")
        if n < 0:
            return error_response("SCHEMA_VALIDATION_FAILED", "n must be >= 0", f"pipeline.steps[{idx}].n")
    
    return None

def normalize_step(step):
    op = step.get("op", "").strip().lower()
    
    known_fields = {"op"}
    if op == "select":
        known_fields.add("columns")
    elif op == "filter":
        known_fields.add("where")
    elif op == "map":
        known_fields.add("as")
        known_fields.add("expr")
    elif op == "rename":
        known_fields.add("from")
        known_fields.add("to")
        known_fields.add("mapping")
    elif op == "limit":
        known_fields.add("n")
    
    result = {"op": op}
    
    other_fields = sorted([k for k in known_fields if k != "op" and k in step])
    
    for k in other_fields:
        v = step[k]
        if k in ("where", "expr"):
            result[k] = v.strip() if isinstance(v, str) else v
        elif k == "as":
            result[k] = v.strip() if isinstance(v, str) else v
        elif k in ("from", "to"):
            result[k] = v.strip() if isinstance(v, str) else v
        elif k == "columns":
            result[k] = list(v) if isinstance(v, list) else v
        elif k == "mapping":
            result[k] = dict(v) if isinstance(v, dict) else v
        else:
            result[k] = v
    
    if op == "rename" and "from" in result and "to" in result:
        result["mapping"] = {result.pop("from"): result.pop("to")}
        new_result = {"op": result.pop("op")}
        for k in sorted(result.keys()):
            new_result[k] = result[k]
        result = new_result
    
    return result

def execute_step(step, data, idx):
    op = step["op"]
    
    if op == "select":
        columns = step["columns"]
        result = []
        for row in data:
            new_row = {}
            for col_idx, col in enumerate(columns):
                if col not in row:
                    return error_response("MISSING_COLUMN", f"column '{col}' not found in row", f"pipeline.steps[{idx}].columns[{col_idx}]")
                new_row[col] = row[col]
            result.append(new_row)
        return result
    
    if op == "filter":
        where_expr = step["where"]
        try:
            ast = parse_expr(where_expr)
        except ExprError as e:
            return error_response("BAD_EXPR", str(e), f"pipeline.steps[{idx}].where")
        result = []
        for row in data:
            try:
                val = eval_expr(ast, row)
                if is_truthy(val):
                    result.append(row)
            except Exception as e:
                return error_response("EXECUTION_FAILED", str(e), f"pipeline.steps[{idx}]")
        return result
    
    if op == "map":
        as_field = step["as"]
        expr = step["expr"]
        try:
            ast = parse_expr(expr)
        except ExprError as e:
            return error_response("BAD_EXPR", str(e), f"pipeline.steps[{idx}].expr")
        result = []
        for row in data:
            new_row = dict(row)
            try:
                val = eval_expr(ast, row)
                new_row[as_field] = val
            except Exception as e:
                return error_response("EXECUTION_FAILED", str(e), f"pipeline.steps[{idx}]")
            result.append(new_row)
        return result
    
    if op == "rename":
        mapping = step.get("mapping", {})
        result = []
        for row in data:
            new_row = dict(row)
            for src, dst in mapping.items():
                if src not in new_row:
                    return error_response("MISSING_COLUMN", f"column '{src}' not found in row", f"pipeline.steps[{idx}].mapping.{src}")
                new_row[dst] = new_row.pop(src)
            result.append(new_row)
        return result
    
    if op == "limit":
        n = step["n"]
        return data[:n]
    
    return data

def execute_pipeline(steps, dataset):
    data = [dict(row) for row in dataset]
    rows_in = len(data)
    
    for idx, step in enumerate(steps):
        result = execute_step(step, data, idx)
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        data = result
    
    rows_out = len(data)
    return ok_response_executed(data, rows_in, rows_out)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", default=False, help="Execute the pipeline")
    args = parser.parse_args()
    
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "invalid JSON", "")))
        sys.exit(1)
    
    if not isinstance(data, dict):
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "input must be an object", "")))
        sys.exit(1)
    
    if "dataset" not in data:
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "missing dataset", "")))
        sys.exit(1)
    
    dataset = data["dataset"]
    if not isinstance(dataset, list):
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "dataset must be an array", "dataset")))
        sys.exit(1)
    
    for i, item in enumerate(dataset):
        if not isinstance(item, dict):
            print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", f"dataset[{i}] must be an object", f"dataset[{i}]")))
            sys.exit(1)
    
    if "pipeline" not in data:
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "missing pipeline", "")))
        sys.exit(1)
    
    pipeline = data["pipeline"]
    if not isinstance(pipeline, dict):
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "pipeline must be an object", "pipeline")))
        sys.exit(1)
    
    if "steps" not in pipeline:
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "missing steps", "pipeline")))
        sys.exit(1)
    
    steps = pipeline["steps"]
    if not isinstance(steps, list):
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "steps must be an array", "pipeline.steps")))
        sys.exit(1)
    
    for i, step in enumerate(steps):
        err = validate_step(step, i)
        if err:
            print(json.dumps(err))
            sys.exit(1)
    
    normalized_steps = [normalize_step(step) for step in steps]
    
    if args.execute:
        result = execute_pipeline(normalized_steps, dataset)
        print(json.dumps(result))
    else:
        print(json.dumps(ok_response_normalized(normalized_steps)))
    
    sys.exit(0)

if __name__ == "__main__":
    main()
