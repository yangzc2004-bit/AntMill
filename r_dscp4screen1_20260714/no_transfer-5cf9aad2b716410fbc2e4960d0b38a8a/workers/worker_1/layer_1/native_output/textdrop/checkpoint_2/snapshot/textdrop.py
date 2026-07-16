#!/usr/bin/env python3
"""TextDrop - A self-hosted text sharing service with markdown support."""

import argparse
import html
import http.server
import json
import os
import random
import re
import string
import urllib.parse
import sys

import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, ClassNotFound
from pygments.formatters import HtmlFormatter

NOTE_IDS = {}  # noteID -> content
HEADING_SLUG_COUNTS = {}  # Not used - we keep same id for duplicates per spec


def generate_note_id():
    """Generate a URL-safe alphanumeric ID of length 4-12."""
    length = random.randint(4, 12)
    chars = string.ascii_letters + string.digits
    while True:
        candidate = ''.join(random.choices(chars, k=length))
        if candidate not in NOTE_IDS:
            return candidate


def slugify(text):
    """Create a heading id slug from heading text."""
    s = text.lower()
    s = s.replace(' ', '-')
    s = re.sub(r'[^a-z0-9-]', '', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    return s


def make_markdown_extensions():
    """Create markdown extension list with custom heading ID and code highlight."""
    class HeadingIdProcessor(markdown.treeprocessors.Treeprocessor):
        def run(self, root):
            for h in root.iter('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                text = ''.join(h.itertext())
                slug = slugify(text)
                h.set('id', slug)
            return root

    class CodeHighlightPreprocessor(markdown.preprocessors.Preprocessor):
        def run(self, lines):
            return lines

    class CodeHighlightPostprocessor(markdown.postprocessors.Postprocessor):
        def run(self, text):
            return text

    ext_configs = {
        'fenced_code': {},
        'codehilite': {
            'css_class': 'highlight',
            'linenums': False,
            'guess_lang': False,
        },
        'tables': {},
    }

    extensions = ['fenced_code', 'codehilite', 'tables']

    return extensions, ext_configs, HeadingIdProcessor


def render_markdown(text):
    """Render markdown text to HTML with custom heading IDs and syntax highlighting."""
    extensions, ext_configs, HeadingIdProcessor = make_markdown_extensions()

    md = markdown.Markdown(
        extensions=extensions,
        extension_configs=ext_configs,
    )
    # Add heading id treeprocessor after build
    md.treeprocessors.register(HeadingIdProcessor(), 'heading_ids', 15)

    html_output = md.convert(text)
    return html_output


def render_plain_text(content):
    """Escape content and wrap in pre/code."""
    escaped = html.escape(content)
    return f"<pre><code>{escaped}</code></pre>"


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
            content_type = self.headers.get('Content-Type', '').lower()
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)

            # UTF-8 validation
            try:
                body_str = raw_body.decode('utf-8')
            except UnicodeDecodeError:
                self._send_error(400, "Bad Request - Content is not valid UTF-8.")
                return

            content = None
            mode = ''

            if 'application/json' in content_type:
                try:
                    data = json.loads(body_str)
                except json.JSONDecodeError:
                    self._send_error(400, "Bad Request - Invalid JSON.")
                    return
                content = data.get('body')
                mode = data.get('mode', '')
            elif 'application/x-www-form-urlencoded' in content_type:
                params = urllib.parse.parse_qs(body_str, keep_blank_values=True)
                content = params.get('content', [None])[0]
                mode = params.get('mode', [''])[0]
            else:
                self._send_error(400, "Bad Request - Unsupported Content-Type.")
                return

            # Validate content
            if content is None or content.strip() == '':
                self._send_error(400, "Bad Request - Content cannot be empty.")
                return

            # Validate mode
            if mode not in ('', 'markdown'):
                self._send_error(400, "Bad Request - Invalid mode.")
                return

            note_id = generate_note_id()
            NOTE_IDS[note_id] = (content, mode)
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
        stored = NOTE_IDS.get(note_id)
        if stored is None:
            self._serve_404()
            return

        if isinstance(stored, tuple):
            content, mode = stored
        else:
            # backward compatibility for old entries
            content = stored
            mode = ''

        if mode == 'markdown':
            rendered_body = render_markdown(content)
        else:
            rendered_body = render_plain_text(content)

        html_page = render_html_page("Note", rendered_body)
        self._send_response(200, html_page, content_type='text/html')

    def _serve_note_raw(self, note_id):
        stored = NOTE_IDS.get(note_id)
        if stored is None:
            self._serve_404()
            return

        if isinstance(stored, tuple):
            content, mode = stored
        else:
            content = stored

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
