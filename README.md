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
  (`tenancy`, `agents`, `workflow`, `workflow_instances`, `documents`), each with its own
  `models.py`, `exceptions.py`, and `repository.py` (persistence port).
- `app/infrastructure/db/` — SQLAlchemy session/engine, unit of work, and the repository
  implementations. `app/infrastructure/seed.py` is the demo data script.
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
