#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import tempfile
import heapq
import pickle
import functools
import shutil
from datetime import datetime, date, timezone

TYPE_PRIORITY = {'timestamp': 7, 'date': 6, 'bool': 5, 'int': 4, 'float': 3, 'string': 1}

def parse_args():
    parser = argparse.ArgumentParser(description='Merge and sort CSV files.')
    parser.add_argument('--output', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--desc', action='store_true')
    parser.add_argument('--schema', default=None)
    parser.add_argument('--infer', choices=['strict', 'loose'], default='strict')
    parser.add_argument('--on-type-error', choices=['coerce-null', 'fail', 'keep-string'], default='coerce-null')
    parser.add_argument('--memory-limit-mb', type=int, default=64)
    parser.add_argument('--temp-dir', default=None)
    parser.add_argument('--csv-quotechar', default='"')
    parser.add_argument('--csv-escapechar', default=None)
    parser.add_argument('--csv-null-literal', default='')
    parser.add_argument('inputs', nargs='+')
    args = parser.parse_args()
    args.key = [k.strip() for k in args.key.split(',')]
    if len(args.csv_quotechar) != 1:
        parser.error('--csv-quotechar must be a single character.')
    if args.csv_escapechar and len(args.csv_escapechar) != 1:
        parser.error('--csv-escapechar must be a single character.')
    return args

def load_schema(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return [(col['name'], col['type']) for col in data['columns']]

def has_time_component(s):
    s = s.strip()
    if 'T' in s or ' ' in s:
        return True
    if len(s) > 10:
        remainder = s[10:]
        if '+' in remainder or '-' in remainder:
            return True
    return False

def infer_types_from_value(value):
    if value == '':
        return []
    possible = []
    if value.lower() in ('true', 'false', '1', '0', 'yes', 'no'):
        possible.append('bool')
    try:
        int(value)
        possible.append('int')
    except ValueError:
        pass
    try:
        float(value)
        possible.append('float')
    except ValueError:
        pass
    try:
        date.fromisoformat(value)
        possible.append('date')
    except ValueError:
        pass
    try:
        if has_time_component(value):
            datetime.fromisoformat(value)
            possible.append('timestamp')
    except ValueError:
        pass
    possible.sort(key=lambda t: TYPE_PRIORITY.get(t, 0), reverse=True)
    return possible

def infer_schema_from_files(inputs, mode, csv_kwargs):
    all_columns = set()
    file_headers = []
    file_types = []
    file_raw_values = []
    for fpath in inputs:
        with open(fpath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f, **csv_kwargs)
            headers = next(reader)
            all_columns.update(headers)
            file_headers.append(set(headers))
            type_map = {}
            for h in headers:
                type_map[h] = set()
            raw_values = {}
            for h in headers:
                raw_values[h] = []
            for row in reader:
                for h, val in zip(headers, row):
                    if mode == 'loose' and val == '':
                        continue
                    raw_values[h].append(val)
                    inferred = infer_types_from_value(val)
                    if inferred:
                        type_map[h].add(inferred[0])
                    else:
                        type_map[h].add('string')
            file_types.append(type_map)
            file_raw_values.append(raw_values)
    sorted_cols = sorted(all_columns)
    final_schema = []
    for col in sorted_cols:
        observed = set()
        for i, hset in enumerate(file_headers):
            if col in hset:
                observed.update(file_types[i].get(col, {'string'}))
            else:
                observed.add('string')
        if not observed:
            observed = {'string'}
        if mode == 'strict':
            if len(observed) > 1:
                final_type = 'string'
            else:
                final_type = observed.pop()
        else:
            candidate_types = sorted(observed, key=lambda t: TYPE_PRIORITY.get(t, 0), reverse=True)
            best_type = 'string'
            for candidate in candidate_types:
                if candidate == 'string':
                    best_type = 'string'
                    break
                all_parse = True
                for i, hset in enumerate(file_headers):
                    if col in hset:
                        for raw_val in file_raw_values[i].get(col, []):
                            try:
                                if candidate == 'int':
                                    int(raw_val)
                                elif candidate == 'float':
                                    float(raw_val)
                                elif candidate == 'bool':
                                    if raw_val.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                                        raise ValueError
                                elif candidate == 'date':
                                    date.fromisoformat(raw_val)
                                elif candidate == 'timestamp':
                                    if not has_time_component(raw_val):
                                        raise ValueError
                                    datetime.fromisoformat(raw_val)
                            except (ValueError, TypeError):
                                all_parse = False
                                break
                    if not all_parse:
                        break
                if all_parse:
                    best_type = candidate
                    break
            final_type = best_type
        final_schema.append((col, final_type))
    return final_schema

def make_cmp(key_columns, schema_index_map, desc):
    def cmp_func(r1, r2):
        for col in key_columns:
            idx = schema_index_map[col]
            v1 = r1[0][idx]
            v2 = r2[0][idx]
            if v1 is None and v2 is None:
                continue
            if v1 is None:
                return -1 if not desc else 1
            if v2 is None:
                return 1 if not desc else -1
            try:
                if v1 == v2:
                    continue
                less = v1 < v2
            except TypeError:
                less = str(v1) < str(v2)
            if less:
                return -1 if not desc else 1
            else:
                return 1 if not desc else -1
        return -1 if r1[1] < r2[1] else 1
    return cmp_func

def external_sort(rows_iterator, key_columns, schema_index_map, desc, memory_limit_bytes, temp_dir):
    cmp_func = make_cmp(key_columns, schema_index_map, desc)
    est_row_size = 200
    chunk_size = max(1, memory_limit_bytes // est_row_size)
    chunk_size = min(chunk_size, 50000)
    
    temp_files = []
    rows = []
    for row in rows_iterator:
        rows.append(row)
        if len(rows) >= chunk_size:
            rows.sort(key=functools.cmp_to_key(cmp_func))
            fd, path = tempfile.mkstemp(dir=temp_dir, suffix='.bin')
            with os.fdopen(fd, 'wb') as f:
                pickle.dump(rows, f)
            temp_files.append(path)
            rows = []
    if rows:
        rows.sort(key=functools.cmp_to_key(cmp_func))
        fd, path = tempfile.mkstemp(dir=temp_dir, suffix='.bin')
        with os.fdopen(fd, 'wb') as f:
            pickle.dump(rows, f)
        temp_files.append(path)
        rows = []
    
    if not temp_files:
        return iter([])
    
    class HeapItem:
        __slots__ = ('row', 'idx')
        def __init__(self, row, idx):
            self.row = row
            self.idx = idx
        def __lt__(self, other):
            c = cmp_func(self.row, other.row)
            if c != 0:
                return c < 0
            return self.idx < other.idx
    
    file_handles = []
    heap = []
    for idx, path in enumerate(temp_files):
        f = open(path, 'rb')
        chunk = pickle.load(f)
        f.close()
        file_handles.append(iter(chunk))
        try:
            first = next(file_handles[idx])
            heapq.heappush(heap, HeapItem(first, idx))
        except StopIteration:
            pass
    
    while heap:
        item = heapq.heappop(heap)
        yield item.row
        try:
            nxt = next(file_handles[item.idx])
            heapq.heappush(heap, HeapItem(nxt, item.idx))
        except StopIteration:
            pass
    
    for path in temp_files:
        try:
            os.unlink(path)
        except OSError:
            pass

def write_output(sorted_rows, schema_names, schema_types, null_literal, csv_kwargs, output_path):
    write_stdout = output_path == '-'
    if not write_stdout:
        out_fd = open(output_path, 'w', newline='', encoding='utf-8')
    else:
        out_fd = sys.stdout
    try:
        writer = csv.writer(out_fd, **csv_kwargs)
        writer.writerow(schema_names)
        for row_tuple in sorted_rows:
            values = row_tuple[0]
            formatted = [format_value(values[i], schema_types[schema_names[i]], null_literal) for i in range(len(schema_names))]
            writer.writerow(formatted)
    finally:
        if not write_stdout:
            out_fd.close()

def cast_value(val, target_type, on_type_error, null_literal):
    if val == '' or val == null_literal:
        return None
    try:
        if target_type == 'string':
            return val
        elif target_type == 'int':
            return int(val)
        elif target_type == 'float':
            return float(val)
        elif target_type == 'bool':
            if val.lower() in ('true', '1', 'yes'):
                return True
            elif val.lower() in ('false', '0', 'no'):
                return False
            else:
                raise ValueError
        elif target_type == 'date':
            return date.fromisoformat(val)
        elif target_type == 'timestamp':
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        else:
            return val
    except (ValueError, TypeError):
        if on_type_error == 'coerce-null':
            return None
        elif on_type_error == 'fail':
            raise ValueError(f"Cannot cast '{val}' to type {target_type}")
        else:
            return val

def format_value(val, target_type, null_literal):
    if val is None:
        return null_literal
    if target_type == 'timestamp':
        return val.strftime('%Y-%m-%dT%H:%M:%SZ')
    elif target_type == 'date':
        return val.isoformat()
    elif target_type == 'bool':
        return 'true' if val else 'false'
    elif target_type == 'int':
        return str(val)
    elif target_type == 'float':
        return str(val)
    else:
        return str(val)

def main():
    args = parse_args()
    csv_kwargs = {}
    if args.csv_quotechar:
        csv_kwargs['quotechar'] = args.csv_quotechar
    if args.csv_escapechar:
        csv_kwargs['escapechar'] = args.csv_escapechar
    else:
        csv_kwargs['doublequote'] = True
    
    if args.schema:
        schema = load_schema(args.schema)
    else:
        schema = infer_schema_from_files(args.inputs, args.infer, csv_kwargs)
    
    schema_names = [c[0] for c in schema]
    schema_types = dict(schema)
    schema_index_map = {name: i for i, name in enumerate(schema_names)}
    
    for k in args.key:
        if k not in schema_index_map:
            print(f"Error: Key column '{k}' not found in schema.", file=sys.stderr)
            sys.exit(1)
    
    null_literal = args.csv_null_literal
    on_type_error = args.on_type_error
    output_path = args.output
    key_columns = args.key
    desc = args.desc
    memory_limit_bytes = args.memory_limit_mb * 1024 * 1024
    temp_dir = args.temp_dir
    
    # For fail mode: pre-validate all rows before writing any output to avoid partial output
    # If memory-limited, we still need to stream. For simplicity, if fail mode, we scan all rows first.
    # Better: write to a temporary output file and only rename on success.
    if on_type_error == 'fail' and output_path != '-':
        # Write to a temp file, then rename on success
        tmp_out = output_path + '.tmp_merge'
        try:
            def row_generator():
                source_order = 0
                for fpath in args.inputs:
                    with open(fpath, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.reader(f, **csv_kwargs)
                        headers = next(reader)
                        col_index = {h: i for i, h in enumerate(headers)}
                        for row in reader:
                            values = []
                            for col_name in schema_names:
                                if col_name in col_index:
                                    idx = col_index[col_name]
                                    raw = row[idx] if idx < len(row) else ''
                                else:
                                    raw = ''
                                val = cast_value(raw, schema_types[col_name], on_type_error, null_literal)
                                values.append(val)
                            yield (values, source_order)
                            source_order += 1
            
            sorted_rows = external_sort(row_generator(), key_columns, schema_index_map, desc, memory_limit_bytes, temp_dir)
            write_output(sorted_rows, schema_names, schema_types, null_literal, csv_kwargs, tmp_out)
            os.replace(tmp_out, output_path)
        except (ValueError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            try:
                os.unlink(tmp_out)
            except OSError:
                pass
            sys.exit(1)
    else:
        def row_generator():
            source_order = 0
            for fpath in args.inputs:
                with open(fpath, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f, **csv_kwargs)
                    headers = next(reader)
                    col_index = {h: i for i, h in enumerate(headers)}
                    for row in reader:
                        values = []
                        for col_name in schema_names:
                            if col_name in col_index:
                                idx = col_index[col_name]
                                raw = row[idx] if idx < len(row) else ''
                            else:
                                raw = ''
                            val = cast_value(raw, schema_types[col_name], on_type_error, null_literal)
                            values.append(val)
                        yield (values, source_order)
                        source_order += 1
        
        sorted_rows = external_sort(row_generator(), key_columns, schema_index_map, desc, memory_limit_bytes, temp_dir)
        write_output(sorted_rows, schema_names, schema_types, null_literal, csv_kwargs, output_path)

if __name__ == '__main__':
    main()
