# metrics-service/Dockerfile
# FastAPI metrics service — containerized with uv.

FROM python:3.11-slim

# uv: fast Python package manager (matches the project's uv.lock).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (layer caching: deps change less often than code).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy the application code.
COPY app ./app
COPY metrics ./metrics
COPY data_quality ./data_quality

# uv put the venv at /app/.venv; put it on PATH so `uvicorn` resolves.
ENV PATH="/app/.venv/bin:$PATH"

# The service listens on 8000. Container Apps will route to this.
EXPOSE 8000

# 0.0.0.0 so the container accepts external connections (not just localhost).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
