# Plan: from separate tools to one content system

This repository turns into a single local app, a system of record for content
with automation tools around it. Ideas, collaborators, assets and performance
live in one place, and you can measure how long each piece takes to come to life.

It has two parts:

- **backend**: an MCP server. It holds all the logic and is the only thing
  that writes to the database.
- **frontend**: a Streamlit UI that talks to the backend through MCP.

## Principles

- **The backend is the only writer.** Claude (Code/Desktop) and the frontend
  are both MCP clients. The frontend never touches the database. There is no CLI.
- **The frontend reads files read-only.** Images stay on disk. Tools return
  paths, and the frontend mounts the data folder `:ro`. Uploads go to tools as
  base64.
- **Don't rebuild what already exists.** Publishing and scheduling belong to
  Buffer, and Todoist keeps life tasks. The backend exposes only what nobody else
  has: pieces, stages, time, lineage, assets, explore tools, and performance per
  piece.
- **Local first.** `docker compose up` or `uv run`. No hosting or auth for now,
  but the database URL comes from the environment and file access goes through
  one module, so a later move to the cloud is a config change.
- **Each phase must make the next piece of content faster.** If one doesn't,
  stop and reassess.

## Decisions

| Topic | Decision |
|---|---|
| Naming | `backend/` and `frontend/`. Not `mcp/`, because a top-level package with that name would shadow the `mcp` library that FastMCP depends on. In Claude the server is registered as `marketing-tools`. |
| Pieces | A piece is one unit of work. Derivatives (a video from a blog post, clips from a video) are child pieces. There is no publication entity: pieces are not tied to where they were published. |
| Analytics | Per piece only: **impressions** (views) and **engagement** (likes, comments, saves, shares), summed across platforms. No conversion tracking for now. |
| Publishing | Out of scope. Buffer does it. |
| Todoist | Brand content leaves Todoist. The backend owns pieces and stages, and there is no sync. Mariano handles the migration and skill updates once the system is proven. This repo never touches Todoist or the skills. |
| WordPress | `wordpress/` stays where it is, untouched and outside the system. It may become a tool later. |
| Packaging | One `pyproject.toml` + `uv.lock` and one Docker image, run through Compose. The per-project `requirements.txt` files for `youtube/` and `asset_generation/` go away. |
| Frontend | Keep Streamlit, with `st.navigation` sections **Explore / Create / Analyse**. |
| Database | SQLite (WAL) through SQLAlchemy, with Alembic migrations from day one. |
| MCP | FastMCP over streamable HTTP, with plain tools. |

## Target layout

```text
pyproject.toml  uv.lock  Dockerfile  compose.yaml  .env.example
backend/                  # MCP server, the only writer
  server.py               # FastMCP app: registers the tools below
  config.py               # env: DATABASE_URL, DATA_DIR, API keys
  db.py  models.py        # SQLAlchemy engine + tables
  storage.py              # save / open / path_for (the only file I/O)
  create/
    assets/               # generation.py, prompt_manager.py (moved as-is)
    pieces.py             # pieces, stages, lineage, time
  explore/
    youtube/              # youtube_api, pipeline, metrics, filters, aggregation
    people.py             # collaborators, podcasts, outlets
  analyse/
    performance.py        # metric sync + per-piece reports
frontend/                 # Streamlit, MCP client, data mounted read-only
  app.py                  # st.navigation with the three sections
  client.py               # call(tool, **args) → backend
  pages/                  # library, create asset, worlds, board, piece,
                          # creator search/results/detail, people, performance
migrations/               # Alembic
tests/
wordpress/                # untouched, outside the system
data/                     # gitignored: app.db + img/<world>/<type>/
```

Compose runs two services from one image:

- `backend` on :8765, data mounted read-write.
- `frontend` (Streamlit) on :8501, data mounted read-only, `BACKEND_URL=http://backend:8765/mcp`.

## Data model

| Table | Key columns |
|---|---|
| `piece` | id, title, format (blog/video/short/podcast/newsletter/post), stage, parent_id → piece, notes, external_refs (JSON, see below), created_at, published_at |
| `stage_event` | piece_id, stage, entered_at, left_at, minutes |
| `world` | id, name, slug |
| `asset` | id, world_id, type (character/object/location/scene/other), name, style, provider, generation_uid, path (relative to `DATA_DIR`), created_at |
| `piece_asset` | piece_id, asset_id, role |
| `person` | id, name, kind (creator/podcast/guest/outlet), links, notes, source (e.g. YouTube channel id) |
| `piece_person` | piece_id, person_id, role (guest, collaborator, host) |
| `piece_metric` | piece_id, date, impressions, likes, comments, saves, shares |

