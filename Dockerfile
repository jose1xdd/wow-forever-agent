FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/model-cache \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

WORKDIR /app

# CPU-only PyTorch: do not pull CUDA runtimes for a local embedding model.
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1+cpu"

ENV WOW_PROJECT_ROOT=/app

# Keep third-party dependencies in a layer that survives edits to Python code.
COPY pyproject.toml ./
RUN python -c "import subprocess,sys,tomllib; deps=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir',*deps])"

COPY README.md alembic.ini ./
COPY src/ ./src/
COPY config/ ./config/
RUN python -m pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 wow \
    && mkdir -p /model-cache \
    && chown -R wow:wow /app /model-cache

USER wow

# No HTTP port: OpenCode owns this process and talks to it over STDIO.
CMD ["python", "-m", "wow_knowledge.mcp_server"]
