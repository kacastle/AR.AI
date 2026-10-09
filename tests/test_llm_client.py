"""backend/llm/client.py against a stand-in Ollama server on localhost, and with nothing listening."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.llm import client


class FakeOllama(BaseHTTPRequestHandler):
    seen = []
    reply = {"message": {"content": '```json\n{"ok": 1}\n```'}, "done_reason": "stop"}

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeOllama.seen.append((self.path, json.loads(body)))
        data = json.dumps(FakeOllama.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def no_pause():
    client._down_until = 0.0
    yield
    client._down_until = 0.0


@pytest.fixture
def fake_ollama(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(client, "BASE_URL", f"http://127.0.0.1:{server.server_port}")
    FakeOllama.seen.clear()
    yield FakeOllama
    server.shutdown()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_request_has_the_settings_from_the_spec(fake_ollama):
    schema = {"type": "object", "required": ["title"]}
    text, finish = client.chat("gemma4:e4b", "SYS", "USER", 0.5, 600, schema=schema)
    assert (text, finish) == ('{"ok": 1}', "stop")          # code fences removed
    path, body = fake_ollama.seen[0]
    assert path == "/api/chat"
    assert body["model"] == "gemma4:e4b"
    assert body["stream"] is False and body["keep_alive"] == "30m" and body["think"] is False
    assert body["format"] == schema
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert body["options"] == {"temperature": 0.5, "num_predict": 600}


def test_without_a_schema_the_format_is_json(fake_ollama):
    client.chat("m", "s", "u", 0.3, 100)
    assert fake_ollama.seen[0][1]["format"] == "json"


def test_ollama_off_raises_model_error_quickly(monkeypatch):
    monkeypatch.setattr(client, "BASE_URL", f"http://127.0.0.1:{free_port()}")
    with pytest.raises(client.ModelError):
        client.chat("m", "s", "u", 0.3, 100)
    assert client.available() is False


def test_only_localhost():
    assert client.BASE_URL.startswith("http://localhost:") or client.BASE_URL.startswith("http://127.0.0.1:")


def test_after_a_refused_connection_calls_are_skipped_for_a_while(monkeypatch):
    monkeypatch.setattr(client, "BASE_URL", f"http://127.0.0.1:{free_port()}")
    with pytest.raises(client.ModelError):
        client.chat("m", "s", "u", 0.3, 100)
    start = time.perf_counter()
    with pytest.raises(client.ModelError, match="skipped"):
        client.chat("m", "s", "u", 0.3, 100)
    assert time.perf_counter() - start < 0.1


def test_a_working_server_clears_the_pause(fake_ollama):
    client._down_until = time.monotonic() - 1
    assert client.chat("m", "s", "u", 0.3, 100)[0] == '{"ok": 1}'
