from http.server import BaseHTTPRequestHandler
import json
import sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from main import run_job

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            result = run_job()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "result": "started"}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
