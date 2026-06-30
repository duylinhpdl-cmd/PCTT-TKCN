"""
🌀 Storm Monitor Bot v8
Báo cáo đầy đủ 5 thông tin: tên · cấp độ · hướng · khu vực · dự kiến đổ bộ
Scrape nội dung bài báo + API JTWC/JMA để có dữ liệu chính xác nhất
Thời gian: giờ Việt Nam (GMT+7)
"""

import os, json, re, hashlib, requests, time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

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

# Từ khoá lọc bài báo tiếng Việt
VN_KEYWORDS = [
    "áp thấp nhiệt đới","áp thấp","bão số","cơn bão","bão nhiệt đới",
    "bão mạnh","vùng áp thấp","nhiễu động nhiệt đới","biển đông","đổ bộ",
    "ảnh hưởng bão","cảnh báo bão","tin bão khẩn",
]

# ── Bảng tra cứu ──────────────────────────────────────────────────────────────
# (từ khoá tiếng Anh, nhãn tiếng Việt, cấp số 0-5)
INTENSITY_TABLE = [
    ("SUPER TYPHOON",       "Siêu bão",             5),
    ("SEVERE TYPHOON",      "Bão rất mạnh",          4),
    ("TYPHOON",             "Bão",                  3),
    ("TROPICAL STORM",      "Bão nhiệt đới",         2),
    ("TROPICAL DEPRESSION", "Áp thấp nhiệt đới",    1),
    ("DISTURBANCE",         "Nhiễu động nhiệt đới", 0),
    ("LOW",                 "Vùng áp thấp",         0),
]

# Cấp gió Beaufort tương ứng
CAP_GIO_VI = {
    5: "Cấp 12+ (≥ 118 km/h)",
    4: "Cấp 11-12 (103-117 km/h)",
    3: "Cấp 8-12 (63-117 km/h)",
    2: "Cấp 6-7 (39-62 km/h)",
    1: "Cấp 6 (39-49 km/h)",
    0: "Dưới cấp 6",
}

DIRECTION_VI = {
    "N":"Bắc","NNE":"Bắc-Đông Bắc","NE":"Đông Bắc","ENE":"Đông-Đông Bắc",
    "E":"Đông","ESE":"Đông-Đông Nam","SE":"Đông Nam","SSE":"Nam-Đông Nam",
    "S":"Nam","SSW":"Nam-Tây Nam","SW":"Tây Nam","WSW":"Tây-Tây Nam",
    "W":"Tây","WNW":"Tây-Tây Bắc","NW":"Tây Bắc","NNW":"Bắc-Tây Bắc",
    "STATIONARY":"Đứng yên",
    # Tiếng Anh đầy đủ
    "NORTH":"Bắc","SOUTH":"Nam","EAST":"Đông","WEST":"Tây",
    "NORTHWEST":"Tây Bắc","NORTHEAST":"Đông Bắc",
    "SOUTHWEST":"Tây Nam","SOUTHEAST":"Đông Nam",
    "WEST-NORTHWEST":"Tây-Tây Bắc","WEST-SOUTHWEST":"Tây-Tây Nam",
    "EAST-NORTHEAST":"Đông-Đông Bắc","EAST-SOUTHEAST":"Đông-Đông Nam",
    # Tiếng Việt → chuẩn hoá
    "TÂY BẮC":"Tây Bắc","TÂY NAM":"Tây Nam",
    "ĐÔNG BẮC":"Đông Bắc","ĐÔNG NAM":"Đông Nam",
    "TÂY":"Tây","ĐÔNG":"Đông","BẮC":"Bắc","NAM":"Nam",
}

