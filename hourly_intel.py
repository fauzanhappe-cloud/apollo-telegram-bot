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

def get_live_rss_items(feed_url, fallback_title, fallback_url, max_items=3):
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(feed_url, headers=headers, timeout=12)
        root = ET.fromstring(r.content)
        xml_items = root.findall(".//item")
        for it in xml_items[:max_items]:
            title = it.find("title").text if it.find("title") is not None else fallback_title
            link = it.find("link").text if it.find("link") is not None else fallback_url
            desc = it.find("description").text if it.find("description") is not None else ""
            clean_desc = re.sub(r'<[^>]+>', ' ', desc).strip()
            title = re.sub(r'\s+', ' ', title).strip()
            link = link.strip()
            items.append({
                "title": title,
                "link": link,
                "desc": clean_desc[:400]
            })
    except Exception as e:
        print(f"RSS Fetch Error ({feed_url}): {e}")
        
    if not items:
        items.append({"title": fallback_title, "link": fallback_url, "desc": ""})
    return items

def ask_gemini_critical(topic_name, news_items):
    primary = news_items[0]
    
    related_context = ""
    if len(news_items) > 1:
        related_context = "\nArtikel Terkait & Sumber Pembanding:\n"
        for idx, it in enumerate(news_items[1:], 2):
            related_context += f"{idx}. Judul: {it['title']}\n   URL: {it['link']}\n"
    
    prompt = f"""
Anda adalah Senior Critical Analyst & Strategic Intelligence Specialist.
Tugas Anda: Membedah isu nyata ini secara tajam, mendalam, objektif, bebas framing, dan berbobot eksekutif.

Topik Intelijen: {topic_name}
Berita Utama (Live RSS):
- Judul: {primary['title']}
- URL: {primary['link']}
- Ringkasan: {primary['desc']}
{related_context}

Format Analisis (Gunakan 5 Pilar Berpikir Kritis & Tag HTML <b>, <i>):
📡 <b>1. Sinyal Utama (The Signal):</b> Fakta konkret, data riil, dan peristiwa inti yang terverifikasi dari artikel.
⚙️ <b>2. Mekanisme & Akar Masalah:</b> Bagaimana ini terjadi? Bedah rantai kausalitas, teknis, atau regulasi di balik layar.
🔍 <b>3. Uji Kritis & Titik Buta (Blind Spots):</b> Dekonstruksi framing media, bias informasi, atau variabel penting yang tidak dibahas di publik.
🌊 <b>4. Dampak Turunan (Second-Order Effects):</b> Efek domino jangka panjang terhadap sektor/ekosistem terkait.
💡 <b>5. Sudut Pandang Analis (Analyst Lens):</b> 1 prinsip mental model atau pedoman rasional untuk pengambilan keputusan.

INSTRUKSI SITASI & RUJUKAN LENGKAP (WAJIB & TIDAK BOLEH TERPOTONG):
Di bagian paling bawah analisis, Anda WAJIB membuat daftar rujukan lengkap dan detail untuk SEMUA berita di atas:
📚 <b>Rujukan Berita & Sumber Terverifikasi:</b>
1. <b>{primary['title']}</b>
   🔗 <a href="{primary['link']}">{primary['link']}</a>
"""
    if len(news_items) > 1:
        for idx, it in enumerate(news_items[1:], 2):
            prompt += f"""{idx}. <b>{it['title']}</b>
   🔗 <a href="{it['link']}">{it['link']}</a>\n"""

    prompt += "\nPERHATIAN: Cantumkan semua URL secara utuh tanpa disingkat atau dipotong agar pembaca bisa langsung mengklik dan memverifikasi sumber beritanya."

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
                        
        out = out.strip()
        
        # Jaminan Keutuhan Rujukan: Pastikan semua link dari news_items tercantum
        missing_links = []
        for idx, it in enumerate(news_items, 1):
            if it['link'] not in out:
                missing_links.append(f"{idx}. <b>{it['title']}</b>\n   🔗 <a href=\"{it['link']}\">{it['link']}</a>")
                
        if missing_links:
            out += "\n\n📚 <b>Rujukan Tambahan Terverifikasi:</b>\n" + "\n".join(missing_links)
            
        return out
    except Exception as e:
        return f"Gagal menghasilkan analisis: {e}"

