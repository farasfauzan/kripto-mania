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
    # Pakai KEEP_ALIVE_PORT supaya tidak bentrok dengan Streamlit
    # yang di Docker Hugging Face Space sudah pakai PORT=7860.
    # Fallback ke PORT hanya kalau KEEP_ALIVE_PORT tidak diset
    # (mempertahankan kompatibilitas dengan Render.com).
    port = int(
        os.environ.get('KEEP_ALIVE_PORT')
        or os.environ.get('PORT', 8080)
    )
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()
