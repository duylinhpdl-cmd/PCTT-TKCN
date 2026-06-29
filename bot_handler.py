"""
🤖 bot_handler.py v10
Fixes: offset lưu đúng, 24h.com.vn, hướng từ JMA/JTWC, tên bão rõ hơn,
dự kiến đổ bộ dựa tọa độ, bàn phím sau mọi tin, tắt link preview báo cáo
"""

import os, json, time, re, requests
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_IDS = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_F  = "bot_state.json"
API      = f"https://api.telegram.org/bot{TOKEN}"
ALLOWED  = {s.strip() for s in CHAT_IDS.split(",") if s.strip()}
VN_TZ    = timezone(timedelta(hours=7))
HEADERS  = {"User-Agent": "Mozilla/5.0 StormBot/1.0"}

VN_KW = [
    "áp thấp nhiệt đới","áp thấp","bão số","cơn bão","bão nhiệt đới",
    "bão mạnh","vùng áp thấp","nhiễu động","biển đông","đổ bộ",
    "cảnh báo bão","tin bão",
]

INTENSITY = [
    ("SUPER TYPHOON","Siêu bão",5),
    ("SEVERE TYPHOON","Bão rất mạnh",4),
    ("TYPHOON","Bão",3),
    ("TROPICAL STORM","Bão nhiệt đới",2),
    ("TROPICAL DEPRESSION","Áp thấp nhiệt đới",1),
    ("DISTURBANCE","Nhiễu động nhiệt đới",0),
    ("LOW","Vùng áp thấp",0),
]

DIRECTION_VI = {
    "N":"Bắc","NNE":"Bắc-Đông Bắc","NE":"Đông Bắc","ENE":"Đông-Đông Bắc",
    "E":"Đông","ESE":"Đông-Đông Nam","SE":"Đông Nam","SSE":"Nam-Đông Nam",
    "S":"Nam","SSW":"Nam-Tây Nam","SW":"Tây Nam","WSW":"Tây-Tây Nam",
    "W":"Tây","WNW":"Tây-Tây Bắc","NW":"Tây Bắc","NNW":"Bắc-Tây Bắc",
    "STATIONARY":"Đứng yên",
}

# ── Tiện ích ──────────────────────────────────────────────────────────────────
def now_vn(): return datetime.now(VN_TZ)
def fmt_vn(): return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")
def has_kw(t): return any(k in t.lower() for k in VN_KW)

def load_state():
    if os.path.exists(STATE_F):
        with open(STATE_F, encoding="utf-8") as f: return json.load(f)
    return {"offset": 0}

def save_state(s):
    with open(STATE_F, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def dich_cuong_do(text):
    t = text.upper()
    for en, vi, cap in INTENSITY:
        if en in t: return vi, cap
    if "siêu bão" in text.lower():  return "Siêu bão", 5
    if "bão số" in text.lower() or "cơn bão" in text.lower(): return "Bão", 3
    if "áp thấp nhiệt đới" in text.lower(): return "Áp thấp nhiệt đới", 1
    if "áp thấp" in text.lower():   return "Vùng áp thấp", 0
    return "Chưa xác định", -1

def parse_latlon(text):
    m = re.search(r"(\d+\.?\d*)\s*[Nn]\s+(\d+\.?\d*)\s*[Ee]", text)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)

def parse_num(s):
    m = re.search(r"(\d+\.?\d*)", str(s or ""))
    return float(m.group(1)) if m else None

def tinh_do_bo(lat, lon, huong_raw=""):
    """Ước tính dự kiến đổ bộ VN dựa theo tọa độ và hướng."""
    if lat is None or lon is None:
        return "Chưa đủ dữ liệu"
    h = huong_raw.upper()
    vao_vn = any(k in h for k in ["W","NW","WNW","WSW","SW"])
    # Đang ở Biển Đông
    if 100 <= lon <= 115 and 8 <= lat <= 23:
        kc = abs(lon - 109) * 111
        if kc < 150:  return "⚡ Trong vòng 12 giờ tới"
        if kc < 350:  return "Khoảng 1-2 ngày tới"
        return "Khoảng 2-4 ngày tới"
    # Đang ở Tây TBD
    if lon > 130:
        return "Khoảng 5-7 ngày nếu duy trì hướng hiện tại" if vao_vn \
               else "Chưa xác định — cần theo dõi thêm"
    if lon > 120:
        return "Khoảng 3-5 ngày tới" if vao_vn \
               else "Chưa xác định — hướng chưa rõ"
    return "Khoảng 1-3 ngày tới" if vao_vn else "Chưa xác định"

