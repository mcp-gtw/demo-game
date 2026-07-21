# build the client bundle into src/app/web/dist
FROM node:22-slim AS client
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY client ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GATEWAY_HOST=0.0.0.0

WORKDIR /srv

# requires mcp-gtw to be resolvable from the index (e.g. published to PyPI)
COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=client /src/app/web/dist ./src/app/web/dist

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "app.main"]
