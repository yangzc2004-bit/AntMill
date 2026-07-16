#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
import yaml


def parse_args():
    parser = argparse.ArgumentParser(description='Backup scheduler')
    parser.add_argument('--schedule', required=True, help='Path to YAML schedule file')
    parser.add_argument('--now', required=True, help='Wall clock in ISO-8601 format')
    parser.add_argument('--duration', type=float, default=24, help='Duration in hours')
    parser.add_argument('--mount', required=True, help='Mount path')
    return parser.parse_args()


def format_iso(dt):
    """Format datetime as ISO 8601 with timezone: using Z for UTC."""
    s = dt.isoformat()
    if s.endswith('+00:00'):
        s = s[:-6] + 'Z'
    return s


def _translate_segment(seg):
    """Translate a single glob segment (no /) to regex."""
    rx = ''
    j = 0
    while j < len(seg):
        c = seg[j]
        if c == '*':
            rx += r'[^/]*'
        elif c == '?':
            rx += r'[^/]'
        elif c == '[':
            k = j + 1
            if k < len(seg) and seg[k] in ('!', '^'):
                k += 1
            if k < len(seg) and seg[k] == ']':
                k += 1
            while k < len(seg) and seg[k] != ']':
                k += 1
            bracket = seg[j:k+1]
            if bracket.startswith('[!'):
                bracket = '[^' + bracket[2:]
            rx += bracket
            j = k
        else:
            rx += re.escape(c)
        j += 1
    return rx


def glob_to_regex(pattern):
    """Convert glob pattern to regex."""
    segments = pattern.split('/')
    regex_parts = []
    for i, seg in enumerate(segments):
        if i > 0:
            prev = segments[i - 1]
            if prev != '**':
                regex_parts.append('/')

        if seg == '**':
            if i == len(segments) - 1:
                regex_parts.append(r'(?:[^/]+/)*[^/]*')
            elif i == 0:
                regex_parts.append(r'(?:[^/]+/)*')
            else:
                regex_parts.append(r'(?:[^/]+/)*')
        else:
            regex_parts.append(_translate_segment(seg))

    return '^' + ''.join(regex_parts) + '$'


def match_glob(path, pattern):
    return re.match(glob_to_regex(pattern), path) is not None


def file_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return 'sha256:' + h.hexdigest()


