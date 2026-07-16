import http.server
import socketserver
import json
import urllib.parse

PORT = 18505

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"found": True, "value": "notanumber", "version": 1}).encode())
    
    def log_message(self, format, *args):
        pass

with ReuseAddrTCPServer(("", PORT), Handler) as httpd:
    httpd.timeout = 2
    httpd.handle_request()
