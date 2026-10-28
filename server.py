
"""
IONA — Local AI Server with JSON Memory

Fitur:
- Menyajikan HTML, CSS, dan JavaScript.
- Menghubungkan aplikasi dengan Ollama.
- Menyimpan satu percakapan ke conversation.json.
- Menyimpan memori jangka panjang ke memory.json.
- Memuat riwayat ketika aplikasi dibuka kembali.
- Mendukung perintah eksplisit untuk menyimpan dan menghapus memori.
- Memindahkan riwayat localStorage lama ke JSON jika memungkinkan.

Tidak memerlukan library Python tambahan.

Jalankan:
    py server.py

Buka:
    http://127.0.0.1:8000
"""

import copy
import json
import logging
import os
import re
import socket
import threading
import uuid

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


# ==================================================
# 1. KONFIGURASI
# ==================================================

HOST = "127.0.0.1"
PORT = 8000

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL_NAME = "qwen3.5:0.8b"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CONVERSATION_FILE = os.path.join(
    DATA_DIR,
    "conversation.json"
)

MEMORY_FILE = os.path.join(
    DATA_DIR,
    "memory.json"
)

MAX_REQUEST_SIZE = 2_000_000
MAX_MEMORY_LENGTH = 600
MAX_STORED_MEMORIES = 300
MAX_CONTEXT_MESSAGES = 6
MAX_PROMPT_MEMORIES = 5
MAX_CONTEXT_MESSAGES = 4
MAX_PROMPT_MEMORIES = 3

MODEL_OPTIONS = {
    "num_ctx": 2048,
    "num_predict": 512,
    "temperature": 0.7,
    "num_thread": 2,
}

DATA_LOCK = threading.RLock()

DEFAULT_CONVERSATION = {
    "version": 1,
    "messages": [],
}

DEFAULT_MEMORY = {
    "version": 1,
    "memories": [],
}


# ==================================================
# 2. WAKTU DAN FILE JSON
# ==================================================

def current_timestamp():
    """Menghasilkan waktu dalam format ISO 8601 UTC."""

    return datetime.now(timezone.utc).isoformat()


def save_json_unlocked(file_path, data):
    """
    Menyimpan JSON secara atomik.
    File sementara digunakan agar file utama tidak
    mudah rusak jika proses penulisan terganggu.
    """

    temp_path = file_path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    os.replace(temp_path, file_path)


def read_json_unlocked(file_path, default_value):
    """Membaca JSON. Fungsi dipanggil saat DATA_LOCK dipegang."""

    if not os.path.exists(file_path):
        return copy.deepcopy(default_value)

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    except (OSError, json.JSONDecodeError):
        logging.exception(
            "File JSON tidak dapat dibaca: %s",
            file_path,
        )

        return copy.deepcopy(default_value)


def ensure_data_files():
    """Membuat folder data dan file awal bila belum tersedia."""

    os.makedirs(DATA_DIR, exist_ok=True)

    with DATA_LOCK:
        if not os.path.exists(CONVERSATION_FILE):
            save_json_unlocked(
                CONVERSATION_FILE,
                DEFAULT_CONVERSATION,
            )

        if not os.path.exists(MEMORY_FILE):
            save_json_unlocked(
                MEMORY_FILE,
                DEFAULT_MEMORY,
            )


def get_conversation():
    """Mengambil pesan dari satu percakapan yang tersimpan."""

    with DATA_LOCK:
        data = read_json_unlocked(
            CONVERSATION_FILE,
            DEFAULT_CONVERSATION,
        )

        if not isinstance(data, dict):
            return copy.deepcopy(DEFAULT_CONVERSATION)

        messages = data.get("messages", [])

        if not isinstance(messages, list):
            messages = []

        valid_messages = []

        for item in messages:
            if not isinstance(item, dict):
                continue

            if item.get("role") not in ("user", "assistant"):
                continue

            if not isinstance(item.get("content"), str):
                continue

            valid_messages.append(item)

        return {
            "version": 1,
            "messages": valid_messages,
        }


