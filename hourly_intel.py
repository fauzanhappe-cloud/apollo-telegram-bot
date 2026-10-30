import os
import json
import time
import re
from datetime import datetime
import xml.etree.ElementTree as ET
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

def get_live_rss_item(feed_url, fallback_title, fallback_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(feed_url, headers=headers, timeout=10)
        root = ET.fromstring(r.content)
        item = root.find(".//item")
        if item is not None:
            title = item.find("title").text if item.find("title") is not None else fallback_title
            link = item.find("link").text if item.find("link") is not None else fallback_url
            desc = item.find("description").text if item.find("description") is not None else ""
            clean_desc = re.sub(r'<[^>]+>', ' ', desc).strip()
            return {
                "title": title.strip(),
                "link": link.strip(),
                "desc": clean_desc
            }
    except Exception as e:
        print(f"RSS Fetch Error: {e}")
    return {"title": fallback_title, "link": fallback_url, "desc": ""}

def ask_gemini_critical(topic_name, news_item):
    prompt = f"""
Anda adalah Senior Critical Analyst & Intelligence Specialist.
Tugas Anda: Membedah artikel berita nyata ini secara kritis, objektif, bebas bias, dan berbasis logika.

Materi Berita Nyata (Terverifikasi dari Live RSS):
Topik: {topic_name}
Judul: {news_item['title']}
URL Asli: {news_item['link']}
Ringkasan: {news_item['desc']}

Formatkan dalam 5 Pilar Berpikir Kritis:
📡 1. Sinyal Utama (The Signal): Fakta konkret atau peristiwa terverifikasi dari artikel.
⚙️ 2. Mekanisme & Akar Masalah: Mengapa ini terjadi dan regulasi/teknis di baliknya.
🔍 3. Uji Kritis & Titik Buta (Blind Spots): Dekonstruksi framing media, bias yang ada, dan fakta yang terabaikan.
🌊 4. Dampak Turunan (Second-Order Effects): Konsekuensi jangka panjang ke sektor terkait.
💡 5. Sudut Pandang Analis (Analyst Lens): 1 prinsip rasional / mental model.

Formatkan dengan tag HTML rapi (<b>, <i>). Di akhir analisis, WAJIB sertakan link artikel riil ini:
🔗 <b>Akses Berita Lengkap:</b>
<a href="{news_item['link']}">{news_item['link']}</a>
"""
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gemini-3.5-flash-lite",
        "input": prompt
    }
    try:
        r = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=25)
        data = r.json()
        out = ""
        for s in data.get("steps", []):
            if s.get("type") == "model_output":
                for c in s.get("content", []):
                    if "text" in c:
                        out += c["text"]
        return out.strip()
    except Exception as e:
        return f"Gagal analisis: {e}"

def send_telegram(text):
    if len(text) > 4000:
        text = text[:3990] + "\n..."
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(TELEGRAM_API_URL, json=payload, timeout=10)
        if not r.json().get("ok"):
            payload.pop("parse_mode", None)
            requests.post(TELEGRAM_API_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send: {e}")

def run_hourly_intelligence():
    now_str = datetime.now().strftime("%d %b %Y | %H:00 WIB")
    print(f"Running Grounded Hourly Intelligence for {now_str}...")

    # 1. AI Global (TechCrunch AI RSS)
    news1 = get_live_rss_item(
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "AWS AI Capex & Enterprise Expansion",
        "https://techcrunch.com/category/artificial-intelligence/"
    )
    analysis1 = ask_gemini_critical("AI Global", news1)
    msg1 = f"🧭 <b>STRATEGIC BRIEFING [1/3]</b>\n🤖 <b>POKOK 1: ARTIFICIAL INTELLIGENCE (GLOBAL)</b>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis1}"
    send_telegram(msg1)
    time.sleep(2)

    # 2. Audit Keuangan Negara RI (Google News Audit / APBN RSS)
    news2 = get_live_rss_item(
        "https://news.google.com/rss/search?q=BPK+BPKP+Kejaksaan+KPK+APBN&hl=id&gl=ID&ceid=ID:id",
        "Pemeriksaan Keuangan Negara & Audit APBN",
        "https://www.bpk.go.id/news"
    )
    analysis2 = ask_gemini_critical("Audit Keuangan RI", news2)
    msg2 = f"🧭 <b>STRATEGIC BRIEFING [2/3]</b>\n⚖️ <b>POKOK 2: AUDIT KEUANGAN NEGARA (RI)</b>\n🏛️ <i>BPK RI • BPKP • Kejaksaan RI • KPK</i>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis2}"
    send_telegram(msg2)
    time.sleep(2)

    # 3. Saham BEI (CNBC Indonesia Market RSS)
    news3 = get_live_rss_item(
        "https://www.cnbcindonesia.com/market/rss",
        "Dinamika Pasar Modal IHSG & Saham Perbankan",
        "https://www.cnbcindonesia.com/market"
    )
    analysis3 = ask_gemini_critical("Saham BEI", news3)
    msg3 = f"🧭 <b>STRATEGIC BRIEFING [3/3]</b>\n📈 <b>POKOK 3: PASAR SAHAM BEI & ARUS DANA</b>\n📊 <i>IHSG • Likuiditas Asing • Saham Penggerak</i>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis3}"
    send_telegram(msg3)
    print("All 3 grounded briefings sent successfully!")

if __name__ == "__main__":
    run_hourly_intelligence()
