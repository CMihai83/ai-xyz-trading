#!/usr/bin/env python3
"""
Serve the dashboard on port 8888
"""
import http.server
import socketserver
import os
import sys

os.chdir('/home/misu/live/ai-trading-system')

PORT = 8888

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/dashboard.html'
        return super().do_GET()

print(f"🌐 Starting dashboard server on port {PORT}")
print(f"📊 Open your browser and go to: http://localhost:{PORT}")
print(f"🎯 Dashboard URL: http://localhost:{PORT}/dashboard.html")
print(f"💡 Press Ctrl+C to stop")

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    httpd.serve_forever()