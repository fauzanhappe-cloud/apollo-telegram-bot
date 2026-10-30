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

def clean_text_for_telegram(text):
    """
    Membersihkan total seluruh tag HTML (seperti <b>, </b>, <i>, <a>, dll)
    dan format mentah agar chat Telegram selalu tampil bersih, rapi, dan elegan.
    """
    if not text:
        return ""
    # Hapus semua tag HTML kurung siku <...>
    cleaned = re.sub(r'</?[a-zA-Z][^>]*>', '', text)
    # Hapus markdown asterisks ** atau *
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'\1', cleaned)
    # Kembalikan entitas HTML ke karakter normal
    cleaned = cleaned.replace('&amp;', '&').replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
    return cleaned.strip()

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
    
    # Audit Trail special injection for Pillar 2 (Audit Keuangan RI)
    audit_guide = ""
    if "Audit" in topic_name:
        audit_guide = """
PEDOMAN KHUSUS AUDIT TRAILS (STANDAR SPKN & UU PERBENDAHARAAN NEGARA):
- Uji Jejak Audit (Audit Trail): Telusuri apakah ada indikasi putusnya jejak dokumen (DIPA -> BAST -> SPM -> SP2D).
- Deteksi Titik Kritis: Soroti potensi manipulasi termin, pencairan mendahului prestasi kerja, atau penyimpangan rekening tujuan.
"""

    citation_list = ""
    for idx, it in enumerate(news_items, 1):
        citation_list += f"{idx}. {it['title']}\n   🔗 {it['link']}\n"

    prompt = f"""
Anda adalah Senior Critical Analyst, Audit Specialist & Strategic Intelligence Specialist.
Tugas Anda: Membedah isu nyata ini secara mendalam, objektif, tanpa bias, dan berbobot eksekutif.

Topik Intelijen: {topic_name}
Berita Utama (Live RSS):
- Judul: {primary['title']}
- URL: {primary['link']}
- Ringkasan: {primary['desc']}
{related_context}
{audit_guide}

Format Analisis Wajib (Gunakan 5 Pilar Berpikir Kritis):
📡 1. SINYAL UTAMA (THE SIGNAL): Fakta konkret, angka riil, dan peristiwa inti yang terverifikasi dari artikel.
⚙️ 2. MEKANISME & AKAR MASALAH: Bagaimana ini terjadi? Bedah rantai kausalitas, regulasi, tata kelola, atau audit trail di baliknya.
🔍 3. UJI KRITIS & TITIK BUTA (BLIND SPOTS): Dekonstruksi framing media, bias informasi, atau variabel penting yang tidak dibahas di publik.
🌊 4. DAMPAK TURUNAN (SECOND-ORDER EFFECTS): Efek domino jangka panjang terhadap sektor/ekosistem terkait atau keuangan negara.
💡 5. SUDUT PANDANG ANALIS (ANALYST LENS): 1 prinsip mental model atau pedoman rasional pengambilan keputusan.

INSTRUKSI RUJUKAN LENGKAP:
Di akhir analisis, Anda WAJIB membuat daftar rujukan lengkap dan detail untuk SEMUA berita di atas:
📚 RUJUKAN BERITA & SUMBER TERVERIFIKASI:
{citation_list}

ATURAN FORMATTING WAJIB (SANGAT PENTING):
1. DILARANG KERAS menggunakan tag HTML seperti <b>, </b>, <i>, </i>, <a>, </a>, <br> atau tanda kurung sudut < > apapun!
2. Gunakan huruf kapital, emoji, dan bullet point (•) untuk penataan teks agar mudah dibaca di layar HP.
3. Seluruh URL ditulis langsung bersih (contoh: 🔗 https://...) tanpa dibungkus tag HTML.
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
                        
        out = clean_text_for_telegram(out.strip())
        
        # Jaminan Keutuhan Rujukan: Pastikan semua link dari news_items tercantum
        missing_links = []
        for idx, it in enumerate(news_items, 1):
            if it['link'] not in out:
                missing_links.append(f"{idx}. {it['title']}\n   🔗 {it['link']}")
                
        if missing_links:
            out += "\n\n📚 RUJUKAN TAMBAHAN TERVERIFIKASI:\n" + "\n".join(missing_links)
            
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
    clean_text = clean_text_for_telegram(text)
    chunks = split_text_into_chunks(clean_text, max_len=3700)
    total_parts = len(chunks)
    
    for idx, chunk in enumerate(chunks):
        formatted_chunk = chunk
        if total_parts > 1:
            if idx == 0:
                formatted_chunk = f"{chunk}\n\n[Bagian 1/{total_parts}] ⏩ (Bersambung ke chat berikutnya...)"
            else:
                formatted_chunk = f"[Bagian {idx+1}/{total_parts}] 📄 (Lanjutan chat sebelumnya)\n\n{chunk}"
                
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": formatted_chunk,
            "disable_web_page_preview": False
        }
        try:
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
    msg1 = f"🧭 STRATEGIC BRIEFING [1/3]\n🤖 POKOK 1: ARTIFICIAL INTELLIGENCE (GLOBAL)\n📅 {now_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{analysis1}"
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
    msg2 = f"🧭 STRATEGIC BRIEFING [2/3]\n⚖️ POKOK 2: AUDIT KEUANGAN NEGARA (RI)\n🏛️ BPK RI • BPKP • Kejaksaan RI • KPK\n📅 {now_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{analysis2}"
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
    msg3 = f"🧭 STRATEGIC BRIEFING [3/3]\n📈 POKOK 3: PASAR SAHAM BEI & ARUS DANA\n📊 IHSG • Likuiditas Asing • Saham Penggerak\n📅 {now_str}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{analysis3}"
    send_telegram(msg3)
    print("All 3 grounded briefings sent successfully!")

if __name__ == "__main__":
    run_hourly_intelligence()
