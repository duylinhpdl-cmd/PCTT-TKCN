"""
🌀 Storm Monitor Bot v7 - Theo dõi áp thấp / bão Thái Bình Dương → Biển Đông
Nguồn: NCHMF, JTWC, JMA, NHC, VnExpress, 24h, Dân Trí, Tuổi Trẻ, Thanh Niên
Thời gian hiển thị theo giờ Việt Nam (UTC+7)
Báo cáo gồm 5 thông tin cơ bản: Tên, Cấp độ, Hướng di chuyển, Khu vực ảnh hưởng, Thời gian đổ bộ
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

VN_TZ   = timezone(timedelta(hours=7))

BIEN_DONG  = {"lat_min": 5,  "lat_max": 25, "lon_min": 100, "lon_max": 125}
WATCH_ZONE = {"lat_min": 5,  "lat_max": 30, "lon_min": 100, "lon_max": 155}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

VN_KEYWORDS = [
    "áp thấp nhiệt đới", "áp thấp", "bão số",
    "cơn bão", "bão nhiệt đới", "bão mạnh",
    "vùng áp thấp", "nhiễu động nhiệt đới",
    "biển đông", "đổ bộ", "ảnh hưởng bão",
    "cảnh báo bão", "tin bão khẩn",
]

# ── Tiện ích ───────────────────────────────────────────────────────────────────
def now_vn():
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

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_coords(text):
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

def parse_num(s):
    m = re.search(r"(\d+\.?\d*)", str(s))
    return float(m.group(1)) if m else None

# ── Bảng dịch ─────────────────────────────────────────────────────────────────
INTENSITY_VI = [
    ("SUPER TYPHOON",       "Siêu bão"),
    ("SEVERE TYPHOON",      "Bão dữ dội"),
    ("TYPHOON",             "Bão lớn"),
    ("TROPICAL STORM",      "Bão nhiệt đới"),
    ("TROPICAL DEPRESSION", "Áp thấp nhiệt đới"),
    ("DISTURBANCE",         "Nhiễu động nhiệt đới"),
    ("REMNANTS",            "Tàn dư áp thấp"),
    ("LOW",                 "Vùng áp thấp"),
]

DIRECTION_VI = {
    "N":"Bắc","NNE":"Bắc-Đông Bắc","NE":"Đông Bắc","ENE":"Đông-Đông Bắc",
    "E":"Đông","ESE":"Đông-Đông Nam","SE":"Đông Nam","SSE":"Nam-Đông Nam",
    "S":"Nam","SSW":"Nam-Tây Nam","SW":"Tây Nam","WSW":"Tây-Tây Nam",
    "W":"Tây","WNW":"Tây-Tây Bắc","NW":"Tây Bắc","NNW":"Bắc-Tây Bắc",
    "STATIONARY":"Đứng yên",
}

NGUON_VI = {
    "NCHMF 🏛️":     "Trung tâm Khí tượng Thủy văn Quốc gia",
    "VnExpress 📰":  "Báo VnExpress",
    "24h.com.vn 📡": "Báo 24h",
    "Dân Trí 📰":    "Báo Dân Trí",
    "Tuổi Trẻ 📰":   "Báo Tuổi Trẻ",
    "Thanh Niên 📰": "Báo Thanh Niên",
    "JTWC 🇺🇸":      "Trung tâm Cảnh báo Bão Hải quân Mỹ",
    "JMA 🇯🇵":       "Cơ quan Khí tượng Nhật Bản",
    "NHC/NOAA 🇺🇸":  "Trung tâm Bão Quốc gia Mỹ (NOAA)",
}

def dich_tieu_de(text):
    result = text
    for en, vi in INTENSITY_VI:
        result = re.sub(en, vi, result, flags=re.IGNORECASE)
    for en, vi in DIRECTION_VI.items():
        result = re.sub(rf"\b{en}\b", vi, result)
    return result

def cap_do_canh_bao(title):
    t = title.upper()
    if "SUPER TYPHOON" in t or "SIÊU BÃO" in t:
        return "🌀🌀", "SIÊU BÃO", "danger"
    if "SEVERE TYPHOON" in t:
        return "🌀", "BÃO DỮ DỘI", "danger"
    if any(k in t for k in ["TYPHOON","BÃO SỐ","CƠN BÃO","BÃO MẠNH","BÃO LỚN"]):
        return "🌀", "BÃO", "high"
    if any(k in t for k in ["TROPICAL STORM","BÃO NHIỆT ĐỚI"]):
        return "🌪️", "BÃO NHIỆT ĐỚI", "medium"
    if any(k in t for k in ["TROPICAL DEPRESSION","ÁP THẤP NHIỆT ĐỚI"]):
        return "⚠️", "ÁP THẤP NHIỆT ĐỚI", "medium"
    if any(k in t for k in ["DISTURBANCE","NHIỄU ĐỘNG"]):
        return "🔵", "NHIỄU ĐỘNG NHIỆT ĐỚI", "low"
    if any(k in t for k in ["LOW","ÁP THẤP","VÙNG ÁP THẤP"]):
        return "🔵", "VÙNG ÁP THẤP", "low"
    return "📢", "THÔNG BÁO THỜI TIẾT", "info"

# ── Trích xuất 5 thông tin cơ bản từ bài báo ─────────────────────────────────
def trich_xuat_ten_bao(title, source=""):
    """Trích tên cơn bão/áp thấp từ tiêu đề."""
    # Tên bão quốc tế (ví dụ: TYPHOON BEBINCA, TROPICAL STORM KONG-REY)
    m = re.search(
        r"(?:TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|SUPER TYPHOON)\s+([A-Z]{2,})",
        title.upper()
    )
    if m:
        return m.group(1).capitalize()

    # Bão số (tiếng Việt)
    m = re.search(r"bão số\s*(\d+)", title, re.IGNORECASE)
    if m:
        return f"Bão số {m.group(1)}"

    # Áp thấp nhiệt đới / áp thấp
    if "áp thấp nhiệt đới" in title.lower():
        return "Áp thấp nhiệt đới"
    if "áp thấp" in title.lower():
        return "Áp thấp"
    if "nhiễu động" in title.lower():
        return "Nhiễu động nhiệt đới"

    # Tên từ JMA (đã được format sẵn)
    if "JMA" in source:
        m = re.search(r"(Siêu bão|Bão lớn|Bão nhiệt đới|Áp thấp nhiệt đới)\s+(\w+)", title)
        if m:
            return f"{m.group(1)} {m.group(2)}"

    return "Chưa có tên chính thức"

def trich_xuat_cap_do(title):
    """Trả về cấp độ bão dạng chuỗi mô tả đầy đủ."""
    t = title.upper()
    # Cấp Beaufort / cấp gió trong tiêu đề tiếng Việt
    m = re.search(r"cấp\s*(\d+)", title, re.IGNORECASE)
    cap_str = f", cấp {m.group(1)}" if m else ""

    if "SUPER TYPHOON" in t or "SIÊU BÃO" in t:
        return f"Siêu bão{cap_str}"
    if "SEVERE TYPHOON" in t or "BÃO DỮ DỘI" in t:
        return f"Bão dữ dội{cap_str}"
    if any(k in t for k in ["TYPHOON","BÃO SỐ","CƠN BÃO","BÃO MẠNH","BÃO LỚN"]):
        return f"Bão{cap_str}"
    if any(k in t for k in ["TROPICAL STORM","BÃO NHIỆT ĐỚI"]):
        return f"Bão nhiệt đới{cap_str}"
    if any(k in t for k in ["TROPICAL DEPRESSION","ÁP THẤP NHIỆT ĐỚI"]):
        return f"Áp thấp nhiệt đới{cap_str}"
    if any(k in t for k in ["DISTURBANCE","NHIỄU ĐỘNG"]):
        return f"Nhiễu động nhiệt đới{cap_str}"
    if any(k in t for k in ["LOW","ÁP THẤP"]):
        return f"Vùng áp thấp{cap_str}"
    return f"Chưa xác định{cap_str}"

def trich_xuat_huong(title, alert=None):
    """Trích hướng di chuyển từ tiêu đề hoặc metadata."""
    # Hướng từ JMA đã có trong title
    for en, vi in DIRECTION_VI.items():
        if f"hướng {vi}" in title.lower():
            return vi
        if f"di chuyển về hướng {vi}" in title.lower():
            return vi

    # Hướng tiếng Anh từ JTWC/NHC
    t = title.upper()
    for en, vi in DIRECTION_VI.items():
        if re.search(rf"\bMOVING\s+{en}\b|\bMOVEMENT\s+{en}\b|\b{en}\s+AT\b", t):
            return vi

    # Từ khoá đổ bộ → ngầm định hướng Tây
    if any(k in title.lower() for k in ["đổ bộ", "vào đất liền", "tiến vào biển đông"]):
        return "Tây (hướng vào Biển Đông / Việt Nam)"

    # Metadata hướng nếu có
    if alert and alert.get("huong"):
        return alert["huong"]

    return "Chưa xác định — xem bài báo gốc"

def trich_xuat_khu_vuc(title, lat=None, lon=None):
    """Xác định khu vực ảnh hưởng."""
    t = title.lower()

    # Tỉnh/vùng Việt Nam
    tinh_viet = [
        "quảng ninh","hải phòng","thái bình","nam định","ninh bình",
        "thanh hóa","nghệ an","hà tĩnh","quảng bình","quảng trị",
        "thừa thiên huế","đà nẵng","quảng nam","quảng ngãi","bình định",
        "phú yên","khánh hòa","ninh thuận","bình thuận",
        "bà rịa","vũng tàu","cà mau","kiên giang","bạc liêu",
        "miền bắc","miền trung","miền nam","bắc bộ","trung bộ","nam bộ",
    ]
    found = [p for p in tinh_viet if p in t]
    if found:
        return "Việt Nam — " + ", ".join(p.title() for p in found[:3])

    # Theo toạ độ
    if lat is not None and lon is not None:
        if in_bien_dong(lat, lon):
            return f"Biển Đông ({lat:.1f}°N, {lon:.1f}°E)"
        if lon > 125:
            return f"Tây Thái Bình Dương ({lat:.1f}°N, {lon:.1f}°E)"
        return f"({lat:.1f}°N, {lon:.1f}°E)"

    # Từ khoá vùng biển
    if "biển đông" in t:
        return "Biển Đông"
    if "philippines" in t or "philippine" in t:
        return "Tây Thái Bình Dương (gần Philippines)"
    if "thái bình dương" in t or "pacific" in t:
        return "Tây Thái Bình Dương"
    if "đổ bộ" in t or "ven biển" in t:
        return "Ven biển Việt Nam (xem bài báo)"

    return "Tây Thái Bình Dương / Biển Đông — xem bài báo"

def trich_xuat_thoi_gian_do_bo(title):
    """Trích thời gian đổ bộ dự kiến từ tiêu đề."""
    t = title.lower()

    # Ngày cụ thể
    m = re.search(
        r"(?:ngày|lúc|vào|dự kiến|khoảng)\s*"
        r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}\s*tháng\s*\d{1,2})",
        t
    )
    if m:
        return f"Dự kiến {m.group(1)}"

    # Khoảng thời gian tương đối
    for phrase in ["hôm nay","tối nay","đêm nay","sáng mai","chiều mai","ngày mai",
                   "cuối tuần","trong 24 giờ","trong 48 giờ","trong vài ngày",
                   "cuối tháng","đầu tháng"]:
        if phrase in t:
            return f"Dự kiến {phrase}"

    # Từ khoá "đổ bộ" không có thời gian cụ thể
    if "đổ bộ" in t:
        return "Đang tiến vào đất liền — chưa có giờ cụ thể"

    return "Chưa có thông tin — xem bài báo gốc"

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
                if has_keyword(title + " " + desc):
                    alerts.append({"source": "VnExpress 📰", "title": title,
                                   "url": link, "id": make_id(title),
                                   "lat": None, "lon": None})
        except Exception as e:
            print(f"[VnExpress] {e}")
    return alerts

# ── Nguồn 3: 24h ──────────────────────────────────────────────────────────────
def scrape_24h():
    alerts = []
    urls = [
        "https://www.24h.com.vn/thoi-tiet-c270.html",
        "https://www.24h.com.vn/tin-tuc-trong-ngay-c46.html",
    ]
    for url in urls:
        try:
            soup = get_page(url)
            for a in soup.find_all("a", href=True):
                text = a.get("title", "") or a.get_text(strip=True)
                href = a.get("href", "")
                if len(text) < 15:
                    continue
                if has_keyword(text):
                    full = href if href.startswith("http") else "https://www.24h.com.vn" + href
                    alerts.append({"source": "24h.com.vn 📡", "title": text[:200],
                                   "url": full, "id": make_id(text),
                                   "lat": None, "lon": None})
        except Exception as e:
            print(f"[24h] {e}")
    return alerts

# ── Nguồn 4: Dân Trí ──────────────────────────────────────────────────────────
def scrape_dantri():
    alerts = []
    for rss in ["https://dantri.com.vn/xa-hoi.rss"]:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({"source": "Dân Trí 📰", "title": title,
                                   "url": link, "id": make_id(title),
                                   "lat": None, "lon": None})
        except Exception as e:
            print(f"[DanTri] {e}")
    return alerts

# ── Nguồn 5: Tuổi Trẻ ─────────────────────────────────────────────────────────
def scrape_tuoitre():
    alerts = []
    for rss in ["https://tuoitre.vn/rss/thoi-su.rss", "https://tuoitre.vn/rss/tin-moi-nhat.rss"]:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({"source": "Tuổi Trẻ 📰", "title": title,
                                   "url": link, "id": make_id(title),
                                   "lat": None, "lon": None})
        except Exception as e:
            print(f"[TuoiTre] {e}")
    return alerts

# ── Nguồn 6: Thanh Niên ───────────────────────────────────────────────────────
def scrape_thanhnien():
    alerts = []
    for rss in ["https://thanhnien.vn/rss/thoi-su.rss", "https://thanhnien.vn/rss/home.rss"]:
        try:
            r = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if has_keyword(title + " " + desc):
                    alerts.append({"source": "Thanh Niên 📰", "title": title,
                                   "url": link, "id": make_id(title),
                                   "lat": None, "lon": None})
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
                    # Trích hướng từ JTWC description
                    huong = None
                    m = re.search(r"MOVING\s+([A-Z]{1,3})\s+AT", desc.upper())
                    if m:
                        huong = DIRECTION_VI.get(m.group(1), m.group(1))
                    alerts.append({
                        "source": "JTWC 🇺🇸", "title": title,
                        "url": link, "id": make_id(title),
                        "lat": lat, "lon": lon, "huong": huong,
                    })
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
            speed_ms  = storm.get("movement", {}).get("speed", {}).get("value", "")
            # Thời gian đổ bộ dự kiến từ forecast track
            do_bo_du_kien = "Chưa có thông tin"
            forecasts = storm.get("forecastTrack", [])
            for fc in forecasts:
                fc_pos = fc.get("position", {})
                fc_lat = parse_num(fc_pos.get("latitude", ""))
                fc_lon = parse_num(fc_pos.get("longitude", ""))
                if fc_lat and fc_lon and in_bien_dong(fc_lat, fc_lon):
                    fc_time = fc.get("datetime", "")
                    if fc_time:
                        try:
                            dt = datetime.fromisoformat(fc_time.replace("Z","+00:00"))
                            dt_vn = dt.astimezone(VN_TZ)
                            do_bo_du_kien = dt_vn.strftime("%d/%m/%Y %H:%M (GMT+7)")
                        except:
                            do_bo_du_kien = fc_time
                    break

            cuong_do_vi = next((vi for en, vi in INTENSITY_VI if en.upper() in intensity.upper()), intensity)
            huong_vi    = DIRECTION_VI.get(direction.upper().strip(), direction)
            toc_do_str  = f", tốc độ ~{speed_ms} km/h" if speed_ms else ""
            title = (
                f"{cuong_do_vi} {name} — vị trí {lat}°N {lon}°E, "
                f"di chuyển về hướng {huong_vi}{toc_do_str}"
            )
            alerts.append({
                "source": "JMA 🇯🇵", "title": title,
                "url": "https://www.jma.go.jp/en/typh/",
                "id": make_id(title), "lat": lat, "lon": lon,
                "in_bien_dong": in_bien_dong(lat, lon),
                "ten": f"{cuong_do_vi} {name}",
                "cap_do": cuong_do_vi,
                "huong": huong_vi,
                "khu_vuc": f"Biển Đông ({lat}°N, {lon}°E)" if in_bien_dong(lat, lon) else f"Tây TBD ({lat}°N, {lon}°E)",
                "do_bo": do_bo_du_kien,
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

# ── Format block 5 thông tin cho mỗi hệ thống ────────────────────────────────
def format_5_thong_tin(alert):
    """Trả về block 5 dòng thông tin cơ bản cho 1 hệ thống bão."""
    title  = alert.get("title", "")
    source = alert.get("source", "")
    lat    = alert.get("lat")
    lon    = alert.get("lon")

    # Ưu tiên metadata đã parse sẵn (từ JMA/JTWC), fallback sang trích từ title
    ten      = alert.get("ten")      or trich_xuat_ten_bao(title, source)
    cap_do   = alert.get("cap_do")   or trich_xuat_cap_do(title)
    huong    = alert.get("huong")    or trich_xuat_huong(title, alert)
    khu_vuc  = alert.get("khu_vuc") or trich_xuat_khu_vuc(title, lat, lon)
    do_bo    = alert.get("do_bo")    or trich_xuat_thoi_gian_do_bo(title)

    url = alert.get("url", "")
    tieu = title[:80] + ("..." if len(title) > 80 else "")
    header = f'  📌 <a href="{url}">{tieu}</a>' if url else f"  📌 {tieu}"

    return (
        f"{header}\n"
        f"     1️⃣ <b>Tên:</b> {ten}\n"
        f"     2️⃣ <b>Cấp độ:</b> {cap_do}\n"
        f"     3️⃣ <b>Hướng di chuyển:</b> {huong}\n"
        f"     4️⃣ <b>Khu vực ảnh hưởng:</b> {khu_vuc}\n"
        f"     5️⃣ <b>Dự kiến đổ bộ VN:</b> {do_bo}\n"
    )

# ── Format báo cáo tổng hợp ───────────────────────────────────────────────────
def format_bao_cao(all_alerts, new_alerts, gio_bao_cao):
    bao       = [a for a in all_alerts if any(k in a["title"].upper()
                  for k in ["TYPHOON","BÃO SỐ","CƠN BÃO","BÃO MẠNH","BÃO LỚN","SIÊU BÃO"])]
    at_nhiet  = [a for a in all_alerts if any(k in a["title"].upper()
                  for k in ["TROPICAL STORM","TROPICAL DEPRESSION",
                             "ÁP THẤP NHIỆT ĐỚI","BÃO NHIỆT ĐỚI"])]
    nhieu_dong= [a for a in all_alerts if any(k in a["title"].upper()
                  for k in ["DISTURBANCE","NHIỄU ĐỘNG","VÙNG ÁP THẤP","LOW"])]
    bien_dong = [a for a in all_alerts if a.get("in_bien_dong")]
    co_su_kien = bool(bao or at_nhiet or nhieu_dong)

    if bao and bien_dong:
        danh_gia = "🔴 <b>RẤT NGUY HIỂM — BÃO ĐANG Ở BIỂN ĐÔNG</b>"
    elif bao:
        danh_gia = "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif at_nhiet and bien_dong:
        danh_gia = "🟠 <b>CẦN THEO DÕI — ÁP THẤP NHIỆT ĐỚI VÀO BIỂN ĐÔNG</b>"
    elif at_nhiet:
        danh_gia = "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    elif nhieu_dong:
        danh_gia = "🟡 <b>THEO DÕI — CÓ NHIỄU ĐỘNG TRÊN BIỂN</b>"
    else:
        danh_gia = "🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ SỰ KIỆN BẤT THƯỜNG</b>"

    msg  = f"📋 <b>BÁO CÁO THỜI TIẾT {gio_bao_cao}</b>\n"
    msg += f"🕐 {fmt_time_vn()}\n"
    msg += f"{'━' * 24}\n\n"
    msg += f"{danh_gia}\n\n"

    if not co_su_kien:
        msg += (
            "✅ Không ghi nhận sự kiện nào:\n"
            "  • Không có bão\n"
            "  • Không có áp thấp nhiệt đới\n"
            "  • Không có nhiễu động đáng kể\n"
            "  • Biển Đông và Tây Thái Bình Dương ổn định\n\n"
            "📡 Đã kiểm tra <b>9 nguồn tin</b> trong nước và quốc tế.\n"
        )
    else:
        # ── BÃO ──
        if bao:
            msg += f"🌀 <b>BÃO ({len(bao)} hệ thống):</b>\n"
            for a in bao[:3]:
                msg += format_5_thong_tin(a)
            msg += "\n"

        # ── ÁP THẤP NHIỆT ĐỚI / BÃO NHIỆT ĐỚI ──
        if at_nhiet:
            msg += f"⚠️ <b>ÁP THẤP NHIỆT ĐỚI / BÃO NHIỆT ĐỚI ({len(at_nhiet)} hệ thống):</b>\n"
            for a in at_nhiet[:3]:
                msg += format_5_thong_tin(a)
            msg += "\n"

        # ── NHIỄU ĐỘNG / VÙNG ÁP THẤP ──
        if nhieu_dong:
            msg += f"🔵 <b>VÙNG ÁP THẤP / NHIỄU ĐỘNG ({len(nhieu_dong)} khu vực):</b>\n"
            for a in nhieu_dong[:3]:
                msg += format_5_thong_tin(a)
            msg += "\n"

        # ── HỆ THỐNG Ở BIỂN ĐÔNG ──
        if bien_dong:
            msg += "🇻🇳 <b>⚡️ ĐANG Ở BIỂN ĐÔNG:</b>\n"
            for a in bien_dong[:3]:
                msg += format_5_thong_tin(a)
            msg += "\n"

        # ── TIN MỚI ──
        if new_alerts:
            msg += f"🆕 <b>Tin mới so với báo cáo trước:</b> {len(new_alerts)} mục\n\n"

    msg += f"{'━' * 24}\n"
    msg += "📡 Nguồn: NCHMF · VnExpress · 24h · Dân Trí · Tuổi Trẻ · Thanh Niên · JTWC · JMA · NOAA\n"
    msg += f"⏰ Báo cáo tiếp theo: lúc {gio_tiep_theo()} (giờ VN)"
    return msg

def format_alert(alert):
    """Format cảnh báo chi tiết (gửi kèm khi có tin nghiêm trọng mới)."""
    title  = alert.get("title", "")
    src    = alert.get("source", "?")
    url    = alert.get("url", "")
    lat    = alert.get("lat")
    lon    = alert.get("lon")
    in_bd  = alert.get("in_bien_dong", False)

    icon, cap_do, level = cap_do_canh_bao(title)
    ten_nguon = NGUON_VI.get(src, src)
    tieu_de   = dich_tieu_de(title)

    if in_bd:
        vi_tri = "🇻🇳 <b>ĐANG Ở BIỂN ĐÔNG</b>\n     ⚡️ Nguy cơ ảnh hưởng trực tiếp đến Việt Nam!"
    elif lat and lon:
        vi_tri = f"📍 Vị trí: {lat:.1f}°N, {lon:.1f}°E (Tây Thái Bình Dương)"
    else:
        vi_tri = "📍 Khu vực: Tây Thái Bình Dương / Biển Đông"

    MUC_DO = {
        "danger": "🔴 Mức độ: <b>RẤT NGUY HIỂM</b>",
        "high":   "🟠 Mức độ: <b>NGUY HIỂM</b>",
        "medium": "🟡 Mức độ: <b>CẦN THEO DÕI</b>",
        "low":    "🟢 Mức độ: <b>THEO DÕI</b>",
        "info":   "🔵 Mức độ: <b>THÔNG TIN</b>",
    }

    # 5 thông tin cơ bản
    ten     = alert.get("ten")     or trich_xuat_ten_bao(title, src)
    huong   = alert.get("huong")   or trich_xuat_huong(title, alert)
    khu_vuc = alert.get("khu_vuc") or trich_xuat_khu_vuc(title, lat, lon)
    do_bo   = alert.get("do_bo")   or trich_xuat_thoi_gian_do_bo(title)

    msg = (
        f"{icon} <b>CẢNH BÁO: {cap_do}</b>\n"
        f"{'━' * 22}\n"
        f"📋 {tieu_de}\n\n"
        f"1️⃣ <b>Tên:</b> {ten}\n"
        f"2️⃣ <b>Cấp độ:</b> {trich_xuat_cap_do(title)}\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {huong}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {khu_vuc}\n"
        f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {do_bo}\n\n"
        f"{MUC_DO.get(level,'')}\n"
        f"{vi_tri}\n\n"
        f"📡 Nguồn: {ten_nguon}\n"
        f"🕐 Cập nhật: {fmt_time_vn()}\n"
        f"{'━' * 22}"
    )
    if url:
        msg += f"\n🔗 <a href='{url}'>Xem bài viết đầy đủ</a>"
    return msg

def gio_tiep_theo():
    gio_bao_cao = [2, 8, 14, 20]
    h = now_vn().hour
    for g in gio_bao_cao:
        if g > h:
            return f"{g:02d}:00"
    return "02:00 (ngày mai)"

def gio_bao_cao_hien_tai():
    h = now_vn().hour
    if 1 <= h < 7:
        return "02:00"
    elif 7 <= h < 13:
        return "08:00"
    elif 13 <= h < 19:
        return "14:00"
    else:
        return "20:00"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))

    all_alerts = []
    for fn in [scrape_nchmf, scrape_vnexpress, scrape_24h, scrape_dantri,
               scrape_tuoitre, scrape_thanhnien, scrape_jtwc, scrape_jma, scrape_nhc]:
        try:
            all_alerts += fn()
        except Exception as e:
            print(f"[Scrape] {e}")

    seen = set()
    unique = [a for a in all_alerts if not (a["id"] in seen or seen.add(a["id"]))]
    print(f"[Bot] Tổng: {len(unique)} mục (sau lọc trùng)")

    new_alerts = [a for a in unique if a["id"] not in sent_ids]

    gio = gio_bao_cao_hien_tai()
    bao_cao = format_bao_cao(unique, new_alerts, gio)
    send_telegram(bao_cao)

    keywords_nghiem = [
        "TYPHOON","SUPER TYPHOON","TROPICAL STORM","TROPICAL DEPRESSION",
        "BÃO SỐ","CƠN BÃO","BÃO NHIỆT ĐỚI","ÁP THẤP NHIỆT ĐỚI","SIÊU BÃO"
    ]
    tin_nghiem_moi = [
        a for a in new_alerts
        if any(k in a["title"].upper() for k in keywords_nghiem)
    ]
    if tin_nghiem_moi:
        send_telegram(f"🚨 <b>Chi tiết {len(tin_nghiem_moi)} tin nghiêm trọng mới:</b>")
        for a in tin_nghiem_moi[:5]:
            send_telegram(format_alert(a))

    all_ids = list(sent_ids) + [a["id"] for a in new_alerts]
    state["sent_ids"]     = all_ids[-300:]
    state["last_run_vn"]  = fmt_time_vn()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Xong.")

if __name__ == "__main__":
    main()
