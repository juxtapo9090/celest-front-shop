#!/usr/bin/env python3
"""HTTP server for the KrakedDev Arena. Serves this directory and, in the same
process, answers the room's live endpoints — so the page and the relay are one
origin and nothing is ever blocked as mixed content. Reads $PORT when hosted.

Also accepts POST /__shot with a PNG data URL and writes it to shot.png. The page
is often open in a background tab, where the browser pauses requestAnimationFrame —
so the only way to actually look at the game from outside is to ask the page to step
a frame and hand the canvas back. Loopback only; see the handler.

And it carries the live tool feed:

  POST /event    one tool call, JSON {"seat", "tool", "ok"}   — from the hook
  GET  /events?since=<id>    everything newer than <id>       — from the page
  POST /chat     one visitor line, JSON {"name", "text"}      — from the page
  GET  /chat?since=<id>      everything newer than <id>       — from the page
  POST /pos      where one visitor is standing               — from the page
  GET  /peers?me=<id>        everyone else standing there    — from the page

The ring is in memory on purpose. This is a window onto what is happening right
now; a tool call nobody was watching is not worth a file on disk. The visitor
table is the same idea taken further: it has no history at all, only a present.
"""

import http.server
import socketserver
import json
import os
import base64
import threading
import time

PORT = int(os.environ.get("PORT", 8960))
RING_MAX = 500

# 🔴 Am I hosted? mojave hands a service its port in $PORT, so the answer is
# already in the environment and nothing new has to be configured or remembered.
# It matters because the page asks: a hosted room must NEVER run the simulated
# ticker, which invents tool calls under real people's names. Getting this
# wrong in the safe direction costs a quiet room; getting it wrong the other way
# publishes a lie with Fable's name on it.
HOSTED = "PORT" in os.environ

os.chdir(os.path.dirname(os.path.abspath(__file__)))

_lock = threading.Lock()
_ring = []          # [{id, seat, tool, ok, ts}]
_next_id = 1

CHAT_MAX = 200
NAME_MAX = 24
TEXT_MAX = 240
_chat_lock = threading.Lock()
_chat = []          # [{id, name, text, ts}]
_chat_next_id = 1


def say(name, text):
    global _chat_next_id
    with _chat_lock:
        msg = {"id": _chat_next_id, "name": name, "text": text, "ts": time.time()}
        _chat_next_id += 1
        _chat.append(msg)
        if len(_chat) > CHAT_MAX:
            del _chat[:-CHAT_MAX]
        return msg


def chat_since(marker):
    with _chat_lock:
        return [m for m in _chat if m["id"] > marker], _chat_next_id - 1


# ---------------------------------------------------------------
# The visitor table — where everybody is standing, right now.
#
# It is a dict keyed by a browser-chosen id, not a log, and it has no history:
# a visitor who stops posting simply falls out of it after PEER_TTL. That is the
# whole disconnect story — no goodbye message, no socket to notice closing, no
# ghost left standing in the room when a laptop lid shuts. The cost is that a
# body lingers for a few seconds after someone leaves, which reads as them
# walking out rather than as a bug.
# ---------------------------------------------------------------
PEER_TTL = 6.0        # seconds of silence before a visitor is gone
PEER_MAX = 48         # a room, not a stadium
FACINGS = ("up", "down", "left", "right")

_peers_lock = threading.Lock()
_peers = {}           # id -> {id, name, body, x, y, facing, moving, room, say, ts}


def place(d):
    """Record one visitor's position. Returns None if the room is full."""
    now = time.time()
    pid = str(d.get("id", "")).strip()[:32]
    facing = str(d.get("facing", "down"))
    rec = {
        "id": pid,
        "name": str(d.get("name", "")).strip()[:NAME_MAX] or "visitor",
        "body": "f" if str(d.get("body", "m")) == "f" else "m",
        "x": round(float(d.get("x", 0)), 2),
        "y": round(float(d.get("y", 0)), 2),
        "facing": facing if facing in FACINGS else "down",
        "moving": bool(d.get("moving")),
        # Which room they are standing in. The page filters on it — two visitors
        # in different rooms should not haunt each other's map.
        "room": "lake" if str(d.get("room", "office")) == "lake" else "office",
        "say": str(d.get("say") or "").strip()[:TEXT_MAX],
        "ts": now,
    }
    with _peers_lock:
        for k in [k for k, v in _peers.items() if now - v["ts"] > PEER_TTL]:
            del _peers[k]
        if pid not in _peers and len(_peers) >= PEER_MAX:
            return None
        _peers[pid] = rec
        return rec


def peers_except(me):
    now = time.time()
    with _peers_lock:
        return [v for v in _peers.values()
                if v["id"] != me and now - v["ts"] <= PEER_TTL]


