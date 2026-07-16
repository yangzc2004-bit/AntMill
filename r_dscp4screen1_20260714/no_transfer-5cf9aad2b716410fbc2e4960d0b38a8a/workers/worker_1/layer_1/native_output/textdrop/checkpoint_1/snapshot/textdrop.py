#!/usr/bin/env python3
"""TextDrop - A self-hosted text sharing service."""

import argparse
import html
import http.server
import json
import os
import random
import string
import urllib.parse
import sys

NOTE_IDS = {}  # noteID -> content

def generate_note_id():
    """Generate a URL-safe alphanumeric ID of length 4-12."""
    length = random.randint(4, 12)
    chars = string.ascii_letters + string.digits
    while True:
        candidate = ''.join(random.choices(chars, k=length))
        if candidate not in NOTE_IDS:
            return candidate

def render_html_page(title, body):
    """Return a complete HTML document as string."""
    return f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{html.escape(title)}</title></head>
<body>
{body}
</body>
</html>'''

def render_error_page(status_code, message):
    """Return an HTML error page."""
    title = f"{status_code} {message}"
    body = f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
    return render_html_page(title, body)

def render_editor_page():
    """Render the editor form page."""
    form_html = '''<form action="/submit" method="post" enctype="application/x-www-form-urlencoded">
<textarea name="content" rows="10" cols="80"></textarea><br>
<input type="submit" value="Submit">
</form>'''
    return render_html_page("TextDrop - New Note", form_html)

class TextDropHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if path == '/':
            self._serve_editor()
        elif path == '/submit':
            self._serve_editor()
        elif path == '/health':
            self._serve_health()
        elif path.startswith('/n/'):
            parts = path[3:].split('/')
            note_id = parts[0]
            if len(parts) == 1:
                self._serve_note_view(note_id)
            elif len(parts) == 2 and parts[1] == 'text':
                self._serve_note_raw(note_id)
            else:
                self._serve_404()
        else:
            self._serve_404()

    def do_POST(self):
        if self.path == '/submit':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8', errors='replace')
            params = urllib.parse.parse_qs(body, keep_blank_values=True)
            content = params.get('content', [None])[0]
            mode = params.get('mode', [''])[0]

            # Validate
            if content is None or content.strip() == '':
                self._send_error(400, "Bad Request - Content cannot be empty.")
                return
            if mode != '':
                self._send_error(400, "Bad Request - Invalid mode.")
                return

            note_id = generate_note_id()
            NOTE_IDS[note_id] = content
            self._send_redirect(f'/n/{note_id}')
        else:
            self._serve_404()

    def _serve_editor(self):
        html_page = render_editor_page()
        self._send_response(200, html_page, content_type='text/html')

    def _serve_health(self):
        body = json.dumps({"status": "active"})
        self._send_response(200, body, content_type='application/json')

    def _serve_note_view(self, note_id):
        content = NOTE_IDS.get(note_id)
        if content is None:
            self._serve_404()
            return
        escaped = html.escape(content)
        body = f"<pre><code>{escaped}</code></pre>"
        html_page = render_html_page("Note", body)
        self._send_response(200, html_page, content_type='text/html')

    def _serve_note_raw(self, note_id):
        content = NOTE_IDS.get(note_id)
        if content is None:
            self._serve_404()
            return
        self._send_response(200, content, content_type='text/plain; charset=utf-8')

    def _serve_404(self):
        html_page = render_error_page(404, "Not Found")
        self._send_response(404, html_page, content_type='text/html')

    def _send_redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def _send_response(self, status, body, content_type='text/html; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def _send_error(self, status, message):
        html_page = render_error_page(status, message)
        self._send_response(status, html_page, content_type='text/html')

    def log_message(self, format, *args):
        # Suppress logs for cleaner output
        pass

def parse_args():
    parser = argparse.ArgumentParser(description='TextDrop server')
    parser.add_argument('--host', default=None, help='Host to bind')
    parser.add_argument('--port', type=int, default=None, help='Port to listen on')
    args = parser.parse_args()
    host = args.host or os.environ.get('TEXTDROP_HOST', '')
    port = args.port
    if port is None:
        try:
            port = int(os.environ.get('TEXTDROP_PORT', '8080'))
        except ValueError:
            port = 8080
    return host, port

def main():
    host, port = parse_args()
    if not host:
        host = ''  # all interfaces
    server = http.server.HTTPServer((host, port), TextDropHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    main()
