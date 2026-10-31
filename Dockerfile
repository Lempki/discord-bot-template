# The uv stage only supplies the uv binary. A named stage lets Dependabot keep its tag current.
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.14-slim
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
# While connected to Discord, the bot refreshes /tmp/bot-healthy every 30 seconds.
# A file older than 90 seconds, or none at all, marks the container unhealthy.
# Checks run every 5 seconds while the bot starts, so the run script sees it ready quickly.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=5s --retries=3 \
    CMD ["python", "-c", "import os, sys, time; sys.exit(time.time() - os.path.getmtime('/tmp/bot-healthy') > 90)"]
CMD ["python", "bot.py"]