# Danh sách tỉnh/vùng ven biển VN để nhận diện khu vực ảnh hưởng
TINH_VEN_BIEN = {
    "quảng ninh":"Quảng Ninh","hải phòng":"Hải Phòng",
    "thái bình":"Thái Bình","nam định":"Nam Định","ninh bình":"Ninh Bình",
    "thanh hóa":"Thanh Hóa","nghệ an":"Nghệ An","hà tĩnh":"Hà Tĩnh",
    "quảng bình":"Quảng Bình","quảng trị":"Quảng Trị",
    "thừa thiên":"Thừa Thiên-Huế","huế":"Thừa Thiên-Huế",
    "đà nẵng":"Đà Nẵng","quảng nam":"Quảng Nam","quảng ngãi":"Quảng Ngãi",
    "bình định":"Bình Định","phú yên":"Phú Yên","khánh hòa":"Khánh Hòa",
    "ninh thuận":"Ninh Thuận","bình thuận":"Bình Thuận",
    "bà rịa":"Bà Rịa-Vũng Tàu","vũng tàu":"Bà Rịa-Vũng Tàu",
    "bến tre":"Bến Tre","trà vinh":"Trà Vinh","sóc trăng":"Sóc Trăng",
    "bạc liêu":"Bạc Liêu","cà mau":"Cà Mau","kiên giang":"Kiên Giang",
    "miền bắc":"Các tỉnh Bắc Bộ","miền trung":"Các tỉnh Trung Bộ",
    "miền nam":"Các tỉnh Nam Bộ","bắc bộ":"Bắc Bộ",
    "trung bộ":"Trung Bộ","nam bộ":"Nam Bộ",
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
    "NHC":      "Trung tâm Bão Quốc gia Mỹ (NHC/NOAA)",
}

# ── Tiện ích cơ bản ───────────────────────────────────────────────────────────
def now_vn():      return datetime.now(VN_TZ)
def fmt_time_vn(): return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")
def make_id(t):    return hashlib.md5(t.encode()).hexdigest()[:12]
def has_kw(t):     return any(k in t.lower() for k in VN_KEYWORDS)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    return {"sent_ids": []}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def get_page(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def send_telegram(msg, retries=3):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg); return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg,
               "parse_mode": "HTML", "disable_web_page_preview": False}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                print("[TG] ✅ Gửi OK")
                return
            else:
                print(f"[TG] ❌ HTTP {r.status_code}: {r.text[:120]}")
                return
        except requests.exceptions.Timeout:
            print(f"[TG] ⏱ Timeout lần {attempt}/{retries} — thử lại...")
            time.sleep(3)
        except Exception as e:
            print(f"[TG] ❌ Lỗi: {e}")
            return
    print(f"[TG] ❌ Bỏ qua sau {retries} lần thử — tin nhắn KHÔNG gửi được")

def in_zone(lat, lon, z):
    if lat is None or lon is None: return False
    return z["lat_min"] <= lat <= z["lat_max"] and z["lon_min"] <= lon <= z["lon_max"]

def in_bien_dong(lat, lon): return in_zone(lat, lon, BIEN_DONG)
def in_watch(lat, lon):     return in_zone(lat, lon, WATCH_ZONE)

# ── Helpers trích xuất ───────────────────────────────────────────────────────
def parse_latlon(text):
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)

def parse_num(s):
    m = re.search(r"(\d+\.?\d*)", str(s or ""))
    return float(m.group(1)) if m else None

def dich_cuong_do(text):
    t = text.upper()
    for en, vi, cap in INTENSITY_TABLE:
        if en in t: return vi, cap
    # Tiếng Việt
    if "siêu bão" in text.lower():           return "Siêu bão", 5
    if "bão rất mạnh" in text.lower():       return "Bão rất mạnh", 4
    if "cơn bão" in text.lower() or "bão số" in text.lower(): return "Bão", 3
    if "áp thấp nhiệt đới" in text.lower():  return "Áp thấp nhiệt đới", 1
    if "áp thấp" in text.lower():            return "Vùng áp thấp", 0
    return "Không xác định", 0

def dich_huong(raw):
    if not raw: return "Chưa xác định"
    return DIRECTION_VI.get(raw.upper().strip(), raw)

def tim_khu_vuc(text):
    """Tìm tỉnh/vùng ven biển VN trong đoạn văn."""
    t = text.lower()
    found = []
    for kw, ten in TINH_VEN_BIEN.items():
        if kw in t and ten not in found:
            found.append(ten)
    if found: return ", ".join(found[:3])
    if "biển đông" in t: return "Biển Đông"
    return ""

def tim_huong_vi(text):
    """Tìm hướng di chuyển trong tiếng Việt."""
    t = text.lower()
    patterns = [
        (r"di chuyển về hướng\s+([\w\s]+?)(?:\s+với|\s+tốc|\s*[,.]|$)", 1),
        (r"hướng\s+(tây bắc|tây nam|đông bắc|đông nam|tây|đông|bắc|nam)", 1),
        (r"(tây bắc|tây nam|đông bắc|đông nam)", 1),
    ]
    for pat, grp in patterns:
        m = re.search(pat, t)
        if m:
            h = m.group(grp).strip().upper()
            return DIRECTION_VI.get(h, h.title())
    return ""

