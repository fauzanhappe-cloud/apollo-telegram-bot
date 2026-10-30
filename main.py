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

def send_telegram_message(chat_id, text):
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    
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
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML"
        }
        if idx == len(chunks) - 1:
            payload["reply_markup"] = keyboard

        try:
            r = requests.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json=payload,
                timeout=10
            )
            if not r.json().get("ok"):
                # Fallback without parse_mode if HTML entities failed
                payload.pop("parse_mode", None)
                requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send message: {e}")

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

    if AUTHORIZED_CHAT_ID and chat_id != str(AUTHORIZED_CHAT_ID).strip():
        return jsonify({"ok": True}), 200

    # 1. Command Dasar
    if text.lower() == "/start":
        welcome = (
            f"👋 Halo {user_name}!\n\n"
            "Saya <b>Apollo Bot</b> yang berjalan 24 jam nonstop di Cloud (Vercel) "
            "ditenagai <b>Gemini 3.5 Flash Lite</b>! 🧠⚡\n\n"
            "• 🧠 <b>Analisis Kritis</b>: <code>/analisis [topik/link]</code>\n"
            "• 🌐 <b>Web Reader</b>: Kirim link artikel web apa saja\n"
            "• 🌦️ <b>Cuaca Live</b>: <code>Cuaca di Nabire</code>\n"
            "• 💬 <b>Chat AI Cerdas</b>: Bebas tanya apa saja"
        )
        send_telegram_message(chat_id, welcome)
        return jsonify({"ok": True}), 200

    if text.lower() in ["/ping", "🏓 ping bot"]:
        send_telegram_message(chat_id, "🏓 <b>Pong!</b>\n\nBot aktif 24 jam di Vercel Cloud dengan lancar! ☁️✅")
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
