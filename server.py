
"""
IONA — Local AI Server

Fungsi:
1. Menyajikan index.html, style.css, dan app.js.
2. Menghubungkan browser dengan Ollama.
3. Memeriksa koneksi Ollama dan ketersediaan model.
4. Tidak membutuhkan Flask atau library tambahan.

Jalankan:
    py server.py

Buka:
    http://127.0.0.1:8000
"""

import json
import logging
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


# =========================================
# 1. KONFIGURASI
# =========================================

HOST = "127.0.0.1"
PORT = 8000

OLLAMA_URL = "http://127.0.0.1:11434"

MODEL_NAME = "qwen3.5:2b"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAX_REQUEST_SIZE = 1_000_000

# Batasi beban pemrosesan untuk laptop dengan RAM terbatas.
MODEL_OPTIONS = {
    "num_ctx": 2048,
    "num_predict": 512,
    "temperature": 0.7,
}


# =========================================
# 2. FUNGSI BANTUAN
# =========================================

def send_ollama_request(endpoint, payload=None, timeout=10):
    """
    Mengirim permintaan HTTP ke API Ollama.
    Jika payload None, permintaan menggunakan GET.
    Jika payload tersedia, permintaan menggunakan POST.
    """

    url = f"{OLLAMA_URL}{endpoint}"

    if payload is None:
        request = Request(url, method="GET")
    else:
        body = json.dumps(payload).encode("utf-8")

        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

    with urlopen(request, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


# =========================================
# 3. HTTP REQUEST HANDLER
# =========================================

class IonaRequestHandler(BaseHTTPRequestHandler):
    server_version = "IonaLocalServer/1.0"

    def log_message(self, format_string, *args):
        """
        Menampilkan log permintaan di terminal.
        """

        logging.info(
            "%s - %s",
            self.address_string(),
            format_string % args,
        )

    def send_json(self, status_code, data):
        """
        Mengirim respons JSON ke browser.
        """

        content = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        self.wfile.write(content)

    def send_text(self, status_code, message):
        """
        Mengirim respons teks sederhana.
        """

        content = message.encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()

        self.wfile.write(content)

    # -------------------------------------
    # GET: HALAMAN, FILE STATIS, DAN STATUS
    # -------------------------------------

    def do_GET(self):
        path = urlsplit(self.path).path

        # Endpoint untuk memeriksa Ollama.
        if path == "/api/health":
            self.handle_health()
            return

        # Halaman utama.
        if path in ("", "/"):
            filename = "index.html"

        # Hanya izinkan file proyek yang diperlukan.
        elif path in ("/index.html", "/style.css", "/app.js"):
            filename = path.lstrip("/")

        else:
            self.send_text(404, "Halaman atau file tidak ditemukan.")
            return

        file_path = os.path.join(BASE_DIR, filename)

        try:
            with open(file_path, "rb") as file:
                content = file.read()

        except FileNotFoundError:
            self.send_text(
                404,
                f"File {filename} tidak ditemukan. "
                "Pastikan semua file proyek berada di folder yang sama.",
            )
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }

        extension = os.path.splitext(filename)[1].lower()
        content_type = content_types.get(
            extension,
            "application/octet-stream",
        )

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        self.wfile.write(content)

    def handle_health(self):
        """
        Memeriksa apakah Ollama aktif dan model tersedia.
        """

        try:
            result = send_ollama_request(
                "/api/tags",
                timeout=5,
            )

            available_models = result.get("models", [])

            model_available = any(
                item.get("name") == MODEL_NAME
                or item.get("model") == MODEL_NAME
                for item in available_models
            )

            self.send_json(
                200,
                {
                    "ok": model_available,
                    "ollamaRunning": True,
                    "modelAvailable": model_available,
                    "model": MODEL_NAME,
                    "availableModels": [
                        item.get("name", "")
                        for item in available_models
                    ],
                },
            )

        except (URLError, socket.timeout, TimeoutError, OSError):
            self.send_json(
                200,
                {
                    "ok": False,
                    "ollamaRunning": False,
                    "modelAvailable": False,
                    "model": MODEL_NAME,
                    "error": (
                        "Ollama tidak dapat dihubungi. "
                        "Pastikan aplikasi Ollama sedang berjalan."
                    ),
                },
            )

        except (ValueError, json.JSONDecodeError) as error:
            logging.exception("Respons pemeriksaan Ollama tidak valid.")

            self.send_json(
                502,
                {
                    "ok": False,
                    "ollamaRunning": False,
                    "modelAvailable": False,
                    "error": str(error),
                },
            )

    # -------------------------------------
    # POST: PERCAKAPAN AI
    # -------------------------------------

    def do_POST(self):
        path = urlsplit(self.path).path

        if path != "/api/chat":
            self.send_json(
                404,
                {"error": "Endpoint tidak ditemukan."},
            )
            return

        # Validasi panjang permintaan.
        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )
        except ValueError:
            self.send_json(
                400,
                {"error": "Ukuran permintaan tidak valid."},
            )
            return

        if content_length <= 0:
            self.send_json(
                400,
                {"error": "Pesan tidak boleh kosong."},
            )
            return

        if content_length > MAX_REQUEST_SIZE:
            self.send_json(
                413,
                {"error": "Permintaan terlalu besar."},
            )
            return

        # Membaca data dari JavaScript.
        try:
            raw_body = self.rfile.read(content_length)
            request_data = json.loads(raw_body.decode("utf-8"))

        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(
                400,
                {"error": "Format JSON tidak valid."},
            )
            return

        messages = request_data.get("messages")

        if not isinstance(messages, list) or not messages:
            self.send_json(
                400,
                {"error": "Daftar pesan tidak valid."},
            )
            return

        # Validasi isi pesan sebelum diteruskan ke Ollama.
        cleaned_messages = []

        for message in messages:
            if not isinstance(message, dict):
                self.send_json(
                    400,
                    {"error": "Format pesan tidak valid."},
                )
                return

            role = message.get("role")
            content = message.get("content")

            if role not in ("system", "user", "assistant"):
                self.send_json(
                    400,
                    {"error": "Peran pesan tidak valid."},
                )
                return

            if not isinstance(content, str):
                self.send_json(
                    400,
                    {"error": "Isi pesan harus berupa teks."},
                )
                return

            cleaned_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        # Meneruskan percakapan ke API lokal Ollama.
        ollama_payload = {
            "model": MODEL_NAME,
            "messages": cleaned_messages,
            "stream": False,

            # Menonaktifkan mode thinking agar model
            # langsung menghasilkan jawaban yang dapat dibaca Iona.
            "think": False,

            "options": MODEL_OPTIONS,
        }

        try:
            result = send_ollama_request(
                "/api/chat",
                payload=ollama_payload,
                timeout=240,
            )

            model_message = result.get("message", {})
            answer = model_message.get("content", "")

            if not isinstance(answer, str) or not answer.strip():
                self.send_json(
                    502,
                    {
                        "error": (
                            "Ollama memberikan jawaban kosong. "
                            "Coba kirim pesan kembali."
                        )
                    },
                )
                return

            self.send_json(
                200,
                {
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "model": result.get("model", MODEL_NAME),
                },
            )

        except HTTPError as error:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )

            logging.error(
                "Ollama memberikan HTTP %s: %s",
                error.code,
                detail,
            )

            if error.code == 404:
                friendly_message = (
                    f"Model {MODEL_NAME} tidak ditemukan. "
                    f"Jalankan perintah: ollama pull {MODEL_NAME}"
                )
            else:
                friendly_message = (
                    "Ollama gagal memproses pesan "
                    f"(HTTP {error.code})."
                )

            self.send_json(
                502,
                {
                    "error": friendly_message,
                    "detail": detail[:500],
                },
            )

        except (URLError, socket.timeout, TimeoutError, OSError) as error:
            logging.error("Ollama tidak dapat dihubungi: %s", error)

            self.send_json(
                502,
                {
                    "error": (
                        "Tidak dapat terhubung ke Ollama. "
                        "Periksa apakah aplikasi Ollama berjalan."
                    )
                },
            )

        except (ValueError, json.JSONDecodeError) as error:
            logging.exception("Respons Ollama tidak valid.")

            self.send_json(
                502,
                {
                    "error": "Respons dari Ollama tidak valid.",
                    "detail": str(error),
                },
            )


# =========================================
# 4. MENJALANKAN SERVER
# =========================================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        server = ThreadingHTTPServer(
            (HOST, PORT),
            IonaRequestHandler,
        )

    except OSError as error:
        logging.error(
            "Gagal menjalankan server pada port %s: %s",
            PORT,
            error,
        )
        logging.error(
            "Pastikan port tersebut tidak digunakan aplikasi lain."
        )
        return

    logging.info("Iona local server aktif.")
    logging.info("Alamat aplikasi: http://%s:%s", HOST, PORT)
    logging.info("Model AI: %s", MODEL_NAME)
    logging.info("Tekan Ctrl+C untuk menghentikan server.")

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        logging.info("Server Iona sedang dihentikan.")

    finally:
        server.server_close()
        logging.info("Server Iona berhenti.")


if __name__ == "__main__":
    main()