def tim_toc_do_km(text):
    """Trích tốc độ gió km/h từ văn bản."""
    m = re.search(r"(\d+)\s*(?:km/h|km\/h|km\s+mỗi\s+giờ)", text, re.IGNORECASE)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:knots?|kt)", text, re.IGNORECASE)
    if m: return round(int(m.group(1)) * 1.852)
    return None

def tinh_cap_tu_gio(gio_km):
    if gio_km is None: return None
    if gio_km >= 118: return 5
    if gio_km >= 103: return 4
    if gio_km >= 63:  return 3
    if gio_km >= 39:  return 2
    if gio_km >= 29:  return 1
    return 0

def du_kien_do_bo(lat, lon, huong_raw):
    """Ước tính thô thời gian đổ bộ vào Việt Nam."""
    if lat is None or lon is None: return "Chưa đủ dữ liệu"
    h = (huong_raw or "").upper()
    huong_vao_vn = any(k in h for k in ["W","WEST","NW","SW","WNW","WSW",
                                         "TÂY","BẮC","NAM"])
    if in_bien_dong(lat, lon):
        kc = abs(lon - 109) * 111
        if kc < 150:  return "⚡ Trong vòng 12 giờ tới"
        if kc < 350:  return "Trong vòng 1-2 ngày tới"
        return "Trong vòng 2-4 ngày tới"
    if lon > 130:
        return "Khoảng 5-7 ngày nếu duy trì hướng hiện tại" if huong_vao_vn \
               else "Chưa xác định — cần theo dõi"
    if lon > 120:
        return "Khoảng 3-5 ngày tới" if huong_vao_vn \
               else "Chưa xác định — hướng chưa rõ"
    return "Khoảng 2-3 ngày tới" if huong_vao_vn else "Chưa xác định"

def xac_dinh_khu_vuc_toa_do(lat, lon):
    if lat is None: return "Chưa xác định"
    VUNG = [
        (20,23.5,102,108,"Bắc Bộ và vùng biển phía Bắc"),
        (15,20,107,110,  "Trung Bộ và vùng biển miền Trung"),
        (8,15,104,110,   "Nam Bộ và vùng biển phía Nam"),
        (5,25,100,125,   "Biển Đông"),
        (5,22,116,128,   "Tây Philippines"),
        (5,30,120,145,   "Tây Thái Bình Dương"),
    ]
    for la0,la1,lo0,lo1,name in VUNG:
        if la0<=lat<=la1 and lo0<=lon<=lo1:
            return name
    return f"Tọa độ {lat:.1f}°N {lon:.1f}°E"

# ── Cấu trúc dữ liệu bão chuẩn ───────────────────────────────────────────────
def make_storm(ten, loai, cap_so, lat, lon, huong_raw,
               khu_vuc_ah, url, source, title, toc_do_km=None):
    cap_do_vi = loai
    if toc_do_km:
        cap_so_from_gio = tinh_cap_tu_gio(toc_do_km)
        if cap_so_from_gio and cap_so_from_gio > cap_so:
            cap_so = cap_so_from_gio
            cap_do_vi = INTENSITY_TABLE[5-cap_so][1] if cap_so<=5 else loai

    huong_vi  = dich_huong(huong_raw)
    khu_vuc   = khu_vuc_ah or xac_dinh_khu_vuc_toa_do(lat, lon)
    do_bo     = du_kien_do_bo(lat, lon, huong_raw)
    cap_gio   = CAP_GIO_VI.get(cap_so, "Không xác định")
    gio_str   = f"{toc_do_km} km/h" if toc_do_km else ""

    return {
        "id":         make_id(ten + loai + str(lat) + str(lon) + url[:30]),
        "ten":        ten,
        "loai":       loai,
        "cap_do_vi":  cap_do_vi,
        "cap_so":     cap_so,
        "cap_gio":    cap_gio + (f" — {gio_str}" if gio_str else ""),
        "lat": lat, "lon": lon,
        "huong_raw":  huong_raw,
        "huong_vi":   huong_vi,
        "khu_vuc":    khu_vuc,
        "do_bo":      do_bo,
        "in_bien_dong": in_bien_dong(lat, lon),
        "url":    url,
        "source": source,
        "title":  title,
    }

