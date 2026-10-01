# Marketing Tools

Tools for finding collaborators and creating content assets, in two parts:

- **backend**: an MCP server. It holds the logic and is the only thing that
  writes data. Claude connects to it directly.
- **frontend**: one Streamlit app that talks to the backend through MCP. It
  reads images from the data folder but never changes them.

| Section | Tool | What it does |
|---|---|---|
| Explore | [Creator Discovery](backend/youtube/README.md) | Find YouTube creators to collaborate with |
| Create | [Asset Generation](backend/assets/README.md) | Generate characters, objects, locations and scenes with OpenAI + Gemini, organised in worlds |

## Setup

Copy `.env.example` to `.env` and fill in the keys you need:

```env
GEMINI_API_KEY=...    # asset generation
OPENAI_API_KEY=...    # asset generation
YOUTUBE_API_KEY=...   # creator discovery
```

Generated images live in `data/img/` (gitignored).

## Run with Docker

```bash
docker compose up --build
```

The frontend is at <http://localhost:8501> and the backend at
`http://localhost:8765/mcp`.

## Run with uv

```bash
uv sync
uv run backend                              # terminal 1
uv run streamlit run frontend/app.py        # terminal 2
```

## Connect Claude

With the backend running:

```bash
claude mcp add --transport http marketing-tools http://localhost:8765/mcp
```

Claude can then list and generate assets, manage worlds and search creators.
Generations run in the background: `start_generation` returns a job id that
`get_job` reports on.

## Layout

```text
backend/
  server.py        # MCP tools, the only writer
  config.py        # .env, DATA_DIR, host/port
  assets/          # generation, prompts, worlds, library, jobs
  youtube/         # YouTube API, search pipeline, metrics, filters
frontend/
  app.py           # navigation: Explore, Create
  client.py        # call(tool, **args) -> backend
  pages/           # one file per page
tests/             # backend tools through an in-memory MCP client
wordpress/         # standalone scripts, outside the app
```

## Tests

```bash
uv run pytest
```

The tests replace the image and YouTube providers with fakes, so they need no
API keys and cost nothing.

## Moving from the old layout

If you used `asset_generation/` or `youtube/` before:

```bash
mkdir -p data && mv asset_generation/img data/img
```

Then merge the keys from `asset_generation/.env` and `youtube/.env` into the
root `.env`, and delete the old folders.
