import http.server
import socketserver
import json
import urllib.parse
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8500

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        if path == '/v1/primary/kv':
            key = query.get('key', [''])[0]
            if key == 'config/port':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": True, "value": "9090", "version": 1}).encode())
            elif key == 'config/debug':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": True, "value": "true", "version": 2}).encode())
            elif key == 'app/port':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": True, "value": "9090", "version": 1}).encode())
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": False}).encode())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"found": False}).encode())

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.timeout = 2
    start = time.time()
    while time.time() - start < 30:
        httpd.handle_request()
