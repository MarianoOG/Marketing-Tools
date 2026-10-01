FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.8.17

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend backend
COPY frontend frontend
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data
