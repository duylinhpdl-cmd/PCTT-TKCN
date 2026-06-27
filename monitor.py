"""
🌀 Storm Monitor Bot - Theo dõi áp thấp / bão Thái Bình Dương → Biển Đông
Chạy trên GitHub Actions (miễn phí), gửi cảnh báo qua Telegram
"""

import os
import json
import requests
import re
import hashlib
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE         = "state.json"   # Lưu trạng thái để không gửi trùng

# Vùng Biển Đông + khu vực có khả năng ảnh hưởng (lon/lat bounding box)
BIEN_DONG = {"lat_min": 5, "lat_max": 25, "lon_min": 100, "lon_max": 125}
# Khu vực Thái Bình Dương "nguy hiểm" (có thể di chuyển vào Biển Đông)
WATCH_ZONE = {"lat_min": 5, "lat_max": 30, "lon_min": 100, "lon_max": 155}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StormMonitorBot/1.0)"}

# ── Tiện ích ───────────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"sent_ids": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Chưa cấu hình token/chat_id — in ra console:")
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
        print("[Telegram] ✅ Đã gửi cảnh báo")
    else:
        print(f"[Telegram] ❌ Lỗi: {r.text}")

def in_watch_zone(lat, lon):
    z = WATCH_ZONE
    return z["lat_min"] <= lat <= z["lat_max"] and z["lon_min"] <= lon <= z["lon_max"]

def in_bien_dong(lat, lon):
    z = BIEN_DONG
    return z["lat_min"] <= lat <= z["lat_max"] and z["lon_min"] <= lon <= z["lon_max"]

