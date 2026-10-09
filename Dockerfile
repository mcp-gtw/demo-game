FROM node:24-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS client
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY client ./
RUN npm run build

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
WORKDIR /build
RUN pip install --no-cache-dir --upgrade pip==26.2.1 uv==0.12.24
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --from=client /src/app/web/dist ./src/app/web/dist
RUN uv export --frozen --no-dev --no-emit-project \
    --output-file requirements.txt && uv build --wheel

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GATEWAY_HOST=0.0.0.0
WORKDIR /srv
COPY --from=build /build/requirements.txt /tmp/requirements.txt
COPY --from=build /build/dist /tmp/wheels
RUN pip install --no-cache-dir --upgrade pip==26.2.1 \
    && pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps /tmp/wheels/*.whl \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && groupadd --gid 10001 game \
    && useradd --uid 10001 --gid game --no-create-home game \
    && mkdir /data && chown game:game /data
USER game
EXPOSE 8000
CMD ["python", "-m", "app.main"]
