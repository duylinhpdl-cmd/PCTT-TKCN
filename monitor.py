"""
🌀 Storm Monitor Bot v22
Nguồn: nchmf.gov.vn (kttvsite - chữ thường)
Logic:
  1. Quét trang listing Bão/ATNĐ → tìm cặp (thumbnail=ảnh đường đi, link=bài viết)
  2. Đọc bài viết → xác nhận có nội dung khí tượng thật
  3. Chỉ gửi khi có bài viết thật VÀ có ảnh đường đi
  4. Khi không có sự kiện → gửi báo cáo bình thường
"""

import os, json, re, hashlib, requests, time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.json"
VN_TZ = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# URL chính xác (chữ thường kttvsite)
LISTING_URL = "https://nchmf.gov.vn/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html"
BASE = "https://nchmf.gov.vn"
KTTV_BASE = "https://kttv.gov.vn"

# Nhận diện URL bài viết thật: phải có đuôi -postNNNN.html
RE_BAI_VIET = re.compile(r"-post\d+\.html$", re.IGNORECASE)

# Nhận diện URL trang danh mục (KHÔNG phải bài viết)
RE_DANH_MUC = re.compile(
    r"-\d{3,5}-\d{1,3}\.html$|/index\.html$|/homerss\.html$', re.IGNORECASE"
)

# Từ khoá xác nhận KHÔNG có sự kiện
KHONG_CO = [
    "đang cập nhật dữ liệu", "đang cập nhật", "hiện không có",
    "không có bão", "không có áp thấp", "currently no", "no active",
]

# Từ khoá xác nhận CÓ bão/ATNĐ thật
CO_BAO = [
    "áp thấp nhiệt đới", "bão số", "cơn bão", "bão nhiệt đới",
    "siêu bão", "tropical depression", "tropical storm", "typhoon",
]

# Từ khoá khí tượng cụ thể — phải có ≥ 3
KW_KHI_TUONG = [
    "km/h", "cấp ", "sức gió", "gió giật", "vĩ bắc", "kinh đông",
    "tây bắc", "tây nam", "đông bắc", "đông nam",
    "hướng tây", "hướng bắc", "hướng nam", "hướng đông",
    "đổ bộ", "ảnh hưởng", "vùng biển", "ven biển", "đất liền",
    "mbar", "hpa", "knot", "sóng biển",
    "quảng ninh","hải phòng","thanh hóa","nghệ an","hà tĩnh",
    "quảng bình","quảng trị","đà nẵng","quảng nam","quảng ngãi",
    "bình định","phú yên","khánh hòa","biển đông","hoàng sa",
]

TINH = {
    "quảng ninh":"Quảng Ninh","hải phòng":"Hải Phòng","thái bình":"Thái Bình",
    "nam định":"Nam Định","thanh hóa":"Thanh Hóa","nghệ an":"Nghệ An",
    "hà tĩnh":"Hà Tĩnh","quảng bình":"Quảng Bình","quảng trị":"Quảng Trị",
    "thừa thiên":"Thừa Thiên-Huế","đà nẵng":"Đà Nẵng","quảng nam":"Quảng Nam",
    "quảng ngãi":"Quảng Ngãi","bình định":"Bình Định","phú yên":"Phú Yên",
    "khánh hòa":"Khánh Hòa","ninh thuận":"Ninh Thuận","bình thuận":"Bình Thuận",
    "vũng tàu":"Bà Rịa-Vũng Tàu","cà mau":"Cà Mau","kiên giang":"Kiên Giang",
    "miền bắc":"Các tỉnh Bắc Bộ","miền trung":"Các tỉnh Trung Bộ",
    "miền nam":"Các tỉnh Nam Bộ","bắc bộ":"Bắc Bộ","trung bộ":"Trung Bộ",
    "hoàng sa":"Khu vực Hoàng Sa","trường sa":"Khu vực Trường Sa",
}

CAP_GIO = {
    5:"Cấp 12+ (≥118 km/h) — Siêu bão",
    4:"Cấp 11-12 (103-117 km/h) — Bão rất mạnh",
    3:"Cấp 8-12 (63-117 km/h) — Bão",
    2:"Cấp 6-7 (39-62 km/h) — Bão nhiệt đới",
    1:"Cấp 6 (39-49 km/h) — Áp thấp nhiệt đới",
    0:"Dưới cấp 6",
}

