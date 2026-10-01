# Marketing Tools

Creator discovery and asset generation behind one MCP backend and one
Streamlit frontend. See `README.md` for setup and `PLAN.md` for direction.

## Architecture

- **`backend/`** is a FastMCP server (`backend/server.py`) and the only thing
  that writes to `DATA_DIR`. Each tool is a thin wrapper over a function in
  `backend/assets/` or `backend/youtube/`. Keep logic in those modules, not in
  the tools.
- **`frontend/`** is one Streamlit app (`frontend/app.py`) with sections
  Explore and Create. Pages change things only through
  `frontend.client.call(tool, **args)`. They may import pure constants and
  helpers from `backend` (styles, presets, formatters, filters), never anything
  that does I/O. Images are read from the data folder, mounted read-only in
  Docker.
- Asset paths cross the wire relative to `DATA_DIR` (`img/<world>/<type>/<file>`).
- `wordpress/` is standalone and outside the app.

```text
backend/
  server.py, config.py
  assets/      # generation, prompt_manager, worlds, library, jobs
  youtube/     # youtube_api, pipeline, metrics, filters, aggregation, sorting, config
frontend/
  app.py, client.py, state.py, assets.py, youtube_components.py
  pages/       # explore_*.py, create_*.py
tests/
```

## Environment

Dependencies are managed with uv (`pyproject.toml` + `uv.lock`). Python 3.12.

```bash
uv sync
uv run backend                          # MCP server on :8765
uv run streamlit run frontend/app.py    # UI on :8501
uv run pytest                           # backend tests, no API keys needed
docker compose up --build               # both, in containers
```

## Workflow Guidelines

- **New tool:** add the logic under `backend/`, a tool in `backend/server.py`,
  a test in `tests/`, and a page in `frontend/pages/` registered in
  `frontend/app.py`.
- **After code changes:** check whether the relevant README needs updating.
  Keep documentation general to minimize future edits.
- **API keys:** live in the root `.env`. Never commit `.env` files or expose
  API keys.
- **Dependencies:** `uv add <package>`. Never edit `uv.lock` by hand.

## Code Style

- Use type hints for function signatures
- Keep functions focused and single-purpose
- Follow existing patterns in each module
