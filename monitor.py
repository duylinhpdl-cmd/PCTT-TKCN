"""
🌀 Storm Monitor Bot - Theo dõi áp thấp / bão Thái Bình Dương → Biển Đông
Nguồn: NCHMF, JTWC, JMA, NHC, VnExpress, 24h, Dân Trí, Tuổi Trẻ, Thanh Niên
Thời gian hiển thị theo giờ Việt Nam (UTC+7)
"""

import os
import json
import requests
import re
import hashlib
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE         = "state.json"

VN_TZ   = timezone(timedelta(hours=7))   # UTC+7 giờ Việt Nam

BIEN_DONG  = {"lat_min": 5,  "lat_max": 25, "lon_min": 100, "lon_max": 125}
WATCH_ZONE = {"lat_min": 5,  "lat_max": 30, "lon_min": 100, "lon_max": 155}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# Từ khoá lọc bài báo tiếng Việt
VN_KEYWORDS = [
    "áp thấp nhiệt đới", "áp thấp", "bão số",
    "cơn bão", "bão nhiệt đới", "bão mạnh",
    "vùng áp thấp", "nhiễu động nhiệt đới",
    "biển đông", "đổ bộ", "ảnh hưởng bão",
    "cảnh báo bão", "tin bão khẩn",
]

# ── Tiện ích ───────────────────────────────────────────────────────────────────
def now_vn():
    """Trả về thời gian hiện tại theo giờ Việt Nam."""
    return datetime.now(VN_TZ)

def fmt_time_vn():
    return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"sent_ids": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

def has_keyword(text):
    t = text.lower()
    return any(kw in t for kw in VN_KEYWORDS)

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Chưa cấu hình — in console:")
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code == 200:
        print("[Telegram] ✅ Đã gửi")
    else:
        print(f"[Telegram] ❌ {r.status_code}: {r.text[:200]}")

def in_watch_zone(lat, lon):
    if lat is None or lon is None:
        return False
    z = WATCH_ZONE
    return z["lat_min"] <= lat <= z["lat_max"] and z["lon_min"] <= lon <= z["lon_max"]

def in_bien_dong(lat, lon):
    if lat is None or lon is None:
        return False
    z = BIEN_DONG
    return z["lat_min"] <= lat <= z["lat_max"] and z["lon_min"] <= lon <= z["lon_max"]

