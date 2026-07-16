#!/usr/bin/env python3
"""
CSV Merger and Sorter - merges multiple CSV files, aligns schemas, and produces sorted output.
"""

import argparse
import csv
import io
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path


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
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    parser.add_argument("--schema", help="JSON schema file path")
    parser.add_argument("--infer", choices=["strict", "loose"], default="strict")
    parser.add_argument("--on-type-error", choices=["coerce-null", "fail", "keep-string"], default="coerce-null")
    parser.add_argument("--memory-limit-mb", type=int, default=64)
    parser.add_argument("--temp-dir", help="Temporary directory for sorting")
    parser.add_argument("--csv-quotechar", default='"')
    parser.add_argument("--csv-escapechar", default=None)
    parser.add_argument("--csv-null-literal", default="")
    parser.add_argument("inputs", nargs="+", help="Input CSV files")
    return parser.parse_args()


def parse_bool(value):
    if value is None or value == "":
        return None
    v = value.strip().lower()
    if v in ("1", "true", "yes", "t", "y"):
        return True
    if v in ("0", "false", "no", "f", "n"):
        return False
    raise ValueError(f"Cannot parse bool: {value}")


def parse_int(value):
    if value is None or value == "":
        return None
    return int(value)


def parse_float(value):
    if value is None or value == "":
        return None
    return float(value)


def parse_date(value):
    if value is None or value == "":
        return None
    # ISO-8601 YYYY-MM-DD
    dt = datetime.strptime(value.strip(), "%Y-%m-%d")
    return dt.date()


def parse_timestamp(value):
    if value is None or value == "":
        return None
    v = value.strip()
    # Try various ISO-8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(v, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {value}")


def format_timestamp(dt):
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date(d):
    if d is None:
        return None
    return d.strftime("%Y-%m-%d")


def format_bool(b):
    if b is None:
        return None
    return "true" if b else "false"


def cast_value(value, target_type, on_error):
    if value is None or value == "":
        return None
    try:
        if target_type == "string":
            return value
        elif target_type == "int":
            return parse_int(value)
        elif target_type == "float":
            return parse_float(value)
        elif target_type == "bool":
            return parse_bool(value)
        elif target_type == "date":
            return parse_date(value)
        elif target_type == "timestamp":
            return parse_timestamp(value)
        else:
            return value
    except (ValueError, TypeError) as e:
        if on_error == "fail":
            print(f"Type cast error: {e}", file=sys.stderr)
            sys.exit(1)
        elif on_error == "keep-string":
            return value
        else:  # coerce-null
            return None


def format_value(value, col_type):
    if value is None:
        return None
    if col_type == "timestamp":
        return format_timestamp(value)
    elif col_type == "date":
        return format_date(value)
    elif col_type == "bool":
        return format_bool(value)
    elif col_type == "int":
        return str(value)
    elif col_type == "float":
        # Use repr to avoid precision issues, but strip trailing .0 if needed
        s = repr(value)
        return s
    else:
        return str(value)


def infer_type(value, mode):
    """Infer type of a single value. Returns type string or None if null."""
    if value is None or value.strip() == "":
        return None
    v = value.strip()
    
    # Try bool first
    if v.lower() in ("true", "false", "1", "0"):
        return "bool"
    
    # Try int
    try:
        int(v)
        return "int"
    except ValueError:
        pass
    
    # Try float
    try:
        float(v)
        if "." not in v.lower() and "e" not in v.lower():
            # It's actually an int, but we already tried int above
            pass
        return "float"
    except ValueError:
        pass
    
    # Try date
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return "date"
    except ValueError:
        pass
    
    # Try timestamp
    try:
        parse_timestamp(v)
        return "timestamp"
    except ValueError:
        pass
    
    return "string"


def merge_types(type1, type2, mode):
    """Merge two inferred types, returning the resolved type."""
    if type1 is None:
        return type2
    if type2 is None:
        return type1
    if type1 == type2:
        return type1
    
    if mode == "strict":
        return "string"
    else:  # loose
        # Check if one is a subset of the other
        if type1 == "int" and type2 == "float":
            return "float"
        if type1 == "float" and type2 == "int":
            return "float"
        if type1 == "date" and type2 == "timestamp":
            return "timestamp"
        if type1 == "timestamp" and type2 == "date":
            return "timestamp"
        
        p1 = TYPE_PRIORITY.get(type1, 0)
        p2 = TYPE_PRIORITY.get(type2, 0)
        if p1 != p2:
            return type1 if p1 > p2 else type2
        return "string"


