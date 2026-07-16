FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ARG SCBENCH_COMMIT

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/SprocketLab/slop-code-bench.git /opt/scbench \
    && git -C /opt/scbench switch --detach "${SCBENCH_COMMIT}"

WORKDIR /opt/scbench
RUN uv sync --frozen --no-dev

ENV PATH="/opt/scbench/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "slop-code", "--help"]
