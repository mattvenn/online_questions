# Online Questions

## Aim

Allow a workshop leader to ask a question to a virtual audience like "how confident are you with Verilog" and as the audience answers, the results are visible immediately as a graph on screen.

## Description 
* Allow attendees to an online workshop answer questions quickly by:
	* scanning a qr code with their phone or clicking a link
	* the types of questions:
		* multiple choice of 5 things
		* a rating from 1 to 10
		* checkboxes
		* free text
	* as people answer, the results are visible on a dashboard that can be shared onscreen
		* a % of people who have answered and some other stats are shown
		* window to answer closes after some time
* History is stored and easily exported
* Questions can be queued via a simple interface or read in a csv/spreadsheet
* On the spur of the moment a new question can be asked

## Implementation

* Should be hosted on a digital ocean style droplet with Linux as OS
* served via nginx
* simple webpages with a simple style and very fast loading
* installable as a pip python package

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

58 tests covering all endpoints, validation, CSV export, and the bulk data helpers.

### Questions

Questions are defined in `questions.json`. Each question needs `id`, `text`, and `type`. Supported types:

- `rating` — slider from `min` to `max`, with optional `label_min` / `label_max`
- `checkbox` — multiple-select from an `options` list

New questions can also be added live from the teacher dashboard ("+ Ask impromptu question").

### Exporting results

Click **Export CSV** on the teacher dashboard, or GET `/export`. One row per response, with `question_id`, `question_text`, `type`, `answer`, and `timestamp` columns.

