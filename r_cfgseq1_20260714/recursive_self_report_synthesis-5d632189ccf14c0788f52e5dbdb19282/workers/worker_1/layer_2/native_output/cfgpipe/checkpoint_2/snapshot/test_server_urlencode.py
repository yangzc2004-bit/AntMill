import http.server
import socketserver
import json
import urllib.parse

PORT = 18506

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        key = query.get('key', [''])[0]
        if key == 'config/port':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"found": True, "value": "9090", "version": 1}).encode())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"found": False}).encode())
    
    def log_message(self, format, *args):
        pass

with ReuseAddrTCPServer(("", PORT), Handler) as httpd:
    httpd.timeout = 2
    httpd.handle_request()
