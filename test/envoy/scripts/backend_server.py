#!/usr/bin/env python3
import http.server
import json
import urllib.parse
import os
import sys


class BenchmarkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        size = int(params.get('size', [str(DATA_SIZE)][0]))
        body = 'x' * size
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok', 'size': len(body)}).encode())

    def log_message(self, format, *args):
        pass


DATA_SIZE = int(os.environ.get('DATA_SIZE', '1000'))
PORT = int(os.environ.get('BACKEND_PORT', '8080'))

if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', PORT), BenchmarkHandler)
    server.serve_forever()
