import os
import json
import re
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfigurasi dari Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

user_sessions = {}

def send_chat_action(chat_id, action="typing"):
    try:
        requests.post(
            f"{TELEGRAM_API_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=5
        )
    except Exception:
        pass

def clean_text_for_telegram(text):
    if not text:
        return ""
    cleaned = re.sub(r'</?[a-zA-Z][^>]*>', '', text)
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'\1', cleaned)
    cleaned = cleaned.replace('&amp;', '&').replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
    return cleaned.strip()

def split_text_into_chunks(text, max_len=3700):
    if len(text) <= max_len:
        return [text]
    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""
    for p in paragraphs:
        if len(p) > max_len:
            lines = p.split("\n")
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_len:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
        else:
            if len(current_chunk) + len(p) + 2 > max_len:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
            else:
                current_chunk += p + "\n\n"
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks

def send_telegram_message(chat_id, text):
    clean_text = clean_text_for_telegram(text)
    chunks = split_text_into_chunks(clean_text, max_len=3700)
    total_parts = len(chunks)
    
    keyboard = {
        "keyboard": [
            ["🧠 Analisis Kritis", "🌦️ Cuaca Nabire"],
            ["⏰ Jam & Waktu", "🔄 Reset Sesi AI"],
            ["❓ Bantuan"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

    for idx, chunk in enumerate(chunks):
        formatted_chunk = chunk
        if total_parts > 1:
            if idx == 0:
                formatted_chunk = f"{chunk}\n\n[Bagian 1/{total_parts}] ⏩ (Bersambung...)"
            else:
                formatted_chunk = f"[Bagian {idx+1}/{total_parts}] 📄 (Lanjutan)\n\n{chunk}"

        payload = {
            "chat_id": chat_id,
            "text": formatted_chunk
        }
        if idx == len(chunks) - 1:
            payload["reply_markup"] = keyboard

        try:
            requests.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json=payload,
                timeout=10
            )
        except Exception as e:
            print(f"[ERROR] Failed to send message: {e}")
        if total_parts > 1:
            time.sleep(1)

def get_webpage_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        text = r.text
        # Remove script and style tags
        text = re.sub(r'(?is)<script.*?</script>', '', text)
        text = re.sub(r'(?is)<style.*?</style>', '', text)
        text = re.sub(r'(?is)<noscript.*?</noscript>', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:5000]
    except Exception as e:
        return f"Gagal membaca URL ({url}): {e}"

def get_live_weather(city="Nabire"):
    try:
        r = requests.get(f"https://wttr.in/{city}?format=%l:+%c+%t,+kelembaban+%h,+angin+%w", timeout=5)
        if r.status_code == 200 and "Unknown location" not in r.text:
            return r.text.strip()
        return f"{city}: Cuaca sedang tidak dapat diakses."
    except Exception:
        return f"{city}: Data cuaca belum tersedia."

def ask_gemini_ai(prompt, prev_id=None):
    if not GEMINI_API_KEY:
        return "⚠️ GEMINI_API_KEY belum dikonfigurasi.", prev_id

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gemini-3.5-flash-lite",
        "input": prompt
    }
    if prev_id:
        payload["previous_interaction_id"] = prev_id

    try:
        res = requests.post(
            GEMINI_INTERACTIONS_URL,
            headers=headers,
            json=payload,
            timeout=9
        )
        data = res.json()
        
        output_text = ""
        for step in data.get("steps", []):
            if step.get("type") == "model_output":
                for c in step.get("content", []):
                    if "text" in c:
                        output_text += c["text"]
                        
        if not output_text:
            output_text = "Maaf, tidak dapat menghasilkan jawaban saat ini."
            
        return output_text, data.get("id")
    except Exception as e:
        # Retry without previous_interaction_id
        if prev_id:
            return ask_gemini_ai(prompt, prev_id=None)
        return f"⚠️ Terjadi kendala menghubungi Gemini AI: {e}", None

def invoke_critical_analysis(topic, source_url=None):
    system_instruction = (
        "Anda adalah Apollo Agent - Senior Critical Analyst & Strategic Thinker.\n"
        "Tugas Anda: membedah masalah secara objektif, bebas bias, dan berbasis logika.\n\n"
        "Kerangka Analisis Kritis:\n"
        "🎯 1. DEKONSTRUKSI INTI PERMASALAHAN & ASUMSI DASAR\n"
        "⚖️ 2. EVALUASI DIALEKTIKA (PRO & KONTRA SECARA JUJUR)\n"
        "🔍 3. TITIK BUTA (BLIND SPOTS) & DETEKSI POTENSI BIAS / FRAMING\n"
        "⚠️ 4. ANALISIS DAMPAK TURUNAN (SECOND-ORDER EFFECTS)\n"
        "💡 5. KESIMPULAN STRATEGIS & REKOMENDASI SOLUTIF\n"
    )
    prompt = f"{system_instruction}\n\n--- TOPIK / MATERI ANALISIS ---\n{topic}"
    if source_url:
        prompt += f"\n(Sumber web rujukan: {source_url})"
    
    ans, _ = ask_gemini_ai(prompt, prev_id=None)
    return ans

@app.route("/", methods=["GET"])
def index():
    return "✅ Apollo Telegram Bot (Vercel 24/7 Cloud) is running!", 200

@app.route("/diag", methods=["GET"])
def diag():
    token_status = "OK (Terbaca)" if TELEGRAM_BOT_TOKEN else "KOSONG (Belum diset di Vercel)"
    gemini_status = "OK (Terbaca)" if GEMINI_API_KEY else "KOSONG (Belum diset di Vercel)"
    chat_status = f"OK ({AUTHORIZED_CHAT_ID})" if AUTHORIZED_CHAT_ID else "TIDAK DIBATASI (Semua chat diterima)"
    return jsonify({
        "status": "online",
        "telegram_bot_token": token_status,
        "gemini_api_key": gemini_status,
        "authorized_chat_id": chat_status
    }), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True)
    if not update or "message" not in update:
        return jsonify({"ok": True}), 200

    msg = update["message"]
    text = msg.get("text", "").strip()
    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_name = msg.get("from", {}).get("first_name", "Pengguna")

    if not text:
        return jsonify({"ok": True}), 200

    # 1. Command Dasar
    if text.lower() == "/start":
        welcome = (
            f"👋 Halo {user_name}!\n\n"
            "Saya Apollo Bot yang berjalan 24 jam nonstop di Cloud (Vercel) "
            "ditenagai Gemini 3.5 Flash Lite! 🧠⚡\n\n"
            "• 🧠 Analisis Kritis: /analisis [topik/link]\n"
            "• 🌐 Web Reader: Kirim link artikel web apa saja\n"
            "• 🌦️ Cuaca Live: Cuaca di Nabire\n"
            "• 💬 Chat AI Cerdas: Bebas tanya apa saja langsung di sini!"
        )
        send_telegram_message(chat_id, welcome)
        return jsonify({"ok": True}), 200

    if text.lower() in ["/ping", "🏓 ping bot", "ping"]:
        send_telegram_message(chat_id, "🏓 Pong!\n\nBot aktif 24 jam di Vercel Cloud dengan lancar! ☁️✅")
        return jsonify({"ok": True}), 200

    if text.lower() in ["/reset", "🔄 reset sesi ai"]:
        user_sessions.pop(chat_id, None)
        send_telegram_message(chat_id, "🔄 Sesi AI telah di-reset! Kita mulai topik baru.")
        return jsonify({"ok": True}), 200

    if text.lower() in ["/help", "❓ bantuan"]:
        help_text = (
            "📖 <b>PANDUAN APOLLO BOT (24/7 CLOUD)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🧠 <b>Analisis Kritis:</b>\n"
            "Ketik <code>/analisis [topik/link]</code> untuk bedah masalah 5 pilar.\n\n"
            "🌐 <b>Baca Website:</b>\n"
            "Kirim tautan https://... untuk dirangkum otomatis.\n\n"
            "🌦️ <b>Cek Cuaca:</b>\n"
            "Ketik <code>Cuaca di Nabire</code> atau <code>/cuaca [kota]</code>.\n\n"
            "💬 <b>Tanya AI:</b>\n"
            "Ketik pertanyaan bebas kapan saja dari HP!\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(chat_id, help_text)
        return jsonify({"ok": True}), 200

    # Menu Tombol: Analisis Kritis
    if text.lower() in ["🧠 analisis kritis", "/analisis"]:
        menu = (
            "🧠 <b>MODE AGEN ANALISIS KRITIS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Ketik perintah:\n"
            "<code>/analisis [topik atau link artikel]</code>\n\n"
            "<b>Contoh:</b>\n"
            "• <code>/analisis Dampak AI terhadap dunia pendidikan</code>\n"
            "• <code>/analisis https://kompas.com/...</code>\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(chat_id, menu)
        return jsonify({"ok": True}), 200

    # Cuaca Nabire Tombol
    if "cuaca nabire" in text.lower():
        send_chat_action(chat_id, "typing")
        weather = get_live_weather("Nabire")
        prompt = f"Data cuaca real-time: {weather}. Berikan laporan cuaca Nabire yang ramah dan informatif."
        ans, _ = ask_gemini_ai(prompt)
        send_telegram_message(chat_id, f"🌦️ {weather}\n\n{ans}")
        return jsonify({"ok": True}), 200

    # 2. Fitur Analisis Kritis (/analisis ...)
    match_analisis = re.match(r'^/(?:analisis|kritis)\s+(.+)$', text, re.I) or re.match(r'^(?:analisis|bedah kritis)\s+(.+)$', text, re.I)
    if match_analisis:
        topic = match_analisis.group(1).strip()
        send_chat_action(chat_id, "typing")
        
        url_match = re.search(r'(https?://[^\s]+)', topic)
        if url_match:
            url = url_match.group(1)
            send_telegram_message(chat_id, f"🔍 <i>Membuka dan menganalisis kritis artikel web: {url}...</i>")
            web_content = get_webpage_text(url)
            analysis = invoke_critical_analysis(web_content, source_url=url)
            send_telegram_message(chat_id, f"🔬 <b>HASIL ANALISIS KRITIS ARTIKEL:</b>\n━━━━━━━━━━━━━━━━━━\n{analysis}")
        else:
            send_telegram_message(chat_id, "🔍 <i>Sedang melakukan bedah analisis kritis mendalam...</i>")
            analysis = invoke_critical_analysis(topic)
            send_telegram_message(chat_id, f"🔬 <b>HASIL BEDAH ANALISIS KRITIS:</b>\n━━━━━━━━━━━━━━━━━━\n{analysis}")
        return jsonify({"ok": True}), 200

    # 3. Fitur Web Reader Otomatis (Jika ada URL)
    url_match = re.search(r'(https?://[^\s]+)', text)
    if url_match:
        url = url_match.group(1)
        send_chat_action(chat_id, "typing")
        send_telegram_message(chat_id, f"🌐 <i>Sedang membaca website: {url}...</i>")
        web_content = get_webpage_text(url)
        prompt = f"Berikut isi artikel dari ({url}):\n\n{web_content}\n\nInstruksi: Rangkum poin-poin penting artikel ini secara jelas dan informatif dalam bahasa Indonesia."
        ans, new_id = ask_gemini_ai(prompt, user_sessions.get(chat_id))
        if new_id:
            user_sessions[chat_id] = new_id
        send_telegram_message(chat_id, f"📄 <b>Ringkasan Website:</b>\n\n{ans}")
        return jsonify({"ok": True}), 200

    # 4. Deteksi Cuaca Otomatis
    if re.search(r'(cuaca|hujan|suhu|derajat).*(nabire|jakarta|surabaya|jayapura|makassar|[a-z]+)', text, re.I):
        send_chat_action(chat_id, "typing")
        city = "Nabire"
        m_city = re.search(r'(?:di|kota)\s+([a-zA-Z]+)', text, re.I)
        if m_city:
            city = m_city.group(1)
        weather = get_live_weather(city)
        prompt = f"Pertanyaan pengguna: '{text}'. Data live cuaca: {weather}. Jawab dengan ramah dan akurat."
        ans, _ = ask_gemini_ai(prompt, user_sessions.get(chat_id))
        send_telegram_message(chat_id, f"🌦️ {weather}\n\n{ans}")
        return jsonify({"ok": True}), 200

    # 5. Chat Biasa via Gemini AI
    send_chat_action(chat_id, "typing")
    prev_id = user_sessions.get(chat_id)
    answer, new_id = ask_gemini_ai(text, prev_id)
    if new_id:
        user_sessions[chat_id] = new_id

    send_telegram_message(chat_id, answer)
    return jsonify({"ok": True}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
