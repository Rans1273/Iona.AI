
/* =========================================
   IONA — SINGLE CONVERSATION + JSON MEMORY
   ========================================= */

(() => {
    "use strict";


    // ---------- 1. KONFIGURASI ----------

    const MODEL_NAME = "qwen3.5:0.8b";

    // Nama kunci dari versi Iona sebelumnya.
    // Digunakan sekali untuk migrasi riwayat lama.
    const LEGACY_STORAGE_KEY = "iona_single_conversation_v1";


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
dan menyelesaikan masalah.

BAHASA DAN KOMUNIKASI
1. Gunakan bahasa Indonesia sebagai bahasa utama.
2. Berbicaralah secara alami, ramah, dan tidak kaku.
3. Jawab langsung sesuai inti pertanyaan.
4. Untuk pertanyaan sederhana, jawab dengan ringkas.
5. Untuk masalah kompleks, berikan penjelasan terstruktur.
6. Hindari pengulangan, basa-basi panjang, dan daftar yang tidak perlu.
7. Sesuaikan panjang jawaban dengan kebutuhan pengguna.

PENYELESAIAN MASALAH
1. Pahami maksud dan konteks pertanyaan sebelum menjawab.
2. Pecah masalah rumit menjadi tahap yang mudah diikuti.
3. Pilih solusi yang realistis dan sesuai kebutuhan.
4. Jelaskan jika terdapat kekeliruan dalam asumsi pengguna.
5. Jangan mengarang jawaban jika informasi tidak mencukupi.
6. Tanyakan informasi tambahan hanya jika diperlukan.

KETEPATAN DAN KEJUJURAN
1. Utamakan ketepatan, relevansi, dan kejelasan.
2. Bedakan fakta, perkiraan, opini, dan ketidakpastian.
3. Jika tidak mengetahui jawabannya, akui keterbatasanmu.
4. Jangan mengarang sumber, kutipan, hasil pengujian, atau data.
5. Jangan mengaku telah mengakses internet, membaca file,
   menjalankan kode, atau memeriksa perangkat jika tidak dilakukan.
6. Jangan memberikan kepastian palsu tentang keberhasilan solusi.

PEMROGRAMAN DAN TEKNIS
1. Jelaskan langkah teknis secara berurutan.
2. Berikan contoh konkret yang mudah diterapkan.
3. Jika diminta kode lengkap, berikan kode yang utuh.
4. Saat memperbaiki kode, pertahankan fitur serta tampilan
   yang tidak diminta untuk diubah.
5. Tunjukkan dengan jelas file dan bagian yang perlu diubah.
6. Lakukan debugging secara sistematis.
7. Jangan mengarang nama fungsi, library, atau kemampuan teknologi.
8. Jika kode belum diuji, katakan bahwa kode perlu diuji.

KONTEKS PENGGUNA
Pengguna tertarik pada perangkat lunak dan perangkat keras,
HTML, CSS, JavaScript, Python, IoT, ESP32, Arduino, Firebase,
dan pengembangan aplikasi.
Gunakan konteks ini jika relevan. Jangan menganggap semua
pertanyaan pasti berkaitan dengan teknologi.

MEMORI DAN KONTEKS PERCAKAPAN
1. Gunakan riwayat percakapan yang tersedia untuk memahami konteks.
2. Gunakan memori jangka panjang yang diberikan sistem jika relevan.
3. Jangan mengarang ingatan atau mengaku mengingat informasi
   yang tidak tersedia dalam riwayat maupun memori.
4. Jika informasi lama tidak tersedia, jelaskan keterbatasanmu.
5. Jangan mengulang memori pribadi pengguna jika tidak relevan.
6. Jika pengguna meminta informasi tertentu dilupakan, hormati
   permintaan tersebut sesuai kemampuan aplikasi.

BATASAN
1. Kamu berjalan menggunakan model lokal melalui Ollama.
2. Kamu hanya dapat melakukan tindakan yang didukung aplikasi.
3. Kamu tidak otomatis memiliki akses ke internet, file,
   kamera, mikrofon, atau perangkat fisik.
4. Jika suatu kemampuan belum tersedia, jelaskan keterbatasannya
   dan berikan alternatif yang realistis.

FORMAT JAWABAN
1. Gunakan judul jika jawaban memiliki beberapa bagian.
2. Gunakan daftar untuk langkah atau pilihan yang memang perlu.
3. Gunakan tabel jika membantu perbandingan.
4. Berikan kode dalam blok kode yang sesuai.
5. Jelaskan istilah teknis dengan bahasa sederhana jika diperlukan.

PRINSIP UTAMA
Jadilah asisten yang membantu pengguna menyelesaikan masalah,
bukan sekadar menghasilkan banyak teks.
Utamakan jawaban yang tepat, relevan, jujur, dan dapat diterapkan.
Tetaplah menjadi Iona.
        `.trim()
    };


    // ---------- 4. STATUS KONEKSI ----------

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
        setConnectionStatus(
            "warning",
            "Memeriksa koneksi..."
        );

        try {
            const response = await fetch("/api/health", {
                method: "GET",
                cache: "no-store"
            });

            if (!response.ok) {
                throw new Error(
                    "Server memberikan respons yang tidak berhasil."
                );
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


    // ---------- 5. TAMPILAN PESAN ----------

    function scrollToBottom(behavior = "smooth") {
        requestAnimationFrame(() => {
            chatArea.scrollTo({
                top: chatArea.scrollHeight,
                behavior
            });
        });
    }


    function updateWelcomeScreen(hasMessages) {
        welcomeScreen.hidden = hasMessages;
    }


    function addMessage(role, text, shouldScroll = true, isError = false) {
        const messageElement = document.createElement("article");

        messageElement.className = `message ${role}`;

        if (isError) {
            messageElement.classList.add("message-error");
        }

        const messageHeader = document.createElement("div");
        messageHeader.className = "message-header";

        const avatar = document.createElement("span");
        avatar.className = "message-avatar";

        avatar.textContent = role === "assistant" ? "i" : "K";
        avatar.setAttribute("aria-hidden", "true");

        const name = document.createElement("span");

        name.textContent = role === "assistant"
            ? "Iona"
            : "Kamu";

        messageHeader.append(avatar, name);

        const messageContent = document.createElement("div");
        messageContent.className = "message-content";

        // Teks tidak dieksekusi sebagai HTML.
        messageContent.textContent = text;

        messageElement.append(
            messageHeader,
            messageContent
        );

        messagesContainer.appendChild(messageElement);

        if (shouldScroll) {
            scrollToBottom();
        }

        return messageElement;
    }


    // ---------- 6. INDIKATOR PROSES ----------

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
            indicator.appendChild(
                document.createElement("span")
            );
        }

        content.appendChild(indicator);

        messageElement.append(
            messageHeader,
            content
        );

        messagesContainer.appendChild(messageElement);

        scrollToBottom();

        return messageElement;
    }


    // ---------- 7. MEMUAT RIWAYAT DARI JSON ----------

    async function migrateOldBrowserHistory() {
        /*
         * Versi Iona sebelumnya menyimpan riwayat ke localStorage.
         * Jika data tersebut masih ada dan riwayat server kosong,
         * pindahkan ke file JSON melalui server Python.
         */

        let oldRawData;

        try {
            oldRawData = localStorage.getItem(
                LEGACY_STORAGE_KEY
            );
        } catch (error) {
            console.warn(
                "Iona: Penyimpanan browser lama tidak dapat diperiksa.",
                error
            );

            return;
        }

        if (!oldRawData) {
            return;
        }

        let oldMessages;

        try {
            oldMessages = JSON.parse(oldRawData);
        } catch (error) {
            console.warn(
                "Iona: Riwayat browser lama bukan JSON yang valid.",
                error
            );

            return;
        }

        if (!Array.isArray(oldMessages) || oldMessages.length === 0) {
            return;
        }

        try {
            const currentResponse = await fetch(
                "/api/conversation",
                { cache: "no-store" }
            );

            if (!currentResponse.ok) {
                return;
            }

            const currentData = await currentResponse.json();
            const currentMessages = Array.isArray(currentData.messages)
                ? currentData.messages
                : [];

            // Jangan mencampur riwayat lama dengan percakapan
            // JSON yang sudah terisi.
            if (currentMessages.length > 0) {
                return;
            }

            const importResponse = await fetch(
                "/api/import-conversation",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        messages: oldMessages
                    })
                }
            );

            if (!importResponse.ok) {
                console.warn(
                    "Iona: Migrasi riwayat lama tidak berhasil."
                );

                return;
            }

            const result = await importResponse.json();

            if (result.imported) {
                try {
                    // Hapus salinan lama hanya setelah server
                    // mengonfirmasi bahwa impor berhasil.
                    localStorage.removeItem(
                        LEGACY_STORAGE_KEY
                    );
                } catch (error) {
                    console.warn(
                        "Iona: Salinan lama tetap tersimpan di browser.",
                        error
                    );
                }

                console.info(
                    `Iona: ${result.count} pesan berhasil dipindahkan ke JSON.`
                );
            }

        } catch (error) {
            console.warn(
                "Iona: Migrasi riwayat lama tidak tersedia.",
                error
            );
        }
    }


    async function restoreConversation() {
        const response = await fetch(
            "/api/conversation",
            {
                method: "GET",
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                "Riwayat percakapan tidak dapat dimuat dari server."
            );
        }

        const result = await response.json();

        const messages = Array.isArray(result.messages)
            ? result.messages
            : [];

        messagesContainer.replaceChildren();

        const validMessages = messages.filter((message) => {
            return (
                message &&
                ["user", "assistant"].includes(message.role) &&
                typeof message.content === "string"
            );
        });

        validMessages.forEach((message) => {
            addMessage(
                message.role,
                message.content,
                false
            );
        });

        updateWelcomeScreen(validMessages.length > 0);

        if (validMessages.length > 0) {
            scrollToBottom("auto");
        }
    }


    // ---------- 8. INPUT PESAN ----------

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


    messageInput.addEventListener(
        "input",
        resizeInput
    );


    // Enter = kirim pesan.
    // Shift + Enter = baris baru.
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


    // ---------- 9. MENGIRIM PESAN KE IONA ----------

    let isSending = false;
    
    
    function showMemoryNotice(memoryAction) {
        if (!memoryAction) {
            return;
        }

        let noticeText = "";

        if (
            memoryAction.action === "auto_add" &&
            memoryAction.saved
        ) {
            noticeText = "Memori jangka panjang tersimpan otomatis.";
        } else if (
            memoryAction.action === "add" &&
            memoryAction.saved
        ) {
            noticeText = "Memori jangka panjang berhasil disimpan.";
        } else if (
            memoryAction.action === "clear" &&
            memoryAction.saved
        ) {
            noticeText = "Semua memori jangka panjang telah dihapus.";
        } else if (
            memoryAction.action === "delete" &&
            memoryAction.saved
        ) {
            noticeText =
                `${memoryAction.removed} memori berhasil dihapus.`;
        }

        if (!noticeText) {
            return;
        }

        const notice = document.createElement("div");

        notice.className = "memory-notice";
        notice.setAttribute("role", "status");
        notice.textContent = `♧ ${noticeText}`;

        messagesContainer.appendChild(notice);

        scrollToBottom();
    }

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

        updateWelcomeScreen(true);

        // Tampilkan pesan dengan segera.
        // Pesan akan disimpan oleh server setelah AI berhasil menjawab.
        addMessage("user", text);

        messageInput.value = "";
        resetInputHeight();

        const typingElement = showTypingIndicator();

        try {
            const response = await fetch(
                "/api/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        message: text,
                        systemPrompt: SYSTEM_MESSAGE.content
                    })
                }
            );

            let result;

            try {
                result = await response.json();
            } catch {
                throw new Error(
                    "Server tidak memberikan respons JSON yang valid."
                );
            }

            if (!response.ok) {
                throw new Error(
                    result.error ||
                    "Iona gagal memproses pesan."
                );
            }

            const reply = result.message?.content;

            if (
                typeof reply !== "string" ||
                !reply.trim()
            ) {
                throw new Error(
                    "Iona menerima jawaban kosong dari Ollama."
                );
            }

            typingElement.remove();

            addMessage(
                "assistant",
                reply
            );

            showMemoryNotice(result.memoryAction);

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

            addMessage(
                "assistant",

                "Maaf, brow. Aku belum berhasil memproses pesanmu.\n\n" +
                error.message +
                "\n\nPeriksa apakah Ollama dan server.py masih berjalan.",

                true,
                true
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


    // ---------- 10. FORM DAN KARTU SARAN ----------

    chatForm.addEventListener("submit", (event) => {
        event.preventDefault();
        sendMessage(messageInput.value);
    });


    document.querySelectorAll(".suggestion-card").forEach((button) => {
        button.addEventListener("click", () => {
            const prompt = button.dataset.prompt;

            if (prompt) {
                sendMessage(prompt);
            }
        });
    });


    // ---------- 11. MULAI APLIKASI ----------

    async function initializeIona() {
        try {
            await migrateOldBrowserHistory();
            await restoreConversation();

        } catch (error) {
            console.error(
                "Iona: Riwayat percakapan gagal dimuat.",
                error
            );

            setConnectionStatus(
                "warning",
                "Riwayat belum dapat dimuat"
            );
        }

        await checkConnection();

        messageInput.focus();

        console.log(
            `Iona siap digunakan dengan model ${MODEL_NAME}.`
        );
    }


    initializeIona();

})();
