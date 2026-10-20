from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
from typing import Any
from urllib.parse import urlsplit

from .errors import AgentError


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise AgentError("NapCat WebSocket 连接已关闭。")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _masked_frame(payload: bytes, opcode: int = 1) -> bytes:
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    mask = os.urandom(4)
    header.extend(mask)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes(header) + masked


def _read_frame(sock: socket.socket) -> tuple[int, bool, bytes]:
    first, second = _recv_exact(sock, 2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    if length > 8 * 1024 * 1024:
        raise AgentError("NapCat WebSocket 消息过大。")
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length)
    if masked:
        payload = bytes(
            value ^ mask[index % 4] for index, value in enumerate(payload)
        )
    return opcode, fin, payload


class OneBotWebSocketClient:
    def __init__(self, url: str, access_token: str = ""):
        self.url = url
        self.access_token = access_token

    def _connect(self) -> socket.socket:
        parsed = urlsplit(self.url)
        if parsed.scheme != "ws" or not parsed.hostname:
            raise AgentError("目前只支持 ws:// 形式的 NapCat OneBot 地址。")
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        sock = socket.create_connection((parsed.hostname, port), timeout=15)
        sock.settimeout(20)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        headers = [
            f"GET {path} HTTP/1.1",
            f"Host: {parsed.hostname}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        if self.access_token:
            headers.append(f"Authorization: Bearer {self.access_token}")
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise AgentError("NapCat WebSocket 握手失败。")
            response.extend(chunk)
            if len(response) > 32768:
                sock.close()
                raise AgentError("NapCat WebSocket 握手响应异常。")
        head, _, buffered = bytes(response).partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        if not lines or " 101 " not in lines[0]:
            sock.close()
            raise AgentError(f"NapCat WebSocket 握手被拒绝：{lines[0] if lines else 'unknown'}")
        response_headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            response_headers[name.strip().lower()] = value.strip()
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if response_headers.get("sec-websocket-accept") != accept:
            sock.close()
            raise AgentError("NapCat WebSocket 握手校验失败。")
        if buffered:
            # This runtime only sends an action after connecting, so an unsolicited
            # first frame is not needed for the response correlation.
            pass
        return sock

    def call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        echo = f"errorjiang-{os.getpid()}-{time.time_ns()}"
        payload = json.dumps(
            {"action": action, "params": params, "echo": echo},
            ensure_ascii=False,
        ).encode("utf-8")
        sock = self._connect()
        fragments = bytearray()
        try:
            sock.sendall(_masked_frame(payload))
            while True:
                opcode, fin, data = _read_frame(sock)
                if opcode == 0x9:
                    sock.sendall(_masked_frame(data, opcode=0xA))
                    continue
                if opcode == 0x8:
                    raise AgentError("NapCat WebSocket 提前关闭。")
                if opcode in (0x1, 0x0):
                    fragments.extend(data)
                    if not fin:
                        continue
                    try:
                        message = json.loads(fragments.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        fragments.clear()
                        continue
                    fragments.clear()
                    if str(message.get("echo") or "") != echo:
                        continue
                    if message.get("status") == "failed":
                        error = message.get("message") or message.get("wording")
                        raise AgentError(str(error or "NapCat 操作失败。"))
                    result = message.get("data")
                    return result if isinstance(result, dict) else {"data": result}
        finally:
            try:
                sock.sendall(_masked_frame(b"", opcode=0x8))
            except OSError:
                pass
            sock.close()
