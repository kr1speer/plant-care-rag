"""Serve deterministic Chat Completions responses for browser integration tests."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWERS = (
    ("прорезей", "D02", "Мелкие листья связаны с недостатком света."),
    ("температура", "D03", "Летом 25–30 °C, зимой 16–20 °C."),
    ("пересаживать орхидею", "D10", "Пересаживайте раз в год после цветения."),
)


class Handler(BaseHTTPRequestHandler):
    """Accept a completion request and cite a matching context fragment."""

    def do_POST(self):
        """Return a fixture completion when its source is present in the context."""
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return

        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size))
        question, _, context = request["messages"][1]["content"].partition(
            "\n\nКонтекст:\n"
        )
        question = " ".join(question.lower().split())
        reply = {
            "answer": "В документах нет этой информации",
            "refused": True,
            "sources": [],
        }
        for phrase, doc_id, answer in ANSWERS:
            if phrase in question and re.search(rf"^\[{doc_id}\] .+ — ", context, re.M):
                reply = {
                    "answer": f"{answer} [{doc_id}]",
                    "refused": False,
                    "sources": [doc_id],
                }
                break

        body = json.dumps({"choices": [{"message": {"content": json.dumps(reply)}}]})
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8001), Handler) as server:
        server.serve_forever()
