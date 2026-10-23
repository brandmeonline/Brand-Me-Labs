"""Local GCS JSON API contract fixture, NOT a cloud IAM/storage verification."""
from contextlib import contextmanager
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, unquote, urlsplit

BUCKET = "brandme-development-exports-tests"


class StorageState:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.lock = threading.Lock()
        self.next_generation = 1
        self.lose_upload_ack = False
        self.delete_failure = False
        self.override = None
        self.policy = {"name": BUCKET, "iamConfiguration": {"publicAccessPrevention": "enforced",
                       "uniformBucketLevelAccess": {"enabled": True}}, "softDeletePolicy": {"retentionDurationSeconds": "0"},
                       "lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 1}}]}}


@contextmanager
def storage_server():
    state = StorageState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, body=b"", headers=None):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # expected when a bounded client cancels an oversized reply

        def handle_request(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            path = unquote(url.path)
            state.calls.append((self.command, path, query))
            if state.override:
                return self.reply(*state.override)
            if self.command == "GET" and path == f"/storage/v1/b/{BUCKET}":
                return self.reply(200, state.policy)
            if self.command == "POST" and path == f"/upload/storage/v1/b/{BUCKET}/o":
                if query != {"uploadType": ["multipart"], "ifGenerationMatch": ["0"]}:
                    return self.reply(400)
                data = self.rfile.read(int(self.headers["Content-Length"]))
                msg = BytesParser(policy=default).parsebytes(("Content-Type: " + self.headers["Content-Type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + data)
                parts = list(msg.iter_parts())
                metadata = json.loads(parts[0].get_payload(decode=True))
                content = parts[1].get_payload(decode=True)
                key = metadata["name"]
                with state.lock:
                    if key in state.objects:
                        return self.reply(412)
                    gen = str(state.next_generation)
                    state.next_generation += 1
                    state.objects[key] = (gen, content, metadata)
                if state.lose_upload_ack:
                    self.close_connection = True
                    return
                return self.reply(200, {"name": key, "generation": gen, "size": str(len(content))})
            prefix = f"/storage/v1/b/{BUCKET}/o/"
            if not path.startswith(prefix):
                return self.reply(404)
            key = path[len(prefix):]
            with state.lock:
                if key not in state.objects:
                    return self.reply(404)
                gen, data, _metadata = state.objects[key]
                if self.command == "GET":
                    if query.get("alt") == ["media"]:
                        if query.get("generation") != [gen]:
                            return self.reply(404)
                        return self.reply(200, data)
                    return self.reply(200, {"name": key, "generation": gen, "size": str(len(data))})
                if self.command == "DELETE":
                    if state.delete_failure:
                        return self.reply(503, {"private_provider_error": "must-not-leak"})
                    if query.get("ifGenerationMatch") != [gen]:
                        return self.reply(412)
                    del state.objects[key]
                    return self.reply(204)
            return self.reply(405)

        do_GET = do_POST = do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


if __name__ == "__main__":
    import os
    import signal
    if os.environ.get("BRANDME_MODE") != "development" or not os.environ.get("SPANNER_EMULATOR_HOST"):
        raise SystemExit("contract fixture requires development and Spanner emulator")
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    with storage_server() as (host, _state):
        print(json.dumps({"host": host}), flush=True)
        stopped.wait()