# ── Nguồn 1: JMA JSON (dữ liệu cấu trúc tốt nhất) ───────────────────────────
def scrape_jma():
    storms = []
    try:
        r    = requests.get("https://www.jma.go.jp/bosai/typhoon/data/tropicalCyclone.json",
                            headers=HEADERS, timeout=15)
        data = r.json()
        items = data.get("TropicalCyclone", [])
        if isinstance(items, dict): items = [items]
        for s in items:
            name     = s.get("name",{}).get("en","Chưa đặt tên")
            intens   = s.get("intensity",{}).get("description",{}).get("en","")
            loai, cap_so = dich_cuong_do(intens)
            pos      = s.get("currentPosition",{})
            lat      = parse_num(pos.get("latitude",""))
            lon      = parse_num(pos.get("longitude",""))
            if lat and not in_watch(lat, lon): continue
            dir_en   = s.get("movement",{}).get("direction",{}).get("en","")
            spd_kt   = parse_num(s.get("movement",{}).get("speed",{}).get("knot","")) or 0
            wind_kt  = parse_num(s.get("maximumWind",{}).get("knot","")) or 0
            wind_km  = round(wind_kt * 1.852) if wind_kt else None

            # Khu vực ảnh hưởng: kết hợp tọa độ + cảnh báo JMA
            kv = xac_dinh_khu_vuc_toa_do(lat, lon)

            storms.append(make_storm(
                ten=name, loai=loai, cap_so=cap_so,
                lat=lat, lon=lon, huong_raw=dir_en,
                khu_vuc_ah=kv, toc_do_km=wind_km,
                url="https://www.jma.go.jp/en/typh/",
                source="JMA",
                title=f"{loai} {name} — {lat}°N {lon}°E",
            ))
    except Exception as e:
        print(f"[JMA] {e}")
    return storms

# ── Nguồn 2: JTWC RSS + đọc nội dung bản tin ─────────────────────────────────
def scrape_jtwc():
    storms = []
    try:
        r    = requests.get("https://www.metoc.navy.mil/jtwc/rss/jtwc.rss",
                            headers=HEADERS, timeout=15)
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            text  = title + " " + desc
            if not any(k in text.upper() for k in ["WP","WESTERN PACIFIC"]): continue
            if not any(k in text.upper()
                       for k in ["DEPRESSION","STORM","TYPHOON","DISTURBANCE"]): continue

            lat, lon = parse_latlon(text)
            if lat and not in_watch(lat, lon): continue

            loai, cap_so = dich_cuong_do(text)

            # Hướng: "MOVING WNW AT 12 KT"
            m_dir  = re.search(r"MOVING\s+([A-Z\-]+)\s+AT\s+(\d+)\s*KT", text.upper())
            dir_raw  = m_dir.group(1) if m_dir else ""
            spd_kt   = int(m_dir.group(2)) if m_dir else 0

            # Tốc độ gió tối đa: "MAX SUSTAINED WINDS 45 KT"
            m_wind = re.search(r"MAX(?:IMUM)?\s+SUSTAINED\s+WINDS?\s+(\d+)\s*KT", text.upper())
            wind_km = round(int(m_wind.group(1)) * 1.852) if m_wind else None

            # Tên: "TROPICAL DEPRESSION 09W" hoặc "TYPHOON BEBINCA"
            m_name = re.search(
                r"(?:TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION|DISTURBANCE)\s+([\w\d]+)",
                title.upper())
            ten = m_name.group(1) if m_name else "N/A"

            # Đọc thêm nội dung bản tin nếu có link
            khu_vuc = xac_dinh_khu_vuc_toa_do(lat, lon)
            if link:
                try:
                    r2   = requests.get(link, headers=HEADERS, timeout=8)
                    body = r2.text[:3000]
                    kv2  = tim_khu_vuc(body)
                    if kv2: khu_vuc = kv2
                except Exception:
                    pass

            storms.append(make_storm(
                ten=ten, loai=loai, cap_so=cap_so,
                lat=lat, lon=lon, huong_raw=dir_raw,
                khu_vuc_ah=khu_vuc, toc_do_km=wind_km,
                url=link, source="JTWC", title=title,
            ))
    except Exception as e:
        print(f"[JTWC] {e}")
    return storms

