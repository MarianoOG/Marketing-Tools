# Plan: one backend, one frontend

This plan moves the two existing tools, **Creator Discovery** (`youtube/`) and
the **Asset Generation Studio** (`asset_generation/`), into one structure that
can grow later:

- **backend**: an MCP server. It holds all the logic and is the only thing
  that writes data.
- **frontend**: one Streamlit UI that talks to the backend through MCP.

It adds no new features. Everything that works today keeps working the same way.
The only change is where the code lives and how its parts talk to each other.

## Principles

- **The backend is the only writer.** Claude (Code/Desktop) and the frontend
  are both MCP clients. The frontend never touches the database. There is no CLI.
- **The frontend reads files read-only.** Images stay on disk. Tools return
  paths, and the frontend mounts the data folder `:ro`. Uploads go to tools as
  base64.
- **Local first.** `docker compose up` or `uv run`. No hosting or auth. The
  database URL comes from the environment and file access goes through one
  module, so a later move to the cloud stays a config change.

## Decisions

| Topic | Decision |
|---|---|
| Naming | `backend/` and `frontend/`. Not `mcp/`, because a top-level package with that name would shadow the `mcp` library that FastMCP depends on. In Claude the server is registered as `marketing-tools`. |
| Packaging | One `pyproject.toml` + `uv.lock` and one Docker image, run through Compose. The `requirements.txt` files of `youtube/` and `asset_generation/` go away. |
| Frontend | Streamlit, with `st.navigation` sections. Explore holds Creator Discovery; Create holds the asset library, the generation form and worlds. A section appears only once it has a tool. |
| Database | SQLite (WAL) through SQLAlchemy, with Alembic migrations. It holds only what exists today: worlds and assets. The images themselves stay on disk. |
| MCP | FastMCP over streamable HTTP, with plain tools. |
| WordPress | `wordpress/` stays where it is, untouched and outside the structure. |

## Target layout

```text
pyproject.toml  uv.lock  Dockerfile  compose.yaml  .env.example
backend/                  # MCP server, the only writer
  server.py               # FastMCP app: registers the tools below
  config.py               # env: DATABASE_URL, DATA_DIR, API keys
  db.py  models.py        # SQLAlchemy engine + world/asset tables
  storage.py              # save / open / path_for (the only file I/O)
  assets/                 # generation.py, prompt_manager.py, worlds, library, jobs
  youtube/                # youtube_api, pipeline, metrics, filters, aggregation, sorting, config
frontend/                 # Streamlit, MCP client, data mounted read-only
  app.py                  # st.navigation: Explore, Create
  client.py               # call(tool, **args) → backend
  pages/                  # today's pages: search, results, creator,
                          # library, create, worlds
migrations/               # Alembic
tests/
wordpress/                # untouched, outside the structure
data/                     # gitignored: app.db + img/<world>/<type>/
```

Compose runs two services from one image:

- `backend` on :8765, data mounted read-write.
- `frontend` (Streamlit) on :8501, data mounted read-only, `BACKEND_URL=http://backend:8765/mcp`.

## Data model

| Table | Columns |
|---|---|
| `world` | id, name, slug |
| `asset` | id, world_id, type (character/object/location/scene), name, style, provider, generation_uid, path (relative to `DATA_DIR`), created_at |

That's everything the filename and folder already encode today, moved into
rows. The filename convention stays, so files remain readable without the
database.

## MCP tools

Each tool is an existing function, wrapped:

- **Assets:** `list_assets(world, type, style, provider, limit, cursor)`,
  `get_asset`, `start_generation(...)` → job id, `get_job`, `move_asset`,
  `copy_asset`, `delete_asset`
- **Worlds:** `list_worlds`, `create_world`, `rename_world`, `delete_world`
- **YouTube:** `search_creators(keyword, view_range, subscriber_range,
  activity_days)`, `get_creator`. Results stay transient, as they are today.

## Phases

### Phase 0: one package, one app (no behavior change)

1. Add `pyproject.toml` + `uv.lock` (Python 3.12), and remove the
   `requirements.txt` files of `youtube/` and `asset_generation/`.
2. Move the code into `backend/` and `frontend/` as laid out above, fixing
   imports. Until Phase 1, the frontend imports backend modules directly.
3. One Streamlit app with `st.navigation`: Explore (Creator Discovery) and
   Create (library, create, worlds).
4. Merge the two `.env` files into one root `.env.example`. Move `img/` under
   `data/img/`.
5. Add `Dockerfile` and `compose.yaml` (frontend only at this point).
6. Update `CLAUDE.md` and the READMEs.

**Done when:** both tools work exactly as before from `docker compose up` and
from `uv run streamlit run frontend/app.py`.

### Phase 1: backend for assets and worlds

1. `config.py`, `db.py`, `models.py`, and an Alembic baseline (`world`, `asset`).
2. `storage.py` becomes the only place that touches files.
3. Index the existing `img/` tree into `world` and `asset` (the filename parse
   from `library.py`), run once on startup and idempotent.
4. `server.py` with the asset and world tools. The background generation runner
   (`jobs.py`) moves into the backend.
5. `frontend/client.py`. The library, create and worlds pages switch to MCP
   calls, and the frontend mounts `data/` read-only.
6. Add the `backend` service to Compose and document `claude mcp add
   --transport http marketing-tools http://localhost:8765/mcp`.
7. Tests: pytest using FastMCP's in-memory `Client` against a temporary
   database.

**Done when:** the asset pages behave as today but go through the backend, and
Claude can list worlds and assets and generate new ones.

### Phase 2: backend for Creator Discovery

1. `search_creators` and `get_creator` tools wrapping `pipeline.py` and
   `youtube_api.py`.
2. The search, results and creator pages switch to MCP calls.

**Done when:** Creator Discovery behaves as today but goes through the backend,
and Claude can search creators.

## Not in this plan

These came up and were set aside. Each would be its own plan later:

- **Pieces, stages and lineage** (the content system of record). Until they
  exist, the Brand pipeline stays in Todoist.
- **People and outlets** saved from Explore.
- **Analytics and publishing**: Buffer already covers both.
- **WordPress** as a tool.
