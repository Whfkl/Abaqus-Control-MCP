"""Client used by the MCP server to call the Abaqus-side socket agent."""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from typing import Any

from .protocol import read_message, send_message


@dataclass(frozen=True)
class AbaqusBridgeClient:
    host: str = "127.0.0.1"
    port: int = 48152
    timeout: float = 60.0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params.setdefault("timeout", self.timeout)
        payload = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": request_params,
        }
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            send_message(sock, payload)
            response = read_message(sock)

        if response.get("id") != payload["id"]:
            raise RuntimeError("Abaqus agent returned a mismatched response id")
        if not response.get("ok", False):
            error = response.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(message or "Abaqus agent returned an error")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Abaqus agent returned an invalid result envelope")
        return result

    def ping(self) -> dict[str, Any]:
        return self.request("ping")

    def execute(self, code: str) -> dict[str, Any]:
        return self.request("execute", {"code": code})
