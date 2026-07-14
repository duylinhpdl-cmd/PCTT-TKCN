"""
🌀 Storm Monitor Bot v17
- Đọc nội dung bài viết thật (không chỉ tiêu đề)
- Lọc bỏ trang đầu mục, trang listing không có dữ liệu
- Trích đủ 5 trường: tên · cấp độ · hướng · khu vực · dự kiến đổ bộ
- Hỗ trợ nhiều Chat ID (nhóm + cá nhân)
"""

import os, json, re, hashlib, requests, time
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.json"
VN_TZ = timezone(timedelta(hours=7))

BIEN_DONG  = dict(lat_min=5,  lat_max=25, lon_min=100, lon_max=125)
WATCH_ZONE = dict(lat_min=5,  lat_max=30, lon_min=100, lon_max=155)

HEADERS = {"User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)}

VN_KW = [
    "áp thấp nhiệt đới","áp thấp","bão số","cơn bão","bão nhiệt đới",
    "bão mạnh","vùng áp thấp","nhiễu động nhiệt đới","biển đông","đổ bộ",
    "ảnh hưởng bão","cảnh báo bão","tin bão khẩn",
]

# Các URL listing/đầu mục — KHÔNG có nội dung thật
LISTING_URLS = [
    "tin-bao-khan-cap-post.html",
    "tin-ap-thap-nhiet-doi-post.html",
    "thoi-tiet-c270.html",
    "thoi-su.rss",
    "xa-hoi.rss",
    "home.rss",
    "tin-moi-nhat.rss",
    "category","/tag/","/chu-de/",
]

def la_trang_listing(url):
    return any(k in url for k in LISTING_URLS)

# ── Bảng tra cứu ──────────────────────────────────────────────────────────────
INTENSITY_TABLE = [
    ("SUPER TYPHOON",       "Siêu bão",             5),
    ("SEVERE TYPHOON",      "Bão rất mạnh",          4),
    ("TYPHOON",             "Bão",                  3),
    ("TROPICAL STORM",      "Bão nhiệt đới",         2),
    ("TROPICAL DEPRESSION", "Áp thấp nhiệt đới",    1),
    ("DISTURBANCE",         "Nhiễu động nhiệt đới", 0),
    ("LOW",                 "Vùng áp thấp",         0),
]

CAP_GIO_VI = {
    5:"Cấp 12+ (≥118 km/h)",
    4:"Cấp 11-12 (103-117 km/h)",
    3:"Cấp 8-12 (63-117 km/h)",
    2:"Cấp 6-7 (39-62 km/h)",
    1:"Cấp 6 (39-49 km/h)",
    0:"Dưới cấp 6",
}

DIRECTION_VI = {
    "N":"Bắc","NNE":"Bắc-Đông Bắc","NE":"Đông Bắc","ENE":"Đông-Đông Bắc",
    "E":"Đông","ESE":"Đông-Đông Nam","SE":"Đông Nam","SSE":"Nam-Đông Nam",
    "S":"Nam","SSW":"Nam-Tây Nam","SW":"Tây Nam","WSW":"Tây-Tây Nam",
    "W":"Tây","WNW":"Tây-Tây Bắc","NW":"Tây Bắc","NNW":"Bắc-Tây Bắc",
    "STATIONARY":"Đứng yên",
}

TINH_VEN_BIEN = {
    "quảng ninh":"Quảng Ninh","hải phòng":"Hải Phòng","thái bình":"Thái Bình",
    "nam định":"Nam Định","thanh hóa":"Thanh Hóa","nghệ an":"Nghệ An",
    "hà tĩnh":"Hà Tĩnh","quảng bình":"Quảng Bình","quảng trị":"Quảng Trị",
    "thừa thiên":"Thừa Thiên-Huế","đà nẵng":"Đà Nẵng","quảng nam":"Quảng Nam",
    "quảng ngãi":"Quảng Ngãi","bình định":"Bình Định","phú yên":"Phú Yên",
    "khánh hòa":"Khánh Hòa","ninh thuận":"Ninh Thuận","bình thuận":"Bình Thuận",
    "vũng tàu":"Bà Rịa-Vũng Tàu","cà mau":"Cà Mau","kiên giang":"Kiên Giang",
    "miền bắc":"Các tỉnh Bắc Bộ","miền trung":"Các tỉnh Trung Bộ",
    "miền nam":"Các tỉnh Nam Bộ","bắc bộ":"Bắc Bộ","trung bộ":"Trung Bộ",
}

NGUON_VI = {
    "NCHMF":    "Trung tâm Khí tượng Thủy văn Quốc gia",
    "VnExpress":"Báo VnExpress",
    "24h":      "Báo 24h",
    "DanTri":   "Báo Dân Trí",
    "TuoiTre":  "Báo Tuổi Trẻ",
    "ThanhNien":"Báo Thanh Niên",
    "JTWC":     "Trung tâm Cảnh báo Bão Hải quân Mỹ (JTWC)",
    "JMA":      "Cơ quan Khí tượng Nhật Bản (JMA)",
}

# ── Tiện ích ───────────────────────────────────────────────────────────────────
def now_vn():      return datetime.now(VN_TZ)
def fmt_time_vn(): return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")
def make_id(t):    return hashlib.md5(t.encode()).hexdigest()[:12]
def has_kw(t):     return any(k in t.lower() for k in VN_KW)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    return {"sent_ids": []}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def doc_trang(url, timeout=10):
    """Đọc nội dung trang web, trả về (soup, text)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","nav","header","footer","aside"]):
            tag.decompose()
        return soup, soup.get_text(separator=" ", strip=True)
    except Exception as e:
        print(f"[doc_trang] {url[:60]}: {e}")
        return None, ""

def fetch_rss(url, timeout=8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return ET.fromstring(r.content).findall(".//item")
    except: return []

# ── Helpers trích xuất ────────────────────────────────────────────────────────
def dich_cuong_do(text):
    t = text.upper()
    for en, vi, cap in INTENSITY_TABLE:
        if en in t: return vi, cap
    if "siêu bão" in text.lower():            return "Siêu bão", 5
    if "bão số" in text.lower() or "cơn bão" in text.lower(): return "Bão", 3
    if "áp thấp nhiệt đới" in text.lower():  return "Áp thấp nhiệt đới", 1
    if "áp thấp" in text.lower():             return "Vùng áp thấp", 0
    return "Chưa xác định", -1

def dich_huong(raw):
    if not raw: return "Chưa xác định"
    return DIRECTION_VI.get(raw.upper().strip(), raw)

def parse_latlon(text):
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)

def parse_num(s):
    m = re.search(r"(\d+\.?\d*)", str(s or ""))
    return float(m.group(1)) if m else None

def in_bien_dong(lat, lon):
    if not lat: return False
    z = BIEN_DONG
    return z["lat_min"]<=lat<=z["lat_max"] and z["lon_min"]<=lon<=z["lon_max"]

def in_watch(lat, lon):
    if not lat: return False
    z = WATCH_ZONE
    return z["lat_min"]<=lat<=z["lat_max"] and z["lon_min"]<=lon<=z["lon_max"]

def tim_tinh(text):
    t = text.lower()
    found = []
    for kw, ten in TINH_VEN_BIEN.items():
        if kw in t and ten not in found: found.append(ten)
    return ", ".join(found[:3]) if found else ""

def tim_huong_vi(text):
    t = text.lower()
    for kw, val in [
        ("tây bắc","Tây Bắc"),("tây nam","Tây Nam"),
        ("đông bắc","Đông Bắc"),("đông nam","Đông Nam"),
        ("hướng tây ","Tây"),("hướng bắc","Bắc"),
        ("hướng nam","Nam"),("hướng đông","Đông"),
        (" tây "," Tây "),(" bắc "," Bắc "),
    ]:
        if kw in t: return val.strip()
    return "Chưa xác định"

def tim_toc_do(text):
    m = re.search(r"(\d+)\s*(?:km/h|km\/h|km\s*mỗi\s*giờ)", text, re.IGNORECASE)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:knots?|kt)", text, re.IGNORECASE)
    if m: return round(int(m.group(1)) * 1.852)
    return None

def tim_do_bo(text):
    """Tìm câu dự kiến đổ bộ trong bài viết."""
    patterns = [
        r"dự kiến[^.]{0,150}(?:đổ bộ|ảnh hưởng|vào đất liền)[^.]{0,100}",
        r"(?:đổ bộ|ảnh hưởng trực tiếp)[^.]{0,150}(?:ngày|giờ|sáng|chiều|tối)[^.]{0,80}",
        r"(?:ngày|đêm)\s+\d+[^.]{0,100}(?:đổ bộ|ảnh hưởng|vào bờ)[^.]{0,80}",
        r"(?:khoảng|vào)\s+(?:ngày|đêm|sáng|chiều)\s+\d+[^.]{0,150}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result = m.group(0).strip()[:200]
            # Dọn dẹp khoảng trắng thừa
            result = re.sub(r'\s+', ' ', result)
            return result
    return ""

def tinh_do_bo_toa_do(lat, lon, huong_raw=""):
    """Ước tính dự kiến đổ bộ từ tọa độ."""
    if lat is None: return "Chưa đủ dữ liệu"
    h = huong_raw.upper()
    vao_vn = any(k in h for k in ["W","NW","WNW","WSW","SW"])
    if in_bien_dong(lat, lon):
        kc = abs(lon - 109) * 111
        if kc < 150: return "⚡ Trong vòng 12 giờ tới"
        if kc < 350: return "Khoảng 1-2 ngày tới"
        return "Khoảng 2-4 ngày tới"
    if lon > 130:
        return "Khoảng 5-7 ngày nếu duy trì hướng" if vao_vn else "Chưa xác định"
    if lon > 120:
        return "Khoảng 3-5 ngày tới" if vao_vn else "Chưa xác định"
    return "Khoảng 1-3 ngày tới" if vao_vn else "Chưa xác định"

def khu_vuc_toa_do(lat, lon):
    if lat is None: return "Chưa xác định"
    if 100<=lon<=125 and 5<=lat<=25:  return "Biển Đông"
    if 100<=lon<=110 and 20<=lat<=23: return "Bắc Bộ VN"
    if 107<=lon<=110 and 15<=lat<=20: return "Trung Bộ VN"
    if 116<=lon<=128 and 5<=lat<=22:  return "Tây Philippines"
    return f"Tây TBD ({lat:.0f}°N {lon:.0f}°E)"

# ── Kiểm tra bài viết có nội dung thật không ─────────────────────────────────
MIN_NOI_DUNG = 200   # Tối thiểu 200 ký tự nội dung mới coi là có thông tin

def co_noi_dung_that(text, url):
    """Kiểm tra bài viết có đủ nội dung thật để trích xuất không."""
    if la_trang_listing(url):
        return False
    if len(text) < MIN_NOI_DUNG:
        return False
    # Phải có ít nhất 1 từ khoá thời tiết
    if not has_kw(text):
        return False
    return True

# ── Tạo storm object chuẩn ───────────────────────────────────────────────────
def make_storm(ten, loai, cap_so, lat, lon, huong, khu_vuc,
               do_bo, url, source, title, gio_km=None):
    cap_do = loai
    cap_gio = CAP_GIO_VI.get(cap_so, "Không xác định")
    if gio_km: cap_gio += f" (~{gio_km} km/h)"
    return {
        "id":       make_id(ten + loai + str(lat) + str(lon) + url[:20]),
        "ten":      ten,
        "loai":     loai,
        "cap_do":   cap_do,
        "cap_so":   cap_so,
        "cap_gio":  cap_gio,
        "lat": lat, "lon": lon,
        "huong":    huong,
        "khu_vuc":  khu_vuc,
        "do_bo":    do_bo,
        "in_bd":    in_bien_dong(lat, lon),
        "url":      url,
        "source":   source,
        "title":    title,
    }

# ── Nguồn 1: JMA (tốt nhất — có tọa độ, hướng, tốc độ chính xác) ────────────
def scrape_jma():
    storms = []
    try:
        r = requests.get(
            "https://www.jma.go.jp/bosai/typhoon/data/tropicalCyclone.json",
            headers=HEADERS, timeout=12)
        data = r.json()
        items = data.get("TropicalCyclone", [])
        if isinstance(items, dict): items = [items]
        for s in items:
            name   = s.get("name",{}).get("en","Chưa đặt tên")
            inten  = s.get("intensity",{}).get("description",{}).get("en","")
            loai, cap_so = dich_cuong_do(inten)
            pos    = s.get("currentPosition",{})
            lat    = parse_num(pos.get("latitude",""))
            lon    = parse_num(pos.get("longitude",""))
            if lat and not in_watch(lat, lon): continue
            dir_en = s.get("movement",{}).get("direction",{}).get("en","")
            huong  = dich_huong(dir_en)
            wind_kt= parse_num(s.get("maximumWind",{}).get("knot","")) or 0
            wind_km= round(wind_kt*1.852) if wind_kt else None
            kv     = khu_vuc_toa_do(lat, lon)
            do_bo  = tinh_do_bo_toa_do(lat, lon, dir_en)
            ten    = name if name not in ("UNNAMED","","?") else "Chưa đặt tên"
            storms.append(make_storm(
                ten=ten, loai=loai, cap_so=cap_so,
                lat=lat, lon=lon, huong=huong, khu_vuc=kv,
                do_bo=do_bo, url="https://www.jma.go.jp/en/typh/",
                source="JMA",
                title=f"{loai} {ten} — {lat}°N {lon}°E",
                gio_km=wind_km,
            ))
    except Exception as e: print(f"[JMA] {e}")
    return storms

# ── Nguồn 2: JTWC RSS + đọc nội dung bản tin ─────────────────────────────────
def scrape_jtwc():
    storms = []
    try:
        items = fetch_rss("https://www.metoc.navy.mil/jtwc/rss/jtwc.rss")
        for item in items:
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            text  = title + " " + desc
            if not any(k in text.upper() for k in ["WP","WESTERN PACIFIC"]): continue
            if not any(k in text.upper() for k in ["DEPRESSION","STORM","TYPHOON"]): continue
            loai, cap_so = dich_cuong_do(text)
            lat, lon = parse_latlon(text)
            if lat and not in_watch(lat, lon): continue
            m_dir = re.search(r"MOVING\s+([A-Z\-]+)\s+AT\s+(\d+)\s*KT", text.upper())
            dir_raw = m_dir.group(1) if m_dir else ""
            huong = dich_huong(dir_raw)
            m_wind = re.search(r"MAX\w*\s+SUSTAINED\s+WINDS?\s+(\d+)\s*KT", text.upper())
            wind_km = round(int(m_wind.group(1))*1.852) if m_wind else None
            m_name = re.search(r"(?:TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION)\s+([\w\d]+)", title.upper())
            ten = m_name.group(1).title() if m_name else "Chưa đặt tên"
            kv  = khu_vuc_toa_do(lat, lon)
            do_bo = tinh_do_bo_toa_do(lat, lon, dir_raw)
            storms.append(make_storm(
                ten=ten, loai=loai, cap_so=cap_so,
                lat=lat, lon=lon, huong=huong, khu_vuc=kv,
                do_bo=do_bo, url=link, source="JTWC", title=title,
                gio_km=wind_km,
            ))
    except Exception as e: print(f"[JTWC] {e}")
    return storms

# ── Nguồn 3: NCHMF — đọc nội dung bài thật ──────────────────────────────────
def scrape_nchmf():
    storms = []
    # Lấy danh sách link từ trang listing
    listing_urls = [
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-ap-thap-nhiet-doi-post.html",
    ]
    bai_urls = []
    for lu in listing_urls:
        try:
            soup, _ = doc_trang(lu)
            if not soup: continue
            for a in soup.select("a[href]")[:10]:
                href = a.get("href","")
                text = a.get_text(strip=True)
                if not has_kw(text): continue
                # Bỏ qua link listing
                full = href if href.startswith("http") else "https://nchmf.gov.vn" + href
                if not la_trang_listing(full) and full not in bai_urls:
                    bai_urls.append((text, full))
        except Exception as e: print(f"[NCHMF listing] {e}")

    # Đọc từng bài viết thật
    for tieu_de, url in bai_urls[:5]:
        try:
            soup, noi_dung = doc_trang(url)
            if not co_noi_dung_that(noi_dung, url):
                print(f"[NCHMF] Bỏ qua (không đủ nội dung): {url[:60]}")
                continue

            all_text = tieu_de + " " + noi_dung
            loai, cap_so = dich_cuong_do(all_text)
            m_so  = re.search(r"bão số\s*(\d+)", all_text, re.IGNORECASE)
            ten   = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
            huong = tim_huong_vi(all_text)
            kv    = tim_tinh(all_text) or "Biển Đông / Việt Nam"
            lat, lon = parse_latlon(all_text)
            gio_km = tim_toc_do(all_text)

            # Ưu tiên câu dự kiến đổ bộ từ bài viết
            do_bo = tim_do_bo(all_text)
            if not do_bo:
                do_bo = tinh_do_bo_toa_do(lat, lon, huong)

            storms.append(make_storm(
                ten=ten, loai=loai, cap_so=cap_so,
                lat=lat, lon=lon, huong=huong, khu_vuc=kv,
                do_bo=do_bo, url=url, source="NCHMF",
                title=tieu_de, gio_km=gio_km,
            ))
            time.sleep(0.5)
        except Exception as e: print(f"[NCHMF bài] {e}")
    return storms

# ── Nguồn 4-7: Báo VN — đọc nội dung bài thật từ RSS ────────────────────────
def _scrape_bao_rss(rss_urls, source, base=""):
    storms = []
    for rss in rss_urls:
        try:
            items = fetch_rss(rss)
            for item in items[:8]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(
                    item.findtext("description") or "", "html.parser"
                ).get_text()

                # Bước 1: lọc theo tiêu đề/mô tả
                if not has_kw(title + " " + desc): continue

                # Bước 2: đọc nội dung bài thật
                _, noi_dung = doc_trang(link)
                if not co_noi_dung_that(noi_dung, link):
                    print(f"[{source}] Bỏ qua (ít nội dung): {title[:50]}")
                    continue

                all_text = title + " " + noi_dung
                loai, cap_so = dich_cuong_do(all_text)
                m_so  = re.search(r"bão số\s*(\d+)", all_text, re.IGNORECASE)
                ten   = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
                huong = tim_huong_vi(all_text)
                kv    = tim_tinh(all_text) or "Biển Đông / Việt Nam"
                lat, lon = parse_latlon(all_text)
                gio_km = tim_toc_do(all_text)
                do_bo  = tim_do_bo(all_text) or tinh_do_bo_toa_do(lat, lon, huong)

                storms.append(make_storm(
                    ten=ten, loai=loai, cap_so=cap_so,
                    lat=lat, lon=lon, huong=huong, khu_vuc=kv,
                    do_bo=do_bo, url=link, source=source,
                    title=title, gio_km=gio_km,
                ))
                time.sleep(0.4)
        except Exception as e: print(f"[{source}] {e}")
    return storms

def scrape_vnexpress():
    return _scrape_bao_rss([
        "https://vnexpress.net/rss/thoi-tiet.rss",
        "https://vnexpress.net/rss/tin-tuc-su-kien.rss",
    ], "VnExpress")

def scrape_tuoitre():
    return _scrape_bao_rss([
        "https://tuoitre.vn/rss/thoi-su.rss",
    ], "TuoiTre")

def scrape_dantri():
    return _scrape_bao_rss([
        "https://dantri.com.vn/xa-hoi.rss",
    ], "DanTri")

def scrape_thanhnien():
    return _scrape_bao_rss([
        "https://thanhnien.vn/rss/thoi-su.rss",
    ], "ThanhNien")

# ── Gửi Telegram (nhiều Chat ID) ─────────────────────────────────────────────
def _gui_mot(chat_id, msg, url_api, retries=3):
    payload = {"chat_id": chat_id, "text": msg,
               "parse_mode": "HTML", "disable_web_page_preview": False}
    for i in range(1, retries+1):
        try:
            r = requests.post(url_api, json=payload, timeout=30)
            if r.status_code == 200:
                print(f"[TG] ✅ → {chat_id}"); return
            print(f"[TG] ❌ {chat_id}: {r.text[:80]}"); return
        except requests.exceptions.Timeout:
            print(f"[TG] ⏱ Timeout {i}/{retries}"); time.sleep(3)
        except Exception as e:
            print(f"[TG] ❌ {e}"); return
    print(f"[TG] ❌ Bỏ qua {chat_id} sau {retries} lần")

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg); return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ids = [i.strip() for i in TELEGRAM_CHAT_ID.split(",") if i.strip()]
    for cid in ids:
        _gui_mot(cid, msg, url)
        if len(ids) > 1: time.sleep(0.3)

# ── Format thẻ bão 5 trường ──────────────────────────────────────────────────
def format_storm_card(s, stt=None):
    cap_so = s.get("cap_so", 0)
    icon = "🌀🌀" if cap_so>=5 else "🌀" if cap_so>=3 else "⚠️" if cap_so>=1 else "🔵"
    in_bd = " 🇻🇳" if s.get("in_bd") else ""
    dau   = f"{stt}." if stt else "•"
    ten   = s.get("ten","Chưa đặt tên")
    cap   = s.get("cap_do","?")
    nguon = NGUON_VI.get(s.get("source",""), s.get("source",""))
    url   = s.get("url","")
    card  = (
        f"{icon} <b>{dau} {cap.upper()}{in_bd}</b>\n"
        f"{'─'*22}\n"
        f"1️⃣ <b>Tên:</b> {ten}\n"
        f"2️⃣ <b>Cấp độ:</b> {cap} ({s.get('cap_gio','')})\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {s.get('huong','Chưa xác định')}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {s.get('khu_vuc','Chưa xác định')}\n"
        f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {s.get('do_bo','Chưa xác định')}\n"
        f"📡 Nguồn: {nguon}\n"
    )
    if url: card += f"🔗 <a href='{url}'>Xem bài viết đầy đủ</a>"
    return card

def format_alert(s): return format_storm_card(s)

# ── Format báo cáo tổng hợp ──────────────────────────────────────────────────
def gio_tiep_theo():
    h = now_vn().hour
    for g in [2,8,14,20]:
        if g > h: return f"{g:02d}:00"
    return "02:00 (ngày mai)"

def gio_bao_cao_hien_tai():
    h = now_vn().hour
    if 1<=h<7:   return "02:00"
    if 7<=h<13:  return "08:00"
    if 13<=h<19: return "14:00"
    return "20:00"

def format_bao_cao(unique, new_storms, gio):
    def dedup(lst):
        seen, out = set(), []
        for x in lst:
            if x["id"] not in seen: seen.add(x["id"]); out.append(x)
        return out

    bao    = dedup([s for s in unique if s["cap_so"]>=3])
    at     = dedup([s for s in unique if s["cap_so"] in (1,2)])
    nhieu  = dedup([s for s in unique if s["cap_so"]==0])
    in_bd  = [s for s in unique if s.get("in_bd")]
    co_sk  = bool(bao or at or nhieu)

    if bao and in_bd:    dg = "🔴 <b>RẤT NGUY HIỂM — BÃO ĐANG Ở BIỂN ĐÔNG</b>"
    elif bao:            dg = "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif at and in_bd:   dg = "🟠 <b>CẦN THEO DÕI — ÁP THẤP VÀO BIỂN ĐÔNG</b>"
    elif at:             dg = "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    elif nhieu:          dg = "🟡 <b>THEO DÕI — CÓ NHIỄU ĐỘNG TRÊN BIỂN</b>"
    else:                dg = "🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ SỰ KIỆN BẤT THƯỜNG</b>"

    msg  = f"📋 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
    msg += f"🕐 {fmt_time_vn()}\n{'━'*24}\n\n{dg}\n\n"

    if not co_sk:
        msg += (
            "✅ <b>Không ghi nhận sự kiện nào:</b>\n"
            "  • Không có bão\n"
            "  • Không có áp thấp nhiệt đới\n"
            "  • Biển Đông và Tây TBD ổn định\n\n"
            "📡 Đã kiểm tra <b>7 nguồn</b> (JMA · JTWC · NCHMF · VnExpress · Tuổi Trẻ · Dân Trí · Thanh Niên)\n"
        )
    else:
        stt = 1
        for s in (bao+at+nhieu)[:6]:
            msg += format_storm_card(s, stt) + "\n"
            stt += 1
        if new_storms:
            msg += f"🆕 <b>Mới kể từ báo cáo trước:</b> {len(new_storms)} tin\n\n"

    msg += f"{'━'*24}\n"
    msg += "📡 JMA · JTWC · NCHMF · VnExpress · Tuổi Trẻ · Dân Trí · Thanh Niên\n"
    msg += f"⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    return msg

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))

    unique = []
    seen   = set()

    for fn in [scrape_jma, scrape_jtwc, scrape_nchmf,
               scrape_vnexpress, scrape_tuoitre,
               scrape_dantri, scrape_thanhnien]:
        try:
            for s in fn():
                if s["id"] not in seen:
                    seen.add(s["id"]); unique.append(s)
        except Exception as e:
            print(f"[{fn.__name__}] {e}")

    print(f"[Bot] Tổng: {len(unique)} hệ thống")
    new_storms = [s for s in unique if s["id"] not in sent_ids]

    send_telegram(format_bao_cao(unique, new_storms, gio_bao_cao_hien_tai()))

    nghiem_moi = [s for s in new_storms if s["cap_so"]>=1]
    if nghiem_moi:
        send_telegram(f"🚨 <b>Chi tiết {len(nghiem_moi)} hệ thống mới:</b>")
        for s in nghiem_moi[:4]:
            send_telegram(format_storm_card(s))

    state["sent_ids"]     = (list(sent_ids)+[s["id"] for s in new_storms])[-300:]
    state["last_run_vn"]  = fmt_time_vn()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Xong.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Bot] ❌ Lỗi: {e}")
        import traceback; traceback.print_exc()
