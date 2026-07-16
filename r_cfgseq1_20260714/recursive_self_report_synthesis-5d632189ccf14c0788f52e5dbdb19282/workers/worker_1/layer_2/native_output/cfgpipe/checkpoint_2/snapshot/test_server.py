import http.server
import socketserver
import json
import urllib.parse

PORT = 18502

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        
        if parsed.path == '/v1/primary/kv':
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
                self.wfile.write(json.dumps({"found": True, "value": "true", "version": 1}).encode())
            elif key == 'app/port':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": True, "value": "9090", "version": 1}).encode())
            elif key == 'app/retries':
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": False}).encode())
            elif key == 'app/timeout':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": True, "value": "5.5", "version": 1}).encode())
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"found": False}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

with ReuseAddrTCPServer(("", PORT), Handler) as httpd:
    httpd.timeout = 2
    httpd.handle_request()
    httpd.handle_request()
    httpd.handle_request()
    httpd.handle_request()
    httpd.handle_request()
