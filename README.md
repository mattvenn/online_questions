# Online Questions

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

## Aim

Allow a workshop leader to ask a question to a virtual audience like "how confident are you with Verilog" and as the audience answers, the results are visible immediately as a graph on screen.

## Description
* Allow attendees to an online workshop to answer questions quickly by:
	* scanning a QR code with their phone or clicking a link
	* the types of questions supported:
		* multiple choice (pick one)
		* a rating from 1 to 10 (or any range)
		* checkboxes (multi-select)
	* as people answer, results are visible live on a dashboard that can be shared on screen
		* total response count is shown and updates every second
* Results are stored in memory and exportable as CSV
* Questions are pre-loaded from a file in `question_sets/` or added live from the teacher dashboard
* On the spur of the moment a new question can be asked

## Implementation

* Hosted on a Linux server (e.g. DigitalOcean droplet)
* Served via nginx → gunicorn
* Simple webpages with minimal dependencies and fast loading

## Takes inspiration from 

* Mentimeter.com

## Usage

### Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### Start the server

```bash
venv/bin/python server.py
```

- **Teacher dashboard:** http://127.0.0.1:5001/teacher
- **Student page** (shown as QR code on the dashboard): http://\<your-lan-ip\>:5001/

### Start with pre-loaded test data

Useful for working on the teacher graph display without needing real respondents:

```bash
venv/bin/python server.py --preload
```

Injects 200 fake responses for each question (bell-curve distribution for ratings, skewed distribution for checkboxes) and activates the first question.

### Run tests

```bash
venv/bin/pytest test_server.py -v
```

109 tests covering all endpoints, question types, validation, CSV export, and bulk data helpers.

### Load test against a live server

Simulates a crowd of students answering questions in real time. You control the
pacing from the teacher dashboard; the script detects each new question
automatically.

```bash
venv/bin/python load_test.py
```

Defaults to `https://q.tiny.tt`, 200 users per question, responses
spread over 4 seconds. Override any of these:

```bash
venv/bin/python load_test.py --url https://your-server.example.com --users 50 --spread 8
```

**Workflow:**

1. Start the script — it prints `Waiting for a question…` and checks the student page is reachable.
2. On the teacher dashboard, click **Ask this** for the first question.
3. The script fires responses and prints a summary (`✓ 200 submitted, 0 errors`).
4. Click **Stop** or **Ask this** on the next question to advance.
5. Repeat for each question. Press `Ctrl-C` to quit.

### Questions

Questions are defined in JSON files under `question_sets/`, one file per set, named `questions_<key>.json` (e.g. `question_sets/questions_tiny_tapeout.json`). Each question needs `id`, `text`, and `type`. Supported types:

- `rating` — slider from `min` to `max`, with optional `label_min` / `label_max`
- `checkbox` — multiple-select from an `options` list
- `multiple_choice` — pick one from an `options` list

Any file matching that pattern is auto-discovered and selectable from the "Questions" dropdown on the teacher dashboard, with the display name derived from the filename. The active set persists across restarts in `question_set.json`.

New questions can also be added live from the teacher dashboard ("+ Ask impromptu question"). Questions can be saved to / reloaded from the active set's file using the "Questions file" card, and the currently loaded questions can be saved under a new name to create a new set.

### Exporting results

Click **Export results CSV** on the teacher dashboard. The file has one block per question (title, then one `label,count` row per option) with a blank line between questions — paste into Google Sheets and select a block to insert a chart directly.

## Deployment (Linux server)

Requires nginx and a Python venv already set up. Serves on port 80 via nginx → gunicorn.

### 1. Clone and create venv

```bash
git clone <repo-url> /opt/online-questions
cd /opt/online-questions
python3 -m venv venv
```

### 2. Run the install script

```bash
sudo bash install.sh
```

This will:
- Install dependencies (including gunicorn) into the venv
- Write and enable `/etc/systemd/system/online-questions.service` (starts on boot)
- Configure nginx for `q.tiny.tt` and reload it

### 3. Verify

```bash
systemctl status online-questions
journalctl -u online-questions -f   # live logs
```

### Changing the public URL

Edit `BASE_URL` in `/etc/systemd/system/online-questions.service`, then:

```bash
sudo systemctl daemon-reload && sudo systemctl restart online-questions
```

This controls the URL shown in the QR code on the teacher dashboard.

### Teacher password

The teacher dashboard is protected by `TEACHER_PASSWORD`, an environment
variable read by `server.py`. If unset, the dashboard requires no login.

It's set via `Environment=TEACHER_PASSWORD=...` in
`/etc/systemd/system/online-questions.service`, but a systemd drop-in at
`/etc/systemd/system/online-questions.service.d/override.conf` (if present)
takes precedence — check there first when looking for the value actually in
use. To see what's live on the running service:

```bash
systemctl show online-questions -p Environment
```

To change it, edit the override (or the service file if no override
exists), then:

```bash
sudo systemctl daemon-reload && sudo systemctl restart online-questions
```

