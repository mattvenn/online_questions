#!/usr/bin/env python3
"""
Live load test against the running server.

Polls /api/current waiting for you to activate a question on the teacher
dashboard, then fires --users simulated responses spread over --spread seconds,
prints a summary, and waits for the next question.

Usage:
    python load_test.py                          # test.mattvenn.net, 200 users
    python load_test.py --url https://localhost:5001 --users 50 --spread 4

Workflow:
    1. Run this script — it prints "Waiting for a question…"
    2. On the teacher dashboard, click "Ask this" for the first question.
    3. Watch the script fire responses and report results.
    4. Click "Stop" (or "Ask this" on the next question) to advance.
    5. Repeat. Press Ctrl-C to quit.

Only hits student-facing endpoints (/api/current, /api/results, /answer) —
no teacher password needed.
"""
import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


# Follow 301 (HTTP→HTTPS) but not 302 — a 302 from /answer means success.
class _NoFollow302(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp  # return the 302 response as-is, don't chase it
    http_error_303 = http_error_307 = http_error_308 = http_error_302

_opener = urllib.request.build_opener(_NoFollow302)


def check_student_page(base_url):
    """Fetch the student page and verify it contains real HTML content."""
    try:
        with urllib.request.urlopen(f'{base_url}/', timeout=10) as r:
            body = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [ERROR] Could not reach student page: {e}', file=sys.stderr)
        sys.exit(1)

    # Must contain the markers present in both waiting and question states
    required = ['<!DOCTYPE html>', '<body']
    for marker in required:
        if marker.lower() not in body.lower():
            print(f'  [ERROR] Student page missing expected content: {marker!r}', file=sys.stderr)
            print(f'          Response was {len(body)} bytes — possible white/error page.', file=sys.stderr)
            print(f'          First 500 chars: {body[:500]!r}', file=sys.stderr)
            sys.exit(1)

    # Must be one of the two known states
    if 'Waiting for a question' in body:
        print('  Student page OK (waiting state)')
    elif 'question-text' in body or 'Thanks for your answer' in body:
        print('  Student page OK (question active)')
    else:
        print('  [WARN] Student page loaded but state unclear — check manually.')
        print(f'         First 300 chars: {body[:300]!r}')


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def submit_one(base_url, q_type, q_data, delay):
    """Sleep for `delay` seconds then POST one answer. Returns HTTP status or error string."""
    time.sleep(delay)

    if q_type == 'rating':
        lo, hi = int(q_data['labels'][0]), int(q_data['labels'][-1])
        mid = (lo + hi) / 2 + 1          # slight upward skew, same as preload
        v = round(random.gauss(mid, (hi - lo) / 5))
        v = max(lo, min(hi, v))
        payload = urllib.parse.urlencode({'rating': v}).encode()
    elif q_type == 'multiple_choice':
        # weight toward first option (realistic skew)
        opts = q_data['labels']
        weights = [1.0 - i * (0.6 / max(len(opts) - 1, 1)) for i in range(len(opts))]
        choice = random.choices(opts, weights=weights)[0]
        payload = urllib.parse.urlencode({'option': choice}).encode()
    elif q_type == 'checkbox':
        opts = q_data['labels']
        weights = [0.8 - i * (0.6 / max(len(opts) - 1, 1)) for i in range(len(opts))]
        chosen = [o for o, w in zip(opts, weights) if random.random() < w] or [opts[0]]
        payload = urllib.parse.urlencode([('options', o) for o in chosen]).encode()
    else:
        return f'unknown type: {q_type}'

    req = urllib.request.Request(
        f'{base_url}/answer',
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with _opener.open(req, timeout=10) as r:
            return r.status   # 302 redirect = accepted
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return str(e)


def fire_responses(base_url, q_data, n_users, spread):
    q_type = q_data['type']
    print(f'\n  [{q_type}] "{q_data["question"]}"')
    print(f'  Firing {n_users} responses spread over {spread}s …', flush=True)

    delays = sorted(random.uniform(0, spread) for _ in range(n_users))

    ok = errors = 0
    with ThreadPoolExecutor(max_workers=min(n_users, 50)) as pool:
        futures = {pool.submit(submit_one, base_url, q_type, q_data, d) for d in delays}
        for f in as_completed(futures):
            result = f.result()
            if isinstance(result, int) and result in (200, 302):
                ok += 1
            else:
                errors += 1
                if errors <= 5:   # don't spam on mass failure
                    print(f'  [error] {result}', file=sys.stderr)

    print(f'  ✓ {ok} submitted, {errors} errors')
    if errors > 5:
        print(f'  … ({errors - 5} further errors suppressed)', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Live load test for online-questions server')
    parser.add_argument('--url', default='https://test.mattvenn.net',
                        help='Base URL of the server (default: http://test.mattvenn.net)')
    parser.add_argument('--users', type=int, default=200,
                        help='Simulated users per question (default: 200)')
    parser.add_argument('--spread', type=float, default=4.0,
                        help='Spread submissions over this many seconds (default: 8)')
    args = parser.parse_args()

    base = args.url.rstrip('/')
    print(f'Load test  →  {base}')
    print(f'  {args.users} users per question, responses spread over {args.spread}s\n')

    print('Checking student page…')
    check_student_page(base)

    print(f'\n  Activate questions on the teacher dashboard when ready.')
    print(f'  Press Ctrl-C to stop.\n')
    print('  Waiting for a question…', flush=True)

    seen_qid = object()   # sentinel that won't match any real qid or None

    try:
        while True:
            try:
                current = fetch_json(f'{base}/api/current')
            except Exception as e:
                print(f'  [warn] could not reach server: {e}', file=sys.stderr)
                time.sleep(3)
                continue

            qid = current.get('question_id')

            if qid == seen_qid:
                time.sleep(1)
                continue

            if qid is None:
                # question was deactivated
                seen_qid = None
                print('  Question deactivated — waiting for the next one…', flush=True)
                time.sleep(1)
                continue

            # New question detected
            seen_qid = qid
            try:
                q_data = fetch_json(f'{base}/api/results')
            except Exception as e:
                print(f'  [warn] /api/results failed: {e}', file=sys.stderr)
                time.sleep(1)
                continue

            if not q_data.get('active'):
                time.sleep(1)
                continue

            fire_responses(base, q_data, args.users, args.spread)
            print('  Waiting for next question…', flush=True)

    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
