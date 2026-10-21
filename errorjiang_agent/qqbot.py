from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import ssl
import threading
import time
import traceback
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .errors import AgentError
from .onebot import MessageEvent
from .onebot_ws import WS_GUID, _masked_frame, _read_frame


TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = "https://api.sgroup.qq.com"
GROUP_AND_C2C_EVENT = 1 << 25


class _BufferedSocket:
    def __init__(self, sock: ssl.SSLSocket, buffered: bytes = b""):
        self.sock = sock
        self.buffer = bytearray(buffered)

    @property
    def has_buffered(self) -> bool:
        return bool(self.buffer)

    def recv(self, size: int) -> bytes:
        if self.buffer:
            data = bytes(self.buffer[:size])
            del self.buffer[:size]
            return data
        return self.sock.recv(size)

    def sendall(self, data: bytes) -> None:
        self.sock.sendall(data)

    def settimeout(self, value: float | None) -> None:
        self.sock.settimeout(value)

    def close(self) -> None:
        self.sock.close()


def parse_qqbot_event(
    event_type: str,
    payload: dict[str, Any],
    self_id: int | str,
) -> MessageEvent | None:
    if event_type not in ("GROUP_AT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE"):
        return None
    author = payload.get("author") or {}
    message_id = str(payload.get("id") or "").strip()
    if not message_id:
        return None
    text = str(payload.get("content") or "").strip()
    if event_type == "GROUP_AT_MESSAGE_CREATE":
        user_id = str(author.get("member_openid") or "").strip()
        chat_id = str(payload.get("group_openid") or "").strip()
        message_type = "group"
    else:
        user_id = str(author.get("user_openid") or author.get("id") or "").strip()
        chat_id = user_id
        message_type = "private"
    if not user_id or not chat_id:
        return None
    return MessageEvent(
        self_id=self_id,
        user_id=user_id,
        message_type=message_type,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        to_me=True,
        platform="qqbot",
    )


class QQBotClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        bot_qq: str,
        on_event: Callable[[MessageEvent], None],
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_qq = bot_qq
        self.on_event = on_event
        self._stop = threading.Event()
        self._token_lock = threading.Lock()
        self._access_token = ""
        self._token_expires_at = 0.0
        self._reply_lock = threading.Lock()
        self._reply_sequences: dict[str, int] = {}
        self.connected = False
        self.last_error = ""
        self.connected_at = 0

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "connected": self.connected,
            "bot_qq": self.bot_qq,
            "connected_at": self.connected_at,
            "last_error": self.last_error,
        }

    def close(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_once()
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)[:300]
                print(f"[QQBot] 连接中断：{exc}", flush=True)
                traceback.print_exc()
            if self._stop.wait(5):
                break

    def _http_json(
        self,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "ErrorJ-QQBot/1.0",
                **(headers or {}),
            },
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = detail.get("message") or detail.get("error") or exc.reason
            except Exception:
                message = exc.reason
            raise AgentError(f"QQBot HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise AgentError(f"无法连接 QQBot：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AgentError("QQBot 返回了无效 JSON。") from exc

    def _ensure_token(self) -> str:
        with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at - 60:
                return self._access_token
            data = self._http_json(
                TOKEN_URL,
                {
                    "appId": self.app_id,
                    "clientSecret": self.app_secret,
                },
            )
            token = str(data.get("access_token") or "").strip()
            if not token:
                raise AgentError("QQBot 没有返回 access_token。")
            try:
                expires_in = int(data.get("expires_in") or 7200)
            except (TypeError, ValueError):
                expires_in = 7200
            self._access_token = token
            self._token_expires_at = time.time() + max(300, expires_in)
            return token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"QQBot {self._ensure_token()}"}

    def _gateway_url(self) -> str:
        data = self._http_json(
            API_BASE + "/gateway/bot",
            headers=self._auth_headers(),
        )
        url = str(data.get("url") or "").strip()
        if not url:
            raise AgentError("QQBot 没有返回 Gateway 地址。")
        return url

    def _connect_websocket(self, url: str) -> _BufferedSocket:
        parsed = urlsplit(url)
        if parsed.scheme != "wss" or not parsed.hostname:
            raise AgentError("QQBot Gateway 不是有效的 wss:// 地址。")
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        raw_sock = socket.create_connection((parsed.hostname, port), timeout=15)
        context = ssl.create_default_context()
        sock = context.wrap_socket(raw_sock, server_hostname=parsed.hostname)
        sock.settimeout(20)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        host = parsed.hostname if port == 443 else f"{parsed.hostname}:{port}"
        headers = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "User-Agent: ErrorJ-QQBot/1.0",
        ]
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise AgentError("QQBot WebSocket 握手失败。")
            response.extend(chunk)
            if len(response) > 32768:
                sock.close()
                raise AgentError("QQBot WebSocket 握手响应异常。")
        head, _, buffered = bytes(response).partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        if not lines or " 101 " not in lines[0]:
            sock.close()
            raise AgentError(
                f"QQBot WebSocket 握手被拒绝：{lines[0] if lines else 'unknown'}"
            )
        response_headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            response_headers[name.strip().lower()] = value.strip()
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if response_headers.get("sec-websocket-accept") != accept:
            sock.close()
            raise AgentError("QQBot WebSocket 握手校验失败。")
        return _BufferedSocket(sock, buffered)

    @staticmethod
    def _send_frame(sock: _BufferedSocket, payload: dict[str, Any]) -> None:
        sock.sendall(
            _masked_frame(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
        )

    def _run_once(self) -> None:
        token = self._ensure_token()
        sock = self._connect_websocket(self._gateway_url())
        heartbeat_interval = 30.0
        heartbeat_due = time.monotonic() + heartbeat_interval
        last_sequence: int | None = None
        identified = False
        sock.settimeout(None)
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= heartbeat_due:
                    self._send_frame(
                        sock,
                        {"op": 1, "d": last_sequence},
                    )
                    heartbeat_due = now + heartbeat_interval
                if not sock.has_buffered:
                    readable, _, _ = select.select([sock.sock], [], [], 1.0)
                    if not readable:
                        continue
                opcode, fin, data = _read_frame(sock)
                if opcode == 0x9:
                    sock.sendall(_masked_frame(data, opcode=0xA))
                    continue
                if opcode == 0x8:
                    raise AgentError("QQBot WebSocket 已关闭。")
                if opcode not in (0x1, 0x0) or not fin:
                    continue
                try:
                    message = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                op = int(message.get("op") or 0)
                sequence = message.get("s")
                if sequence is not None:
                    last_sequence = int(sequence)
                if op == 10:
                    hello = message.get("d") or {}
                    try:
                        heartbeat_interval = max(
                            5.0,
                            float(hello.get("heartbeat_interval") or 30000)
                            / 1000,
                        )
                    except (TypeError, ValueError):
                        heartbeat_interval = 30.0
                    heartbeat_due = time.monotonic() + heartbeat_interval
                    self._send_frame(
                        sock,
                        {
                            "op": 2,
                            "d": {
                                "token": f"QQBot {token}",
                                "intents": GROUP_AND_C2C_EVENT,
                                "shard": [0, 1],
                                "properties": {
                                    "$os": "linux",
                                    "$browser": "ErrorJ-QQBot",
                                    "$device": "ErrorJ-QQBot",
                                },
                            },
                        },
                    )
                    identified = True
                    continue
                if op == 11:
                    continue
                if op in (7, 9):
                    raise AgentError("QQBot 要求重新建立连接。")
                if op != 0:
                    continue
                event_type = str(message.get("t") or "")
                event_payload = message.get("d") or {}
                if event_type == "READY":
                    self.connected = True
                    self.connected_at = int(time.time())
                    self.last_error = ""
                    print(
                        f"[QQBot] 已连接：{self.bot_qq or self.app_id}",
                        flush=True,
                    )
                    continue
                if not identified:
                    continue
                event = parse_qqbot_event(
                    event_type,
                    event_payload,
                    self.bot_qq or self.app_id,
                )
                if event:
                    try:
                        self.on_event(event)
                    except Exception:
                        traceback.print_exc()
        finally:
            self.connected = False
            try:
                sock.sendall(_masked_frame(b"", opcode=0x8))
            except OSError:
                pass
            sock.close()

    def send_message(
        self,
        message_type: str,
        chat_id: str,
        message_id: str,
        content: str,
    ) -> None:
        target = "groups" if message_type == "group" else "users"
        with self._reply_lock:
            sequence = self._reply_sequences.get(message_id, 0) + 1
            self._reply_sequences[message_id] = sequence
            if len(self._reply_sequences) > 2000:
                self._reply_sequences.clear()
                self._reply_sequences[message_id] = sequence
        self._http_json(
            f"{API_BASE}/v2/{target}/{quote(str(chat_id))}/messages",
            {
                "content": str(content or "")[:1800],
                "msg_type": 0,
                "msg_id": str(message_id),
                "msg_seq": sequence,
            },
            headers=self._auth_headers(),
        )
