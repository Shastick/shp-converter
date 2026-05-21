FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shp_converter/ shp_converter/

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "shp2geojson"]
