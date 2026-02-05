# Marketing Tools

A collection of marketing automation tools. Each subdirectory is a standalone project.

## Project Structure

```
Marketing Tools/
├── youtube/          # Creator Discovery - Find YouTube creators for partnerships
│   ├── Home.py           # Main entry point (search page)
│   ├── pages/            # Multi-page Streamlit pages
│   │   ├── 1_Results.py  # Search results with filters
│   │   └── 2_Creator.py  # Creator detail view
│   ├── shared/           # Shared components
│   │   ├── state.py      # Session state management
│   │   └── components.py # Reusable UI components
│   ├── youtube_api.py    # YouTube Data API integration
│   ├── metrics.py        # Performance metric calculations
│   ├── filters.py        # Search filtering logic
│   ├── aggregation.py    # Data aggregation
│   ├── sorting.py        # Result sorting
│   ├── pipeline.py       # Data processing pipeline
│   ├── config.py         # Configuration
│   └── .env              # API keys (YOUTUBE_API_KEY)
└── .venv/            # Shared Python 3.12 virtual environment
```

## Environment

Always activate the virtual environment before running or testing Python code:

```bash
source .venv/bin/activate
```

## Running Apps

**YouTube Creator Discovery:**
```bash
cd youtube && streamlit run Home.py
```

## Workflow Guidelines

- **Before running Python:** Always activate `.venv` first
- **After code changes:** Check if the relevant README.md needs updating. Keep documentation general to minimize future edits
- **API keys:** Never commit `.env` files or expose API keys
- **Dependencies:** Add new packages to the project's `requirements.txt`

## Code Style

- Use type hints for function signatures
- Keep functions focused and single-purpose
- Follow existing patterns in each project