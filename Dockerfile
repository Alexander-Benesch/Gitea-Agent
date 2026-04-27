FROM python:3.10-slim AS base
WORKDIR /app
RUN groupadd -r samuel && useradd -r -g samuel samuel

# Dependencies first (cached layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir pydantic ">=2.0,<3"

# Full install with source
COPY . .
RUN pip install --no-cache-dir -e ".[all]" 2>/dev/null || pip install --no-cache-dir .

USER samuel
EXPOSE 7777

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -m samuel health || exit 1

ENTRYPOINT ["python", "-m", "samuel"]
CMD ["watch", "--once"]
