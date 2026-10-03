# The uv stage only supplies the uv binary. A named stage lets Dependabot keep its tag current.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

FROM python:3.12-slim
# FFmpeg decodes audio and libopus0 encodes it for Discord voice.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
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
# The database lives in /app/data, which compose mounts as a volume so it survives rebuilds.
RUN mkdir -p /app/data && chown appuser:appuser /app/data
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE_PATH=/app/data/bot.db
USER appuser
CMD ["python", "bot.py"]
