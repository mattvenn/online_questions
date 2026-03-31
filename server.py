from flask import Flask, render_template, request, jsonify, make_response, redirect, session, url_for
from functools import wraps
import json
import csv
import io
import os
import random
import qrcode as qrcode_lib
import base64
import socket
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
PORT = int(os.environ.get('PORT', 5001))
TEACHER_PASSWORD = os.environ.get('TEACHER_PASSWORD', '')

with open('questions.json') as f:
    questions = json.load(f)

current_idx = -1  # -1 = no active question
responses = {}    # str(question_id) -> list of {answer, timestamp}


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def make_qr_base64(url):
    qr = qrcode_lib.QRCode(version=1, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def student_url():
    base = os.environ.get('BASE_URL', '').rstrip('/')
    return base if base else f"http://{get_local_ip()}:{PORT}"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if TEACHER_PASSWORD and not session.get('teacher_logged_in'):
            return redirect(url_for('teacher_login', next=request.path))
        return f(*args, **kwargs)
    return decorated


# --- Auth routes ---

@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == TEACHER_PASSWORD:
            session['teacher_logged_in'] = True
            return redirect(request.args.get('next') or url_for('teacher'))
        error = 'Incorrect password'
    return render_template('login.html', error=error)


@app.route('/teacher/logout', methods=['POST'])
def teacher_logout():
    session.pop('teacher_logged_in', None)
    return redirect(url_for('teacher_login'))


# --- Student routes ---

@app.route('/')
def student():
    q = questions[current_idx] if current_idx >= 0 else None
    answered = bool(q and request.cookies.get(f'answered_{q["id"]}'))
    return render_template('student.html', question=q, answered=answered)


@app.route('/answer', methods=['POST'])
def submit_answer():
    if current_idx < 0:
        return redirect('/')
    q = questions[current_idx]
    qid = str(q['id'])

    if q['type'] == 'rating':
        value = request.form.get('rating', '')
        if value.isdigit():
            responses.setdefault(qid, []).append({
                'answer': int(value),
                'timestamp': datetime.now().isoformat()
            })
    elif q['type'] == 'checkbox':
        values = request.form.getlist('options')
        if values:
            responses.setdefault(qid, []).append({
                'answer': values,
                'timestamp': datetime.now().isoformat()
            })
    elif q['type'] == 'multiple_choice':
        value = request.form.get('option', '').strip()
        if value and value in q['options']:
            responses.setdefault(qid, []).append({
                'answer': value,
                'timestamp': datetime.now().isoformat()
            })

    resp = make_response(redirect('/'))
    resp.set_cookie(f'answered_{q["id"]}', '1', max_age=7200)
    return resp


@app.route('/api/current')
def api_current():
    qid = questions[current_idx]['id'] if current_idx >= 0 else None
    return jsonify({'question_id': qid})


# --- Teacher routes ---

@app.route('/teacher')
@login_required
def teacher():
    url = student_url()
    qr = make_qr_base64(url)
    return render_template('teacher.html',
                           questions=questions,
                           current_idx=current_idx,
                           student_url=url,
                           qr=qr,
                           teacher_auth=bool(TEACHER_PASSWORD))


@app.route('/api/add_question', methods=['POST'])
@login_required
def add_question():
    global current_idx
    data = request.get_json()
    q_type = data.get('type')
    text = data.get('text', '').strip()
    if not text or q_type not in ('rating', 'checkbox', 'multiple_choice'):
        return jsonify({'ok': False, 'error': 'invalid input'}), 400

    new_id = max((q['id'] for q in questions), default=0) + 1
    q = {'id': new_id, 'text': text, 'type': q_type}
    if q_type == 'rating':
        q['min'] = int(data.get('min', 1))
        q['max'] = int(data.get('max', 10))
        q['label_min'] = data.get('label_min', '')
        q['label_max'] = data.get('label_max', '')
    elif q_type in ('checkbox', 'multiple_choice'):
        opts = [o.strip() for o in data.get('options', []) if o.strip()]
        if not opts:
            return jsonify({'ok': False, 'error': 'need at least one option'}), 400
        q['options'] = opts

    questions.append(q)
    current_idx = len(questions) - 1
    return jsonify({'ok': True, 'current_idx': current_idx})


@app.route('/api/activate/<int:idx>', methods=['POST'])
@login_required
def activate(idx):
    global current_idx
    if 0 <= idx < len(questions):
        current_idx = idx
    return jsonify({'ok': True, 'current_idx': current_idx})


@app.route('/api/deactivate', methods=['POST'])
@login_required
def deactivate():
    global current_idx
    current_idx = -1
    return jsonify({'ok': True})


@app.route('/api/results')
def api_results():
    if current_idx < 0:
        return jsonify({'active': False})
    q = questions[current_idx]
    qid = str(q['id'])
    entries = responses.get(qid, [])
    total = len(entries)

    if q['type'] == 'rating':
        counts = {str(i): 0 for i in range(q['min'], q['max'] + 1)}
        for e in entries:
            key = str(e['answer'])
            counts[key] = counts.get(key, 0) + 1
        return jsonify({
            'active': True,
            'type': 'rating',
            'question': q['text'],
            'labels': [str(i) for i in range(q['min'], q['max'] + 1)],
            'label_min': q.get('label_min', ''),
            'label_max': q.get('label_max', ''),
            'counts': counts,
            'total': total
        })

    elif q['type'] == 'checkbox':
        counts = {opt: 0 for opt in q['options']}
        for e in entries:
            for item in e['answer']:
                if item in counts:
                    counts[item] += 1
        return jsonify({
            'active': True,
            'type': 'checkbox',
            'question': q['text'],
            'labels': q['options'],
            'counts': counts,
            'total': total
        })

    elif q['type'] == 'multiple_choice':
        counts = {opt: 0 for opt in q['options']}
        for e in entries:
            if e['answer'] in counts:
                counts[e['answer']] += 1
        return jsonify({
            'active': True,
            'type': 'multiple_choice',
            'question': q['text'],
            'labels': q['options'],
            'counts': counts,
            'total': total
        })

    return jsonify({'active': False})


@app.route('/api/save_questions', methods=['POST'])
@login_required
def save_questions():
    with open('questions.json', 'w') as f:
        json.dump(questions, f, indent=2)
    return jsonify({'ok': True})


@app.route('/api/load_questions', methods=['POST'])
@login_required
def load_questions():
    global current_idx
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({'ok': False, 'error': 'expected a JSON array'}), 400
    for q in data:
        if not isinstance(q, dict) or not q.get('text') or \
                q.get('type') not in ('rating', 'checkbox', 'multiple_choice'):
            return jsonify({'ok': False, 'error': f'invalid question: {q!r}'}), 400
        if q['type'] == 'rating' and ('min' not in q or 'max' not in q):
            return jsonify({'ok': False, 'error': f'rating question missing min/max'}), 400
        if q['type'] in ('checkbox', 'multiple_choice') and not q.get('options'):
            return jsonify({'ok': False, 'error': f'question missing options list'}), 400
    questions[:] = data
    current_idx = -1
    return jsonify({'ok': True, 'count': len(questions)})


@app.route('/export')
@login_required
def export():
    buf = io.StringIO()
    writer = csv.writer(buf)
    for i, q in enumerate(questions):
        if i > 0:
            writer.writerow([])
        qid = str(q['id'])
        entries = responses.get(qid, [])
        total = len(entries)

        if q['type'] == 'rating':
            labels = [str(v) for v in range(q['min'], q['max'] + 1)]
            counts = {l: 0 for l in labels}
            for e in entries:
                k = str(e['answer'])
                if k in counts:
                    counts[k] += 1
            title = f'{q["text"]} ({q["type"]}, {total} responses)'
        else:
            labels = q['options']
            counts = {opt: 0 for opt in labels}
            for e in entries:
                ans = e['answer']
                targets = ans if isinstance(ans, list) else [ans]
                for t in targets:
                    if t in counts:
                        counts[t] += 1
            if q['type'] == 'checkbox':
                selections = sum(counts.values())
                title = (f'{q["text"]} (checkbox, {total} respondents, '
                         f'{selections} selections total)')
            else:
                title = f'{q["text"]} (multiple_choice, {total} responses)'

        writer.writerow([title])
        for l in labels:
            writer.writerow([l, counts[l]])

    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    fname = f'summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    resp.headers['Content-Disposition'] = f'attachment; filename={fname}'
    return resp


def preload_test_data(n=200, seed=42):
    """Inject n fake responses for every question. Used by --preload and tests."""
    global current_idx
    rng = random.Random(seed)
    ts = '2026-01-01T00:00:00'
    for q in questions:
        qid = str(q['id'])
        entries = []
        if q['type'] == 'rating':
            lo, hi = q['min'], q['max']
            mid = (lo + hi) / 2 + 1          # skew slightly above centre
            for _ in range(n):
                v = round(rng.gauss(mid, (hi - lo) / 5))
                entries.append({'answer': max(lo, min(hi, v)), 'timestamp': ts})
        elif q['type'] == 'checkbox':
            # Weight options so the first is most chosen, last least
            weights = [0.8 - i * (0.6 / max(len(q['options']) - 1, 1))
                       for i in range(len(q['options']))]
            for _ in range(n):
                chosen = [opt for opt, w in zip(q['options'], weights)
                          if rng.random() < w]
                if not chosen:
                    chosen = [q['options'][0]]
                entries.append({'answer': chosen, 'timestamp': ts})
        elif q['type'] == 'multiple_choice':
            weights = [0.5 - i * (0.4 / max(len(q['options']) - 1, 1))
                       for i in range(len(q['options']))]
            for _ in range(n):
                entries.append({'answer': rng.choices(q['options'], weights=weights)[0],
                                'timestamp': ts})
        responses[qid] = entries
    current_idx = 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--preload', action='store_true',
                        help='Start with fake responses loaded for graph testing')
    args = parser.parse_args()
    if args.preload:
        preload_test_data()
        print(f"  Preloaded {len(questions)} questions with test data.")
    url = student_url()
    print(f"\n  Teacher dashboard : http://127.0.0.1:{PORT}/teacher")
    print(f"  Student URL (QR)  : {url}/\n")
    app.run(host='0.0.0.0', port=PORT, debug=False)