def ten_bao_dep(ten_en, ma_so=""):
    """Hiển thị tên bão rõ hơn."""
    if not ten_en or ten_en in ("?","UNNAMED","NO NAME"):
        if ma_so: return f"Chưa đặt tên ({ma_so})"
        return "Chưa đặt tên"
    return ten_en.title()

# ── Telegram API ──────────────────────────────────────────────────────────────
def tg(method, **p):
    try:
        r = requests.post(f"{API}/{method}", json=p, timeout=15)
        return r.json()
    except Exception as e:
        print(f"[TG/{method}] {e}"); return {}

def send(chat_id, text, kb=None, preview=False):
    p = {"chat_id": chat_id, "text": text,
         "parse_mode": "HTML",
         "disable_web_page_preview": not preview}
    if kb: p["reply_markup"] = kb
    return tg("sendMessage", **p)

def typing(chat_id): tg("sendChatAction", chat_id=chat_id, action="typing")

def get_updates(offset):
    res = tg("getUpdates", offset=offset, timeout=8, limit=10)
    return res.get("result", [])

def co_quyen(chat_id):
    if not ALLOWED: return True
    return str(chat_id) in ALLOWED

# ── Bàn phím ──────────────────────────────────────────────────────────────────
def kb_chinh():
    return {"keyboard":[
        [{"text":"🔍 Kiểm tra ngay"},{"text":"📊 Tóm tắt tình hình"}],
        [{"text":"🌀 Chỉ xem bão/áp thấp"},{"text":"📰 Tin báo VN"}],
        [{"text":"🛰 Nguồn quốc tế"},{"text":"ℹ️ Hướng dẫn"}],
    ],"resize_keyboard":True}

