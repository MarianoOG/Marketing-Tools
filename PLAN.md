# Plan: from separate tools to one content system

This repository turns into a single local app, a system of record for content
with automation tools around it. The idea → collaborator → assets → publication
→ metrics chain lives in one place, and you can measure how long each piece
takes to come to life.

`studio` is a placeholder name throughout.

## Principles

- **The MCP server is the backend and the only writer.** Claude (Code/Desktop)
  and the Streamlit UI are both MCP clients. No direct database access from the
  UI, no CLI.
- **The UI reads files read-only.** Images stay on disk. Tools return paths,
  and the UI mounts the data folder `:ro`. Uploads go to tools as base64.
- **Don't rebuild what already has an MCP.** Buffer handles scheduling and
  publishing, Brevo handles the newsletter, Todoist handles life tasks. Claude
  combines them. The studio exposes only what nobody else has: pieces, stages,
  time, lineage, assets, explore tools, and joined metrics.
- **Local first.** `docker compose up` or `uv run`. No hosting or auth for now,
  but the database URL comes from the environment and file access goes through
  one module, so a later move to the cloud is a config change.
- **Each phase must make the next piece of content faster.** If one doesn't,
  stop and reassess.

## Decisions

| Topic | Decision |
|---|---|
| Piece vs publication | New work → new **piece**. The same work in a new place → **publication**. Derivatives (a video from a blog post, clips from a video) are child pieces. |
| Todoist | Brand content leaves Todoist. The studio owns pieces and stages, and there is no sync. Mariano handles the migration and skill updates once the studio is proven. This repo never touches Todoist or the skills. |
| Packaging | One uv package (`pyproject.toml` + `uv.lock`) and one Docker image, run through Compose. The per-project `requirements.txt` files go away. |
| UI | Keep Streamlit, with `st.navigation` sections **Explore / Create / Analyse**. |
| Database | SQLite (WAL) through SQLAlchemy, with Alembic migrations from day one. |
| MCP | FastMCP over streamable HTTP. Plain tools; tag filtering only if the tool list actually gets noisy. |
| Out of scope | Scheduling and publishing UI (Buffer), hosting and auth, CLI, Todoist and skill changes. |

## Target layout

```text
pyproject.toml  uv.lock  Dockerfile  compose.yaml  .env.example
src/studio/
  config.py               # env: DATABASE_URL, DATA_DIR, API keys
  db.py  models.py        # SQLAlchemy engine + tables
  storage.py              # save / open / path_for (the only file I/O)
  server.py               # FastMCP app: mounts the modules below
  create/
    assets/               # generation.py, prompt_manager.py (moved as-is)
    pieces.py             # pieces, stages, lineage, time
  explore/
    youtube/              # youtube_api, pipeline, metrics, filters, aggregation
    people.py             # collaborators, podcasts, outlets
  analyse/
    publications.py  sync.py  reports.py
  ui/
    app.py                # st.navigation with the three sections
    client.py             # call(tool, **args) → MCP
    pages/                # library, create asset, worlds, board, piece,
                          # creator search/results/detail, dashboards
migrations/               # Alembic
scripts/wordpress/        # unchanged one-off scripts
data/                     # gitignored: studio.db + img/<world>/<type>/
```

Compose runs two services from one image:

- `mcp`: `studio-server` on :8765, data mounted read-write.
- `ui`: Streamlit on :8501, data mounted read-only, `STUDIO_MCP_URL=http://mcp:8765/mcp`.

## Data model

| Table | Key columns |
|---|---|
| `piece` | id, title, format (blog/video/short/podcast/newsletter/post), stage, parent_id → piece, notes, created_at, published_at |
| `stage_event` | piece_id, stage, entered_at, left_at, minutes |
| `world` | id, name, slug |
| `asset` | id, world_id, type (character/object/location/scene/other), name, style, provider, generation_uid, path (relative to `DATA_DIR`), created_at |
| `piece_asset` | piece_id, asset_id, role |
| `person` | id, name, kind (creator/podcast/guest/outlet), links, notes, source (e.g. YouTube channel id) |
| `piece_person` | piece_id, person_id, role (guest, collaborator, host) |
| `publication` | id, piece_id, channel (blog/youtube/newsletter/linkedin/…), url, external_id, published_at |
| `metric_snapshot` | publication_id, date, views, likes, comments, clicks, signups, raw JSON |

