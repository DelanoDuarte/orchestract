# Orchestract

Orchestrates contracting documents through a customizable workflow: documents move between
**agents** (departments/participants) across a graph of steps you define — not just a fixed
Draft → Sign → Archive pipeline, but branches and loops too (e.g. renewals/amendments looping
back to an active contract, rejected negotiations looping back to draft).

Built with FastAPI + SQLAlchemy 2.0 (async) using domain-driven design: rich aggregates
(`WorkflowDefinition`, `WorkflowInstance`, `Document`, `Agent`, `Organization`) enforce their own
invariants, a repository + unit-of-work layer handles persistence, and an application layer
orchestrates use cases that span multiple aggregates. See `app/domain/` for the model and
`app/application/` for the use cases.

## Setup

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.infrastructure.seed   # demo org, 9 agents, an active workflow, 1 document
uv run fastapi dev main.py
```

Then visit `http://127.0.0.1:8000/acme-corp/` for the UI, or `http://127.0.0.1:8000/docs` for the
API. Most API routes are tenant-scoped via an `X-Organization-Id` header; the seed script prints
the organization slug/id it created.

## Tests

```bash
uv run pytest
```

## Layout

- `app/domain/` — aggregates and rich domain models, one package per bounded context
  (`tenancy`, `agents`, `workflow`, `workflow_instances`, `documents`, `storage`), each with its
  own `models.py`, `exceptions.py`, and `repository.py` (persistence port).
- `app/infrastructure/db/` — SQLAlchemy session/engine, unit of work, and the repository
  implementations. `app/infrastructure/seed.py` is the demo data script.
- `app/infrastructure/storage/` — the pluggable file-storage adapters (see below).
- `app/application/` — use-case services that coordinate repositories + domain methods,
  including the ones that span more than one aggregate (e.g. creating a `Document` and starting
  its `WorkflowInstance` together).
- `app/api/` — JSON API routers under `/api/v1`.
- `app/web/` — Jinja2-rendered UI (`templates/`) and its routes.
- `alembic/` — schema migrations.

## UI stack

Server-rendered Jinja2 templates styled with [Basecoat UI](https://basecoatui.com) (shadcn-style
components in plain HTML/CSS/JS — no React) plus Tailwind CSS, both loaded via CDN with no build
step:

- Tailwind's browser build (`@tailwindcss/browser`) generates utility classes (layout, spacing,
  responsive variants) from the actual rendered HTML at page load.
- Basecoat's CDN CSS provides the component classes (`.btn`, `.card`, `.badge`, `.sidebar`,
  `.field`, `.table`, ...) and loads *after* Tailwind so its component styles win over Tailwind's
  preflight reset, per Basecoat's documented load order.
- `app/web/static/theme.css` overrides Basecoat's shadcn-compatible CSS variables
  (`--background`, `--primary`, `--accent`, ...) with a dark teal/amber palette, and defines the
  `.step-pipeline`/`.step-pill` classes used for the lifecycle graph banner.
- `app/web/icons.py` inlines Lucide SVGs (vendored in `app/web/icons/`) as a Jinja global `icon()`,
  plus a `step_icon()` mapping from workflow step key to icon name.
- Dark/light mode is class-based (`<html class="dark">`) with a toggle button using
  `window.basecoat.theme.toggle()`; a `@custom-variant dark (&:is(html.dark *));` declaration keeps
  Tailwind's `dark:` utilities in sync with Basecoat's toggle instead of the OS-preference default.

Note: both CDN scripts are explicitly documented as dev/prototyping tools, not for production —
swap them for a real Tailwind build + `basecoat-css` npm package (see their install docs) before
shipping.

## File storage

Each organization configures its own `StorageConnection` (`/{org_slug}/settings/storage`):

- **Write backends** — S3, Google Cloud Storage, or MinIO (S3-compatible; same adapter, just
  pointed at a custom `endpoint_url`). Exactly one is the org's *primary* connection, which is
  where new document version bytes get written (`app/infrastructure/storage/s3_compatible.py`,
  `gcs.py`). A `local` provider (`local.py`) writes to `./storage/` on disk — dev/demo only, not
  offered as a production choice, used so the seed script and tests have something real to
  exercise without cloud credentials.
- **Read-only import sources** — Google Drive and OneDrive, connected via OAuth2
  (`google_drive.py`, `onedrive.py` — plain `httpx` calls, no SDK). Files picked from either are
  **copied into the org's primary backend** at import time (`DocumentService.
  import_version_from_external`), so a version stays retrievable even if the source file is later
  deleted or access is revoked. These can never be the primary connection.

Bucket credentials and OAuth tokens (`StorageCredential.secrets`) are encrypted at rest with
Fernet (`app/domain/shared/encrypted_json.py`) using `ORCHESTRACT_STORAGE_ENCRYPTION_KEY`. If
unset, an ephemeral key is generated per-process (logged as a warning) — fine for a single dev
run, but set a persistent one (`.env` in this repo already has one for local dev) or every
previously-stored secret becomes undecryptable on restart.

Google Drive/OneDrive need a real registered OAuth app to actually authenticate —
`ORCHESTRACT_GOOGLE_OAUTH_CLIENT_ID`/`_SECRET` and `ORCHESTRACT_MICROSOFT_OAUTH_CLIENT_ID`/`_SECRET`
are empty by default, and the "Connect..." buttons render disabled until they're set. Redirect
URIs to register: `{ORCHESTRACT_OAUTH_REDIRECT_BASE}/oauth/google-drive/callback` and
`.../oauth/onedrive/callback`.
