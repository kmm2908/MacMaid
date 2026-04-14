import logging
import os
import signal
import socket
import subprocess
import threading
import webbrowser

import cleaner as cleaner_mod
from flask import Flask, Response, jsonify, request

logging.getLogger("werkzeug").setLevel(logging.ERROR)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _make_app(items: list[dict]) -> Flask:
    app = Flask(__name__)
    path_index = {item["path"]: item for item in items}

    @app.get("/")
    def index():
        return Response(_html(), mimetype="text/html")

    @app.get("/api/files")
    def files():
        return jsonify(items)

    @app.post("/api/delete")
    def delete():
        paths = request.json.get("paths", [])
        to_clean = [path_index[p] for p in paths if p in path_index]
        result = cleaner_mod.clean_items(to_clean)
        return jsonify({
            "moved": result.moved,
            "errors": result.errors,
            "bytes_freed": result.bytes_freed,
            "error_paths": result.error_paths,
        })

    @app.post("/api/reveal")
    def reveal():
        path = request.json.get("path", "")
        subprocess.run(["open", "-R", path], check=False)
        return jsonify({"ok": True})

    @app.post("/api/quit")
    def quit_server():
        def _shutdown():
            import time
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGINT)
        threading.Thread(target=_shutdown, daemon=True).start()
        return jsonify({"ok": True})

    return app


def start(items: list[dict]) -> None:
    """Start the Flask review server and open the browser."""
    app = _make_app(items)
    port = _free_port()
    url = f"http://localhost:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="localhost", port=port, use_reloader=False)


def _html() -> str:
    return "<!-- placeholder -->"