def create_pack_tar(files, tmp_dir):
    """Create a tar archive from a list of (path_str, source_dir) tuples.
    Returns (bytes, total_content_size)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w|') as tar:
        for path_str, source_dir in files:
            full_path = source_dir / path_str
            info = tarfile.TarInfo(name=path_str)
            info.size = full_path.stat().st_size
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ''
            info.gname = ''
            with open(full_path, 'rb') as fh:
                tar.addfile(info, fh)
    return buf.getvalue()


def main():
    args = parse_args()

    with open(args.schedule, 'r') as f:
        schedule = yaml.safe_load(f)

    tz_name = schedule.get('timezone', 'UTC')
    tz = ZoneInfo(tz_name)

    now_dt = datetime.fromisoformat(args.now)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=dt_timezone.utc)
    now_local = now_dt.astimezone(tz)
    now_local = now_local.replace(second=0, microsecond=0)

    duration = timedelta(hours=args.duration)
    end_local = now_local + duration

    mount_path = Path(args.mount).resolve()

    events = []

    events.append({
        'event': 'SCHEDULE_PARSED',
        'timezone': tz_name,
        'jobs_total': len(schedule.get('jobs', []))
    })

    due_jobs = []

    for job in schedule.get('jobs', []):
        if not job.get('enabled', True):
            continue

        when = job['when']
        kind = when['kind']

        if kind == 'daily':
            at = when['at']
            at_hour, at_min = map(int, at.split(':'))
            current = now_local.date()
            end_date = end_local.date()
            while current <= end_date:
                trigger = datetime(current.year, current.month, current.day,
                                   at_hour, at_min, tzinfo=tz)
                if now_local <= trigger <= end_local:
                    due_jobs.append((job, trigger))
                current += timedelta(days=1)

        elif kind == 'weekly':
            at = when['at']
            at_hour, at_min = map(int, at.split(':'))
            days = {d.lower()[:3] for d in when['days']}
            current = now_local.date()
            end_date = end_local.date()
            while current <= end_date:
                day_abbr = current.strftime('%a').lower()[:3]
                if day_abbr in days:
                    trigger = datetime(current.year, current.month, current.day,
                                       at_hour, at_min, tzinfo=tz)
                    if now_local <= trigger <= end_local:
                        due_jobs.append((job, trigger))
                current += timedelta(days=1)

        elif kind == 'once':
            at_str = when['at']
            trigger = datetime.fromisoformat(at_str).replace(tzinfo=tz)
            trigger = trigger.replace(second=0, microsecond=0)
            if now_local <= trigger <= end_local:
                due_jobs.append((job, trigger))

    due_jobs.sort(key=lambda x: x[0]['id'])

    for job, trigger_time in due_jobs:
        job_id = job['id']
        kind = job['when']['kind']
        exclude_patterns = job.get('exclude', [])
        strategy = job.get('strategy')

        events.append({
            'event': 'JOB_ELIGIBLE',
            'job_id': job_id,
            'kind': kind,
            'now_local': format_iso(trigger_time)
        })

        events.append({
            'event': 'JOB_STARTED',
            'job_id': job_id,
            'exclude_count': len(exclude_patterns)
        })

        if strategy is not None:
            strategy_kind = strategy['kind']
            events.append({
                'event': 'STRATEGY_SELECTED',
                'job_id': job_id,
                'kind': strategy_kind
            })
        else:
            strategy_kind = None

        source = job['source']
        if source.startswith('mount://'):
            rel_source = source[len('mount://'):]
        else:
            rel_source = source
        rel_source = rel_source.lstrip('/')
        source_dir = mount_path / rel_source if rel_source else mount_path
        source_dir = source_dir.resolve()

        all_files = []
        if source_dir.exists():
            for f in sorted(source_dir.rglob('*')):
                if f.is_file():
                    rel = f.relative_to(source_dir)
                    all_files.append(rel)

        all_files.sort(key=lambda p: p.as_posix())

        selected_count = 0
        excluded_count = 0
        total_size = 0
        packs = 0

        # Pack-specific state
        current_pack_files = []
        current_pack_size = 0
        pack_id = 1
        if strategy_kind == 'pack':
            max_pack_bytes = strategy.get('options', {}).get('max_pack_bytes', 1048576)

        for rel_path in all_files:
            path_str = rel_path.as_posix()
            matched = False
            matched_pattern = None
            for pattern in exclude_patterns:
                if match_glob(path_str, pattern):
                    matched = True
                    matched_pattern = pattern
                    break
            if matched:
                events.append({
                    'event': 'FILE_EXCLUDED',
                    'job_id': job_id,
                    'path': path_str,
                    'pattern': matched_pattern
                })
                excluded_count += 1
            else:
                events.append({
                    'event': 'FILE_SELECTED',
                    'job_id': job_id,
                    'path': path_str
                })
                selected_count += 1
                full_path = source_dir / path_str
                fsize = full_path.stat().st_size
                total_size += fsize

                if strategy_kind == 'full':
                    checksum = file_sha256(full_path)
                    events.append({
                        'event': 'FILE_BACKED_UP',
                        'job_id': job_id,
                        'path': path_str,
                        'size': fsize,
                        'checksum': checksum
                    })
                elif strategy_kind == 'verify':
                    checksum = file_sha256(full_path)
                    events.append({
                        'event': 'FILE_VERIFIED',
                        'job_id': job_id,
                        'path': path_str,
                        'size': fsize,
                        'checksum': checksum
                    })
                elif strategy_kind == 'pack':
                    # Check if adding this file would exceed limit
                    if current_pack_files and current_pack_size + fsize > max_pack_bytes:
                        # Finalize current pack
                        tar_bytes = create_pack_tar(current_pack_files, source_dir)
                        tar_checksum = 'sha256:' + hashlib.sha256(tar_bytes).hexdigest()
                        events.append({
                            'event': 'PACK_CREATED',
                            'job_id': job_id,
                            'name': f'pack-{pack_id}.tar',
                            'size': current_pack_size,
                            'timestamp': format_iso(trigger_time),
                            'checksum': tar_checksum,
                            'tar_size': len(tar_bytes)
                        })
                        packs += 1
                        pack_id += 1
                        current_pack_files = []
                        current_pack_size = 0

                    current_pack_files.append((path_str, source_dir))
                    current_pack_size += fsize
                    events.append({
                        'event': 'FILE_PACKED',
                        'job_id': job_id,
                        'pack_id': pack_id,
                        'path': path_str,
                        'size': fsize
                    })

        # Finalize any remaining pack for pack strategy
        if strategy_kind == 'pack' and current_pack_files:
            tar_bytes = create_pack_tar(current_pack_files, source_dir)
            tar_checksum = 'sha256:' + hashlib.sha256(tar_bytes).hexdigest()
            events.append({
                'event': 'PACK_CREATED',
                'job_id': job_id,
                'name': f'pack-{pack_id}.tar',
                'size': current_pack_size,
                'timestamp': format_iso(trigger_time),
                'checksum': tar_checksum,
                'tar_size': len(tar_bytes)
            })
            packs += 1

        # Build JOB_COMPLETED
        completed_event = {
            'event': 'JOB_COMPLETED',
            'job_id': job_id,
            'selected': selected_count,
            'excluded': excluded_count
        }
        if strategy_kind in ('full', 'verify', 'pack'):
            completed_event['total_size'] = total_size
        if strategy_kind == 'pack':
            completed_event['packs'] = packs

        events.append(completed_event)

    for event in events:
        sys.stdout.write(json.dumps(event, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