# The house token total, replaced wholesale by whichever reader is running.# The arena cannot compute this itself — a PostToolUse hook carries no usage
# numbers and has no time to go looking — so it is posted in from outside, the
# same split as Jaga: a local shortcut, never the shipping lane. A stranger
# running the arena just gets a blank whiteboard, which is honest.
_tokens = {"total": 0, "cost": 0.0, "seats": {}, "ts": 0}


def record(seat, tool, ok):
    global _next_id
    with _lock:
        ev = {"id": _next_id, "seat": seat, "tool": tool,
              "ok": bool(ok), "ts": time.time()}
        _next_id += 1
        _ring.append(ev)
        if len(_ring) > RING_MAX:
            del _ring[:-RING_MAX]
        return ev


def since(marker):
    with _lock:
        return [e for e in _ring if e["id"] > marker], _next_id - 1


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass    # the feed polls constantly; the access log is just noise

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        # The relay is meant to be called from a page that may not be served by
        # this box at all (GitHub Pages, or a copy on someone's laptop), so the
        # API is open by origin. There is nothing private behind it — it holds
        # where cartoon people are standing.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _query(self, key):
        if key + "=" not in self.path:
            return ""
        return self.path.split(key + "=", 1)[1].split("&")[0]

    def do_GET(self):
        if self.path.startswith("/events"):
            marker = 0
            if "since=" in self.path:
                try:
                    marker = int(self.path.split("since=", 1)[1].split("&")[0])
                except ValueError:
                    marker = 0
            events, latest = since(marker)
            self._json({"next": latest, "events": events, "hosted": HOSTED})
            return
        if self.path.startswith("/chat"):
            # Unlike /events, a bare GET hands back the whole ring on purpose:
            # a chat you join mid-conversation with an empty log reads as broken,
            # while a room replaying an hour of tool calls reads as a lie.
            marker = 0
            if "since=" in self.path:
                try:
                    marker = int(self.path.split("since=", 1)[1].split("&")[0])
                except ValueError:
                    marker = 0
            msgs, latest = chat_since(marker)
            self._json({"next": latest, "messages": msgs})
            return
        if self.path.startswith("/peers"):
            self._json({"peers": peers_except(self._query("me"))})
            return
        if self.path.startswith("/tokens"):
            self._json(_tokens)
            return
        http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)

        if self.path == "/event":
            # A hook posts this from inside somebody's tool call, so nothing
            # here may raise: a bad body is a 400, never a stack trace.
            try:
                d = json.loads(raw.decode("utf-8"))
                seat = str(d.get("seat", "")).strip()
                tool = str(d.get("tool", "")).strip() or "?"
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            if not seat:
                self._json({"error": "seat required"}, 400)
                return
            self._json(record(seat, tool, d.get("ok", True)))
            return

        if self.path == "/chat":
            try:
                d = json.loads(raw.decode("utf-8"))
                name = str(d.get("name", "")).strip()[:NAME_MAX]
                text = str(d.get("text", "")).strip()[:TEXT_MAX]
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            if not name or not text:
                self._json({"error": "name and text required"}, 400)
                return
            self._json(say(name, text))
            return

        if self.path == "/pos":
            # Post and poll in one round trip: a visitor who tells the room where
            # they are wants, in the same breath, to know where everyone else is.
            # Two calls at 5Hz each would be twice the traffic for the same fact.
            try:
                d = json.loads(raw.decode("utf-8"))
                if not str(d.get("id", "")).strip():
                    self._json({"error": "id required"}, 400)
                    return
                rec = place(d)
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            if rec is None:
                self._json({"error": "room full"}, 503)
                return
            self._json({"peers": peers_except(rec["id"])})
            return

        if self.path == "/tokens":
            global _tokens
            try:
                d = json.loads(raw.decode("utf-8"))
                seats = d.get("seats") or {}
                _tokens = {"total": int(d.get("total", 0)),
                           "cost": float(d.get("cost", 0.0)),
                           "seats": {str(k): v for k, v in seats.items()},
                           "ts": time.time()}
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            self._json({"ok": True})
            return

        if self.path == "/__shot":
            # 🔴 This writes a file to disk from any POST. That was fine when the
            # only people who could reach the port had been handed a key by
            # hand; it is not fine on a public address. Loopback only — which is
            # exactly where every probe runs from anyway, so nothing that used
            # it loses it.
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self.send_error(403)
                return
            body = raw.decode("ascii")
            payload = body.split(",", 1)[1] if body.startswith("data:") else body
            with open("shot.png", "wb") as f:
                f.write(base64.b64decode(payload))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        self.send_error(404)


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    # threaded: the page polls /events on a timer, and a single-threaded server
    # would let one poll stall the next page load
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ReusableTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"KrakedDev Arena serving on http://0.0.0.0:{PORT}/")
        httpd.serve_forever()