def append_conversation(user_text, assistant_text):
    """Menyimpan satu pertukaran pesan yang berhasil."""

    with DATA_LOCK:
        data = read_json_unlocked(
            CONVERSATION_FILE,
            DEFAULT_CONVERSATION,
        )

        if not isinstance(data, dict):
            data = copy.deepcopy(DEFAULT_CONVERSATION)

        messages = data.get("messages", [])

        if not isinstance(messages, list):
            messages = []

        timestamp = current_timestamp()

        messages.append({
            "role": "user",
            "content": user_text,
            "timestamp": timestamp,
        })

        messages.append({
            "role": "assistant",
            "content": assistant_text,
            "timestamp": current_timestamp(),
        })

        data["version"] = 1
        data["messages"] = messages

        save_json_unlocked(
            CONVERSATION_FILE,
            data,
        )


def get_memory_data():
    """Mengambil daftar memori jangka panjang."""

    with DATA_LOCK:
        data = read_json_unlocked(
            MEMORY_FILE,
            DEFAULT_MEMORY,
        )

        if not isinstance(data, dict):
            return copy.deepcopy(DEFAULT_MEMORY)

        memories = data.get("memories", [])

        if not isinstance(memories, list):
            memories = []

        valid_memories = []

        for item in memories:
            if not isinstance(item, dict):
                continue

            if not isinstance(item.get("content"), str):
                continue

            valid_memories.append(item)

        return {
            "version": 1,
            "memories": valid_memories,
        }


# ==================================================
# 3. PERINTAH MEMORI
# ==================================================

