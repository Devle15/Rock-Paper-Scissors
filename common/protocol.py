"""JSON-line protocol helpers (Python 3).

Each message is one JSON object per line (\n).
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ProtocolError(Exception):
    pass


@dataclass
class JsonLineSocket:
    sock: socket.socket
    buffer: bytearray = field(default_factory=bytearray)

    def send(self, msg: Dict[str, Any]) -> None:
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        self.sock.sendall(data)

    def recv(self, *, max_bytes: int = 65536) -> Optional[Dict[str, Any]]:
        """Return next message dict; None if socket closed cleanly."""
        while True:
            nl = self.buffer.find(b"\n")
            if nl != -1:
                line = self.buffer[:nl]
                del self.buffer[: nl + 1]
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except Exception as e:
                    raise ProtocolError(f"Invalid JSON: {e}")

            chunk = self.sock.recv(4096)
            if not chunk:
                return None
            self.buffer.extend(chunk)
            if len(self.buffer) > max_bytes:
                raise ProtocolError("Message too large")


def safe_close(s: socket.socket) -> None:
    try:
        s.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        s.close()
    except Exception:
        pass
