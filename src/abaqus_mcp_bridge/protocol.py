"""Shared line-delimited JSON protocol helpers."""

from __future__ import annotations

import json
import socket
from typing import Any


class ProtocolError(RuntimeError):
    """Raised when the bridge protocol receives malformed data."""


def send_message(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")


def read_message(sock: socket.socket, max_bytes: int = 16 * 1024 * 1024) -> dict[str, Any]:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise ProtocolError("socket closed before a complete message was received")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ProtocolError(f"message exceeded {max_bytes} bytes")

    try:
        message = json.loads(b"".join(chunks).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON message: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("protocol message must be a JSON object")
    return message