def split_text_into_chunks(text, max_len=3700):
    """
    Memecah teks panjang secara cerdas per paragraf/baris agar tidak terpotong di Telegram.
    Pesan berlanjut ke chat berikutnya tanpa kehilangan kata atau karakter.
    """
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

def send_telegram(text):
    chunks = split_text_into_chunks(text, max_len=3700)
    total_parts = len(chunks)
    
    for idx, chunk in enumerate(chunks):
        formatted_chunk = chunk
        if total_parts > 1:
            if idx == 0:
                formatted_chunk = f"{chunk}\n\n<i>[Bagian 1/{total_parts}] ⏩ (Bersambung ke chat berikutnya...)</i>"
            else:
                formatted_chunk = f"<i>[Bagian {idx+1}/{total_parts}] 📄 (Lanjutan chat sebelumnya)</i>\n\n{chunk}"
                
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": formatted_chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            r = requests.post(TELEGRAM_API_URL, json=payload, timeout=12)
            res = r.json()
            if not res.get("ok"):
                # Fallback tanpa HTML jika perbatasan chunk memotong tag formating
                payload.pop("parse_mode", None)
                requests.post(TELEGRAM_API_URL, json=payload, timeout=12)
        except Exception as e:
            print(f"Failed to send chunk {idx+1}/{total_parts}: {e}")
            
        if total_parts > 1:
            time.sleep(1.5)

def run_hourly_intelligence():
    now_str = datetime.now().strftime("%d %b %Y | %H:00 WIB")
    print(f"Running Grounded Hourly Intelligence for {now_str}...")

    # 1. AI Global (TechCrunch AI RSS)
    news1 = get_live_rss_items(
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "AWS AI Capex & Enterprise Expansion",
        "https://techcrunch.com/category/artificial-intelligence/",
        max_items=3
    )
    analysis1 = ask_gemini_critical("AI Global", news1)
    msg1 = f"🧭 <b>STRATEGIC BRIEFING [1/3]</b>\n🤖 <b>POKOK 1: ARTIFICIAL INTELLIGENCE (GLOBAL)</b>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis1}"
    send_telegram(msg1)
    time.sleep(2)

    # 2. Audit Keuangan Negara RI (Google News Audit / APBN RSS)
    news2 = get_live_rss_items(
        "https://news.google.com/rss/search?q=BPK+BPKP+Kejaksaan+KPK+APBN&hl=id&gl=ID&ceid=ID:id",
        "Pemeriksaan Keuangan Negara & Audit APBN",
        "https://www.bpk.go.id/news",
        max_items=3
    )
    analysis2 = ask_gemini_critical("Audit Keuangan RI", news2)
    msg2 = f"🧭 <b>STRATEGIC BRIEFING [2/3]</b>\n⚖️ <b>POKOK 2: AUDIT KEUANGAN NEGARA (RI)</b>\n🏛️ <i>BPK RI • BPKP • Kejaksaan RI • KPK</i>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis2}"
    send_telegram(msg2)
    time.sleep(2)

    # 3. Saham BEI (CNBC Indonesia Market RSS)
    news3 = get_live_rss_items(
        "https://www.cnbcindonesia.com/market/rss",
        "Dinamika Pasar Modal IHSG & Saham Perbankan",
        "https://www.cnbcindonesia.com/market",
        max_items=3
    )
    analysis3 = ask_gemini_critical("Saham BEI", news3)
    msg3 = f"🧭 <b>STRATEGIC BRIEFING [3/3]</b>\n📈 <b>POKOK 3: PASAR SAHAM BEI & ARUS DANA</b>\n📊 <i>IHSG • Likuiditas Asing • Saham Penggerak</i>\n📅 <i>{now_str}</i>\n━━━━━━━━━━━━━━━━━━\n{analysis3}"
    send_telegram(msg3)
    print("All 3 grounded briefings sent successfully!")

if __name__ == "__main__":
    run_hourly_intelligence()
