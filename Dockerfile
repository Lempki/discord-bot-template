# The uv stage only supplies the uv binary. A named stage lets Dependabot keep its tag current.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsodium-dev \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home appuser
WORKDIR /app

# Dependencies are installed before the source is copied, so code changes reuse the cached layer.
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY . .
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
CMD ["python", "bot.py"]
