from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import os

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot Telegram Aktif dan Berjalan 24/7!")
    
    # Supaya log terminal tidak dipenuhi dengan log akses http
    def log_message(self, format, *args):
        pass

def run_server():
    # Render.com akan memberikan port lewat environment variable PORT
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()
