import logging
import os
import signal
import socket
import subprocess
import threading
import webbrowser

from flask import Flask, Response, jsonify

logging.getLogger("werkzeug").setLevel(logging.ERROR)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _make_app(items: list[dict]) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return Response(_html(), mimetype="text/html")

    @app.get("/api/files")
    def files():
        return jsonify(items)

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