# ── Nguồn 3: NCHMF — đọc nội dung bài ───────────────────────────────────────
def scrape_nchmf():
    storms = []
    pages = [
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
        "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-ap-thap-nhiet-doi-post.html",
    ]
    for page in pages:
        try:
            soup = get_page(page)
            links = [(a.get_text(strip=True), a.get("href",""))
                     for a in soup.select("a") if has_kw(a.get_text(strip=True))][:5]
            for tieu_de, href in links:
                url = href if href.startswith("http") else "https://nchmf.gov.vn" + href
                loai, cap_so = dich_cuong_do(tieu_de)

                # Đọc nội dung bài để lấy thông tin chi tiết
                noi_dung = ""
                try:
                    soup2    = get_page(url)
                    noi_dung = soup2.get_text(separator=" ")[:4000]
                except Exception:
                    noi_dung = tieu_de

                all_text = tieu_de + " " + noi_dung

                # Trích 5 trường từ nội dung
                m_so    = re.search(r"bão số\s*(\d+)", all_text, re.IGNORECASE)
                ten     = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
                huong   = tim_huong_vi(all_text) or ""
                kv      = tim_khu_vuc(all_text) or "Biển Đông / Việt Nam"
                lat,lon = parse_latlon(all_text)
                gio_km  = tim_toc_do_km(all_text)

                # Cập nhật cấp từ tốc độ gió thực
                if gio_km:
                    cap_from_gio = tinh_cap_tu_gio(gio_km)
                    if cap_from_gio and cap_so == 0:
                        cap_so = cap_from_gio

                # Dự kiến đổ bộ — tìm trong bài
                do_bo_text = ""
                m_db = re.search(
                    r"(?:dự kiến|có thể|khả năng)\s+(?:đổ bộ|ảnh hưởng)[^.]{0,120}",
                    all_text, re.IGNORECASE)
                if m_db:
                    do_bo_text = m_db.group(0).strip()[:120]

                storms.append(make_storm(
                    ten=ten, loai=loai, cap_so=cap_so,
                    lat=lat, lon=lon, huong_raw=huong,
                    khu_vuc_ah=kv, toc_do_km=gio_km,
                    url=url, source="NCHMF", title=tieu_de,
                ))
                if do_bo_text:
                    storms[-1]["do_bo"] = do_bo_text
        except Exception as e:
            print(f"[NCHMF] {e}")
    return storms

# ── Nguồn 4-8: Báo VN — đọc nội dung bài báo ────────────────────────────────
def _doc_noi_dung_bai(url, timeout=8):
    """Đọc và trả về văn bản bài báo (tối đa 3000 ký tự)."""
    try:
        r    = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        # Xoá script/style
        for tag in soup(["script","style","nav","header","footer"]): tag.decompose()
        return soup.get_text(separator=" ")[:3000]
    except Exception:
        return ""

def _xu_ly_bai(title, link, source, doc_noi_dung=True):
    """Trích 5 trường từ 1 bài báo."""
    noi_dung = _doc_noi_dung_bai(link) if (doc_noi_dung and link) else ""
    all_text = title + " " + noi_dung

    loai, cap_so = dich_cuong_do(all_text)

    m_so = re.search(r"bão số\s*(\d+)", all_text, re.IGNORECASE)
    ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"

    huong  = tim_huong_vi(all_text)
    kv     = tim_khu_vuc(all_text) or "Biển Đông / Việt Nam"
    lat,lon= parse_latlon(all_text)
    gio_km = tim_toc_do_km(all_text)

    # Dự kiến đổ bộ từ nội dung bài
    do_bo_text = ""
    m_db = re.search(
        r"(?:dự kiến|có thể|khả năng)\s+(?:đổ bộ|ảnh hưởng|vào đất liền)[^.]{0,150}",
        all_text, re.IGNORECASE)
    if m_db:
        do_bo_text = m_db.group(0).strip()[:150]

    s = make_storm(ten=ten, loai=loai, cap_so=cap_so,
                   lat=lat, lon=lon, huong_raw=huong,
                   khu_vuc_ah=kv, toc_do_km=gio_km,
                   url=link, source=source, title=title)
    if do_bo_text:
        s["do_bo"] = do_bo_text
    return s

