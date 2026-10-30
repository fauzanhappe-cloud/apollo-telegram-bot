import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfigurasi dari Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
AUTHORIZED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# Memory percakapan sementara per sesi
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
            ["🔄 Reset Sesi AI", "🏓 Ping Bot"],
            ["❓ Bantuan"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

    for idx, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk
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

def ask_gemini_ai(prompt, prev_id=None):
    if not GEMINI_API_KEY:
        return "⚠️ GEMINI_API_KEY belum dikonfigurasi.", prev_id

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gemini-3.8-flash",
        "input": prompt
    }
    if prev_id:
        payload["previous_interaction_id"] = prev_id

    try:
        res = requests.post(
            GEMINI_INTERACTIONS_URL,
            headers=headers,
            json=payload,
            timeout=30
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
        print(f"[ERROR] Gemini request error: {e}")
        return f"⚠️ Terjadi kendala menghubungi Gemini AI: {e}", prev_id

@app.route("/", methods=["GET"])
def index():
    return "✅ Apollo Telegram Bot (Cloud Run) is running 24/7!", 200

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

    # Keamanan: Hanya layani chat_id pemilik
    if AUTHORIZED_CHAT_ID and chat_id != str(AUTHORIZED_CHAT_ID):
        print(f"[ACCESS DENIED] Unauthorized chat_id: {chat_id}")
        return jsonify({"ok": True}), 200

    # Command Handling
    if text.lower() == "/start":
        welcome = (
            f"👋 Halo {user_name}!\n\n"
            "Saya Apollo Bot yang berjalan di Google Cloud Run (Aktif 24 Jam Nonstop) "
            "ditenagai Gemini 3.8 Flash! 🧠☁️\n\n"
            "Anda bisa bertanya, berdiskusi, atau meminta bantuan apa saja langsung di sini!"
        )
        send_telegram_message(chat_id, welcome)
        return jsonify({"ok": True}), 200

    if text.lower() in ["/ping", "🏓 ping bot"]:
        send_telegram_message(chat_id, "🏓 Pong!\n\nBot aktif 24 jam di Google Cloud Run dengan lancar. ✅")
        return jsonify({"ok": True}), 200

    if text.lower() in ["/reset", "🔄 reset sesi ai"]:
        user_sessions.pop(chat_id, None)
        send_telegram_message(chat_id, "🔄 Sesi AI telah di-reset! Kita mulai percakapan baru.")
        return jsonify({"ok": True}), 200

    if text.lower() in ["/help", "❓ bantuan"]:
        help_text = (
            "📖 PANDUAN PENGGUNAAN BOT (CLOUD RUN)\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🧠 Chat AI Cerdas:\n"
            "Ketik pertanyaan apa saja dan Gemini 3.8 Flash akan membalas.\n\n"
            "⚡ Menu Cepat:\n"
            "• 🏓 Ping Bot (/ping) : Cek status server cloud\n"
            "• 🔄 Reset Sesi AI (/reset) : Hapus memori percakapan lama\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(chat_id, help_text)
        return jsonify({"ok": True}), 200

    # Chat AI via Gemini
    send_chat_action(chat_id, "typing")
    prev_interaction_id = user_sessions.get(chat_id)
    answer, new_interaction_id = ask_gemini_ai(text, prev_interaction_id)

    if new_interaction_id:
        user_sessions[chat_id] = new_interaction_id

    send_telegram_message(chat_id, answer)
    return jsonify({"ok": True}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
