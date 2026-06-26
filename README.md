# RUFF-VI Annotation Tool

A lightweight annotation tool for RUFF-VI pronoun/term selection tasks. It includes annotator username entry, resumable queues, SQLite persistence, CSV instance loading, submitted annotation locking, and a keyed admin dashboard with inter-annotator agreement.

## Setup

1. Clone the repo.
2. Run `npm install` from the project root.
3. Copy `.env.example` to `.env` and fill in your values.
4. Run `npm run dev`.
5. Open <http://localhost:3000>.

This project uses a Python standard-library server behind the npm scripts, so there are no runtime npm dependencies.

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `PORT` | Yes | Port for the local web server. Use `3000` for local development. |
| `NODE_ENV` | Yes | Runtime environment name, such as `development` or `production`. |
| `DATABASE_PATH` | Yes | Path to the SQLite database file. It is created automatically on first run. |
| `ADMIN_SECRET` | Yes | Secret string required for `/admin`, admin result APIs, and CSV imports. |

The app checks these variables on startup. If any are missing, it logs a clear error and exits.

## Loading New Instances

1. Go to `/admin/import`.
2. Enter your `ADMIN_SECRET`.
3. Download the CSV template or prepare a CSV with the documented headers.
4. Upload the CSV and confirm the preview.

CSV upload requests must include:

```text
Authorization: Bearer <ADMIN_SECRET>
```

## Sharing With Annotators

- Deploy to Railway or Render. A free tier is sufficient for small annotation rounds.
- Set the environment variables in the platform dashboard.
- Share the public annotation URL with annotators.
- Keep the `ADMIN_SECRET` private; only researchers should use `/admin` and `/admin/import`.

## Data

The SQLite database is not committed to the repo. On first run it is created automatically at `DATABASE_PATH`.

To back up annotations, open `/admin`, enter `ADMIN_SECRET`, and use the **Export CSV** button.

## Local Storage Keys

- `ruffvi_queue_[username]` — ordered instance queue for a user
- `ruffvi_skip_warning_shown` — whether the skip reasoning warning has been shown this session
- `ruffvi_admin_secret` — admin secret stored locally in the researcher's browser after unlocking admin/import views

## CSV Format

The canonical import format uses these exact headers:

```text
occupation,occupation_en,participant_role,participant_role_en,term_set,narrator_position,distractor_level,intro_vi,intro_en,distractor_1_vi,distractor_1_en,distractor_2_vi,distractor_2_en,distractor_3_vi,distractor_3_en,distractor_4_vi,distractor_4_en,distractor_5_vi,distractor_5_en,target_vi,target_en,correct_answer
```

Rules:

- `distractor_level` must be 0-5.
- Distractor columns beyond `distractor_level` are ignored on import.
- `correct_answer` must be one of: `anh`, `chị`, `cô`, `chú`, `ông`, `bà`, `em`, `nó`, `hắn`, `chanh`.
- Rows with missing required fields are rejected with a row number and reason.
- Duplicate rows matching `(occupation + term_set + narrator_position + distractor_level + intro_vi)` are skipped and reported.

## API

- `POST /api/annotators/check` `{ "username": "..." }`
- `POST /api/annotators/register` `{ "username": "..." }`
- `GET /api/instances/queue?username=X`
- `GET /api/instances`
- `POST /api/annotations`
- `POST /api/annotations/submit` `{ "username": "..." }`
- `GET /api/admin` with `Authorization: Bearer <ADMIN_SECRET>`
- `GET /api/agreement` with `Authorization: Bearer <ADMIN_SECRET>`
- `POST /api/instances/import` with `Authorization: Bearer <ADMIN_SECRET>`
- `GET /api/instances/template`
