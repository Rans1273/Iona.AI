
/* =========================================
   IONA — SINGLE CONVERSATION
   Satu percakapan berkelanjutan
   ========================================= */

(() => {
    "use strict";


    // ---------- 1. KONFIGURASI ----------

    const MODEL_NAME = "qwen3.5:2b";

    // Satu kunci penyimpanan untuk satu percakapan Iona.
    const STORAGE_KEY = "iona_single_conversation_v1";

    // Batasi jumlah pesan yang disimpan di browser.
    const MAX_SAVED_MESSAGES = 100;

    // Jumlah pesan terakhir yang dikirim sebagai konteks model.
    const MAX_CONTEXT_MESSAGES = 10;


    // ---------- 2. ELEMEN HTML ----------

    const chatForm = document.getElementById("chatForm");
    const messageInput = document.getElementById("messageInput");
    const sendButton = document.getElementById("sendButton");

    const chatArea = document.getElementById("chatArea");
    const messagesContainer = document.getElementById("messagesContainer");
    const welcomeScreen = document.getElementById("welcomeScreen");
    const modelStatus = document.getElementById("modelStatus");

    const connectionIndicators = document.querySelectorAll(
        ".connection-indicator"
    );


    if (
        !chatForm ||
        !messageInput ||
        !sendButton ||
        !chatArea ||
        !messagesContainer ||
        !welcomeScreen
    ) {
        console.error(
            "Iona: Elemen HTML utama tidak ditemukan. Periksa index.html."
        );
        return;
    }


    // ---------- 3. IDENTITAS IONA ----------

    const SYSTEM_MESSAGE = {
        role: "system",
        content: `
IDENTITAS
Kamu adalah Iona, asisten AI pribadi pengguna.
Kamu ramah, cerdas, tenang, teliti, dan alami ketika berbicara.
Tujuanmu adalah membantu pengguna belajar, berpikir, berkarya,
serta menyelesaikan masalah.

BAHASA DAN KOMUNIKASI
1. Gunakan bahasa Indonesia sebagai bahasa utama.
2. Berbicara secara alami, ramah, dan tidak kaku.
3. Jawab langsung sesuai inti pertanyaan.
4. Untuk pertanyaan sederhana, jawab secara ringkas.
5. Untuk masalah kompleks, berikan penjelasan terstruktur.
6. Hindari basa-basi panjang, pengulangan, dan daftar yang tidak perlu.
7. Sesuaikan panjang jawaban dengan kebutuhan pengguna.

PENYELESAIAN MASALAH
1. Pahami maksud dan konteks pertanyaan sebelum menjawab.
2. Pecah masalah rumit menjadi tahap yang mudah diikuti.
3. Pilih solusi yang realistis dan sesuai kebutuhan pengguna.
4. Jelaskan jika terdapat kekeliruan dalam asumsi pengguna.
5. Jangan mengarang jawaban jika informasi tidak mencukupi.
6. Tanyakan informasi tambahan hanya jika benar-benar diperlukan.

KETEPATAN DAN KEJUJURAN
1. Utamakan ketepatan, relevansi, dan kejelasan.
2. Bedakan fakta, perkiraan, pendapat, dan ketidakpastian.
3. Jika tidak tahu, akui keterbatasanmu.
4. Jangan mengarang sumber, kutipan, hasil pengujian, atau data.
5. Jangan mengaku telah mengakses internet, membaca file,
   menjalankan kode, atau memeriksa perangkat jika hal itu
   tidak benar-benar dilakukan.
6. Jangan memberikan kepastian palsu tentang keberhasilan solusi.

PEMROGRAMAN DAN TEKNIS
1. Jelaskan langkah teknis secara berurutan.
2. Berikan contoh konkret yang mudah diterapkan.
3. Jika diminta kode lengkap, berikan kode yang utuh.
4. Saat memperbaiki proyek yang sudah ada, pertahankan fitur
   dan tampilan yang tidak diminta untuk diubah.
5. Tunjukkan dengan jelas file dan bagian yang perlu diubah.
6. Saat melakukan debugging, periksa penyebab secara sistematis.
7. Jangan mengarang nama fungsi, library, atau kemampuan teknologi.
8. Jika kode belum diuji, katakan bahwa kode masih perlu diuji.

KONTEKS PENGGUNA
Pengguna tertarik pada perangkat lunak, perangkat keras,
HTML, CSS, JavaScript, Python, IoT, ESP32, Arduino,
Firebase, dan pengembangan aplikasi.
Gunakan konteks tersebut ketika relevan, tetapi jangan
menganggap semua pertanyaan pasti berkaitan dengan teknologi.

KETERBATASAN
1. Kamu berjalan menggunakan model lokal melalui Ollama.
2. Kamu hanya dapat melakukan tindakan yang didukung aplikasi.
3. Kamu tidak otomatis memiliki akses ke internet, file,
   kamera, mikrofon, atau perangkat fisik.
4. Jangan mengaku mengingat percakapan yang tidak tersedia
   dalam konteks yang diberikan.
5. Jika suatu kemampuan belum tersedia, jelaskan keterbatasannya
   dengan jujur dan berikan alternatif yang realistis.

FORMAT JAWABAN
1. Gunakan judul jika jawaban memiliki beberapa bagian.
2. Gunakan daftar untuk langkah atau pilihan yang memang perlu.
3. Gunakan tabel jika membantu membandingkan informasi.
4. Berikan kode dalam blok kode yang sesuai.
5. Jelaskan istilah teknis secara sederhana jika diperlukan.

PRINSIP UTAMA
Jadilah asisten yang membantu pengguna menyelesaikan masalah,
bukan sekadar menghasilkan banyak teks.
Utamakan jawaban yang tepat, relevan, jujur, dan dapat diterapkan.
Tetaplah menjadi Iona.
        `.trim()
    };


    // ---------- 4. PENYIMPANAN SATU PERCAKAPAN ----------

    function loadHistory() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);

            if (!saved) {
                return [];
            }

            const parsed = JSON.parse(saved);

            if (!Array.isArray(parsed)) {
                return [];
            }

            return parsed
                .filter((item) => {
                    return (
                        item &&
                        ["user", "assistant"].includes(item.role) &&
                        typeof item.content === "string"
                    );
                })
                .slice(-MAX_SAVED_MESSAGES);

        } catch (error) {
            console.error(
                "Iona: Riwayat tersimpan tidak dapat dibaca.",
                error
            );

            return [];
        }
    }


    let conversationHistory = loadHistory();
    let isSending = false;


    function saveHistory() {
        try {
            // Simpan hanya pesan percakapan, bukan system prompt.
            conversationHistory = conversationHistory.slice(
                -MAX_SAVED_MESSAGES
            );

            localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify(conversationHistory)
            );

        } catch (error) {
            console.error(
                "Iona: Riwayat tidak berhasil disimpan.",
                error
            );
        }
    }


    // ---------- 5. STATUS KONEKSI ----------

    function setConnectionStatus(state, message) {
        const colors = {
            connected: "#36a779",
            warning: "#d4a34f",
            disconnected: "#dc5b68"
        };

        const color = colors[state] || colors.warning;

        if (modelStatus) {
            modelStatus.textContent = message;
        }

        connectionIndicators.forEach((indicator) => {
            indicator.style.backgroundColor = color;
        });
    }


    async function checkConnection() {
        setConnectionStatus("warning", "Memeriksa koneksi...");

        try {
            const response = await fetch("/api/health", {
                method: "GET",
                cache: "no-store"
            });

            if (!response.ok) {
                throw new Error("Server lokal memberikan respons gagal.");
            }

            const result = await response.json();

            if (!result.ollamaRunning) {
                setConnectionStatus(
                    "disconnected",
                    "Ollama belum berjalan"
                );

                return false;
            }

            if (!result.modelAvailable) {
                setConnectionStatus(
                    "warning",
                    "Model belum tersedia"
                );

                return false;
            }

            setConnectionStatus(
                "connected",
                "Ollama terhubung"
            );

            return true;

        } catch (error) {
            console.error(
                "Iona: Pemeriksaan koneksi gagal.",
                error
            );

            setConnectionStatus(
                "disconnected",
                "Server lokal tidak terhubung"
            );

            return false;
        }
    }


    // ---------- 6. MENGATUR AREA CHAT ----------

    function scrollToBottom(behavior = "smooth") {
        requestAnimationFrame(() => {
            chatArea.scrollTo({
                top: chatArea.scrollHeight,
                behavior
            });
        });
    }


    function updateWelcomeScreen() {
        welcomeScreen.hidden = conversationHistory.length > 0;
    }


    // ---------- 7. MENAMPILKAN PESAN ----------

    function addMessage(role, text, shouldScroll = true) {
        const messageElement = document.createElement("article");
        messageElement.className = `message ${role}`;

        const messageHeader = document.createElement("div");
        messageHeader.className = "message-header";

        const avatar = document.createElement("span");
        avatar.className = "message-avatar";
        avatar.textContent = role === "assistant" ? "i" : "K";
        avatar.setAttribute("aria-hidden", "true");

        const name = document.createElement("span");
        name.textContent = role === "assistant" ? "Iona" : "Kamu";

        messageHeader.append(avatar, name);

        const messageContent = document.createElement("div");
        messageContent.className = "message-content";

        // Tampilkan sebagai teks, bukan HTML aktif.
        messageContent.textContent = text;

        messageElement.append(messageHeader, messageContent);
        messagesContainer.appendChild(messageElement);

        if (shouldScroll) {
            scrollToBottom();
        }

        return messageElement;
    }


    // ---------- 8. INDIKATOR PROSES ----------

    function showTypingIndicator() {
        const messageElement = document.createElement("article");
        messageElement.className = "message assistant";

        const messageHeader = document.createElement("div");
        messageHeader.className = "message-header";

        const avatar = document.createElement("span");
        avatar.className = "message-avatar";
        avatar.textContent = "i";
        avatar.setAttribute("aria-hidden", "true");

        const name = document.createElement("span");
        name.textContent = "Iona sedang berpikir...";

        messageHeader.append(avatar, name);

        const content = document.createElement("div");
        content.className = "message-content";

        const indicator = document.createElement("div");
        indicator.className = "typing-indicator";
        indicator.setAttribute(
            "aria-label",
            "Iona sedang memproses jawaban"
        );

        for (let index = 0; index < 3; index += 1) {
            indicator.appendChild(document.createElement("span"));
        }

        content.appendChild(indicator);
        messageElement.append(messageHeader, content);
        messagesContainer.appendChild(messageElement);

        scrollToBottom();

        return messageElement;
    }


    // ---------- 9. INPUT PESAN ----------

    function resetInputHeight() {
        messageInput.style.height = "auto";
    }


    function resizeInput() {
        messageInput.style.height = "auto";

        const nextHeight = Math.min(
            messageInput.scrollHeight,
            160
        );

        messageInput.style.height = `${nextHeight}px`;
    }


    messageInput.addEventListener("input", resizeInput);


    // Enter untuk mengirim.
    // Shift + Enter untuk membuat baris baru.
    messageInput.addEventListener("keydown", (event) => {
        if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !event.isComposing
        ) {
            event.preventDefault();
            chatForm.requestSubmit();
        }
    });


    // ---------- 10. MENGIRIM PESAN KE OLLAMA ----------

    async function sendMessage(rawText) {
        const text = rawText.trim();

        if (!text || isSending) {
            return;
        }

        isSending = true;

        sendButton.disabled = true;
        messageInput.disabled = true;

        const sendLabel = sendButton.querySelector(
            "span:first-child"
        );

        const sendIcon = sendButton.querySelector(
            "span:last-child"
        );

        if (sendLabel) {
            sendLabel.textContent = "Memproses";
        }

        if (sendIcon) {
            sendIcon.textContent = "…";
        }

        welcomeScreen.hidden = true;

        // Masukkan pesan pengguna ke percakapan tunggal.
        conversationHistory.push({
            role: "user",
            content: text
        });

        saveHistory();
        addMessage("user", text);

        messageInput.value = "";
        resetInputHeight();

        const typingElement = showTypingIndicator();

        try {
            const messagesForModel = [
                SYSTEM_MESSAGE,
                ...conversationHistory.slice(-MAX_CONTEXT_MESSAGES)
            ];

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    messages: messagesForModel
                })
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    result.error || "Permintaan ke model lokal gagal."
                );
            }

            const reply = result.message?.content;

            if (typeof reply !== "string" || !reply.trim()) {
                throw new Error(
                    "Ollama memberikan jawaban kosong. " +
                    "Pastikan model dan server berjalan dengan benar."
                );
            }

            // Simpan jawaban yang berhasil diterima.
            conversationHistory.push({
                role: "assistant",
                content: reply
            });

            saveHistory();

            typingElement.remove();
            addMessage("assistant", reply);

            setConnectionStatus(
                "connected",
                "Ollama terhubung"
            );

        } catch (error) {
            console.error(
                "Iona: Pesan gagal diproses.",
                error
            );

            typingElement.remove();

            // Pesan kesalahan ditampilkan, tetapi tidak dimasukkan
            // ke konteks percakapan AI.
            addMessage(
                "assistant",
                "Maaf, aku belum berhasil memproses pesanmu.\n\n" +
                error.message +
                "\n\nPastikan Ollama dan server.py berjalan, " +
                "serta model " + MODEL_NAME + " tersedia."
            );

            await checkConnection();

        } finally {
            isSending = false;

            sendButton.disabled = false;
            messageInput.disabled = false;

            if (sendLabel) {
                sendLabel.textContent = "Kirim";
            }

            if (sendIcon) {
                sendIcon.textContent = "↑";
            }

            messageInput.focus();
        }
    }


    // ---------- 11. FORM CHAT ----------

    chatForm.addEventListener("submit", (event) => {
        event.preventDefault();
        sendMessage(messageInput.value);
    });


    // ---------- 12. KARTU SARAN AWAL ----------

    document.querySelectorAll(".suggestion-card").forEach((button) => {
        button.addEventListener("click", () => {
            const prompt = button.dataset.prompt;

            if (prompt) {
                sendMessage(prompt);
            }
        });
    });


    // ---------- 13. MEMULIHKAN PERCAKAPAN ----------

    function restoreConversation() {
        if (conversationHistory.length === 0) {
            welcomeScreen.hidden = false;
            return;
        }

        welcomeScreen.hidden = true;

        conversationHistory.forEach((message) => {
            addMessage(
                message.role,
                message.content,
                false
            );
        });

        scrollToBottom("auto");
    }


    // ---------- 14. MULAI IONA ----------

    async function initializeIona() {
        restoreConversation();
        await checkConnection();

        console.log("Iona siap digunakan.");
    }


    initializeIona();

})();
