"""
edge-tts — Microsoft zh-HK-HiuMaanNeural (Chinese Hong Kong HiuMaan).
GET/POST /api/tts?text=...  → audio/mpeg
On failure: 204 (client stays silent; no Mandarin speechSynthesis fallback).
"""
from __future__ import annotations

import asyncio
import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote_plus, urlparse

import edge_tts

VOICE = "zh-HK-HiuMaanNeural"
RATE = "-12%"
MAX_LEN = 180


def _clean_text(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    return text[:MAX_LEN]


async def _synth(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003 — quieter serverless logs
        return

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_HEAD(self):  # noqa: N802
        # Probes (curl -I) should not 501; body omitted.
        qs = parse_qs(urlparse(self.path).query)
        text = _clean_text(qs.get("text", [""])[0])
        if not text:
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("X-TTS-Voice", VOICE)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        qs = parse_qs(urlparse(self.path).query)
        text = _clean_text(qs.get("text", [""])[0])
        self._respond(text)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        text = ""
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
                if isinstance(body, dict) and body.get("text") is not None:
                    text = str(body["text"])
                else:
                    text = raw.decode("utf-8", errors="ignore")
            except Exception:
                text = raw.decode("utf-8", errors="ignore")
        if not text:
            qs = parse_qs(urlparse(self.path).query)
            text = qs.get("text", [""])[0]
        self._respond(_clean_text(unquote_plus(text)))

    def _respond(self, text: str) -> None:
        if not text:
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        try:
            audio = asyncio.run(_synth(text))
        except Exception:
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        if not audio:
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("X-TTS-Voice", VOICE)
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)
