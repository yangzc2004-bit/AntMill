#!/usr/bin/env python3
"""
CSV Merger and Sorter - merges multiple CSV files, aligns schemas, and produces sorted output.
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import heapq
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# Type priority for schema resolution
TYPE_PRIORITY = {
    "timestamp": 6,
    "date": 5,
    "bool": 4,
    "int": 3,
    "float": 2,
    "string": 1,
}


def parse_args():
    parser = argparse.ArgumentParser(description="CSV Merger and Sorter")
    parser.add_argument("--output", required=True, help="Output path or - for stdout")
    parser.add_argument("--key", required=True, help="Comma-separated sort key columns")
    parser.add_argument("--desc", action="store_true", help="Descending sort order")
    parser.add_argument("--schema", help="JSON schema file")
    parser.add_argument("--infer", choices=["strict", "loose"], default="strict")
    parser.add_argument("--on-type-error", choices=["coerce-null", "fail", "keep-string"], default="coerce-null")
    parser.add_argument("--memory-limit-mb", type=int, default=64)
    parser.add_argument("--temp-dir", help="Temporary directory for sorting")
    parser.add_argument("--csv-quotechar", default='"')
    parser.add_argument("--csv-escapechar", default=None)
    parser.add_argument("--csv-null-literal", default="")
    parser.add_argument("inputs", nargs="+", help="Input CSV files")
    return parser.parse_args()


def parse_bool(value: str) -> Optional[bool]:
    v = value.strip().lower()
    if v in ("true", "1", "yes", "y", "t"):
        return True
    if v in ("false", "0", "no", "n", "f"):
        return False
    return None


def parse_int(value: str) -> Optional[int]:
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_float(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_date(value: str) -> Optional[str]:
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_timestamp(value: str) -> Optional[datetime]:
    v = value.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(v, fmt)
            return dt
        except ValueError:
            continue
    return None


def normalize_timestamp(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def infer_type(value: str) -> Optional[str]:
    if value.strip() == "":
        return None
    
    if parse_bool(value) is not None:
        return "bool"
    
    ts = parse_timestamp(value)
    if ts is not None:
        try:
            datetime.strptime(value.strip(), "%Y-%m-%d")
            if ts.hour == 0 and ts.minute == 0 and ts.second == 0 and "T" not in value.upper() and " " not in value:
                return "date"
        except ValueError:
            pass
        return "timestamp"
    
    if parse_int(value) is not None:
        return "int"
    
    if parse_float(value) is not None:
        return "float"
    
    return "string"


def merge_types(t1: Optional[str], t2: Optional[str], mode: str) -> Optional[str]:
    if t1 is None:
        return t2
    if t2 is None:
        return t1
    if t1 == t2:
        return t1
    
    if mode == "strict":
        return "string"
    
    if t1 in ("int", "float") and t2 in ("int", "float"):
        return "float"
    
    if t1 in ("date", "timestamp") and t2 in ("date", "timestamp"):
        return "timestamp"
    
    return "string"


def cast_value(value: str, target_type: str, on_error: str, null_literal: str) -> Tuple[Any, bool]:
    if value.strip() == "":
        return null_literal, True
    
    if target_type == "string":
        return value, True
    
    if target_type == "bool":
        result = parse_bool(value)
        if result is not None:
            return result, True
    elif target_type == "int":
        result = parse_int(value)
        if result is not None:
            return result, True
    elif target_type == "float":
        result = parse_float(value)
        if result is not None:
            return result, True
    elif target_type == "date":
        result = parse_date(value)
        if result is not None:
            return result, True
    elif target_type == "timestamp":
        result = parse_timestamp(value)
        if result is not None:
            return normalize_timestamp(result), True
    
    if on_error == "fail":
        return None, False
    elif on_error == "keep-string":
        return value, True
    else:
        return null_literal, True


def infer_schema_from_files(inputs: List[str], infer_mode: str, quotechar: str, escapechar: Optional[str]) -> List[Dict[str, str]]:
    all_columns = set()
    column_types = {}
    
    for input_file in inputs:
        with open(input_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter=",", quotechar=quotechar, escapechar=escapechar)
            headers = next(reader)
            all_columns.update(headers)
            
            file_types = {}
            for row in reader:
                for i, value in enumerate(row):
                    if i < len(headers):
                        col = headers[i]
                        if value.strip() == "":
                            continue
                        t = infer_type(value)
                        if t is not None:
                            if col not in file_types:
                                file_types[col] = t
                            else:
                                file_types[col] = merge_types(file_types[col], t, infer_mode)
            
            for col, t in file_types.items():
                if col not in column_types:
                    column_types[col] = t
                else:
                    column_types[col] = merge_types(column_types[col], t, infer_mode)
    
    sorted_cols = sorted(all_columns)
    schema = []
    for col in sorted_cols:
        schema.append({"name": col, "type": column_types.get(col, "string")})
    
    return schema


def load_schema(schema_file: str) -> List[Dict[str, str]]:
    with open(schema_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["columns"]


def read_csv_file(input_file: str, schema: List[Dict[str, str]], on_error: str, null_literal: str,
                  quotechar: str, escapechar: Optional[str]) -> List[Dict[str, Any]]:
    rows = []
    
    with open(input_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=",", quotechar=quotechar, escapechar=escapechar)
        headers = next(reader)
        header_map = {h: i for i, h in enumerate(headers)}
        
        for row in reader:
            out_row = {}
            for col in schema:
                col_name = col["name"]
                col_type = col["type"]
                
                if col_name in header_map:
                    idx = header_map[col_name]
                    if idx < len(row):
                        value = row[idx]
                        casted, success = cast_value(value, col_type, on_error, null_literal)
                        if not success:
                            print(f"Error: Failed to cast '{value}' to {col_type} for column '{col_name}'", file=sys.stderr)
                            sys.exit(1)
                        out_row[col_name] = casted
                    else:
                        out_row[col_name] = null_literal
                else:
                    out_row[col_name] = null_literal
            
            rows.append(out_row)
    
    return rows


def make_sort_key(row: Dict[str, Any], key_cols: List[str], null_literal: str):
    key = []
    for col in key_cols:
        val = row.get(col, null_literal)
        is_null = val == null_literal
        if is_null:
            key.append((0, ""))
        else:
            # Convert to string for consistent comparison across types
            if isinstance(val, bool):
                s = "1" if val else "0"
            elif isinstance(val, (int, float)):
                # Use a format that sorts numerically but as strings
                # For mixed int/float, we need consistent representation
                s = str(val)
            else:
                s = str(val)
            key.append((1, s))
    return key


def write_csv_rows(rows: List[Dict[str, Any]], schema: List[Dict[str, str]], output, null_literal: str,
                   quotechar: str, escapechar: Optional[str]):
    headers = [col["name"] for col in schema]
    writer = csv.writer(output, delimiter=",", quotechar=quotechar, escapechar=escapechar,
                       lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    
    for row in rows:
        out_row = []
        for col in schema:
            val = row.get(col["name"], null_literal)
            if val is True:
                out_row.append("true")
            elif val is False:
                out_row.append("false")
            elif val == null_literal:
                out_row.append(null_literal)
            else:
                out_row.append(str(val))
        writer.writerow(out_row)


def sort_rows(rows: List[Dict[str, Any]], key_cols: List[str], desc: bool, null_literal: str):
    def sort_key(row):
        return make_sort_key(row, key_cols, null_literal)
    
    if desc:
        rows.sort(key=sort_key, reverse=True)
    else:
        rows.sort(key=sort_key)
    return rows


def write_sorted_chunk(rows: List[Dict[str, Any]], schema: List[Dict[str, str]], temp_dir: str,
                       null_literal: str, quotechar: str, escapechar: Optional[str]) -> str:
    temp_f = tempfile.NamedTemporaryFile(mode="w+", delete=False, dir=temp_dir,
                                         suffix=".csv", encoding="utf-8")
    write_csv_rows(rows, schema, temp_f, null_literal, quotechar, escapechar)
    temp_f.close()
    return temp_f.name


def external_merge_sort(temp_files: List[str], schema: List[Dict[str, str]], key_cols: List[str],
                        desc: bool, null_literal: str, quotechar: str, escapechar: Optional[str]) -> List[Dict[str, Any]]:
    if len(temp_files) == 0:
        return []
    
    if len(temp_files) == 1:
        with open(temp_files[0], "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter=",", quotechar=quotechar, escapechar=escapechar)
            headers = next(reader)
            result = []
            for row in reader:
                out_row = {}
                for i, col in enumerate(schema):
                    val = row[i] if i < len(row) else null_literal
                    out_row[col["name"]] = val
                result.append(out_row)
        os.unlink(temp_files[0])
        return result
    
    readers = []
    for tf in temp_files:
        f = open(tf, "r", encoding="utf-8", newline="")
        reader = csv.reader(f, delimiter=",", quotechar=quotechar, escapechar=escapechar)
        headers = next(reader)
        readers.append((f, reader))
    
    class ReversedCompare:
        def __init__(self, key):
            self.key = key
        def __lt__(self, other):
            return self.key > other.key
        def __eq__(self, other):
            return self.key == other.key
    
    heap = []
    for i, (f, reader) in enumerate(readers):
        try:
            row = next(reader)
            out_row = {}
            for j, col in enumerate(schema):
                val = row[j] if j < len(row) else null_literal
                out_row[col["name"]] = val
            key = make_sort_key(out_row, key_cols, null_literal)
            if desc:
                key = ReversedCompare(key)
            heapq.heappush(heap, (key, i, out_row))
        except StopIteration:
            pass
    
    result = []
    while heap:
        key, i, out_row = heapq.heappop(heap)
        result.append(out_row)
        
        f, reader = readers[i]
        try:
            row = next(reader)
            next_row = {}
            for j, col in enumerate(schema):
                val = row[j] if j < len(row) else null_literal
                next_row[col["name"]] = val
            next_key = make_sort_key(next_row, key_cols, null_literal)
            if desc:
                next_key = ReversedCompare(next_key)
            heapq.heappush(heap, (next_key, i, next_row))
        except StopIteration:
            f.close()
            os.unlink(temp_files[i])
    
    return result


def main():
    args = parse_args()
    
    key_cols = [k.strip() for k in args.key.split(",")]
    
    if args.schema:
        schema = load_schema(args.schema)
    else:
        schema = infer_schema_from_files(args.inputs, args.infer, args.csv_quotechar, args.csv_escapechar)
    
    schema_cols = {col["name"] for col in schema}
    for key_col in key_cols:
        if key_col not in schema_cols:
            print(f"Error: Key column '{key_col}' not found in schema", file=sys.stderr)
            sys.exit(1)
    
    if args.output == "-":
        output = sys.stdout
    else:
        output = open(args.output, "w", encoding="utf-8", newline="")
    
    temp_dir = args.temp_dir if args.temp_dir else tempfile.gettempdir()
    
    total_size = sum(os.path.getsize(f) for f in args.inputs)
    memory_limit_bytes = args.memory_limit_mb * 1024 * 1024
    
    if total_size <= memory_limit_bytes // 2:
        all_rows = []
        for input_file in args.inputs:
            rows = read_csv_file(input_file, schema, args.on_type_error, args.csv_null_literal,
                                args.csv_quotechar, args.csv_escapechar)
            all_rows.extend(rows)
        
        all_rows = sort_rows(all_rows, key_cols, args.desc, args.csv_null_literal)
        write_csv_rows(all_rows, schema, output, args.csv_null_literal, args.csv_quotechar, args.csv_escapechar)
    else:
        temp_files = []
        chunk = []
        estimated_row_size = 512
        chunk_size = max(1, memory_limit_bytes // (estimated_row_size * 2))
        
        for input_file in args.inputs:
            rows = read_csv_file(input_file, schema, args.on_type_error, args.csv_null_literal,
                                args.csv_quotechar, args.csv_escapechar)
            for row in rows:
                chunk.append(row)
                if len(chunk) >= chunk_size:
                    chunk = sort_rows(chunk, key_cols, args.desc, args.csv_null_literal)
                    temp_files.append(write_sorted_chunk(chunk, schema, temp_dir,
                                                        args.csv_null_literal, args.csv_quotechar, args.csv_escapechar))
                    chunk = []
        
        if chunk:
            chunk = sort_rows(chunk, key_cols, args.desc, args.csv_null_literal)
            temp_files.append(write_sorted_chunk(chunk, schema, temp_dir,
                                                args.csv_null_literal, args.csv_quotechar, args.csv_escapechar))
        
        result = external_merge_sort(temp_files, schema, key_cols, args.desc, args.csv_null_literal,
                                    args.csv_quotechar, args.csv_escapechar)
        write_csv_rows(result, schema, output, args.csv_null_literal, args.csv_quotechar, args.csv_escapechar)
    
    if args.output != "-":
        output.close()


if __name__ == "__main__":
    main()
