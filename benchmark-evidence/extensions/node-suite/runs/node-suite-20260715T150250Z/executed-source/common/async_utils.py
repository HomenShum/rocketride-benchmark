"""Bounded async transport helpers for intentional hard-failure cases."""

from __future__ import annotations

import asyncio
from typing import Any


async def send_with_timeout(
    client: Any,
    token: str,
    payload: str,
    *,
    objinfo: dict[str, str],
    mimetype: str,
    timeout_seconds: float,
) -> Any:
    return await asyncio.wait_for(
        client.send(token, payload, objinfo=objinfo, mimetype=mimetype),
        timeout=timeout_seconds,
    )


async def close_warm_pool(pool: Any, *, timeout_seconds: float) -> None:
    async def close(client: Any, token: str) -> None:
        try:
            await asyncio.wait_for(client.terminate(token), timeout=timeout_seconds)
        except Exception:
            pass
        try:
            detach = getattr(client, "detach", None)
            close_transport = detach if callable(detach) else client.disconnect
            await asyncio.wait_for(close_transport(), timeout=timeout_seconds)
        except Exception:
            pass

    await asyncio.gather(
        *(close(client, token) for client, token in zip(pool.clients, pool.tokens))
    )