def _scrape_rss_bao(rss_urls, source):
    storms = []
    for rss in rss_urls:
        try:
            r    = requests.get(rss, headers=HEADERS, timeout=15)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:10]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text()
                if not has_kw(title + " " + desc): continue
                storms.append(_xu_ly_bai(title, link, source))
                time.sleep(0.3)
        except Exception as e:
            print(f"[{source}] {e}")
    return storms

def _scrape_web_bao(web_urls, source, base=""):
    storms = []
    for url in web_urls:
        try:
            soup = get_page(url)
            for a in soup.find_all("a", href=True)[:40]:
                text = a.get("title","") or a.get_text(strip=True)
                href = a.get("href","")
                if len(text) < 15 or not has_kw(text): continue
                full = href if href.startswith("http") else base + href
                storms.append(_xu_ly_bai(text[:200], full, source))
                time.sleep(0.3)
        except Exception as e:
            print(f"[{source} web] {e}")
    return storms

def scrape_vnexpress():
    return _scrape_rss_bao([
        "https://vnexpress.net/rss/thoi-tiet.rss",
        "https://vnexpress.net/rss/tin-tuc-su-kien.rss",
    ], "VnExpress")

def scrape_24h():
    return _scrape_web_bao([
        "https://www.24h.com.vn/thoi-tiet-c270.html",
    ], "24h", "https://www.24h.com.vn")

def scrape_dantri():
    return _scrape_rss_bao(["https://dantri.com.vn/xa-hoi.rss"], "DanTri")

