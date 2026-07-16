"""Module 11: WebSocket Client.

Resilient async WS client for ``/api/ws/agent``. Exponential backoff
reconnect (cap 30s), ping/pong keepalive, auth via query string.

Public API:
    class WSClient(url, api_key, on_message)
        async run() -> None
        async send_json(dict) -> bool
        stop() -> None
        @property state, last_error, connected
"""
from .client import WSClient  # noqa: F401

__all__ = ["WSClient"]
