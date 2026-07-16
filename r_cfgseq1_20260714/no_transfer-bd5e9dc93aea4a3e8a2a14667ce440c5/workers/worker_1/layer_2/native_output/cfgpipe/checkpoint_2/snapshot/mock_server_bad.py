import http.server
import socketserver
import json
import urllib.parse
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8501

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        self.send_response(500)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"error": "server error"}).encode())

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.timeout = 5
    for _ in range(5):
        httpd.handle_request()
