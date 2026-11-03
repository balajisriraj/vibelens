FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/app/models
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY vibelens ./vibelens
COPY samples ./samples
COPY evals ./evals
# Bake the embedding and Whisper models into the image so the first upload isn't a download.
RUN uv sync --frozen --no-dev \
 && uv run python -c "from vibelens.embeddings import FastEmbedder; FastEmbedder().embed(['warm up']); from vibelens.sources import _whisper; _whisper('base.en')" \
 && useradd --create-home app && mkdir -p /app/data && chown -R app /app
USER app
VOLUME /app/data
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uv", "run", "--no-sync", "vibelens", "serve", "--host", "0.0.0.0", "--port", "8000"]