The stages mirror today's Brand board: `idea → draft → assets → edit → review →
published`. *Repurpose* stops being a stage and becomes child pieces. Lead time
(idea → published) and touch time (sum of minutes) come straight from
`stage_event`.

`external_refs` is the only link to the outside world: the Buffer post IDs (and
YouTube video IDs, if needed) whose numbers belong to the piece. It exists only
so the metric sync knows what to add up. It is not a publication record.

## MCP tools (v1)

- **Assets:** `list_assets(world, type, style, provider, limit, cursor)`,
  `get_asset`, `start_generation(...)` → job id, `get_job`, `move_asset`,
  `copy_asset`, `delete_asset`, `list_worlds`, `create_world`, `rename_world`,
  `delete_world`
- **Pieces:** `create_piece(title, format, parent_id?, created_at?)`,
  `move_piece(id, stage, minutes?, at?)`, `log_time`, `list_pieces(stage, format,
  limit, cursor)`, `get_piece` (with assets, people, children, timing,
  performance), `link_asset`, `link_person`, `add_external_ref`
- **Explore:** `search_creators(keyword, view_range, subscriber_range,
  activity_days)`, `get_creator`, `save_person`, `list_people`
- **Analyse:** `sync_metrics`, `piece_performance(period)`

Optional timestamps (`created_at`, `at`) exist so the Todoist history can be
backfilled later through Claude, without an import script.

## Phases

### Phase 0: one package, one app (no behavior change)

1. Add `pyproject.toml` + `uv.lock` (Python 3.12), and remove the
   `requirements.txt` files of `youtube/` and `asset_generation/`.
2. Move the code into `backend/` and `frontend/` as laid out above, fixing
   imports. Until Phase 1, the frontend imports backend modules directly.
3. One Streamlit app with `st.navigation` sections: Explore (creator
   discovery), Create (library, create, worlds), Analyse (placeholder).
4. Merge the two `.env` files into one root `.env.example`. Move `img/` under
   `data/img/`.
5. Add `Dockerfile` and `compose.yaml` (frontend only at this point).
6. Update `CLAUDE.md` and the READMEs.

**Done when:** both existing tools work exactly as before from
`docker compose up` and from `uv run streamlit run frontend/app.py`.

### Phase 1: database + MCP backend, starting with assets

1. `config.py`, `db.py`, `models.py`, and an Alembic baseline (`world`, `asset`).
2. `storage.py` becomes the only place that touches files.
3. Index the existing `img/` tree into `asset` and `world` (filename parse from
   `shared/library.py`), run once on startup and idempotent.
4. `server.py` with the asset and world tools. The background generation runner
   (today's `shared/jobs.py`) moves into the backend.
5. `frontend/client.py`. The library, create and worlds pages switch to MCP
   calls, and the frontend mounts `data/` read-only.
6. Add the `backend` service to Compose and document `claude mcp add
   --transport http marketing-tools http://localhost:8765/mcp`.
7. Tests: pytest using FastMCP's in-memory `Client` against a temporary
   database.

**Done when:** the asset library works through the backend, and Claude can
generate and list assets.

### Phase 2: pieces (the Create system of record)

1. Migration: `piece`, `stage_event`, `piece_asset`.
2. Piece tools.
3. Frontend: a **Board** (columns per stage, move with time logged) and a
   **Piece** detail page (assets gallery, children, timeline, minutes per stage).
4. Asset generation accepts `piece_id`, and the library can filter by piece.

**Done when:** a new idea can be carried from idea to published in this app
alone, with lead and touch time visible.

### Phase 3: Explore on the backend

1. Migration: `person`, `piece_person`.
2. Creator search and detail tools. Search results stay transient; only saved
   creators become `person` rows.
3. The YouTube pages switch to MCP calls, with a "save as person" action and a
   **People** gallery.

**Done when:** "find collaborators → save → start a piece with them" works from
both Claude and the frontend.

### Phase 4: Analyse (performance per piece)

1. Migration: `piece_metric`.
2. `sync_metrics` reads impressions and engagement for each piece's
   `external_refs` from the Buffer API, plus the YouTube Data API for anything
   Buffer doesn't cover. It runs in the backend, triggered from the frontend or
   by Claude.
3. **Performance** page: impressions and engagement per piece next to its lead
   and touch time, plus repurpose candidates (top performers with no children).

**Done when:** one page shows which pieces performed best and how long each took.

## Open questions

- **Buffer coverage:** does Buffer's API return impressions, likes, comments,
  saves and shares per post for every channel you use, or do some (e.g.
  long-form YouTube) need their own API? Check this before Phase 4.
