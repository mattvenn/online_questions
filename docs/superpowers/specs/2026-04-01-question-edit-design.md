# Question Edit Feature — Design Spec

**Date:** 2026-04-01

## Overview

Add an inline edit form to each question card in the teacher dashboard, allowing the question text and options (or rating labels) to be updated. Question type cannot be changed. If the question has existing responses, the teacher is warned that saving will clear them.

## UI

Each question card in the left panel gains an **Edit** button alongside the existing delete button. Clicking Edit expands an inline form below the card content — the same expand/collapse pattern used by "Add new question".

The edit form contains:
- A `<textarea>` pre-filled with the current question text
- For `rating` type: two text inputs for `label_min` and `label_max` (pre-filled). Min/max numeric range is not editable to avoid corrupting existing response data.
- For `checkbox` and `multiple_choice` types: a `<textarea>` with one option per line (pre-filled).
- The question type is shown as a read-only label (not a dropdown).
- If the question has existing responses, a warning banner: "Warning: saving will clear N existing response(s) for this question."
- **Save** and **Cancel** buttons.

Only one edit form is open at a time — opening a new one collapses any previously open one.

## Backend

New route: `POST /api/edit_question/<int:idx>`

Accepts JSON:
```json
{
  "text": "Updated question text",
  "label_min": "Not at all",   // rating only
  "label_max": "Expert",       // rating only
  "options": ["A", "B", "C"]  // checkbox / multiple_choice only
}
```

Behaviour:
- Validates `text` is non-empty.
- For `checkbox`/`multiple_choice`: validates at least one option is provided.
- If the question has existing responses, clears them from the `responses` dict before saving.
- Updates the question in-place in the `questions` list (no type change allowed — type is ignored if sent).
- Returns `{"ok": true}` or `{"ok": false, "error": "..."}`.
- Protected by `@login_required`.

## Response clearing

The warning shown in the UI is informational only — the teacher clicks Save knowing responses will be cleared. The backend always clears responses for the edited question unconditionally (not conditional on whether options changed), keeping the logic simple.

## Out of scope

- Changing question type.
- Changing rating min/max numeric range.
- Undo / response archiving before clear.
