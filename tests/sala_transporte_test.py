#!/usr/bin/env python3
"""Regresión de transporte: un GAS simulado redirige POST hacia un recurso GET."""
import json
import pathlib
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "nube"))
import sala_cliente as cliente

class RedirectTest(unittest.TestCase):
    def test_post_conserva_cuerpo_en_origen_y_lee_respuesta_con_get(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path != "/exec":
                    self.send_response(405)
                    self.end_headers()
                    self.wfile.write(b"solo GET")
                    return
                received.append((self.path, json.loads(body), self.headers.get("Content-Type")))
                self.send_response(302)
                self.send_header("Location", "/respuesta")
                self.end_headers()
            def do_GET(self):
                if self.path != "/respuesta":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true,"recibidas":1}')
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = {"accion": "produccion", "clave": "sintetica-sin-acceso", "detalle": "á"}
            raw = cliente._curl("http://127.0.0.1:%d/exec" % server.server_port,
                               json.dumps(payload), espera=5)
            self.assertEqual(cliente._leer_json(raw, "GAS simulado"), {"ok": True, "recibidas": 1})
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0][1], payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == "__main__":
    unittest.main()