The stages mirror today's Brand board: `idea → draft → assets → edit → review →
published`. *Repurpose* stops being a stage and becomes child pieces. Lead time
(idea → published) and touch time (sum of minutes) come straight from
`stage_event`.

## MCP tools (v1)

- **Assets:** `list_assets(world, type, style, provider, limit, cursor)`,
  `get_asset`, `start_generation(...)` → job id, `get_job`, `move_asset`,
  `copy_asset`, `delete_asset`, `list_worlds`, `create_world`, `rename_world`,
  `delete_world`
- **Pieces:** `create_piece(title, format, parent_id?, created_at?)`,
  `move_piece(id, stage, minutes?, at?)`, `log_time`, `list_pieces(stage, format,
  limit, cursor)`, `get_piece` (with assets, people, children, publications,
  timing), `link_asset`, `link_person`
- **Explore:** `search_creators(keyword, view_range, subscriber_range,
  activity_days)`, `get_creator`, `save_person`, `list_people`
- **Analyse:** `add_publication`, `sync_metrics`, `report(period)`

Optional timestamps (`created_at`, `at`) exist so the Todoist history can be
backfilled later through Claude, without an import script.

## Phases

### Phase 0: one package, one app (no behavior change)

1. Add `pyproject.toml` + `uv.lock` (Python 3.12) with an entry point for the
   server, and remove the three `requirements.txt` files.
2. Move the code into `src/studio/` as laid out above, fixing imports.
   `wordpress/` → `scripts/wordpress/` untouched.
3. One Streamlit app with `st.navigation` sections: Explore (creator
   discovery), Create (library, create, worlds), Analyse (placeholder).
4. Merge the `.env` files into one root `.env.example`. Move `img/` under
   `data/img/`.
5. Add `Dockerfile` and `compose.yaml` (UI only at this point).
6. Update `CLAUDE.md` and the READMEs.

**Done when:** both existing tools work exactly as before from
`docker compose up` and from `uv run streamlit run src/studio/ui/app.py`.

### Phase 1: database + MCP backend, starting with assets

1. `config.py`, `db.py`, `models.py`, and an Alembic baseline (`world`, `asset`).
2. `storage.py` becomes the only place that touches files.
3. Index the existing `img/` tree into `asset` and `world` (filename parse from
   `shared/library.py`), run once on startup and idempotent.
4. `server.py` with the asset and world tools. The background generation runner
   (today's `shared/jobs.py`) moves into the server.
5. `ui/client.py`. The library, create and worlds pages switch to MCP calls,
   and the UI mounts `data/` read-only.
6. Add the `mcp` service to Compose and document `claude mcp add --transport http
   studio http://localhost:8765/mcp`.
7. Tests: pytest using FastMCP's in-memory `Client` against a temporary
   database.

**Done when:** the asset library works through the MCP, and Claude can generate
and list assets.

### Phase 2: pieces (the Create system of record)

1. Migration: `piece`, `stage_event`, `piece_asset`.
2. Piece tools.
3. UI: a **Board** (columns per stage, move with time logged) and a **Piece**
   detail page (assets gallery, children, timeline, minutes per stage).
4. Asset generation accepts `piece_id`, and the library can filter by piece.

**Done when:** a new idea can be carried idea → published in the studio alone,
with lead and touch time visible.

### Phase 3: Explore on the backend

1. Migration: `person`, `piece_person`.
2. Creator search and detail tools. Search results stay transient; only saved
   creators become `person` rows.
3. The YouTube pages switch to MCP calls, with a "save as person" action and a
   **People** gallery.

**Done when:** "find collaborators → save → start a piece with them" works from
both Claude and the UI.

### Phase 4: Analyse

1. Migration: `publication`, `metric_snapshot`.
2. `sync_metrics` covers the YouTube Data API (own channel), the Buffer API
   (post metrics) and the Brevo API (list growth, campaign stats). It runs in
   the server, triggered from the UI or by Claude.
3. Dashboards: lead and touch time per piece and format, performance per
   publication, and repurpose candidates (top performers with no children).

**Done when:** a single page answers what worked, how long it took, and what to
repurpose next.

## Open questions

- **Brevo attribution:** per-piece signups need UTM tags plus a hidden form field
  (or site analytics). Where is the signup form, and is there site analytics on
  marianoog.com?
- **The name** for `studio`.
- **Whether `scripts/wordpress/`** ever becomes a tool or stays a one-off.
