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

## Production deployment (Docker)

The app ships with a container image and Compose stacks. Production runs on
**PostgreSQL** (the SQLite default is dev-only) fronted by **Caddy** for automatic HTTPS.

```bash
cp .env.example .env
# Fill in the required values. Generate a persistent encryption key:
make keygen        # -> paste into ORCHESTRACT_STORAGE_ENCRYPTION_KEY
# Set a strong POSTGRES_PASSWORD, plus DOMAIN + ACME_EMAIL for TLS.
```

- **Local / direct** (app on `http://localhost:8000`, http-friendly cookie):

  ```bash
  docker compose up -d --build        # or: make up
  ```

- **Production with TLS** (Caddy obtains Let's Encrypt certs for `DOMAIN`, proxies to the app):

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build   # or: make up-prod
  ```

What the stack does:

- **`Dockerfile`** — multi-stage build with `uv` (both stages share the `python:3.13-slim` base so
  the built virtualenv is portable), runs as a non-root user, and ships a `/healthz`-based
  `HEALTHCHECK`.
- **`docker/entrypoint.sh`** — applies `alembic upgrade head` (retrying while the database comes up;
  skip with `RUN_MIGRATIONS=0`) before starting `uvicorn` with `--proxy-headers` and
  `WEB_CONCURRENCY` workers.
- **`docker-compose.yml`** — Postgres 16 (persistent volume, `pg_isready` healthcheck) + the web app
  (waits for the DB to be healthy, persists the local-disk storage fallback on a volume).
- **`docker-compose.override.yml`** — auto-applied for local runs: publishes the app port and relaxes
  the HTTPS-only cookie. Not loaded when you pass explicit `-f` files (i.e. the prod command).
- **`docker-compose.prod.yml` + `Caddyfile`** — adds Caddy (ports 80/443, auto-HTTPS via `DOMAIN`/
  `ACME_EMAIL`, HSTS/security headers) and stops publishing the app port directly.

Production hardening baked in: `ORCHESTRACT_SESSION_COOKIE_SECURE=true` marks the session cookie
`Secure` (HTTPS-only), and `uvicorn --proxy-headers` trusts Caddy's `X-Forwarded-*`. `make help`
lists convenience targets (`migrate`, `seed`, `psql`, `logs`, …).

> Object storage: real deployments should point the org's primary `StorageConnection` at S3/GCS
> (see **File storage** below) rather than the local-disk fallback, which is a single-node volume.

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
- `app/web/static/theme.css` is the design system: it overrides Basecoat's shadcn-compatible CSS
  variables (`--background`, `--primary`, `--accent`, ...) with a dark teal/amber palette and adds
  elevation/motion tokens, refined component styling (cards, tables, sidebar, inputs, badges), the
  `.step-pipeline`/`.step-pill` lifecycle graph, and reusable helpers (`.page`, `.icon-chip`,
  `.stat-card`, `.empty-state`, `.surface-gradient`). Reusable Jinja layout macros
  (`page_header`, `stat_card`, `empty_state`) live in `app/web/templates/_macros.html`.
- SPA-like navigation via [htmx](https://htmx.org) (CDN, no build): `<body hx-boost>` turns
  same-origin navigation into an AJAX swap of just `<main id="page-main">` (with the View
  Transitions API for a flicker-free cross-fade), so the sidebar/header persist and only the page
  content changes. `htmx-config` `responseHandling` also swaps `400`/`422` so re-rendered form
  validation errors still update the view. Auth/logout forms that change the logged-in/out chrome
  opt out with `hx-boost="false"`; the sidebar's active item is re-synced after each swap.
- `app/web/icons.py` inlines Lucide SVGs (vendored in `app/web/icons/`) as a Jinja global `icon()`,
  plus a `step_icon()` mapping from workflow step key to icon name.
- Dark/light mode is class-based (`<html class="dark">`) with a toggle button using
  `window.basecoat.theme.toggle()`; a `@custom-variant dark (&:is(html.dark *));` declaration keeps
  Tailwind's `dark:` utilities in sync with Basecoat's toggle instead of the OS-preference default.

Note: the Tailwind browser build and Basecoat CDN CSS are explicitly documented as dev/prototyping
tools, not for production — swap them for a real Tailwind build + `basecoat-css` npm package (see
their install docs) before shipping. htmx is loaded from CDN too; pin/vendor it for production.

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