def scrape_tuoitre():
    return _scrape_rss_bao([
        "https://tuoitre.vn/rss/thoi-su.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    ], "TuoiTre")

def scrape_thanhnien():
    return _scrape_rss_bao([
        "https://thanhnien.vn/rss/thoi-su.rss",
    ], "ThanhNien")

def scrape_nhc():
    storms = []
    try:
        soup = get_page("https://www.nhc.noaa.gov/productlist.shtml")
        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if not cells: continue
            text = " ".join(c.get_text() for c in cells)
            if "WESTERN PACIFIC" not in text.upper(): continue
            if not any(k in text.upper() for k in ["DEPRESSION","STORM","TYPHOON"]): continue
            a    = row.find("a")
            link = ("https://www.nhc.noaa.gov" + a["href"]) if a else ""
            loai, cap_so = dich_cuong_do(text)
            storms.append(make_storm(
                ten="Hệ thống TBD", loai=loai, cap_so=cap_so,
                lat=None, lon=None, huong_raw="",
                khu_vuc_ah="Tây Thái Bình Dương",
                url=link, source="NHC", title=text[:120].strip(),
            ))
    except Exception as e:
        print(f"[NHC] {e}")
    return storms

# ── Format thẻ 5 thông tin ───────────────────────────────────────────────────
def format_storm_card(s, stt=None):
    cap_so = s.get("cap_so", 0)
    if cap_so >= 5:   icon = "🌀🌀"
    elif cap_so >= 3: icon = "🌀"
    elif cap_so == 2: icon = "🌪️"
    elif cap_so == 1: icon = "⚠️"
    else:             icon = "🔵"

    in_bd  = " 🇻🇳" if s.get("in_bien_dong") else ""
    ten    = s.get("ten", "Chưa đặt tên")
    loai   = s.get("cap_do_vi", s.get("loai","?"))
    nguon  = NGUON_VI.get(s.get("source",""), s.get("source",""))
    tieu   = f"{stt}." if stt else "•"
    url    = s.get("url","")

    card = (
        f"{icon} <b>{tieu} {loai.upper()}{in_bd}</b>\n"
        f"{'─' * 22}\n"
        f"1️⃣ <b>Tên:</b> {ten}\n"
        f"2️⃣ <b>Cấp độ:</b> {loai} ({s.get('cap_gio','Không xác định')})\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {s.get('huong_vi','Chưa xác định')}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {s.get('khu_vuc','Chưa xác định')}\n"
        f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {s.get('do_bo','Chưa xác định')}\n"
        f"📡 Nguồn: {nguon}\n"
    )
    if url:
        card += f"🔗 <a href='{url}'>Xem chi tiết</a>\n"
    return card

def format_alert(s):
    return format_storm_card(s)

# ── Format báo cáo định kỳ ───────────────────────────────────────────────────
def format_bao_cao(unique, new_storms, gio_bao_cao):
    def dedup(lst):
        seen, out = set(), []
        for x in lst:
            if x["id"] not in seen: seen.add(x["id"]); out.append(x)
        return out

    bao       = dedup([s for s in unique if s["cap_so"] >= 3])
    at_nhiet  = dedup([s for s in unique if s["cap_so"] in (1,2)])
    nhieu_dong= dedup([s for s in unique if s["cap_so"] == 0
                        and s["loai"] not in ("Không xác định","")])
    bien_dong = [s for s in unique if s.get("in_bien_dong")]
    co_sk     = bool(bao or at_nhiet or nhieu_dong)

    if bao and bien_dong:     danh_gia = "🔴 <b>RẤT NGUY HIỂM — BÃO ĐANG Ở BIỂN ĐÔNG</b>"
    elif bao:                 danh_gia = "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif at_nhiet and bien_dong: danh_gia = "🟠 <b>CẦN THEO DÕI — ÁP THẤP VÀO BIỂN ĐÔNG</b>"
    elif at_nhiet:            danh_gia = "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    elif nhieu_dong:          danh_gia = "🟡 <b>THEO DÕI — CÓ NHIỄU ĐỘNG TRÊN BIỂN</b>"
    else:                     danh_gia = "🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ SỰ KIỆN BẤT THƯỜNG</b>"

    msg  = f"📋 <b>BÁO CÁO THỜI TIẾT {gio_bao_cao}</b>\n"
    msg += f"🕐 {fmt_time_vn()}\n"
    msg += f"{'━' * 24}\n\n"
    msg += f"{danh_gia}\n\n"

    if not co_sk:
        msg += (
            "✅ <b>Không ghi nhận sự kiện nào:</b>\n"
            "  • Không có bão\n"
            "  • Không có áp thấp nhiệt đới\n"
            "  • Không có nhiễu động đáng kể\n"
            "  • Biển Đông và Tây TBD ổn định\n\n"
            "📡 Đã kiểm tra <b>9 nguồn</b> trong nước và quốc tế.\n"
        )
    else:
        stt = 1
        for s in (bao + at_nhiet + nhieu_dong)[:6]:
            msg += format_storm_card(s, stt) + "\n"
            stt += 1
        if new_storms:
            msg += f"🆕 <b>Mới kể từ báo cáo trước:</b> {len(new_storms)} tin\n\n"

    msg += f"{'━' * 24}\n"
    msg += "📡 Nguồn: NCHMF · VnExpress · 24h · Dân Trí · Tuổi Trẻ · Thanh Niên · JTWC · JMA · NOAA\n"
    msg += f"⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    return msg

def gio_tiep_theo():
    h = now_vn().hour
    for g in [2, 8, 14, 20]:
        if g > h: return f"{g:02d}:00"
    return "02:00 (ngày mai)"

def gio_bao_cao_hien_tai():
    h = now_vn().hour
    if 1 <= h < 7:   return "02:00"
    if 7 <= h < 13:  return "08:00"
    if 13 <= h < 19: return "14:00"
    return "20:00"

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))

    unique = []
    seen   = set()
    for fn in [scrape_jma, scrape_jtwc, scrape_nchmf,
               scrape_vnexpress, scrape_24h, scrape_dantri,
               scrape_tuoitre, scrape_thanhnien, scrape_nhc]:
        try:
            for s in fn():
                if s["id"] not in seen:
                    seen.add(s["id"]); unique.append(s)
        except Exception as e:
            print(f"  [{fn.__name__}] {e}")

    print(f"[Bot] Tổng: {len(unique)} hệ thống")
    new_storms = [s for s in unique if s["id"] not in sent_ids]

    send_telegram(format_bao_cao(unique, new_storms, gio_bao_cao_hien_tai()))

    nghiem_moi = [s for s in new_storms if s["cap_so"] >= 1]
    if nghiem_moi:
        send_telegram(f"🚨 <b>Chi tiết {len(nghiem_moi)} hệ thống nghiêm trọng mới:</b>")
        for s in nghiem_moi[:4]:
            send_telegram(format_storm_card(s))

    state["sent_ids"]     = (list(sent_ids) + [s["id"] for s in new_storms])[-300:]
    state["last_run_vn"]  = fmt_time_vn()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Xong.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Bot] ❌ Lỗi nghiêm trọng không lường trước: {e}")
        import traceback
        traceback.print_exc()
        # Không exit(1) để workflow không báo Failure, vẫn tiếp tục lưu state

