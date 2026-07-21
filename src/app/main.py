from __future__ import annotations

import logging

from app.gateway import AppGateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

gateway = AppGateway()
app = gateway.create_app()


def run() -> None:
    import uvicorn

    settings = gateway.settings
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        ws_max_size=settings.maximum_websocket_message_bytes,
        limit_concurrency=settings.maximum_concurrent_connections,
        proxy_headers=True,
    )


if __name__ == "__main__":
    run()
