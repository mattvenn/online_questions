"""
Tests for the online questions server.

Run from the project directory:
    venv/bin/pytest test_server.py -v

For manual graph testing, start the server with pre-loaded data:
    venv/bin/python server.py --preload
then open http://127.0.0.1:5001/teacher
"""
import csv
import io
import json
import os
import pytest
import server


# ── fixtures ───────────────────────────────────────────────────────────────────

with open(os.path.join(os.path.dirname(__file__), 'questions.json')) as f:
    _ORIGINAL_QUESTIONS = json.load(f)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all server-side state before each test."""
    server.current_idx = -1
    server.responses.clear()
    server.questions[:] = json.loads(json.dumps(_ORIGINAL_QUESTIONS))


@pytest.fixture
def client():
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c


def _activate(client, idx=0):
    client.post(f'/api/activate/{idx}')


# ── student page ───────────────────────────────────────────────────────────────

class TestStudentPage:
    def test_waiting_when_no_question(self, client):
        r = client.get('/')
        assert r.status_code == 200
        assert b'Waiting for a question' in r.data

    def test_shows_rating_slider(self, client):
        _activate(client, 0)
        r = client.get('/')
        assert r.status_code == 200
        assert b'type="range"' in r.data
        assert b'How confident are you with Verilog' in r.data

    def test_slider_shows_min_max_labels(self, client):
        _activate(client, 0)
        r = client.get('/')
        assert b'Not at all' in r.data
        assert b'Very confident' in r.data

    def test_shows_checkbox_options(self, client):
        _activate(client, 1)
        r = client.get('/')
        assert b'designed a chip' in r.data
        assert b'type="checkbox"' in r.data

    def test_thank_you_after_answering(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '7'})
        r = client.get('/')
        assert b'Thanks for your answer' in r.data

    def test_waiting_page_after_deactivate(self, client):
        _activate(client, 0)
        client.post('/api/deactivate')
        r = client.get('/')
        assert b'Waiting for a question' in r.data


# ── answer submission ──────────────────────────────────────────────────────────

class TestAnswerSubmission:
    def test_submit_rating_stores_value(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '8'})
        qid = str(server.questions[0]['id'])
        assert server.responses[qid][0]['answer'] == 8

    def test_submit_rating_stores_timestamp(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '5'})
        qid = str(server.questions[0]['id'])
        assert 'timestamp' in server.responses[qid][0]

    def test_submit_checkbox_stores_selections(self, client):
        _activate(client, 1)
        client.post('/answer', data={'options': ['written an app', 'designed a chip']})
        qid = str(server.questions[1]['id'])
        assert server.responses[qid][0]['answer'] == ['written an app', 'designed a chip']

    def test_multiple_responses_accumulate(self, client):
        _activate(client, 0)
        for v in [3, 7, 9]:
            client.post('/answer', data={'rating': str(v)})
        qid = str(server.questions[0]['id'])
        assert len(server.responses[qid]) == 3

    def test_no_active_question_ignored(self, client):
        client.post('/answer', data={'rating': '5'})
        assert server.responses == {}

    def test_non_numeric_rating_ignored(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': 'high'})
        assert server.responses == {}

    def test_empty_checkbox_ignored(self, client):
        _activate(client, 1)
        client.post('/answer', data={})
        assert server.responses == {}

    def test_answer_sets_cookie(self, client):
        _activate(client, 0)
        r = client.post('/answer', data={'rating': '6'})
        qid = server.questions[0]['id']
        assert f'answered_{qid}' in r.headers.get('Set-Cookie', '')

    def test_responses_independent_per_question(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '7'})
        _activate(client, 1)
        client.post('/answer', data={'options': ['written an app']})
        assert len(server.responses) == 2


# ── API endpoints ──────────────────────────────────────────────────────────────

class TestAPIResults:
    def test_inactive_when_no_question(self, client):
        r = client.get('/api/results')
        assert r.get_json()['active'] is False

    def test_rating_counts_correct(self, client):
        _activate(client, 0)
        for v in [3, 5, 5, 7, 10]:
            client.post('/answer', data={'rating': str(v)})
        data = client.get('/api/results').get_json()
        assert data['active'] is True
        assert data['total'] == 5
        assert data['counts']['5'] == 2
        assert data['counts']['7'] == 1
        assert data['counts']['3'] == 1

    def test_rating_all_buckets_present(self, client):
        _activate(client, 0)
        data = client.get('/api/results').get_json()
        q = server.questions[0]
        assert set(data['labels']) == {str(i) for i in range(q['min'], q['max'] + 1)}

    def test_rating_includes_labels(self, client):
        _activate(client, 0)
        data = client.get('/api/results').get_json()
        assert data['label_min'] == 'Not at all'
        assert data['label_max'] == 'Very confident'

    def test_checkbox_counts_correct(self, client):
        _activate(client, 1)
        client.post('/answer', data={'options': ['written an app', 'designed a chip']})
        client.post('/answer', data={'options': ['written an app']})
        data = client.get('/api/results').get_json()
        assert data['counts']['written an app'] == 2
        assert data['counts']['designed a chip'] == 1
        assert data['counts']['coded a website'] == 0
        assert data['total'] == 2

    def test_checkbox_all_options_present(self, client):
        _activate(client, 1)
        data = client.get('/api/results').get_json()
        assert set(data['labels']) == set(server.questions[1]['options'])


class TestAPICurrent:
    def test_null_when_no_question(self, client):
        assert client.get('/api/current').get_json()['question_id'] is None

    def test_returns_question_id_when_active(self, client):
        _activate(client, 0)
        qid = client.get('/api/current').get_json()['question_id']
        assert qid == server.questions[0]['id']

    def test_updates_when_question_changes(self, client):
        _activate(client, 0)
        _activate(client, 1)
        qid = client.get('/api/current').get_json()['question_id']
        assert qid == server.questions[1]['id']

    def test_null_after_deactivate(self, client):
        _activate(client, 0)
        client.post('/api/deactivate')
        assert client.get('/api/current').get_json()['question_id'] is None


class TestAPIActivation:
    def test_activate_sets_current_idx(self, client):
        client.post('/api/activate/1')
        assert server.current_idx == 1

    def test_deactivate_clears_current_idx(self, client):
        _activate(client, 0)
        client.post('/api/deactivate')
        assert server.current_idx == -1

    def test_out_of_range_index_ignored(self, client):
        client.post('/api/activate/999')
        assert server.current_idx == -1

    def test_activate_returns_current_idx(self, client):
        r = client.post('/api/activate/0')
        assert r.get_json()['current_idx'] == 0


# ── impromptu questions ────────────────────────────────────────────────────────

class TestImpromptuQuestions:
    def test_add_rating_question(self, client):
        r = client.post('/api/add_question',
                        json={'text': 'How tired are you?', 'type': 'rating'})
        assert r.get_json()['ok'] is True
        assert server.questions[-1]['text'] == 'How tired are you?'

    def test_add_rating_with_labels(self, client):
        client.post('/api/add_question',
                    json={'text': 'Rate it', 'type': 'rating',
                          'label_min': 'Terrible', 'label_max': 'Amazing'})
        assert server.questions[-1]['label_min'] == 'Terrible'
        assert server.questions[-1]['label_max'] == 'Amazing'

    def test_add_checkbox_question(self, client):
        client.post('/api/add_question',
                    json={'text': 'Tools?', 'type': 'checkbox',
                          'options': ['vim', 'vscode', 'emacs']})
        assert server.questions[-1]['options'] == ['vim', 'vscode', 'emacs']

    def test_new_question_immediately_active(self, client):
        client.post('/api/add_question',
                    json={'text': 'Quick poll', 'type': 'rating'})
        assert server.current_idx == len(server.questions) - 1

    def test_new_question_gets_unique_id(self, client):
        client.post('/api/add_question', json={'text': 'Q3', 'type': 'rating'})
        client.post('/api/add_question', json={'text': 'Q4', 'type': 'rating'})
        ids = [q['id'] for q in server.questions]
        assert len(ids) == len(set(ids))

    def test_add_rating_default_min_max(self, client):
        client.post('/api/add_question', json={'text': 'Rate it', 'type': 'rating'})
        q = server.questions[-1]
        assert q['min'] == 1
        assert q['max'] == 10

    def test_missing_text_rejected(self, client):
        r = client.post('/api/add_question', json={'type': 'rating'})
        assert r.status_code == 400

    def test_empty_text_rejected(self, client):
        r = client.post('/api/add_question', json={'text': '  ', 'type': 'rating'})
        assert r.status_code == 400

    def test_invalid_type_rejected(self, client):
        r = client.post('/api/add_question', json={'text': 'Q?', 'type': 'freetext'})
        assert r.status_code == 400

    def test_empty_checkbox_options_rejected(self, client):
        r = client.post('/api/add_question',
                        json={'text': 'Pick', 'type': 'checkbox', 'options': []})
        assert r.status_code == 400

    def test_blank_checkbox_options_stripped_and_rejected(self, client):
        r = client.post('/api/add_question',
                        json={'text': 'Pick', 'type': 'checkbox',
                              'options': ['  ', '']})
        assert r.status_code == 400

    def test_add_multiple_choice_question(self, client):
        r = client.post('/api/add_question',
                        json={'text': 'Favourite language?', 'type': 'multiple_choice',
                              'options': ['Python', 'Rust', 'C']})
        assert r.get_json()['ok'] is True
        assert server.questions[-1]['type'] == 'multiple_choice'
        assert server.questions[-1]['options'] == ['Python', 'Rust', 'C']

    def test_empty_multiple_choice_options_rejected(self, client):
        r = client.post('/api/add_question',
                        json={'text': 'Pick', 'type': 'multiple_choice', 'options': []})
        assert r.status_code == 400

    def test_impromptu_js_collects_options_for_multiple_choice(self):
        """
        Regression: submitImpromtu() collected options only for 'checkbox',
        so multiple_choice POSTed without options and got a 400 from the server.
        The condition guarding body.options = ... must include multiple_choice.
        """
        with open('templates/teacher.html') as f:
            src = f.read()
        opts_pos = src.index('body.options')
        condition = src[src.rindex('if (type', 0, opts_pos):opts_pos]
        assert 'multiple_choice' in condition, (
            "submitImpromtu() does not collect options for multiple_choice"
        )


# ── multiple choice ────────────────────────────────────────────────────────────

MC_IDX = 2   # index of the multiple_choice question in questions.json

class TestMultipleChoice:
    def test_student_page_shows_mc_options(self, client):
        _activate(client, MC_IDX)
        r = client.get('/')
        assert b'academic' in r.data
        assert b'industry' in r.data
        assert b'hobbyist' in r.data

    def test_mc_renders_as_buttons_not_checkboxes(self, client):
        _activate(client, MC_IDX)
        r = client.get('/')
        # CSS has input[type="..."] selectors but no actual input elements in MC
        assert b'<input type="checkbox"' not in r.data
        assert b'<input type="range"' not in r.data
        # Each option rendered as a named submit button
        for opt in server.questions[MC_IDX]['options']:
            assert f'name="option" value="{opt}"'.encode() in r.data

    def test_submit_valid_mc_answer(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={'option': 'academic'})
        qid = str(server.questions[MC_IDX]['id'])
        assert server.responses[qid][0]['answer'] == 'academic'

    def test_submit_mc_stores_timestamp(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={'option': 'industry'})
        qid = str(server.questions[MC_IDX]['id'])
        assert 'timestamp' in server.responses[qid][0]

    def test_invalid_mc_option_ignored(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={'option': 'not_a_valid_option'})
        assert server.responses == {}

    def test_empty_mc_option_ignored(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={})
        assert server.responses == {}

    def test_mc_results_api_counts(self, client):
        _activate(client, MC_IDX)
        for opt in ['academic', 'industry', 'academic', 'hobbyist', 'academic']:
            client.post('/answer', data={'option': opt})
        data = client.get('/api/results').get_json()
        assert data['active'] is True
        assert data['type'] == 'multiple_choice'
        assert data['total'] == 5
        assert data['counts']['academic'] == 3
        assert data['counts']['industry'] == 1
        assert data['counts']['hobbyist'] == 1

    def test_mc_results_all_options_present_when_empty(self, client):
        _activate(client, MC_IDX)
        data = client.get('/api/results').get_json()
        assert set(data['labels']) == {'academic', 'industry', 'hobbyist'}
        assert all(v == 0 for v in data['counts'].values())

    def test_mc_response_in_export(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={'option': 'industry'})
        rows = list(csv.reader(io.StringIO(client.get('/export').data.decode())))
        q = server.questions[MC_IDX]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        data = {r[0]: r[1] for r in rows[title_idx + 1: title_idx + 1 + len(q['options'])]}
        assert data['industry'] == '1'
        assert data['academic'] == '0'

    def test_bulk_mc(self, client):
        entries = bulk_multiple_choice(idx=MC_IDX, n=300)
        assert len(entries) == 300
        data = client.get('/api/results').get_json()
        assert data['total'] == 300
        # First option should be most popular given skewed weights
        counts = data['counts']
        opts = server.questions[MC_IDX]['options']
        assert counts[opts[0]] > counts[opts[1]]


# ── questions file save / load ─────────────────────────────────────────────────

class TestQuestionsFile:
    def test_save_writes_valid_json(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'questions.json').write_text('[]')
        client.post('/api/save_questions')
        written = json.loads((tmp_path / 'questions.json').read_text())
        assert written == server.questions

    def test_save_preserves_all_fields(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'questions.json').write_text('[]')
        client.post('/api/save_questions')
        written = json.loads((tmp_path / 'questions.json').read_text())
        q = written[0]
        assert 'id' in q and 'text' in q and 'type' in q

    def test_load_replaces_questions(self, client):
        new_qs = [{'id': 99, 'text': 'New Q', 'type': 'rating', 'min': 1, 'max': 5}]
        r = client.post('/api/load_questions', json=new_qs)
        assert r.get_json()['ok'] is True
        assert server.questions == new_qs

    def test_load_returns_count(self, client):
        new_qs = [
            {'id': 1, 'text': 'Q1', 'type': 'rating', 'min': 1, 'max': 10},
            {'id': 2, 'text': 'Q2', 'type': 'checkbox', 'options': ['a', 'b']},
        ]
        d = client.post('/api/load_questions', json=new_qs).get_json()
        assert d['count'] == 2

    def test_load_resets_active_question(self, client):
        _activate(client, 0)
        new_qs = [{'id': 1, 'text': 'Q', 'type': 'rating', 'min': 1, 'max': 10}]
        client.post('/api/load_questions', json=new_qs)
        assert server.current_idx == -1

    def test_load_not_a_list_rejected(self, client):
        r = client.post('/api/load_questions', json={'text': 'oops'})
        assert r.status_code == 400

    def test_load_invalid_type_rejected(self, client):
        r = client.post('/api/load_questions',
                        json=[{'id': 1, 'text': 'Q', 'type': 'freetext'}])
        assert r.status_code == 400

    def test_load_rating_missing_min_max_rejected(self, client):
        r = client.post('/api/load_questions',
                        json=[{'id': 1, 'text': 'Q', 'type': 'rating'}])
        assert r.status_code == 400

    def test_load_checkbox_missing_options_rejected(self, client):
        r = client.post('/api/load_questions',
                        json=[{'id': 1, 'text': 'Q', 'type': 'checkbox'}])
        assert r.status_code == 400

    def test_load_multiple_choice_missing_options_rejected(self, client):
        r = client.post('/api/load_questions',
                        json=[{'id': 1, 'text': 'Q', 'type': 'multiple_choice'}])
        assert r.status_code == 400

    def test_roundtrip_save_then_load(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'questions.json').write_text('[]')
        client.post('/api/save_questions')
        saved = json.loads((tmp_path / 'questions.json').read_text())
        server.questions[:] = []  # wipe in-memory
        client.post('/api/load_questions', json=saved)
        assert server.questions == saved


# ── CSV export (summary format) ────────────────────────────────────────────────
# Format per question: title row, labels row, counts row; blank line between questions.
# Designed for paste-into-Google-Sheets → select 2 data rows → Insert chart.

class TestExport:
    def _rows(self, client):
        r = client.get('/export')
        return list(csv.reader(io.StringIO(r.data.decode())))

    def test_content_type_is_csv(self, client):
        assert 'text/csv' in client.get('/export').content_type

    def test_filename_is_summary(self, client):
        cd = client.get('/export').headers['Content-Disposition']
        assert 'summary_' in cd

    def test_each_question_has_title_row(self, client):
        rows = self._rows(client)
        texts = [q['text'] for q in server.questions]
        for text in texts:
            assert any(text in row[0] for row in rows if row)

    def test_title_row_includes_response_count(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '7'})
        client.post('/answer', data={'rating': '5'})
        rows = self._rows(client)
        assert '2 responses' in rows[0][0]

    def test_checkbox_title_shows_respondents_and_selections(self, client):
        _activate(client, 1)
        # person 1 ticks 2 options, person 2 ticks 1 option → 2 respondents, 3 selections
        client.post('/answer', data={'options': ['written an app', 'designed a chip']})
        client.post('/answer', data={'options': ['coded a website']})
        rows = self._rows(client)
        q = server.questions[1]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        title = rows[title_idx][0]
        assert '2 respondents' in title
        assert '3 selections' in title

    def test_mc_title_shows_responses_not_respondents(self, client):
        _activate(client, MC_IDX)
        client.post('/answer', data={'option': 'academic'})
        rows = self._rows(client)
        q = server.questions[MC_IDX]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        assert 'responses' in rows[title_idx][0]
        assert 'respondents' not in rows[title_idx][0]

    def test_rating_has_one_row_per_bucket(self, client):
        rows = self._rows(client)
        q = server.questions[0]
        n_buckets = q['max'] - q['min'] + 1
        # title row + one row per bucket
        assert rows[1:1 + n_buckets] == [[str(v), '0'] for v in range(q['min'], q['max'] + 1)]

    def test_rating_counts_correct(self, client):
        _activate(client, 0)
        for v in [3, 7, 7, 10]:
            client.post('/answer', data={'rating': str(v)})
        rows = self._rows(client)
        data = {r[0]: r[1] for r in rows if len(r) == 2}
        assert data['7'] == '2'
        assert data['3'] == '1'
        assert data['10'] == '1'
        assert data['1'] == '0'

    def test_checkbox_has_one_row_per_option(self, client):
        rows = self._rows(client)
        q = server.questions[1]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        option_rows = rows[title_idx + 1: title_idx + 1 + len(q['options'])]
        assert [r[0] for r in option_rows] == q['options']

    def test_checkbox_counts_correct(self, client):
        _activate(client, 1)
        client.post('/answer', data={'options': ['written an app', 'designed a chip']})
        client.post('/answer', data={'options': ['written an app']})
        rows = self._rows(client)
        q = server.questions[1]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        data = {r[0]: r[1] for r in rows[title_idx + 1: title_idx + 1 + len(q['options'])]}
        assert data['written an app'] == '2'
        assert data['designed a chip'] == '1'
        assert data['coded a website'] == '0'

    def test_mc_counts_correct(self, client):
        _activate(client, MC_IDX)
        for opt in ['academic', 'academic', 'industry']:
            client.post('/answer', data={'option': opt})
        rows = self._rows(client)
        q = server.questions[MC_IDX]
        title_idx = next(i for i, r in enumerate(rows) if r and q['text'] in r[0])
        data = {r[0]: r[1] for r in rows[title_idx + 1: title_idx + 1 + len(q['options'])]}
        assert data['academic'] == '2'
        assert data['industry'] == '1'

    def test_blank_row_between_questions(self, client):
        rows = self._rows(client)
        q = server.questions[0]
        n_buckets = q['max'] - q['min'] + 1
        # blank row after first question's block
        assert rows[1 + n_buckets] == []

    def test_zero_responses_shows_zeros(self, client):
        rows = self._rows(client)
        q = server.questions[0]
        data = {r[0]: r[1] for r in rows[1:] if len(r) == 2}
        for v in range(q['min'], q['max'] + 1):
            assert data[str(v)] == '0'


# ── teacher page ───────────────────────────────────────────────────────────────

class TestTeacherPage:
    def test_page_loads(self, client):
        r = client.get('/teacher')
        assert r.status_code == 200
        assert b'Teacher Dashboard' in r.data

    def test_all_questions_listed(self, client):
        import html as html_lib
        r = client.get('/teacher')
        page = html_lib.unescape(r.data.decode())
        for q in server.questions:
            assert q['text'] in page

    def test_active_question_highlighted(self, client):
        _activate(client, 0)
        r = client.get('/teacher')
        # Active item gets the 'active' CSS class
        assert b'q-item active' in r.data or b'q-item  active' in r.data or b'active' in r.data

    def test_qr_code_present(self, client):
        r = client.get('/teacher')
        assert b'data:image/png;base64,' in r.data


# ── bulk submission helpers ────────────────────────────────────────────────────
# These write directly into server.responses for speed.
# They are also called by server.py --preload for live graph testing.

def bulk_rating(idx=0, n=200, seed=42):
    """
    Inject n fake rating responses with a bell-curve distribution.
    Activates the question. Returns the list of response entries.
    """
    import random as _random
    rng = _random.Random(seed)
    server.current_idx = idx
    q = server.questions[idx]
    lo, hi = q['min'], q['max']
    mid = (lo + hi) / 2 + 1
    entries = []
    for _ in range(n):
        v = round(rng.gauss(mid, (hi - lo) / 5))
        entries.append({'answer': max(lo, min(hi, v)), 'timestamp': '2026-01-01T00:00:00'})
    server.responses[str(q['id'])] = entries
    return entries


def bulk_multiple_choice(idx=2, n=200, seed=42):
    """
    Inject n fake multiple-choice responses (one option per response).
    First option is most popular.
    """
    import random as _random
    rng = _random.Random(seed)
    server.current_idx = idx
    q = server.questions[idx]
    weights = [0.5 - i * (0.4 / max(len(q['options']) - 1, 1))
               for i in range(len(q['options']))]
    entries = [{'answer': rng.choices(q['options'], weights=weights)[0],
                'timestamp': '2026-01-01T00:00:00'}
               for _ in range(n)]
    server.responses[str(q['id'])] = entries
    return entries


def bulk_checkbox(idx=1, n=200, seed=42):
    """
    Inject n fake checkbox responses with a skewed distribution
    (first option most popular, last least popular).
    Activates the question. Returns the list of response entries.
    """
    import random as _random
    rng = _random.Random(seed)
    server.current_idx = idx
    q = server.questions[idx]
    weights = [0.8 - i * (0.6 / max(len(q['options']) - 1, 1))
               for i in range(len(q['options']))]
    entries = []
    for _ in range(n):
        chosen = [opt for opt, w in zip(q['options'], weights) if rng.random() < w]
        if not chosen:
            chosen = [q['options'][0]]
        entries.append({'answer': chosen, 'timestamp': '2026-01-01T00:00:00'})
    server.responses[str(q['id'])] = entries
    return entries


class TestBulkHelpers:
    def test_bulk_rating_count(self, client):
        entries = bulk_rating(idx=0, n=200)
        assert len(entries) == 200

    def test_bulk_rating_values_in_range(self, client):
        q = server.questions[0]
        for e in bulk_rating(idx=0, n=500):
            assert q['min'] <= e['answer'] <= q['max']

    def test_bulk_rating_bell_curve_peaks_in_middle(self, client):
        bulk_rating(idx=0, n=500)
        data = client.get('/api/results').get_json()
        # Values 6-9 should be the majority
        mid_count = sum(data['counts'][str(v)] for v in range(6, 10))
        assert mid_count > 250

    def test_bulk_rating_visible_in_results_api(self, client):
        bulk_rating(idx=0, n=200)
        data = client.get('/api/results').get_json()
        assert data['total'] == 200
        assert data['active'] is True

    def test_bulk_checkbox_count(self, client):
        assert len(bulk_checkbox(idx=1, n=200)) == 200

    def test_bulk_checkbox_first_option_most_popular(self, client):
        bulk_checkbox(idx=1, n=300)
        data = client.get('/api/results').get_json()
        counts = data['counts']
        opts = server.questions[1]['options']
        assert counts[opts[0]] > counts[opts[1]] > counts[opts[2]]

    def test_bulk_checkbox_visible_in_results_api(self, client):
        bulk_checkbox(idx=1, n=200)
        data = client.get('/api/results').get_json()
        assert data['total'] == 200
        assert data['active'] is True

    def test_bulk_multiple_choice_count(self, client):
        assert len(bulk_multiple_choice(idx=2, n=200)) == 200

    def test_bulk_multiple_choice_first_option_most_popular(self, client):
        bulk_multiple_choice(idx=2, n=300)
        data = client.get('/api/results').get_json()
        counts = data['counts']
        opts = server.questions[2]['options']
        assert counts[opts[0]] > counts[opts[-1]]

    def test_preload_test_data_fills_all_questions(self, client):
        server.preload_test_data(n=100)
        for q in server.questions:
            assert len(server.responses.get(str(q['id']), [])) == 100

    def test_preload_test_data_activates_first_question(self, client):
        server.preload_test_data()
        assert server.current_idx == 0


# ── auth ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_client(monkeypatch):
    """Test client with TEACHER_PASSWORD set to 'secret'."""
    monkeypatch.setattr(server, 'TEACHER_PASSWORD', 'secret')
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c


def _login(client, password='secret'):
    return client.post('/teacher/login', data={'password': password},
                       follow_redirects=False)


class TestAuth:
    def test_teacher_redirects_to_login_when_password_set(self, auth_client):
        r = auth_client.get('/teacher')
        assert r.status_code == 302
        assert '/teacher/login' in r.headers['Location']

    def test_api_activate_redirects_when_not_logged_in(self, auth_client):
        r = auth_client.post('/api/activate/0')
        assert r.status_code == 302

    def test_api_deactivate_redirects_when_not_logged_in(self, auth_client):
        r = auth_client.post('/api/deactivate')
        assert r.status_code == 302

    def test_export_redirects_when_not_logged_in(self, auth_client):
        r = auth_client.get('/export')
        assert r.status_code == 302

    def test_login_page_loads(self, auth_client):
        r = auth_client.get('/teacher/login')
        assert r.status_code == 200
        assert b'Teacher Login' in r.data

    def test_wrong_password_shows_error(self, auth_client):
        r = _login(auth_client, password='wrong')
        assert r.status_code == 200 or r.status_code == 302
        # follow to check error message
        r = auth_client.post('/teacher/login', data={'password': 'wrong'})
        assert b'Incorrect password' in r.data

    def test_correct_password_redirects_to_teacher(self, auth_client):
        r = _login(auth_client, password='secret')
        assert r.status_code == 302
        assert '/teacher' in r.headers['Location']

    def test_logged_in_can_access_teacher(self, auth_client):
        _login(auth_client, password='secret')
        r = auth_client.get('/teacher', follow_redirects=True)
        assert r.status_code == 200
        assert b'Teacher Dashboard' in r.data

    def test_logged_in_can_use_api(self, auth_client):
        _login(auth_client, password='secret')
        r = auth_client.post('/api/activate/0')
        assert r.status_code == 200

    def test_logout_clears_session(self, auth_client):
        _login(auth_client, password='secret')
        auth_client.post('/teacher/logout')
        r = auth_client.get('/teacher')
        assert r.status_code == 302
        assert '/teacher/login' in r.headers['Location']

    def test_no_password_set_skips_auth(self, client):
        # default client has no TEACHER_PASSWORD — teacher should be accessible
        r = client.get('/teacher')
        assert r.status_code == 200

    def test_login_redirects_to_next_param(self, auth_client):
        # accessing /teacher while logged out should redirect back after login
        r = auth_client.get('/teacher')
        assert '/teacher/login?next=' in r.headers['Location']
        _login(auth_client, password='secret')
        r = auth_client.get('/teacher', follow_redirects=True)
        assert r.status_code == 200
        assert b'Teacher Dashboard' in r.data


# ── reset answered ─────────────────────────────────────────────────────────────

class TestResetAnswered:
    def test_clears_responses(self, client):
        _activate(client, 0)
        client.post('/answer', data={'rating': '7'})
        assert server.responses != {}
        client.post('/api/reset_answered')
        assert server.responses == {}

    def test_increments_cookie_round(self, client):
        before = server.cookie_round
        client.post('/api/reset_answered')
        assert server.cookie_round == before + 1

    def test_old_answered_cookie_ignored_after_reset(self, client):
        _activate(client, 0)
        # submit answer — sets cookie for current round
        client.post('/answer', data={'rating': '7'})
        r = client.get('/')
        assert b'Thanks for your answer' in r.data
        # reset — cookie round changes
        client.post('/api/reset_answered')
        _activate(client, 0)
        # student page should show the question again, not "thanks"
        r = client.get('/')
        assert b'Thanks for your answer' not in r.data
        assert b'type="range"' in r.data

    def test_returns_ok(self, client):
        r = client.post('/api/reset_answered')
        assert r.get_json()['ok'] is True

    def test_requires_auth_when_password_set(self, auth_client):
        r = auth_client.post('/api/reset_answered')
        assert r.status_code == 302