def detect_memory_command(text):
    """
    Memori hanya disimpan ketika pengguna memberi
    perintah yang jelas.

    Contoh:
    - Ingat bahwa aku suka penjelasan bertahap.
    - Catat bahwa aku menggunakan ESP32.
    - Simpan ke memori: aku sedang membuat proyek Iona.
    - Hapus memori: aku menggunakan ESP32.
    - Hapus semua memori.
    """

    clear_pattern = re.compile(
        r"^\s*(?:tolong\s+)?"
        r"(?:hapus|lupakan)\s+"
        r"(?:semua|seluruh)\s+"
        r"(?:memori|ingatan)\s*[.!]?\s*$",
        re.IGNORECASE,
    )

    if clear_pattern.match(text):
        return {
            "action": "clear",
            "content": "",
        }

    delete_patterns = [
        re.compile(
            r"^\s*(?:tolong\s+)?"
            r"(?:hapus|lupakan)\s+"
            r"(?:memori|ingatan)\s*[:,-]?\s*(.+?)\s*$",
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in delete_patterns:
        match = pattern.match(text)

        if match:
            return {
                "action": "delete",
                "content": match.group(1).strip(),
            }

    add_patterns = [
        re.compile(
            r"^\s*(?:tolong\s+)?"
            r"(?:ingat|catat)\s+"
            r"(?:bahwa|kalau)\s+(.+?)\s*$",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*(?:tolong\s+)?"
            r"simpan(?:kan)?\s+"
            r"(?:ke|dalam)\s+memori\s*[:,-]?\s*(.+?)\s*$",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"^\s*ingat\s+ya\s*[:,]\s*(.+?)\s*$",
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in add_patterns:
        match = pattern.match(text)

        if match:
            return {
                "action": "add",
                "content": match.group(1).strip(),
            }

    return None



def detect_automatic_memory(text):
    """
    Mengenali pernyataan yang berpotensi berguna untuk jangka panjang.

    Versi ini menggunakan pola teks, bukan pemanggilan AI tambahan.
    Tidak semua pesan otomatis disimpan.
    """

    content = " ".join(text.strip().split())

    if len(content) < 15 or len(content) > MAX_MEMORY_LENGTH:
        return None

    # Jangan menyimpan informasi sensitif secara otomatis.
    sensitive_patterns = [
        r"\bpassword\b",
        r"\bkata sandi\b",
        r"\bnomor pin\b",
        r"\bpin saya\b",
        r"\botp\b",
        r"\bapi key\b",
        r"\btoken api\b",
        r"\bsecret key\b",
        r"\bnomor rekening\b",
        r"\brekening bank\b",
        r"\bnomor ktp\b",
        r"\bnik\b",
        r"\bnomor paspor\b",
        r"\balamat rumah\b",
        r"\briwayat medis\b",
        r"\bdiagnosis medis\b",
        r"\bpenyakit saya\b",
    ]

    for pattern in sensitive_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return None

    # A. Preferensi komunikasi dan kebiasaan.
    preference_patterns = [
        r"^(?:aku|saya)\s+(?:lebih\s+suka|suka|menyukai|senang|"
        r"tidak\s+suka|kurang\s+suka|lebih\s+nyaman|nyaman|"
        r"memilih|mengutamakan)\b",

        r"^(?:mulai sekarang|ke depannya|untuk jawaban berikutnya)\b",
    ]

    for pattern in preference_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return {
                "content": content,
                "category": "preference",
            }

    # B. Proyek yang sedang dikerjakan.
    project_patterns = [
        r"^(?:aku|saya)\s+(?:(?:sedang|lagi)\s+)?"
        r"(?:mengerjakan|membuat|mengembangkan|membangun|"
        r"merancang|meneliti|menyusun)\b",

        r"^(?:proyek|project)\s+(?:ku|saya)\s+"
        r"(?:adalah|bernama|yaitu)\b",
    ]

    for pattern in project_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return {
                "content": content,
                "category": "project",
            }

    # C. Perangkat dan teknologi yang digunakan.
    technology_pattern = (
        r"\b(?:windows|linux|macos|esp32|arduino|firebase|"
        r"python|javascript|html|css|ollama|qwen|laravel|"
        r"mysql|sqlite|iot|laptop|ram|intel core i[3579]|"
        r"flutter|php|git|github|raspberry pi)\b"
    )

    usage_pattern = (
        r"^(?:aku|saya)\s+(?:menggunakan|memakai|pakai)\b"
    )

    if (
        re.search(usage_pattern, content, re.IGNORECASE)
        and re.search(technology_pattern, content, re.IGNORECASE)
    ):
        return {
            "content": content,
            "category": "technical_context",
        }

    # D. Tujuan belajar yang berkaitan dengan teknologi.
    learning_pattern = (
        r"^(?:aku|saya)\s+(?:(?:sedang|lagi)\s+)?"
        r"(?:belajar|mempelajari)\b"
    )

    if (
        re.search(learning_pattern, content, re.IGNORECASE)
        and re.search(technology_pattern, content, re.IGNORECASE)
    ):
        return {
            "content": content,
            "category": "learning_goal",
        }

    return None


def update_memory_from_user_message(text):
    """
    Mendukung dua cara:
    1. Penyimpanan manual melalui perintah eksplisit.
    2. Deteksi otomatis untuk beberapa pola informasi penting.
    """

    command = detect_memory_command(text)
    automatic = False
    category = "manual"

    # Tidak ada perintah manual? Coba deteksi otomatis.
    if not command:
        candidate = detect_automatic_memory(text)

        if not candidate:
            return None

        command = {
            "action": "add",
            "content": candidate["content"],
        }

        automatic = True
        category = candidate["category"]

    action = command["action"]
    content = command["content"].strip()

    response_action = (
        "auto_add" if automatic else action
    )

    if action == "add" and not content:
        return None

    if len(content) > MAX_MEMORY_LENGTH:
        return {
            "action": response_action,
            "saved": False,
            "message": "Memori terlalu panjang.",
        }

    with DATA_LOCK:
        data = read_json_unlocked(
            MEMORY_FILE,
            DEFAULT_MEMORY,
        )

        if not isinstance(data, dict):
            data = copy.deepcopy(DEFAULT_MEMORY)

        memories = data.get("memories", [])

        if not isinstance(memories, list):
            memories = []

        # Hapus semua memori jika diminta.
        if action == "clear":
            data["version"] = 1
            data["memories"] = []

            save_json_unlocked(MEMORY_FILE, data)

            return {
                "action": "clear",
                "saved": True,
                "message": "Semua memori berhasil dihapus.",
            }

        # Hapus memori yang cocok dengan teks pencarian.
        if action == "delete":
            query = content.casefold()
            kept_memories = []
            removed_count = 0

            for item in memories:
                saved_content = (
                    item.get("content", "")
                    if isinstance(item, dict)
                    else ""
                )

                if query and query in saved_content.casefold():
                    removed_count += 1
                else:
                    kept_memories.append(item)

            if removed_count:
                data["version"] = 1
                data["memories"] = kept_memories
                save_json_unlocked(MEMORY_FILE, data)

            return {
                "action": "delete",
                "saved": removed_count > 0,
                "removed": removed_count,
                "message": (
                    f"{removed_count} memori berhasil dihapus."
                    if removed_count
                    else "Tidak ditemukan memori yang cocok."
                ),
            }

        # Hindari menyimpan informasi yang sama berulang kali.
        normalized = content.casefold()

        duplicate = any(
            isinstance(item, dict)
            and isinstance(item.get("content"), str)
            and item["content"].strip().casefold() == normalized
            for item in memories
        )

        if duplicate:
            return {
                "action": response_action,
                "saved": False,
                "message": "Informasi tersebut sudah tersimpan.",
            }

        memories.append({
            "id": str(uuid.uuid4()),
            "category": category,
            "content": content,
            "source": "automatic" if automatic else "manual",
            "created_at": current_timestamp(),
        })

        # Batasi jumlah memori untuk menjaga file tetap wajar.
        memories = memories[-MAX_STORED_MEMORIES:]

        data["version"] = 1
        data["memories"] = memories

        save_json_unlocked(MEMORY_FILE, data)

        logging.info(
            "Memori tersimpan: kategori=%s, sumber=%s",
            category,
            "automatic" if automatic else "manual",
        )

        return {
            "action": response_action,
            "saved": True,
            "category": category,
            "message": (
                "Informasi berhasil disimpan sebagai memori."
            ),
        }

    """
    Menambah atau menghapus memori berdasarkan
    permintaan eksplisit pengguna.
    """

    command = detect_memory_command(text)

    if not command:
        return None

    action = command["action"]
    content = command["content"].strip()

    if action == "add" and not content:
        return None

    if len(content) > MAX_MEMORY_LENGTH:
        return {
            "action": "rejected",
            "saved": False,
            "message": (
                "Memori terlalu panjang. "
                "Coba simpan dalam kalimat yang lebih singkat."
            ),
        }

    with DATA_LOCK:
        data = read_json_unlocked(
            MEMORY_FILE,
            DEFAULT_MEMORY,
        )

        if not isinstance(data, dict):
            data = copy.deepcopy(DEFAULT_MEMORY)

        memories = data.get("memories", [])

        if not isinstance(memories, list):
            memories = []

        if action == "add":
            normalized = content.casefold()

            duplicate_exists = any(
                isinstance(item, dict)
                and isinstance(item.get("content"), str)
                and item["content"].strip().casefold() == normalized
                for item in memories
            )

            if duplicate_exists:
                return {
                    "action": "add",
                    "saved": False,
                    "message": "Memori tersebut sudah tersimpan.",
                }

            memories.append({
                "id": str(uuid.uuid4()),
                "content": content,
                "created_at": current_timestamp(),
            })

            memories = memories[-MAX_STORED_MEMORIES:]

            data["version"] = 1
            data["memories"] = memories

            save_json_unlocked(MEMORY_FILE, data)

            logging.info("Memori baru berhasil disimpan.")

            return {
                "action": "add",
                "saved": True,
                "message": "Memori berhasil disimpan.",
            }

        if action == "clear":
            data["version"] = 1
            data["memories"] = []

            save_json_unlocked(MEMORY_FILE, data)

            logging.info("Seluruh memori jangka panjang dihapus.")

            return {
                "action": "clear",
                "saved": True,
                "message": "Semua memori berhasil dihapus.",
            }

        if action == "delete":
            query = content.casefold()

            if not query:
                return None

            kept_memories = []
            removed_count = 0

            for item in memories:
                saved_content = (
                    item.get("content", "")
                    if isinstance(item, dict)
                    else ""
                )

                if query in saved_content.casefold():
                    removed_count += 1
                else:
                    kept_memories.append(item)

            if removed_count > 0:
                data["version"] = 1
                data["memories"] = kept_memories

                save_json_unlocked(MEMORY_FILE, data)

            return {
                "action": "delete",
                "saved": removed_count > 0,
                "removed": removed_count,
                "message": (
                    f"{removed_count} memori berhasil dihapus."
                    if removed_count > 0
                    else "Tidak ditemukan memori yang cocok."
                ),
            }

    return None


# ==================================================
# 4. MEMASUKKAN MEMORI KE KONTEKS MODEL
# ==================================================

def build_system_prompt(base_prompt, current_query=""):
    """
    Menggabungkan instruksi Iona dengan memori yang tersimpan.
    Hanya sejumlah kecil memori terbaru dimasukkan agar
    konteks tidak terlalu besar.
    """

    prompt = base_prompt.strip()

    if not prompt:
        prompt = (
            "Kamu adalah Iona, asisten AI pribadi yang ramah, "
            "jujur, dan membantu."
        )

    memory_data = get_memory_data()
    memories = memory_data.get("memories", [])

    if not memories:
        return (
            prompt
            + "\n\nMEMORI JANGKA PANJANG\n"
            + "Saat ini belum ada memori jangka panjang yang tersimpan."
        )

    selected_memories = memories[-MAX_PROMPT_MEMORIES:]

    memory_lines = [
        "",
        "MEMORI JANGKA PANJANG PENGGUNA",
        "Informasi berikut berasal dari catatan yang disimpan pengguna.",
        "Gunakan hanya jika relevan dengan pertanyaan saat ini.",
        "Jangan mengarang fakta baru berdasarkan catatan ini.",
    ]

    for index, item in enumerate(selected_memories, start=1):
        content = item.get("content", "").strip()

        if content:
            memory_lines.append(f"{index}. {content}")

    return prompt + "\n" + "\n".join(memory_lines)


# ==================================================
# 5. API OLLAMA
# ==================================================

def send_ollama_request(endpoint, payload=None, timeout=10):
    """Mengirim permintaan ke API lokal Ollama."""

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
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


# ==================================================
# 6. HTTP RESPONSE HANDLER
# ==================================================

class IonaRequestHandler(BaseHTTPRequestHandler):
    server_version = "IonaLocalServer/2.0"

    def log_message(self, format_string, *args):
        logging.info(
            "%s - %s",
            self.address_string(),
            format_string % args,
        )

    def send_json(self, status_code, data):
        body = json.dumps(
            data,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            logging.warning("Koneksi browser terputus saat mengirim respons.")

    def send_text(self, status_code, message):
        body = message.encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            logging.warning("Koneksi browser terputus.")

    def read_request_json(self):
        """Membaca dan memvalidasi isi JSON dari permintaan POST."""

        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )
        except ValueError:
            raise ValueError("Ukuran permintaan tidak valid.")

        if content_length <= 0:
            raise ValueError("Isi permintaan tidak boleh kosong.")

        if content_length > MAX_REQUEST_SIZE:
            raise OverflowError("Ukuran permintaan terlalu besar.")

        raw_body = self.rfile.read(content_length)

        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Format JSON tidak valid.")

    # ----------------------------------------------
    # GET
    # ----------------------------------------------

    def do_GET(self):
        path = urlsplit(self.path).path

        if path == "/api/health":
            self.handle_health()
            return

        if path == "/api/conversation":
            data = get_conversation()

            self.send_json(
                200,
                {
                    "ok": True,
                    "messages": data["messages"],
                },
            )
            return

        if path == "/api/memory":
            self.send_json(
                200,
                {
                    "ok": True,
                    **get_memory_data(),
                },
            )
            return

        static_files = {
            "/": "index.html",
            "/index.html": "index.html",
            "/style.css": "style.css",
            "/app.js": "app.js",
        }

        filename = static_files.get(path)

        if not filename:
            self.send_text(404, "Halaman atau endpoint tidak ditemukan.")
            return

        file_path = os.path.join(BASE_DIR, filename)

        try:
            with open(file_path, "rb") as file:
                content = file.read()

        except OSError:
            self.send_text(
                404,
                f"File {filename} tidak ditemukan.",
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

        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            logging.warning("Browser terputus saat mengambil file.")

    def handle_health(self):
        try:
            result = send_ollama_request("/api/tags", timeout=5)
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
                },
            )

        except (HTTPError, URLError, socket.timeout, TimeoutError, OSError):
            self.send_json(
                200,
                {
                    "ok": False,
                    "ollamaRunning": False,
                    "modelAvailable": False,
                    "model": MODEL_NAME,
                    "error": (
                        "Ollama tidak dapat dihubungi. "
                        "Pastikan Ollama sedang berjalan."
                    ),
                },
            )

        except Exception as error:
            logging.exception("Pemeriksaan Ollama gagal.")

            self.send_json(
                502,
                {
                    "ok": False,
                    "ollamaRunning": False,
                    "modelAvailable": False,
                    "error": str(error),
                },
            )

    # ----------------------------------------------
    # POST
    # ----------------------------------------------

    def do_POST(self):
        path = urlsplit(self.path).path

        if path not in (
            "/api/chat",
            "/api/import-conversation",
        ):
            self.send_json(
                404,
                {"error": "Endpoint tidak ditemukan."},
            )
            return

        try:
            request_data = self.read_request_json()

        except OverflowError as error:
            self.send_json(413, {"error": str(error)})
            return

        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        if not isinstance(request_data, dict):
            self.send_json(
                400,
                {"error": "Format permintaan harus berupa objek JSON."},
            )
            return

        if path == "/api/import-conversation":
            self.handle_import_conversation(request_data)
            return

        self.handle_chat(request_data)

    def handle_import_conversation(self, request_data):
        """
        Memindahkan riwayat localStorage lama ke JSON.
        Impor hanya diizinkan jika file percakapan server kosong.
        """

        incoming = request_data.get("messages")

        if not isinstance(incoming, list):
            self.send_json(
                400,
                {"error": "Daftar pesan untuk impor tidak valid."},
            )
            return

        cleaned = []

        for item in incoming:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant"):
                continue

            if not isinstance(content, str):
                continue

            content = content.strip()

            if not content or len(content) > 30000:
                continue

            timestamp = item.get("timestamp")

            if not isinstance(timestamp, str):
                timestamp = current_timestamp()

            cleaned.append({
                "role": role,
                "content": content,
                "timestamp": timestamp,
            })

        if not cleaned:
            self.send_json(
                400,
                {"error": "Tidak ada pesan valid untuk diimpor."},
            )
            return

        with DATA_LOCK:
            existing = read_json_unlocked(
                CONVERSATION_FILE,
                DEFAULT_CONVERSATION,
            )

            existing_messages = (
                existing.get("messages", [])
                if isinstance(existing, dict)
                else []
            )

            if existing_messages:
                self.send_json(
                    409,
                    {
                        "ok": False,
                        "imported": False,
                        "error": (
                            "Riwayat server sudah berisi pesan. "
                            "Impor otomatis dibatalkan untuk "
                            "menghindari pencampuran percakapan."
                        ),
                    },
                )
                return

            save_json_unlocked(
                CONVERSATION_FILE,
                {
                    "version": 1,
                    "messages": cleaned,
                },
            )

        logging.info(
            "%s pesan lama berhasil diimpor ke JSON.",
            len(cleaned),
        )

        self.send_json(
            200,
            {
                "ok": True,
                "imported": True,
                "count": len(cleaned),
            },
        )

    def handle_chat(self, request_data):
        user_text = request_data.get("message")
        system_prompt = request_data.get("systemPrompt", "")

        if not isinstance(user_text, str) or not user_text.strip():
            self.send_json(
                400,
                {"error": "Pesan tidak boleh kosong."},
            )
            return

        user_text = user_text.strip()

        if len(user_text) > 10000:
            self.send_json(
                413,
                {"error": "Pesan terlalu panjang."},
            )
            return

        if not isinstance(system_prompt, str):
            system_prompt = ""

        if len(system_prompt) > 30000:
            self.send_json(
                400,
                {"error": "Instruksi sistem terlalu panjang."},
            )
            return

        # Perbarui memori hanya jika pengguna memberi perintah jelas.
        memory_action = update_memory_from_user_message(user_text)

        # Ambil konteks percakapan sebelumnya yang tersimpan.
        conversation = get_conversation()
        stored_messages = conversation["messages"]

        recent_messages = stored_messages[-MAX_CONTEXT_MESSAGES:]

        model_messages = [
            {
                "role": "system",
                "content": build_system_prompt(system_prompt, user_text),
            }
        ]

        for item in recent_messages:
            role = item.get("role")
            content = item.get("content")

            if (
                role in ("user", "assistant")
                and isinstance(content, str)
            ):
                model_messages.append({
                    "role": role,
                    "content": content,
                })

        # Tambahkan pesan saat ini untuk permintaan model.
        # Pesan ini baru disimpan bersama jawabannya jika berhasil.
        model_messages.append({
            "role": "user",
            "content": user_text,
        })

        
        ollama_payload = {
            "model": MODEL_NAME,
            "messages": model_messages,
            "stream": False,
            "think": False,

            # Pertahankan model dalam memori selama 10 menit
            # setelah permintaan selesai.
            "keep_alive": "10m",

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
                raise RuntimeError(
                    "Ollama memberikan jawaban kosong. "
                    "Coba lagi atau periksa versi Ollama."
                )

            answer = answer.strip()

            # Simpan pasangan pesan setelah jawaban berhasil.
            append_conversation(user_text, answer)

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "model": result.get("model", MODEL_NAME),
                    "memoryAction": memory_action,
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
                detail[:1000],
            )

            if error.code == 404:
                friendly_message = (
                    f"Model {MODEL_NAME} tidak ditemukan. "
                    f"Jalankan: ollama pull {MODEL_NAME}"
                )
            else:
                friendly_message = (
                    f"Ollama gagal memproses pesan "
                    f"(HTTP {error.code})."
                )

            self.send_json(
                502,
                {
                    "error": friendly_message,
                    "detail": detail[:500],
                },
            )

        except (
            URLError,
            socket.timeout,
            TimeoutError,
            OSError,
        ) as error:
            logging.error("Tidak dapat terhubung ke Ollama: %s", error)

            self.send_json(
                502,
                {
                    "error": (
                        "Tidak dapat terhubung ke Ollama. "
                        "Pastikan aplikasi Ollama sedang berjalan."
                    ),
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

        except RuntimeError as error:
            logging.error("%s", error)

            self.send_json(
                502,
                {"error": str(error)},
            )

        except Exception:
            logging.exception("Permintaan chat gagal.")

            self.send_json(
                500,
                {
                    "error": (
                        "Terjadi kesalahan pada server Iona. "
                        "Periksa terminal untuk detailnya."
                    ),
                },
            )


# ==================================================
# 7. MENJALANKAN SERVER
# ==================================================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    ensure_data_files()

    try:
        server = ThreadingHTTPServer(
            (HOST, PORT),
            IonaRequestHandler,
        )

    except OSError as error:
        logging.error(
            "Tidak dapat menjalankan server pada port %s: %s",
            PORT,
            error,
        )
        logging.error(
            "Pastikan port 8000 tidak digunakan oleh aplikasi lain."
        )
        return

    logging.info("Iona JSON Memory Server aktif.")
    logging.info(
        "Alamat aplikasi: http://%s:%s",
        HOST,
        PORT,
    )
    logging.info("Model AI: %s", MODEL_NAME)
    logging.info("Lokasi data: %s", DATA_DIR)
    logging.info("Tekan Ctrl+C untuk menghentikan server.")

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        logging.info("Server Iona dihentikan.")

    finally:
        server.server_close()
        logging.info("Server Iona berhenti.")


if __name__ == "__main__":
    main()