def get_page(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")

# ── Nguồn 1: NCHMF ────────────────────────────────────────────────────────────
def scrape_nchmf():
    alerts = []
    urls = [
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-ap-thap-nhiet-doi-post.html",
    ]
    for url in urls:
        try:
            soup = get_page(url)
            for a in soup.select("a")[:20]:
                text = a.get_text(strip=True)
                href = a.get("href", "")
                if len(text) < 10:
                    continue
                if has_keyword(text):
                    full = href if href.startswith("http") else "https://nchmf.gov.vn" + href
                    alerts.append({"source": "NCHMF 🏛️", "title": text, "url": full,
                                   "id": make_id(text), "lat": None, "lon": None})
        except Exception as e:
            print(f"[NCHMF] {e}")
    return alerts

# ── Nguồn 2: VnExpress ────────────────────────────────────────────────────────
def scrape_vnexpress():
    alerts = []
    # VnExpress RSS thời tiết
    rss_urls = [
        "https://vnexpress.net/rss/thoi-tiet.rss",
        "https://vnexpress.net/rss/tin-tuc-su-kien.rss",
    ]
    for rss in rss_urls:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = (item.findtext("description") or "").strip()
                combined = title + " " + desc
                if has_keyword(combined):
                    alerts.append({
                        "source": "VnExpress 📰",
                        "title": title,
                        "url": link,
                        "id": make_id(title),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[VnExpress] {e}")
    return alerts

# ── Nguồn 3: 24h.com.vn ───────────────────────────────────────────────────────
def scrape_24h():
    alerts = []
    urls = [
        "https://www.24h.com.vn/thoi-tiet-c270.html",
        "https://www.24h.com.vn/tin-tuc-trong-ngay-c46.html",
    ]
    for url in urls:
        try:
            soup = get_page(url)
            # 24h dùng nhiều class khác nhau, tìm tất cả thẻ a có title dài
            for a in soup.find_all("a", href=True):
                text = a.get("title", "") or a.get_text(strip=True)
                href = a.get("href", "")
                if len(text) < 15:
                    continue
                if has_keyword(text):
                    full = href if href.startswith("http") else "https://www.24h.com.vn" + href
                    alerts.append({
                        "source": "24h.com.vn 📡",
                        "title": text[:200],
                        "url": full,
                        "id": make_id(text),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[24h] {e}")
    return alerts

# ── Nguồn 4: Dân Trí ──────────────────────────────────────────────────────────
def scrape_dantri():
    alerts = []
    rss_urls = [
        "https://dantri.com.vn/suc-manh-so.rss",   # fallback
        "https://dantri.com.vn/xa-hoi.rss",
    ]
    # Trang web thường
    web_urls = [
        "https://dantri.com.vn/xa-hoi/thoi-tiet.htm",
    ]
    for rss in rss_urls:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({
                        "source": "Dân Trí 📰",
                        "title": title,
                        "url": link,
                        "id": make_id(title),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[DanTri RSS] {e}")
    for url in web_urls:
        try:
            soup = get_page(url)
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a.get("href", "")
                if len(text) < 15:
                    continue
                if has_keyword(text):
                    full = href if href.startswith("http") else "https://dantri.com.vn" + href
                    alerts.append({
                        "source": "Dân Trí 📰",
                        "title": text[:200],
                        "url": full,
                        "id": make_id(text),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[DanTri web] {e}")
    return alerts

# ── Nguồn 5: Tuổi Trẻ Online ──────────────────────────────────────────────────
def scrape_tuoitre():
    alerts = []
    rss_urls = [
        "https://tuoitre.vn/rss/thoi-su.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    ]
    for rss in rss_urls:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({
                        "source": "Tuổi Trẻ 📰",
                        "title": title,
                        "url": link,
                        "id": make_id(title),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[TuoiTre] {e}")
    return alerts

# ── Nguồn 6: Thanh Niên ───────────────────────────────────────────────────────
def scrape_thanhnien():
    alerts = []
    rss_urls = [
        "https://thanhnien.vn/rss/thoi-su.rss",
        "https://thanhnien.vn/rss/home.rss",
    ]
    for rss in rss_urls:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({
                        "source": "Thanh Niên 📰",
                        "title": title,
                        "url": link,
                        "id": make_id(title),
                        "lat": None, "lon": None,
                    })
        except Exception as e:
            print(f"[ThanhNien] {e}")
    return alerts

# ── Nguồn 7: JTWC RSS ─────────────────────────────────────────────────────────
def scrape_jtwc():
    alerts = []
    url = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            text  = title + " " + desc
            if not ("WP" in title or "WESTERN PACIFIC" in text.upper()):
                continue
            lat, lon = parse_coords(text)
            kws = ["TROPICAL DEPRESSION","TROPICAL STORM","TYPHOON","DISTURBANCE","LOW"]
            if any(k in text.upper() for k in kws):
                if in_watch_zone(lat, lon) or (lat is None):
                    alerts.append({"source": "JTWC 🇺🇸", "title": title,
                                   "url": link, "id": make_id(title),
                                   "lat": lat, "lon": lon})
    except Exception as e:
        print(f"[JTWC] {e}")
    return alerts

# ── Nguồn 8: JMA JSON ─────────────────────────────────────────────────────────
def scrape_jma():
    alerts = []
    url = "https://www.jma.go.jp/bosai/typhoon/data/tropicalCyclone.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        storms = data.get("TropicalCyclone", [])
        if isinstance(storms, dict):
            storms = [storms]
        for storm in storms:
            name      = storm.get("name", {}).get("en", "Unknown")
            intensity = storm.get("intensity", {}).get("description", {}).get("en", "")
            pos       = storm.get("currentPosition", {})
            lat       = parse_num(pos.get("latitude", ""))
            lon       = parse_num(pos.get("longitude", ""))
            if not in_watch_zone(lat, lon):
                continue
            direction = storm.get("movement", {}).get("direction", {}).get("en", "")
            title = f"[JMA] {intensity} {name} tại {lat}°N {lon}°E → {direction}"
            alerts.append({
                "source": "JMA 🇯🇵", "title": title,
                "url": "https://www.jma.go.jp/en/typh/",
                "id": make_id(title), "lat": lat, "lon": lon,
                "in_bien_dong": in_bien_dong(lat, lon),
            })
    except Exception as e:
        print(f"[JMA] {e}")
    return alerts

# ── Nguồn 9: NHC/NOAA ────────────────────────────────────────────────────────
def scrape_nhc():
    alerts = []
    try:
        soup = get_page("https://www.nhc.noaa.gov/productlist.shtml")
        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            text = " ".join(c.get_text() for c in cells)
            if any(k in text.upper() for k in ["WESTERN PACIFIC", "WP"]):
                kws = ["DEPRESSION","STORM","TYPHOON","DISTURBANCE"]
                if any(k in text.upper() for k in kws):
                    a = row.find("a")
                    link = ("https://www.nhc.noaa.gov" + a["href"]) if a else ""
                    alerts.append({"source": "NHC/NOAA 🇺🇸", "title": text[:120].strip(),
                                   "url": link, "id": make_id(text[:80]),
                                   "lat": None, "lon": None})
    except Exception as e:
        print(f"[NHC] {e}")
    return alerts

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_coords(text):
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

def parse_num(s):
    m = re.search(r"(\d+\.?\d*)", str(s))
    return float(m.group(1)) if m else None

# ── Format tin nhắn ───────────────────────────────────────────────────────────
def format_alert(alert):
    title   = alert.get("title", "")
    src     = alert.get("source", "?")
    url     = alert.get("url", "")
    lat     = alert.get("lat")
    lon     = alert.get("lon")
    in_bd   = alert.get("in_bien_dong", False)

    # Icon theo mức độ
    t_up = title.upper()
    if any(k in t_up for k in ["TYPHOON", "BÃO SỐ", "CƠN BÃO"]):
        icon = "🌀"
    elif any(k in t_up for k in ["TROPICAL STORM", "BÃO NHIỆT ĐỚI", "BÃO MẠNH"]):
        icon = "🌪️"
    elif any(k in t_up for k in ["DEPRESSION", "ÁP THẤP NHIỆT ĐỚI"]):
        icon = "⚠️"
    elif any(k in t_up for k in ["ÁP THẤP", "VÙNG ÁP THẤP"]):
        icon = "🔵"
    else:
        icon = "📢"

    zone = ""
    if in_bd:
        zone = "\n🇻🇳 <b>ĐANG Ở BIỂN ĐÔNG</b> — nguy cơ ảnh hưởng trực tiếp!"
    elif lat and lon:
        zone = f"\n📍 Vị trí: {lat:.1f}°N, {lon:.1f}°E"

    msg = (
        f"{icon} <b>CẢNH BÁO THỜI TIẾT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 Nguồn: <b>{src}</b>\n"
        f"🕐 {fmt_time_vn()}\n"
        f"📋 {title}"
        f"{zone}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    if url:
        msg += f"\n🔗 <a href='{url}'>Xem chi tiết</a>"
    return msg

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))

    all_alerts = []
    all_alerts += scrape_nchmf()
    all_alerts += scrape_vnexpress()
    all_alerts += scrape_24h()
    all_alerts += scrape_dantri()
    all_alerts += scrape_tuoitre()
    all_alerts += scrape_thanhnien()
    all_alerts += scrape_jtwc()
    all_alerts += scrape_jma()
    all_alerts += scrape_nhc()

    print(f"[Bot] Tổng tìm thấy: {len(all_alerts)} mục")

    new_sent = []
    for alert in all_alerts:
        aid = alert["id"]
        if aid in sent_ids:
            continue
        print(f"[Bot] 🚨 Gửi: {alert['title'][:70]}")
        send_telegram(format_alert(alert))
        new_sent.append(aid)

    if not new_sent:
        print("[Bot] ✅ Không có cảnh báo mới.")

    state["sent_ids"] = (list(sent_ids) + new_sent)[-300:]
    state["last_run_vn"] = fmt_time_vn()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Xong.")

if __name__ == "__main__":
    main()