# ── Nguồn 1: NCHMF (Trung tâm KTTV Quốc gia VN) ──────────────────────────────
def scrape_nchmf():
    alerts = []
    urls = [
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-ap-thap-nhiet-doi-post.html",
    ]
    keywords = [
        "áp thấp", "áp thấp nhiệt đới", "bão", "cơn bão",
        "vùng áp thấp", "nhiễu động nhiệt đới"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            # Tìm các bản tin mới nhất
            items = soup.select("a.title, h3 a, .post-title a, article a")[:10]
            for item in items:
                text = item.get_text(strip=True)
                href = item.get("href", "")
                if any(kw in text.lower() for kw in keywords):
                    full_url = href if href.startswith("http") else "https://nchmf.gov.vn" + href
                    alerts.append({
                        "source": "NCHMF",
                        "title": text,
                        "url": full_url,
                        "id": make_id(text),
                        "lat": None, "lon": None,
                        "in_zone": True,  # NCHMF chỉ đăng khi ảnh hưởng VN
                    })
        except Exception as e:
            print(f"[NCHMF] Lỗi: {e}")
    return alerts

# ── Nguồn 2: JTWC RSS (Trung tâm Cảnh báo Bão Hải quân Mỹ) ──────────────────
def scrape_jtwc():
    alerts = []
    url = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        root = ET.fromstring(r.content)
        ns = ""
        items = root.findall(f".//{ns}item")
        for item in items:
            title = (item.findtext(f"{ns}title") or "").strip()
            desc  = (item.findtext(f"{ns}description") or "").strip()
            link  = (item.findtext(f"{ns}link") or "").strip()
            text  = title + " " + desc

            # Chỉ quan tâm WP (Western Pacific) basin
            if not ("WP" in title or "WESTERN PACIFIC" in text.upper() or "WEST PACIFIC" in text.upper()):
                continue

            # Trích tọa độ từ mô tả
            lat, lon = parse_coords(text)

            keywords = ["TROPICAL DEPRESSION", "TROPICAL STORM", "TYPHOON",
                        "DISTURBANCE", "LOW", "REMNANTS"]
            if any(kw in text.upper() for kw in keywords):
                in_zone = in_watch_zone(lat, lon) if (lat and lon) else True
                if in_zone:
                    alerts.append({
                        "source": "JTWC",
                        "title": title,
                        "url": link,
                        "id": make_id(title),
                        "lat": lat, "lon": lon,
                        "in_zone": in_zone,
                        "desc": desc[:300],
                    })
    except Exception as e:
        print(f"[JTWC] Lỗi: {e}")
    return alerts

# ── Nguồn 3: Weather Underground / TWC Typhoon Tracker ────────────────────────
def scrape_twc_pacific():
    alerts = []
    # TWC Active Storms API (public)
    url = "https://api.weather.com/v3/TropicalWeather/Outlook;basin=EP,CP,WP/en-US.json"
    # Thay bằng NHC / JMA nếu cần
    try:
        r = requests.get(
            "https://www.nhc.noaa.gov/productlist.shtml",
            headers=HEADERS, timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tr")
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue
            text = " ".join(c.get_text() for c in cells)
            if any(kw in text.upper() for kw in ["WESTERN PACIFIC", "WESTERN PAC", "WP"]):
                link_el = row.find("a")
                link = "https://www.nhc.noaa.gov" + link_el["href"] if link_el else ""
                if any(kw in text.upper() for kw in
                       ["DEPRESSION", "STORM", "TYPHOON", "DISTURBANCE"]):
                    alerts.append({
                        "source": "NHC/NOAA",
                        "title": text[:120].strip(),
                        "url": link,
                        "id": make_id(text[:80]),
                        "lat": None, "lon": None,
                        "in_zone": True,
                    })
    except Exception as e:
        print(f"[NHC] Lỗi: {e}")
    return alerts

# ── Nguồn 4: JMA (Japan Meteorological Agency) XML ────────────────────────────
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
            name = storm.get("name", {}).get("en", "Unknown")
            intensity = storm.get("intensity", {}).get("description", {}).get("en", "")
            # Lấy vị trí mới nhất
            positions = storm.get("currentPosition", {})
            lat_str = positions.get("latitude", "")
            lon_str = positions.get("longitude", "")
            lat = parse_lat(lat_str)
            lon = parse_lon(lon_str)

            if lat is None or lon is None:
                continue
            if not in_watch_zone(lat, lon):
                continue

            in_bd = in_bien_dong(lat, lon)
            direction = storm.get("movement", {}).get("direction", {}).get("en", "")

            title = f"JMA: {intensity} {name} ({lat}°N {lon}°E) → {direction}"
            alerts.append({
                "source": "JMA",
                "title": title,
                "url": "https://www.jma.go.jp/en/typh/",
                "id": make_id(title),
                "lat": lat, "lon": lon,
                "in_zone": True,
                "in_bien_dong": in_bd,
                "intensity": intensity,
                "name": name,
            })
    except Exception as e:
        print(f"[JMA] Lỗi: {e}")
    return alerts

# ── Helper: parse tọa độ ───────────────────────────────────────────────────────
def parse_coords(text):
    """Tìm lat/lon dạng '15.2N 132.5E' hoặc '15N 130E' trong văn bản"""
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

def parse_lat(s):
    m = re.search(r"(\d+\.?\d*)", str(s))
    return float(m.group(1)) if m else None

def parse_lon(s):
    m = re.search(r"(\d+\.?\d*)", str(s))
    return float(m.group(1)) if m else None

# ── Định dạng tin nhắn cảnh báo ───────────────────────────────────────────────
def format_alert(alert):
    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    src = alert.get("source", "?")
    title = alert.get("title", "")
    url = alert.get("url", "")
    lat = alert.get("lat")
    lon = alert.get("lon")
    intensity = alert.get("intensity", "")
    in_bd = alert.get("in_bien_dong", False)

    # Chọn emoji theo mức độ
    if any(k in title.upper() for k in ["TYPHOON", "BÃO"]):
        icon = "🌀"
    elif any(k in title.upper() for k in ["TROPICAL STORM", "BÃO NHIỆT ĐỚI"]):
        icon = "🌪️"
    elif any(k in title.upper() for k in ["DEPRESSION", "ÁP THẤP NHIỆT ĐỚI"]):
        icon = "⚠️"
    else:
        icon = "🔵"

    zone_note = ""
    if in_bd:
        zone_note = "\n🇻🇳 <b>ĐANG Ở BIỂN ĐÔNG</b> — nguy cơ ảnh hưởng trực tiếp!"
    elif lat and lon:
        zone_note = f"\n📍 Vị trí: {lat:.1f}°N, {lon:.1f}°E (khu vực theo dõi TBD)"

    msg = (
        f"{icon} <b>CẢNH BÁO THỜI TIẾT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 Nguồn: <b>{src}</b>\n"
        f"🕐 Thời gian: {ts}\n"
        f"📋 {title}"
        f"{zone_note}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    if url:
        msg += f"\n🔗 <a href='{url}'>Xem chi tiết</a>"
    return msg

# ── Chạy chính ─────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu quét lúc {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    sent_ids = set(state.get("sent_ids", []))

    # Thu thập từ tất cả nguồn
    all_alerts = []
    all_alerts += scrape_nchmf()
    all_alerts += scrape_jtwc()
    all_alerts += scrape_twc_pacific()
    all_alerts += scrape_jma()

    print(f"[Bot] Tìm thấy {len(all_alerts)} cảnh báo tiềm năng")

    new_sent = []
    for alert in all_alerts:
        aid = alert["id"]
        if aid in sent_ids:
            print(f"[Bot] Bỏ qua (đã gửi): {alert['title'][:60]}")
            continue
        print(f"[Bot] 🚨 Gửi cảnh báo: {alert['title'][:60]}")
        msg = format_alert(alert)
        send_telegram(msg)
        new_sent.append(aid)

    if not all_alerts or not new_sent:
        print("[Bot] ✅ Không có cảnh báo mới.")

    # Cập nhật state (giữ tối đa 200 ID)
    all_ids = list(sent_ids) + new_sent
    state["sent_ids"] = all_ids[-200:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Hoàn tất.")

if __name__ == "__main__":
    main()