# ── Scraper NHANH ─────────────────────────────────────────────────────────────
def fetch_rss(url, timeout=8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return ET.fromstring(r.content).findall(".//item")
    except: return []

def scrape_nhanh_tat_ca():
    results = []

    # 1. NCHMF
    try:
        r = requests.get(
            "https://nchmf.gov.vn/Kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
            headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a")[:20]:
            t = a.get_text(strip=True)
            if len(t) > 10 and has_kw(t):
                h = a.get("href","")
                url = h if h.startswith("http") else "https://nchmf.gov.vn" + h
                cap, cap_so = dich_cuong_do(t)
                m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
                ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
                results.append({"src":"NCHMF","title":t,"url":url,
                                 "cap":cap,"cap_so":cap_so,"ten":ten,
                                 "huong":"Chưa xác định","do_bo":"Chưa xác định",
                                 "khu_vuc":"Biển Đông / Việt Nam"})
    except Exception as e: print(f"[NCHMF] {e}")

    # 2. VnExpress RSS
    for item in fetch_rss("https://vnexpress.net/rss/thoi-tiet.rss"):
        t = (item.findtext("title") or "").strip()
        u = (item.findtext("link") or "").strip()
        if not has_kw(t): continue
        cap, cap_so = dich_cuong_do(t)
        m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
        ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
        kv   = _tim_tinh(t)
        results.append({"src":"VnExpress","title":t,"url":u,
                         "cap":cap,"cap_so":cap_so,"ten":ten,
                         "huong":_tim_huong(t),"do_bo":"Chưa xác định",
                         "khu_vuc":kv or "Biển Đông / Việt Nam"})

    # 3. Tuổi Trẻ RSS
    for item in fetch_rss("https://tuoitre.vn/rss/thoi-su.rss"):
        t = (item.findtext("title") or "").strip()
        u = (item.findtext("link") or "").strip()
        if not has_kw(t): continue
        cap, cap_so = dich_cuong_do(t)
        m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
        ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
        results.append({"src":"Tuổi Trẻ","title":t,"url":u,
                         "cap":cap,"cap_so":cap_so,"ten":ten,
                         "huong":_tim_huong(t),"do_bo":"Chưa xác định",
                         "khu_vuc":_tim_tinh(t) or "Biển Đông / Việt Nam"})

    # 4. Dân Trí RSS
    for item in fetch_rss("https://dantri.com.vn/xa-hoi.rss"):
        t = (item.findtext("title") or "").strip()
        u = (item.findtext("link") or "").strip()
        if not has_kw(t): continue
        cap, cap_so = dich_cuong_do(t)
        m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
        ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
        results.append({"src":"Dân Trí","title":t,"url":u,
                         "cap":cap,"cap_so":cap_so,"ten":ten,
                         "huong":_tim_huong(t),"do_bo":"Chưa xác định",
                         "khu_vuc":_tim_tinh(t) or "Biển Đông / Việt Nam"})

    # 5. Thanh Niên RSS
    for item in fetch_rss("https://thanhnien.vn/rss/thoi-su.rss"):
        t = (item.findtext("title") or "").strip()
        u = (item.findtext("link") or "").strip()
        if not has_kw(t): continue
        cap, cap_so = dich_cuong_do(t)
        m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
        ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
        results.append({"src":"Thanh Niên","title":t,"url":u,
                         "cap":cap,"cap_so":cap_so,"ten":ten,
                         "huong":_tim_huong(t),"do_bo":"Chưa xác định",
                         "khu_vuc":_tim_tinh(t) or "Biển Đông / Việt Nam"})

    # 6. 24h.com.vn (web scrape)
    try:
        r = requests.get("https://www.24h.com.vn/thoi-tiet-c270.html",
                         headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True)[:30]:
            t = (a.get("title","") or a.get_text(strip=True))[:200]
            if len(t) < 15 or not has_kw(t): continue
            h = a.get("href","")
            url = h if h.startswith("http") else "https://www.24h.com.vn" + h
            cap, cap_so = dich_cuong_do(t)
            m_so = re.search(r"bão số\s*(\d+)", t, re.IGNORECASE)
            ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"
            results.append({"src":"24h","title":t,"url":url,
                             "cap":cap,"cap_so":cap_so,"ten":ten,
                             "huong":_tim_huong(t),"do_bo":"Chưa xác định",
                             "khu_vuc":_tim_tinh(t) or "Biển Đông / Việt Nam"})
    except Exception as e: print(f"[24h] {e}")

    # 7. JMA JSON — nguồn tọa độ chính xác nhất
    try:
        r = requests.get(
            "https://www.jma.go.jp/bosai/typhoon/data/tropicalCyclone.json",
            headers=HEADERS, timeout=8)
        data   = r.json()
        storms = data.get("TropicalCyclone", [])
        if isinstance(storms, dict): storms = [storms]
        for s in storms:
            name_en = s.get("name",{}).get("en","")
            inten   = s.get("intensity",{}).get("description",{}).get("en","")
            cap, cap_so = dich_cuong_do(inten)
            pos   = s.get("currentPosition",{})
            lat   = parse_num(pos.get("latitude",""))
            lon   = parse_num(pos.get("longitude",""))
            dir_en = s.get("movement",{}).get("direction",{}).get("en","")
            huong_vi = DIRECTION_VI.get(dir_en.upper().strip(), dir_en) if dir_en else "Chưa xác định"
            do_bo = tinh_do_bo(lat, lon, dir_en)
            ten   = ten_bao_dep(name_en)
            lat_s = f"{lat}°N" if lat else "?"
            lon_s = f"{lon}°E" if lon else "?"
            results.append({
                "src":"JMA","cap":cap,"cap_so":cap_so,"ten":ten,
                "title":f"{cap} {ten} tại {lat_s} {lon_s}",
                "url":"https://www.jma.go.jp/en/typh/",
                "huong":huong_vi,"do_bo":do_bo,
                "khu_vuc":_khu_vuc_toa_do(lat, lon),
                "lat":lat,"lon":lon,
            })
    except Exception as e: print(f"[JMA] {e}")

    # 8. JTWC RSS
    for item in fetch_rss("https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"):
        t = (item.findtext("title") or "").strip()
        u = (item.findtext("link") or "").strip()
        d = (item.findtext("description") or "")
        text = t + " " + d
        if not any(k in text.upper() for k in ["WP","WESTERN PACIFIC"]): continue
        if not any(k in text.upper() for k in ["DEPRESSION","STORM","TYPHOON"]): continue
        cap, cap_so = dich_cuong_do(text)
        lat, lon = parse_latlon(text)
        m_dir  = re.search(r"MOVING\s+([A-Z\-]+)\s+AT", text.upper())
        dir_raw = m_dir.group(1) if m_dir else ""
        huong_vi = DIRECTION_VI.get(dir_raw.upper(), dir_raw) if dir_raw else "Chưa xác định"
        m_name = re.search(r"(?:TYPHOON|TROPICAL STORM|TROPICAL DEPRESSION)\s+([\w\d]+)", t.upper())
        ma_so  = m_name.group(1) if m_name else ""
        ten    = ten_bao_dep("", ma_so)
        results.append({
            "src":"JTWC","title":t,"url":u,
            "cap":cap,"cap_so":cap_so,"ten":ten,
            "huong":huong_vi,"do_bo":tinh_do_bo(lat, lon, dir_raw),
            "khu_vuc":_khu_vuc_toa_do(lat, lon),
            "lat":lat,"lon":lon,
        })

    # Lọc trùng
    seen, unique = set(), []
    for x in results:
        k = x["title"][:50]
        if k not in seen:
            seen.add(k); unique.append(x)
    print(f"[Scraper] {len(unique)} tin từ 8 nguồn")
    return unique

# ── Helper trích xuất ─────────────────────────────────────────────────────────
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

def _tim_tinh(text):
    t = text.lower()
    found = []
    for kw, ten in TINH_VEN_BIEN.items():
        if kw in t and ten not in found: found.append(ten)
    return ", ".join(found[:3]) if found else ""

def _tim_huong(text):
    t = text.lower()
    for kw, val in [("tây bắc","Tây Bắc"),("tây nam","Tây Nam"),
                    ("đông bắc","Đông Bắc"),("đông nam","Đông Nam"),
                    ("hướng tây","Tây"),("hướng bắc","Bắc"),
                    ("hướng nam","Nam"),("hướng đông","Đông")]:
        if kw in t: return val
    return "Chưa xác định"

def _khu_vuc_toa_do(lat, lon):
    if lat is None: return "Chưa xác định"
    if 100 <= lon <= 125 and 5 <= lat <= 25: return "Biển Đông"
    if 100 <= lon <= 110 and 20 <= lat <= 23: return "Bắc Bộ VN"
    if 107 <= lon <= 110 and 15 <= lat <= 20: return "Trung Bộ VN"
    if 116 <= lon <= 128 and 5 <= lat <= 22: return "Tây Philippines"
    return f"Tây TBD ({lat:.0f}°N {lon:.0f}°E)"

def phan_loai(items):
    bao   = [x for x in items if x["cap_so"] >= 3]
    at    = [x for x in items if x["cap_so"] in (1,2)]
    nhieu = [x for x in items if x["cap_so"] == 0]
    return bao, at, nhieu

# ── Format thẻ chi tiết 5 trường ─────────────────────────────────────────────
def format_the(x, stt=None):
    cap_so = x.get("cap_so", 0)
    icon   = "🌀🌀" if cap_so>=5 else "🌀" if cap_so>=3 else "⚠️" if cap_so>=1 else "🔵"
    dau    = f"{stt}." if stt else "•"
    ten    = x.get("ten","Chưa đặt tên")
    cap    = x.get("cap","Chưa xác định")
    huong  = x.get("huong","Chưa xác định")
    kv     = x.get("khu_vuc","Chưa xác định")
    do_bo  = x.get("do_bo","Chưa xác định")
    src    = x.get("src","")
    url    = x.get("url","")

    card = (
        f"{icon} <b>{dau} {cap.upper()}</b>\n"
        f"{'─'*22}\n"
        f"1️⃣ <b>Tên:</b> {ten}\n"
        f"2️⃣ <b>Cấp độ:</b> {cap}\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {huong}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {kv}\n"
        f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {do_bo}\n"
        f"📡 Nguồn: {src}\n"
    )
    if url:
        card += f"🔗 <a href='{url}'>Xem chi tiết</a>"
    return card

def dong_tin(x):
    url  = x.get("url","")
    tieu = x["title"][:85] + ("..." if len(x["title"])>85 else "")
    src  = x.get("src","")
    if url: return f"  [{src}] <a href='{url}'>{tieu}</a>\n"
    return f"  [{src}] {tieu}\n"

# ── Xử lý lệnh ───────────────────────────────────────────────────────────────
def cmd_start(cid, ten="bạn"):
    send(cid,
        f"👋 Xin chào <b>{ten}</b>!\n\n"
        "🤖 <b>Bot Cảnh báo Thời tiết Việt Nam</b>\n"
        "Theo dõi bão, áp thấp từ Thái Bình Dương → Biển Đông.\n\n"
        "<b>Các lệnh:</b>\n"
        "🔍 <b>Kiểm tra ngay</b> — quét 8 nguồn tin\n"
        "📊 <b>Tóm tắt tình hình</b> — báo cáo tổng hợp\n"
        "🌀 <b>Chỉ xem bão/áp thấp</b> — lọc tin nghiêm trọng\n"
        "📰 <b>Tin báo VN</b> — NCHMF, VnExpress, 24h, Tuổi Trẻ...\n"
        "🛰 <b>Nguồn quốc tế</b> — JTWC, JMA\n\n"
        "⏰ Báo cáo tự động: 02h · 08h · 14h · 20h (GMT+7)\n"
        "⚠️ Phản hồi trong vòng tối đa 10 phút.\n\n"
        f"🕐 {fmt_vn()}", kb_chinh())

def cmd_kiem_tra(cid):
    typing(cid)
    send(cid, "⏳ Đang quét 8 nguồn tin, vui lòng chờ...")
    typing(cid)
    items = scrape_nhanh_tat_ca()
    bao, at, nhieu = phan_loai(items)

    if not items:
        send(cid,
            "✅ <b>Không có hiện tượng thời tiết bất thường</b>\n\n"
            "Đã kiểm tra 8 nguồn trong nước và quốc tế.\n"
            "Biển Đông và Tây Thái Bình Dương hiện ổn định.\n\n"
            f"🕐 {fmt_vn()}", kb_chinh()); return

    if bao and any(any(k in x["title"].lower() for k in ["đổ bộ","việt nam","biển đông"]) for x in bao):
        muc = "🔴 <b>RẤT NGUY HIỂM — BÃO Ở BIỂN ĐÔNG</b>"
    elif bao:  muc = "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif at:   muc = "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    else:      muc = "🟢 <b>THEO DÕI — CÓ NHIỄU ĐỘNG TRÊN BIỂN</b>"

    # Gửi tổng quan
    msg = f"🔍 <b>KẾT QUẢ KIỂM TRA</b>\n🕐 {fmt_vn()}\n{'━'*22}\n\n{muc}\n\n"
    if bao:
        msg += f"🌀 Bão: <b>{len(bao)}</b> hệ thống\n"
    if at:
        msg += f"⚠️ Áp thấp nhiệt đới: <b>{len(at)}</b> hệ thống\n"
    if nhieu:
        msg += f"🔵 Nhiễu động: <b>{len(nhieu)}</b> khu vực\n"
    send(cid, msg)

    # Gửi thẻ chi tiết 5 trường cho từng hệ thống nghiêm trọng
    nghiem = bao + at
    for i, x in enumerate(nghiem[:4], 1):
        time.sleep(0.3)
        send(cid, format_the(x, i), kb_chinh() if i == len(nghiem[:4]) else None)

    # Nếu chỉ có nhiễu động
    if not nghiem and nhieu:
        msg2 = f"🔵 <b>Nhiễu động / Vùng áp thấp:</b>\n"
        for x in nhieu[:3]: msg2 += dong_tin(x)
        send(cid, msg2, kb_chinh())

def cmd_tom_tat(cid):
    typing(cid)
    send(cid, "⏳ Đang tổng hợp...")
    items = scrape_nhanh_tat_ca()
    bao, at, nhieu = phan_loai(items)

    if not bao and not at and not nhieu: dg = "🟢 <b>BÌNH THƯỜNG</b>"
    elif bao:   dg = "🟠 <b>NGUY HIỂM — CÓ BÃO</b>"
    elif at:    dg = "🟡 <b>CẦN THEO DÕI</b>"
    else:       dg = "🟡 <b>THEO DÕI</b>"

    msg = (f"📊 <b>TÓM TẮT TÌNH HÌNH</b>\n"
           f"🕐 {fmt_vn()}\n{'━'*22}\n\n{dg}\n\n"
           f"🌀 Bão: <b>{len(bao)}</b> hệ thống\n"
           f"⚠️ Áp thấp nhiệt đới: <b>{len(at)}</b> hệ thống\n"
           f"🔵 Nhiễu động: <b>{len(nhieu)}</b> khu vực\n\n")

    if bao:
        msg += "🌀 <b>Bão đang theo dõi:</b>\n"
        for x in bao[:2]: msg += dong_tin(x)
    elif at:
        msg += "⚠️ <b>Áp thấp đang theo dõi:</b>\n"
        for x in at[:2]: msg += dong_tin(x)
    else:
        msg += "✅ Không ghi nhận sự kiện nghiêm trọng.\n"

    msg += f"\n{'━'*22}\n📡 NCHMF · VnExpress · 24h · Tuổi Trẻ · Dân Trí · Thanh Niên · JTWC · JMA"
    send(cid, msg, kb_chinh())

def cmd_bao_ap_thap(cid):
    typing(cid)
    items = scrape_nhanh_tat_ca()
    bao, at, _ = phan_loai(items)
    nghiem = bao + at

    if not nghiem:
        send(cid,
            "✅ <b>Không có bão hoặc áp thấp nhiệt đới</b>\n\n"
            "Không tìm thấy hệ thống nào đang hoạt động.\n\n"
            f"🕐 {fmt_vn()}", kb_chinh()); return

    send(cid, f"🌀 <b>BÃO / ÁP THẤP — {len(nghiem)} hệ thống</b>\n🕐 {fmt_vn()}")
    for i, x in enumerate(nghiem[:4], 1):
        time.sleep(0.3)
        send(cid, format_the(x, i), kb_chinh() if i == len(nghiem[:4]) else None)

def cmd_tin_vn(cid):
    typing(cid)
    nguon_vn = {"NCHMF","VnExpress","24h","Tuổi Trẻ","Dân Trí","Thanh Niên"}
    items = [x for x in scrape_nhanh_tat_ca() if x["src"] in nguon_vn]

    if not items:
        send(cid,
            "ℹ️ <b>Báo trong nước chưa có tin thời tiết bất thường</b>\n\n"
            f"🕐 {fmt_vn()}", kb_chinh()); return

    msg = f"📰 <b>TIN BÁO TRONG NƯỚC ({len(items)} bài)</b>\n"
    msg += f"🕐 {fmt_vn()}\n{'━'*22}\n\n"
    for x in items[:6]: msg += dong_tin(x) + "\n"
    send(cid, msg, kb_chinh())

def cmd_tin_qt(cid):
    typing(cid)
    nguon_qt = {"JMA","JTWC"}
    items = [x for x in scrape_nhanh_tat_ca() if x["src"] in nguon_qt]

    if not items:
        send(cid,
            "✅ <b>Nguồn quốc tế không ghi nhận hệ thống nguy hiểm</b>\n\n"
            "Đã kiểm tra: JTWC · JMA\n\n"
            f"🕐 {fmt_vn()}", kb_chinh()); return

    send(cid, f"🛰 <b>NGUỒN QUỐC TẾ — {len(items)} hệ thống</b>\n🕐 {fmt_vn()}")
    for i, x in enumerate(items[:4], 1):
        time.sleep(0.3)
        send(cid, format_the(x, i), kb_chinh() if i == len(items[:4]) else None)

def cmd_huong_dan(cid):
    send(cid,
        "ℹ️ <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n"
        f"{'━'*22}\n\n"
        "🔍 <b>Kiểm tra ngay</b>\n"
        "Quét 8 nguồn, hiển thị đủ 5 trường thông tin.\n\n"
        "📊 <b>Tóm tắt tình hình</b>\n"
        "Tổng hợp nhanh: số bão, áp thấp, nhiễu động.\n\n"
        "🌀 <b>Chỉ xem bão/áp thấp</b>\n"
        "Lọc riêng tin nghiêm trọng, hiển thị 5 trường.\n\n"
        "📰 <b>Tin báo VN</b>\n"
        "NCHMF, VnExpress, 24h, Tuổi Trẻ, Dân Trí, Thanh Niên.\n\n"
        "🛰 <b>Nguồn quốc tế</b>\n"
        "JTWC (Hải quân Mỹ), JMA (Nhật Bản).\n\n"
        f"{'━'*22}\n"
        "⏰ <b>Tự động báo cáo:</b> 02h · 08h · 14h · 20h (GMT+7)\n"
        "⚠️ <b>Phản hồi chậm tối đa 10 phút</b> (GitHub Actions miễn phí).\n\n"
        f"🕐 {fmt_vn()}", kb_chinh())

# ── Phân loại lệnh ───────────────────────────────────────────────────────────
def xu_ly(upd):
    msg  = upd.get("message") or upd.get("channel_post") or {}
    if not msg: return
    cid  = msg.get("chat",{}).get("id")
    text = (msg.get("text") or "").strip()
    ten  = msg.get("from",{}).get("first_name","bạn")
    if not cid or not text: return

    if not co_quyen(cid):
        send(cid, "⛔ Bạn không có quyền dùng bot này."); return

    print(f"[Bot] {cid}: {text[:40]}")

    cmd_map = {
        "/start": (cmd_start, True),
        "/help":  (cmd_start, True),
        "🔍 Kiểm tra ngay":        (cmd_kiem_tra, False),
        "/check":                  (cmd_kiem_tra, False),
        "📊 Tóm tắt tình hình":    (cmd_tom_tat, False),
        "/summary":                (cmd_tom_tat, False),
        "🌀 Chỉ xem bão/áp thấp":  (cmd_bao_ap_thap, False),
        "/bao":                    (cmd_bao_ap_thap, False),
        "📰 Tin báo VN":           (cmd_tin_vn, False),
        "/vn":                     (cmd_tin_vn, False),
        "🛰 Nguồn quốc tế":        (cmd_tin_qt, False),
        "/qt":                     (cmd_tin_qt, False),
        "ℹ️ Hướng dẫn":            (cmd_huong_dan, False),
        "/huongdan":               (cmd_huong_dan, False),
    }

    entry = cmd_map.get(text)
    if entry:
        fn, need_ten = entry
        fn(cid, ten) if need_ten else fn(cid)
    else:
        send(cid,
            f"❓ Không hiểu lệnh: <b>{text[:30]}</b>\n"
            "Nhấn nút bên dưới hoặc gõ /help", kb_chinh())

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        print("❌ Chưa cấu hình TELEGRAM_BOT_TOKEN"); return

    state  = load_state()
    offset = state.get("offset", 0)
    print(f"[Bot Handler] Bắt đầu lúc {fmt_vn()}, offset={offset}")

    poll_min  = int(os.environ.get("POLLING_MINUTES", "4"))
poll_min  = int(os.environ.get("POLLING_MINUTES", "4"))
deadline  = time.time() + poll_min * 60
print(f"[Bot Handler] Polling {poll_min} phút")
  
    while time.time() < deadline:
        try:
            updates = get_updates(offset)
        except Exception as e:
            print(f"[Polling] Lỗi: {e}"); time.sleep(5); continue

        for upd in updates:
            try:
                xu_ly(upd)
            except Exception as e:
                print(f"[xu_ly] Lỗi: {e}")
            offset = upd["update_id"] + 1
            processed += 1
            # Lưu ngay sau mỗi tin để không mất offset nếu crash
            state["offset"]   = offset
            state["last_run"] = fmt_vn()
            save_state(state)

        if not updates:
            state["offset"]   = offset
            state["last_run"] = fmt_vn()
            save_state(state)
            time.sleep(3)

    print(f"[Bot Handler] Xong. Đã xử lý {processed} cập nhật. Offset={offset}")

if __name__ == "__main__":
    main()
