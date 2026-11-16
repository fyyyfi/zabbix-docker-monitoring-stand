"""Мінімальний приймач вебхуків Zabbix: пише кожне сповіщення в журнал."""
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = "/data/alerts.log"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            alert = json.loads(body)
        except ValueError:
            alert = {"raw": body.decode(errors="replace")}
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {json.dumps(alert, ensure_ascii=False)}"
        print(line)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