def read_csv_file(path, quotechar, escapechar):
    """Read a CSV file and return (headers, rows)."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        if escapechar:
            reader = csv.reader(f, delimiter=",", quotechar=quotechar, escapechar=escapechar, lineterminator="\n")
        else:
            reader = csv.reader(f, delimiter=",", quotechar=quotechar, doublequote=True, lineterminator="\n")
        headers = next(reader)
        rows = list(reader)
    return headers, rows


def infer_schema_from_inputs(inputs, mode, quotechar, escapechar):
    """Infer schema from all input files."""
    all_columns = {}  # name -> inferred type
    
    for path in inputs:
        headers, rows = read_csv_file(path, quotechar, escapechar)
        col_idx = {h: i for i, h in enumerate(headers)}
        
        for col_name in headers:
            if col_name not in all_columns:
                all_columns[col_name] = None
            
            for row in rows:
                if col_name in col_idx and col_idx[col_name] < len(row):
                    val = row[col_idx[col_name]]
                else:
                    val = None
                t = infer_type(val, mode)
                all_columns[col_name] = merge_types(all_columns[col_name], t, mode)
    
    # Sort columns lexicographically
    sorted_cols = sorted(all_columns.keys())
    schema = {
        "columns": [
            {"name": c, "type": all_columns.get(c, "string") or "string"}
            for c in sorted_cols
        ]
    }
    return schema


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_csv_rows(rows, headers, schema_types, null_literal, quotechar, output_stream):
    """Write rows to CSV output."""
    writer = csv.writer(output_stream, delimiter=",", quotechar=quotechar, 
                        doublequote=True, lineterminator="\n")
    writer.writerow(headers)
    
    for row in rows:
        out_row = []
        for h in headers:
            val = row.get(h)
            formatted = format_value(val, schema_types[h])
            if formatted is None:
                out_row.append(null_literal)
            else:
                out_row.append(formatted)
        writer.writerow(out_row)


def make_sort_key(row, key_cols, desc):
    """Create a sort key tuple for a row. Nulls are always less than non-null values."""
    result = []
    for col in key_cols:
        val = row.get(col)
        if val is None:
            # Null handling: use a special marker
            # For ascending: null first (use smallest value)
            # For descending: null last (use largest value)
            if desc:
                result.append((2, None))  # null after non-null
            else:
                result.append((0, None))  # null before non-null
        else:
            result.append((1, val))
    # Add original index for stability
    result.append(row.get("_orig_idx", 0))
    return tuple(result)


def external_sort(input_rows, key_func, desc, memory_limit_mb, temp_dir):
    """Sort rows using external merge sort if needed."""
    # Simple approach: try in-memory sort first
    # If that fails, use chunk-based external sort
    
    # For stability, use enumerate
    indexed = [(i, row) for i, row in enumerate(input_rows)]
    
    # Try in-memory sort
    try:
        indexed.sort(key=lambda x: key_func(x[1]), reverse=desc)
        return [row for _, row in indexed]
    except MemoryError:
        pass
    
    # External sort: split into chunks
    chunk_size = max(1000, memory_limit_mb * 1024)  # rough estimate
    
    chunk_files = []
    chunk_idx = 0
    
    try:
        for i in range(0, len(indexed), chunk_size):
            chunk = indexed[i:i+chunk_size]
            chunk.sort(key=lambda x: key_func(x[1]), reverse=desc)
            
            chunk_path = os.path.join(temp_dir, f"chunk_{chunk_idx}.json")
            with open(chunk_path, "w", encoding="utf-8") as f:
                for orig_idx, row in chunk:
                    obj = {"_orig_idx": orig_idx, "row": row}
                    json.dump(obj, f)
                    f.write("\n")
            chunk_files.append(chunk_path)
            chunk_idx += 1
        
        # Merge sorted chunks using heapq
        import heapq
        
        def make_iter(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    yield obj["_orig_idx"], obj["row"]
        
        # Read all chunks and merge
        all_entries = []
        for p in chunk_files:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    all_entries.append((obj["_orig_idx"], obj["row"]))
        
        # Sort all entries
        all_entries.sort(key=lambda x: key_func(x[1]), reverse=desc)
        return [row for _, row in all_entries]
    finally:
        for p in chunk_files:
            try:
                os.remove(p)
            except OSError:
                pass


def process_files(args):
    # Parse keys
    key_cols = [k.strip() for k in args.key.split(",")]
    
    # Load or infer schema
    if args.schema:
        schema = load_schema(args.schema)
    else:
        schema = infer_schema_from_inputs(args.inputs, args.infer, args.csv_quotechar, args.csv_escapechar)
    
    schema_cols = schema["columns"]
    schema_types = {c["name"]: c["type"] for c in schema_cols}
    output_headers = [c["name"] for c in schema_cols]
    
    # Validate key columns
    for k in key_cols:
        if k not in schema_types:
            print(f"Error: key column '{k}' not in schema", file=sys.stderr)
            sys.exit(1)
    
    # Read and cast all rows
    all_rows = []
    row_counter = 0
    
    for path in args.inputs:
        headers, rows = read_csv_file(path, args.csv_quotechar, args.csv_escapechar)
        col_idx = {h: i for i, h in enumerate(headers)}
        
        for row in rows:
            row_dict = {}
            for col in output_headers:
                if col in col_idx and col_idx[col] < len(row):
                    raw_val = row[col_idx[col]]
                else:
                    raw_val = None
                
                # Cast value
                casted = cast_value(raw_val, schema_types[col], args.on_type_error)
                row_dict[col] = casted
            
            # Store original index for stability
            row_dict["_orig_idx"] = row_counter
            row_counter += 1
            all_rows.append(row_dict)
    
    # Sort
    def sort_key(row):
        return make_sort_key(row, key_cols, args.desc)
    
    # Use temp dir
    temp_dir = args.temp_dir or tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)
    
    sorted_rows = external_sort(all_rows, sort_key, args.desc, args.memory_limit_mb, temp_dir)
    
    # Remove internal fields
    for row in sorted_rows:
        if "_orig_idx" in row:
            del row["_orig_idx"]
    
    # Output
    if args.output == "-":
        output_stream = sys.stdout
    else:
        output_stream = open(args.output, "w", encoding="utf-8", newline="")
    
    try:
        write_csv_rows(sorted_rows, output_headers, schema_types, args.csv_null_literal, args.csv_quotechar, output_stream)
    finally:
        if args.output != "-":
            output_stream.close()


def main():
    args = parse_args()
    process_files(args)


if __name__ == "__main__":
    main()