# ── Tiện ích ──────────────────────────────────────────────────────────────────
def now_vn():      return datetime.now(VN_TZ)
def fmt_vn():      return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")
def make_id(s):    return hashlib.md5(s.encode()).hexdigest()[:12]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    return {"sent_ids": []}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def gio_tiep_theo():
    h = now_vn().hour
    for g in [2,8,14,20]:
        if g > h: return f"{g:02d}:00"
    return "02:00 (ngày mai)"

def gio_hien_tai():
    h = now_vn().hour
    if 1<=h<7:   return "02:00"
    if 7<=h<13:  return "08:00"
    if 13<=h<19: return "14:00"
    return "20:00"

def full_url(href):
    if not href: return ""
    href = href.strip()
    if href.startswith("http"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"): return BASE + href
    return BASE + "/" + href

def la_bai_viet(url):
    """Bài viết thật: URL kết thúc bằng -postNNNN.html"""
    return bool(RE_BAI_VIET.search(url))

# ── Đọc trang ────────────────────────────────────────────────────────────────
def get_soup(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[HTTP] Lỗi {url[:60]}: {e}")
        return None

def get_text(soup):
    if not soup: return ""
    for t in soup(["script","style","nav","header","footer","aside"]): t.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(separator=" ")).strip()

# ── Kiểm tra ─────────────────────────────────────────────────────────────────
def la_khong_co(text):
    t = text.lower()
    return any(k in t for k in KHONG_CO)

def co_bao_that(text):
    t = text.lower()
    return any(k in t for k in CO_BAO)

def du_khi_tuong(text):
    t = text.lower()
    return sum(1 for k in KW_KHI_TUONG if k in t) >= 3

# ── Trích xuất ảnh từ URL kttv.gov.vn ───────────────────────────────────────
def chuan_hoa_anh(src):
    """Trả về URL ảnh đầy đủ từ src có thể là relative."""
    if not src: return None
    src = src.strip()
    if src.startswith("http"): return src
    if src.startswith("//"): return "https:" + src
    if src.startswith("/"): return KTTV_BASE + src
    return None

# ── Quét trang listing lấy (bài viết, ảnh thumbnail) ─────────────────────────
def lay_ban_tin_tu_listing(soup):
    """
    Tìm các cặp (url_bai_viet, url_anh_thumbnail, tieu_de) trên trang listing.
    Cấu trúc NCHMF: <a href="article"><img src="thumb"/></a> rồi <a href="article">Tiêu đề</a>
    """
    ket_qua = []
    seen = set()

    # Tìm tất cả <a> chứa <img> → đây là thumbnail bài viết
    for a_img in soup.find_all("a", href=True):
        href = a_img.get("href","")
        url = full_url(href)
        if not la_bai_viet(url): continue

        img = a_img.find("img")
        if not img: continue

        anh = chuan_hoa_anh(img.get("src",""))
        if not anh: continue

        # Tìm tiêu đề: <a> tiếp theo có cùng href
        tieu_de = ""
        # Thử lấy tiêu đề từ <a> cùng href gần nhất
        for a2 in soup.find_all("a", href=True):
            if full_url(a2.get("href","")) == url and not a2.find("img"):
                tieu_de = a2.get_text(strip=True)
                if tieu_de: break

        # Kiểm tra tiêu đề có từ khoá bão không
        if not tieu_de:
            tieu_de = img.get("alt","") or url.split("/")[-1]

        t = tieu_de.lower()
        if not any(k in t for k in ["bão","áp thấp","tropical","typhoon","atnđ","atnd"]):
            continue

        if url not in seen:
            seen.add(url)
            ket_qua.append({
                "url": url,
                "anh": anh,
                "tieu_de": tieu_de,
            })
            print(f"[Listing] ✅ Tìm thấy: {tieu_de[:60]}")
            print(f"           Ảnh: {anh[:70]}")

    return ket_qua

# ── Trích xuất thông tin bão từ nội dung bài ─────────────────────────────────
def trich_xuat(text, tieu_de=""):
    all_text = tieu_de + " " + text

    # Tên/loại
    if re.search(r"bão số\s*(\d+)", all_text, re.I):
        m = re.search(r"bão số\s*(\d+)", all_text, re.I)
        ten = f"Bão số {m.group(1)}"; loai = "Bão"; cap_so = 3
    elif re.search(r"áp thấp nhiệt đới", all_text, re.I):
        ten = "Áp thấp nhiệt đới"; loai = "Áp thấp nhiệt đới"; cap_so = 1
    elif re.search(r"siêu bão", all_text, re.I):
        ten = "Siêu bão"; loai = "Siêu bão"; cap_so = 5
    elif re.search(r"cơn bão|bão nhiệt đới|bão mạnh", all_text, re.I):
        ten = "Bão nhiệt đới"; loai = "Bão"; cap_so = 3
    else:
        ten = "Hệ thống thời tiết nguy hiểm"
        loai = "Cần theo dõi"; cap_so = 0

    # Cấp độ từ văn bản
    m_cap = re.search(r"mạnh cấp\s*(\d+)", all_text, re.I)
    if not m_cap: m_cap = re.search(r"cấp\s*(\d+)", all_text, re.I)
    if m_cap:
        c = int(m_cap.group(1))
        if c>=12: cap_so=5
        elif c>=11: cap_so=4
        elif c>=8:  cap_so=3
        elif c>=6:  cap_so=max(cap_so,2)
        elif c>=1:  cap_so=max(cap_so,1)

    # Giật cấp
    m_giat = re.search(r"giật cấp\s*(\d+)", all_text, re.I)
    giat_str = f", giật cấp {m_giat.group(1)}" if m_giat else ""

    # Tốc độ gió km/h
    m_gio = re.search(r"(\d+)[-–](\d+)\s*km/h", all_text, re.I)
    if not m_gio: m_gio = re.search(r"(\d{2,3})\s*km/h", all_text, re.I)
    gio_str = f" ({m_gio.group(0)})" if m_gio else ""

    cap_gio = CAP_GIO.get(cap_so, "?") + gio_str + giat_str

    # Vị trí tọa độ
    m_vt = re.search(r"(\d+[,.]?\d*)\s*độ\s*vĩ\s*bắc[;,]?\s*(\d+[,.]?\d*)\s*độ\s*kinh\s*đông", all_text, re.I)
    if not m_vt:
        m_vt = re.search(r"(\d+\.?\d*)[Nn][;\s]+(\d+\.?\d*)[Ee]", all_text)
    vi_tri = ""
    if m_vt:
        lat = m_vt.group(1).replace(",",".")
        lon = m_vt.group(2).replace(",",".")
        vi_tri = f"{lat}°N, {lon}°E"

    # Hướng di chuyển
    huong = "Chưa xác định"
    t = all_text.lower()
    for kw, val in [
        ("tây tây bắc","Tây-Tây Bắc"),("tây tây nam","Tây-Tây Nam"),
        ("đông đông bắc","Đông-Đông Bắc"),("đông đông nam","Đông-Đông Nam"),
        ("tây bắc","Tây Bắc"),("tây nam","Tây Nam"),
        ("đông bắc","Đông Bắc"),("đông nam","Đông Nam"),
        ("hướng tây ","Tây"),("hướng bắc","Bắc"),
        ("hướng nam","Nam"),("hướng đông","Đông"),
    ]:
        if kw in t: huong = val; break

    # Tốc độ di chuyển
    m_tdc = re.search(r"(\d+)\s*km/h[^,;.]*(?:di chuyển|hướng|mỗi giờ)", all_text, re.I)
    if not m_tdc:
        m_tdc = re.search(r"(?:tốc độ|khoảng)\s*(\d+)\s*km/h", all_text, re.I)
    tdc_str = f" ~{m_tdc.group(1)} km/h" if m_tdc else ""
    huong_full = huong + tdc_str

    # Khu vực ảnh hưởng
    kv = []
    for kw, ten_vung in TINH.items():
        if kw in t and ten_vung not in kv:
            kv.append(ten_vung)
    khu_vuc = ", ".join(kv[:5]) if kv else "Biển Đông"

    # Dự kiến đổ bộ — trích từ bài (ưu tiên)
    do_bo = ""
    pats = [
        r"dự kiến[^.]{0,150}(?:đổ bộ|ảnh hưởng|vào đất liền|vào bờ)[^.]{0,120}",
        r"(?:ngày|đêm)\s+\d+/\d+[^.]{0,100}(?:đổ bộ|ảnh hưởng|vào bờ)[^.]{0,80}",
        r"(?:đêm nay|sáng mai|hôm nay|ngày mai|chiều tối)[^.]{0,80}(?:đổ bộ|ảnh hưởng)[^.]{0,60}",
        r"sẽ\s+(?:đổ bộ|ảnh hưởng trực tiếp)[^.]{0,150}",
        r"(?:04h|08h|14h|20h)/\d+/\d+[^.]{0,200}",  # Bảng dự báo NCHMF
    ]
    for pat in pats:
        m = re.search(pat, all_text, re.I)
        if m:
            do_bo = re.sub(r'\s+',' ', m.group(0).strip())[:200]
            break
    if not do_bo and kv:
        do_bo = f"⚡ Đang ảnh hưởng / tiến về {', '.join(kv[:2])}"
    elif not do_bo:
        do_bo = "Theo dõi bản tin tiếp theo"

    return {
        "ten": ten, "loai": loai, "cap_so": cap_so,
        "cap_gio": cap_gio, "vi_tri": vi_tri,
        "huong": huong_full, "khu_vuc": khu_vuc, "do_bo": do_bo,
    }

# ── Gửi Telegram ─────────────────────────────────────────────────────────────
def _gui(chat_id, method, payload, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    for i in range(1, retries+1):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                print(f"[TG] ✅ {method} → {chat_id}"); return True
            print(f"[TG] ❌ {r.text[:100]}"); return False
        except requests.exceptions.Timeout:
            print(f"[TG] ⏱ Timeout {i}/{retries}"); time.sleep(3)
        except Exception as e:
            print(f"[TG] ❌ {e}"); return False
    return False

def ids():
    return [i.strip() for i in TELEGRAM_CHAT_ID.split(",") if i.strip()]

def send_text(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg); return
    for cid in ids():
        _gui(cid, "sendMessage", {
            "chat_id": cid, "text": msg,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        })
        if len(ids())>1: time.sleep(0.3)

def send_photo(img_url, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[IMG] {img_url}"); return
    for cid in ids():
        ok = _gui(cid, "sendPhoto", {
            "chat_id": cid, "photo": img_url,
            "caption": caption, "parse_mode": "HTML",
        })
        if not ok:
            # Fallback: gửi text kèm link ảnh
            _gui(cid, "sendMessage", {
                "chat_id": cid,
                "text": caption + f"\n🖼 <a href='{img_url}'>Xem ảnh đường đi</a>",
                "parse_mode": "HTML",
            })
        if len(ids())>1: time.sleep(0.3)

# ── Format báo cáo ────────────────────────────────────────────────────────────
def format_co_su_kien(info, tieu_de, url, gio):
    cap_so = info["cap_so"]
    icon = "🌀🌀" if cap_so>=5 else "🌀" if cap_so>=3 else "⚠️" if cap_so>=1 else "🔵"
    if cap_so>=5:   muc = "🔴 <b>RẤT NGUY HIỂM — SIÊU BÃO</b>"
    elif cap_so>=3: muc = "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif cap_so>=1: muc = "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    else:           muc = "🟡 <b>THEO DÕI — HỆ THỐNG THỜI TIẾT NGUY HIỂM</b>"

    vi_tri = f"\n📍 <b>Vị trí:</b> {info['vi_tri']}" if info.get("vi_tri") else ""

    msg = (
        f"🚨 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
        f"🕐 {fmt_vn()}\n"
        f"{'━'*24}\n\n"
        f"{muc}\n\n"
        f"{icon} <b>{info['loai'].upper()}</b>\n"
        f"{'─'*22}\n"
        f"1️⃣ <b>Tên:</b> {info['ten']}\n"
        f"2️⃣ <b>Cấp độ:</b> {info['loai']} ({info['cap_gio']})\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {info['huong']}"
        f"{vi_tri}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {info['khu_vuc']}\n"
        f"5️⃣ <b>Dự kiến:</b> {info['do_bo']}\n\n"
        f"📡 Nguồn: Trung tâm Khí tượng Thủy văn Quốc gia\n"
        f"🔗 <a href='{url}'>Xem bản tin đầy đủ</a>\n"
        f"{'━'*24}\n"
        f"⏰ Bản tin tiếp theo: {gio_tiep_theo()} (GMT+7)"
    )
    return msg

def format_khong_co(gio):
    return (
        f"📋 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
        f"🕐 {fmt_vn()}\n"
        f"{'━'*24}\n\n"
        f"🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ SỰ KIỆN BẤT THƯỜNG</b>\n\n"
        f"✅ Không ghi nhận:\n"
        f"  • Không có bão\n"
        f"  • Không có áp thấp nhiệt đới\n"
        f"  • Biển Đông và vùng biển VN ổn định\n\n"
        f"📡 Nguồn: nchmf.gov.vn\n"
        f"{'━'*24}\n"
        f"⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))
    gio      = gio_hien_tai()

    # Bước 1: Đọc trang listing
    soup_listing = get_soup(LISTING_URL)
    if not soup_listing:
        print("[Bot] Không đọc được trang NCHMF")
        send_text("⚠️ Không kết nối được nchmf.gov.vn để lấy dữ liệu.")
        return

    text_listing = get_text(soup_listing)

    # Bước 2: Kiểm tra có sự kiện không
    if la_khong_co(text_listing) and not co_bao_that(text_listing):
        print("[Bot] Không có sự kiện bão/ATNĐ")
        send_text(format_khong_co(gio))
        save_state({**state, "last_run_vn": fmt_vn(),
                    "last_run_utc": datetime.now(timezone.utc).isoformat()})
        return

    # Bước 3: Tìm bản tin từ listing
    ban_tins = lay_ban_tin_tu_listing(soup_listing)
    print(f"[Bot] Tìm thấy {len(ban_tins)} bản tin trên listing")

    gui_duoc = False

    for bt in ban_tins[:4]:
        url   = bt["url"]
        anh   = bt["anh"]
        tieu_de = bt["tieu_de"]

        # Bỏ qua nếu đã gửi
        bid = make_id(url)
        if bid in sent_ids:
            print(f"[Bot] Đã gửi trước: {tieu_de[:50]}")
            continue

        # Bước 4: Đọc bài viết
        print(f"[Bot] Đọc bài: {tieu_de[:50]}")
        soup_bai = get_soup(url)
        text_bai = get_text(soup_bai)

        # Kiểm tra nội dung thật
        if not co_bao_that(text_bai):
            print(f"[Bot] Bỏ qua (không có từ khoá bão): {tieu_de[:50]}")
            continue

        if not du_khi_tuong(text_bai):
            print(f"[Bot] Bỏ qua (không đủ nội dung khí tượng): {tieu_de[:50]}")
            continue

        # Tìm thêm ảnh trong bài nếu thumbnail không đẹp
        anh_bai = anh
        if soup_bai:
            for img in soup_bai.find_all("img", src=True):
                src = img.get("src","")
                if "upload/Article" in src or "thoitiet" in src.lower():
                    anh_bai = chuan_hoa_anh(src) or anh
                    if anh_bai != anh:
                        print(f"[Bot] Dùng ảnh trong bài: {anh_bai[:60]}")
                    break

        # Trích xuất 5 trường
        info = trich_xuat(text_bai, tieu_de)
        print(f"[Bot] ✅ Gửi: {tieu_de[:50]}")
        print(f"       Ảnh: {anh_bai[:60]}")

        # Gửi ảnh đường đi + báo cáo
        caption = (
            f"🗺 <b>Ảnh đường đi dự báo</b>\n"
            f"📋 {tieu_de}\n"
            f"📡 Nguồn: nchmf.gov.vn"
        )
        send_photo(anh_bai, caption)
        time.sleep(1)
        send_text(format_co_su_kien(info, tieu_de, url, gio))

        sent_ids.add(bid)
        gui_duoc = True
        time.sleep(0.5)

    if not gui_duoc and ban_tins:
        # Có bản tin nhưng đã gửi hết → gửi báo cáo nhắc nhở
        bt = ban_tins[0]
        send_text(
            f"📋 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
            f"🕐 {fmt_vn()}\n{'━'*24}\n\n"
            f"🟡 <b>ĐÃ CÓ BÁO CÁO TRONG KỲ NÀY</b>\n\n"
            f"Bản tin: {bt['tieu_de']}\n"
            f"🔗 <a href='{bt['url']}'>Xem bản tin mới nhất</a>\n"
            f"{'━'*24}\n⏰ Bản tin tiếp theo: {gio_tiep_theo()} (GMT+7)"
        )
    elif not gui_duoc:
        send_text(format_khong_co(gio))

    state["sent_ids"]     = list(sent_ids)[-200:]
    state["last_run_vn"]  = fmt_vn()
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print("[Bot] Xong.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Bot] ❌ Lỗi: {e}")
        import traceback; traceback.print_exc()

