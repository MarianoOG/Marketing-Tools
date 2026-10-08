# Marketing Tools

Marketing automation tools behind one UI:

- **Assets** — generate characters, objects, locations and scenes with OpenAI and
  Gemini, and organise them into worlds. See `backend/app/assets/README.md`.
- **YouTube** — Creator Discovery, to find creators for partnerships. See
  `backend/app/youtube/README.md`.
- **WordPress** — classify a site's posts with an LLM and write categories back.

## Architecture

Two services that share one `data/` folder:

| Service | What it does | `data/` access |
| --- | --- | --- |
| `backend/` (FastAPI) | All the logic: API calls, generation, files | read and write |
| `frontend/` (Streamlit) | The UI, calling the backend over HTTP | read-only |

The backend returns file paths relative to `data/`, and the frontend opens them
from its own read-only mount. Long work (image renders, YouTube searches,
WordPress runs) runs as background jobs in the backend, so leaving a page never
cancels it. API docs, grouped by tag, are at http://localhost:8000/docs.

## Run with Docker

```bash
cp backend/.env.example backend/.env   # then fill in the keys you need
docker compose up --build
```

The UI is at http://localhost:8501. Both ports are bound to localhost only,
because neither service has authentication and both can spend API credits.

Stopping the stack waits up to three minutes for in-flight renders, so paid
images are not lost.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt

cd backend && uvicorn app.main:app --reload   # terminal 1
cd frontend && streamlit run app.py           # terminal 2
```

Run the backend as a single process (no `--workers`): background jobs are held
in its memory.
