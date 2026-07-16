#!/usr/bin/env python3
import json
import sys
import re

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
            if text[i:i+2] in ('==', '!=', '>=', '<='):
                tokens.append(text[i:i+2])
                i += 2
                continue
            if text[i] in '+-*/()><':
                tokens.append(text[i])
                i += 1
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
        while self.current() == 'or':
            self.consume()
            right = self.parse_and()
            left = ('or', left, right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.current() == 'and':
            self.consume()
            right = self.parse_not()
            left = ('and', left, right)
        return left

    def parse_not(self):
        if self.current() == 'not':
            self.consume()
            operand = self.parse_not()
            return ('not', operand)
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
            return (op, operand)
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
            return ('num', tok)
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tok):
            self.consume()
            return ('var', tok)
        raise ExprError(f"unexpected token: {tok}")

def validate_expr(expr_str):
    try:
        parser = ExprParser(expr_str)
        parser.parse()
        return True
    except ExprError:
        return False

def error_response(error_code, message, path):
    return {
        "status": "error",
        "error_code": error_code,
        "message": f"ETL_ERROR: {message}",
        "path": path
    }

def ok_response(steps):
    return {
        "status": "ok",
        "normalized": {
            "steps": steps
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
    
    # Validate required fields
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
        if not validate_expr(where):
            return error_response("BAD_EXPR", "invalid expression", f"pipeline.steps[{idx}].where")
    
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
        if not validate_expr(expr):
            return error_response("BAD_EXPR", "invalid expression", f"pipeline.steps[{idx}].expr")
    
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
    
    # Known fields per op
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
    
    # Build normalized step with known fields only, op first, then alphabetically
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
    
    # Convert rename from/to to mapping
    if op == "rename" and "from" in result and "to" in result:
        result["mapping"] = {result.pop("from"): result.pop("to")}
        # Reorder to keep op first then alphabetical
        new_result = {"op": result.pop("op")}
        for k in sorted(result.keys()):
            new_result[k] = result[k]
        result = new_result
    
    return result

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "invalid JSON", "")))
        sys.exit(1)
    
    if not isinstance(data, dict):
        print(json.dumps(error_response("SCHEMA_VALIDATION_FAILED", "input must be an object", "")))
        sys.exit(1)
    
    # Validate dataset
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
    
    # Validate pipeline
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
    
    print(json.dumps(ok_response(normalized_steps)))
    sys.exit(0)

if __name__ == "__main__":
    main()
