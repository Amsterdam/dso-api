FROM ghcr.io/astral-sh/uv:0.10-python3.14-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN apt update && apt install --no-install-recommends -y \
    build-essential \
    tree

WORKDIR /app
COPY ./pyproject.toml ./uv.lock ./README.md ./

RUN uv sync --frozen --no-install-project --all-groups
COPY /src /app/src

RUN uv sync --frozen --all-groups

# Start runtime image,
FROM ghcr.io/astral-sh/uv:0.10-python3.14-trixie-slim

# Create user integration_tests with the same UID as github actions runner.
RUN groupadd --system --gid 999  integration_tests  && useradd --system --gid 999 \
    --uid 1001 --create-home integration_tests
RUN apt update && apt install --no-install-recommends -y \
    curl

WORKDIR /app
# Copy python build artifacts from builder image
RUN chown integration_tests:integration_tests /app
COPY --from=builder --chown=integration_tests:integration_tests /app /app
USER integration_tests

ENTRYPOINT ["uv", "run", "dso-test"]
