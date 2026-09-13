🌀 Storm Monitor Bot v21
- CHỈ lấy từ nchmf.gov.vn
- Chỉ gửi khi có nội dung thật về bão/ATNĐ (không phải "Đang cập nhật")
- Gửi kèm ảnh đường đi cơn bão nếu tìm được
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

BASE_NCHMF = "https://nchmf.gov.vn"

# Trang danh mục bão/ATNĐ của NCHMF
NCHMF_LISTING = [
    f"{BASE_NCHMF}/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html",
    f"{BASE_NCHMF}/kttvsite/vi-VN/1/tin-bao-khan-cap-post.html",
    f"{BASE_NCHMF}/kttvsite/vi-VN/1/tin-ap-thap-nhiet-doi-post.html",
]

# Cụm từ cho thấy KHÔNG có sự kiện
KHONG_CO_SU_KIEN = [
    "đang cập nhật dữ liệu",
    "đang cập nhật",
    "hiện không có",
    "không có bão",
    "không có áp thấp",
    "currently no",
    "no active",
]

# Từ khoá xác nhận có nội dung bão/ATNĐ thật
KW_BAO_THAT = [
    "áp thấp nhiệt đới","áp thấp nhiệt đới mạnh","bão số",
    "cơn bão","bão nhiệt đới","siêu bão",
    "tropical depression","tropical storm","typhoon",
]

# Từ khoá khí tượng cụ thể — phải có ≥ 2 cái
KW_KHI_TUONG = [
    "km/h","cấp ","sức gió","gió giật","hướng tây","hướng bắc",
    "hướng nam","hướng đông","tây bắc","tây nam","đông bắc","đông nam",
    "đổ bộ","ảnh hưởng trực tiếp","vùng biển","ven biển","đất liền",
    "vĩ độ","kinh độ","mbar","hpa","knot",
    "quảng ninh","hải phòng","thanh hóa","nghệ an","hà tĩnh",
    "quảng bình","quảng trị","đà nẵng","quảng nam","quảng ngãi",
    "bình định","phú yên","khánh hòa","biển đông",
]

# Các đuôi URL ảnh đường đi bão
IMG_STORM_PATTERNS = [
    r"track", r"duong-di", r"duongdi", r"storm", r"bao_",
    r"atnhietdoi", r"typhoon", r"\.png$", r"\.jpg$", r"\.gif$",
]

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

CAP_GIO_VI = {
    5:"Cấp 12+ (≥118 km/h) — Siêu bão",
    4:"Cấp 11-12 (103-117 km/h) — Bão rất mạnh",
    3:"Cấp 8-12 (63-117 km/h) — Bão",
    2:"Cấp 6-7 (39-62 km/h) — Bão nhiệt đới",
    1:"Cấp 6 (39-49 km/h) — Áp thấp nhiệt đới",
    0:"Dưới cấp 6",
}

# ── Tiện ích ──────────────────────────────────────────────────────────────────
def now_vn():      return datetime.now(VN_TZ)
def fmt_time_vn(): return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")
def make_id(t):    return hashlib.md5(t.encode()).hexdigest()[:12]

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

def gio_bao_cao_hien_tai():
    h = now_vn().hour
    if 1<=h<7:   return "02:00"
    if 7<=h<13:  return "08:00"
    if 13<=h<19: return "14:00"
    return "20:00"

# ── Đọc trang web ─────────────────────────────────────────────────────────────
def get_soup(url, timeout=12):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[HTTP] {url[:60]}: {e}")
        return None

def get_text_sach(soup):
    """Lấy text sạch, bỏ nav/header/footer."""
    if not soup: return ""
    for tag in soup(["script","style","nav","header","footer","aside"]):
        tag.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(separator=" ")).strip()

# ── Kiểm tra nội dung ─────────────────────────────────────────────────────────
def la_khong_co_su_kien(text):
    """Trang hiện thị 'Đang cập nhật' → không có sự kiện."""
    t = text.lower()
    return any(k in t for k in KHONG_CO_SU_KIEN)

def co_bao_that(text):
    """Có cụm từ xác nhận bão/ATNĐ thật."""
    t = text.lower()
    return any(k in t for k in KW_BAO_THAT)

def du_noi_dung_khi_tuong(text):
    """Có ≥ 2 từ khoá khí tượng cụ thể."""
    t = text.lower()
    return sum(1 for k in KW_KHI_TUONG if k in t) >= 2

# ── Tìm ảnh đường đi bão ──────────────────────────────────────────────────────
def tim_anh_duong_di(soup, base_url):
    """
    Tìm ảnh đường đi cơn bão trong trang bản tin.
    Ưu tiên ảnh có tên file liên quan đến 'track', 'bao', 'duong-di'...
    """
    if not soup: return None

    imgs = soup.find_all("img", src=True)
    candidates = []

    for img in imgs:
        src = img.get("src","")
        alt = (img.get("alt","") or "").lower()
        src_lower = src.lower()

        # Bỏ qua logo, icon, thumbnail nhỏ
        if any(k in src_lower for k in ["logo","icon","banner","avatar",
                                         "button","arrow","bullet","star"]):
            continue
        if any(k in alt for k in ["logo","icon","banner"]):
            continue

        # Ưu tiên ảnh có từ khoá track/bão trong tên file
        score = 0
        for pat in IMG_STORM_PATTERNS:
            if re.search(pat, src_lower):
                score += 2
        # Ảnh trong thư mục upload/bão thường là ảnh bản tin
        if "upload" in src_lower or "image" in src_lower:
            score += 1
        if score > 0:
            candidates.append((score, src))

    if not candidates:
        return None

    # Lấy ảnh có điểm cao nhất
    candidates.sort(reverse=True)
    best_src = candidates[0][1]

    # Tạo URL đầy đủ
    if best_src.startswith("http"):
        return best_src
    if best_src.startswith("//"):
        return "https:" + best_src
    if best_src.startswith("/"):
        return BASE_NCHMF + best_src
    return base_url.rstrip("/") + "/" + best_src

# ── Trích xuất thông tin bão ──────────────────────────────────────────────────
def trich_xuat_bao(text, title=""):
    """Trích 5 trường từ nội dung bản tin."""
    all_text = title + " " + text

    # Tên bão
    m_so = re.search(r"bão số\s*(\d+)", all_text, re.IGNORECASE)
    m_atnđ = re.search(r"áp thấp nhiệt đới", all_text, re.IGNORECASE)
    if m_so:
        ten = f"Bão số {m_so.group(1)}"
        loai = "Bão"; cap_so = 3
    elif m_atnđ:
        ten = "Áp thấp nhiệt đới"
        loai = "Áp thấp nhiệt đới"; cap_so = 1
    elif re.search(r"siêu bão", all_text, re.IGNORECASE):
        ten = "Siêu bão"; loai = "Siêu bão"; cap_so = 5
    elif re.search(r"cơn bão|bão mạnh|bão nhiệt đới", all_text, re.IGNORECASE):
        ten = "Bão nhiệt đới"; loai = "Bão"; cap_so = 3
    else:
        ten = "Hệ thống thời tiết nguy hiểm"
        loai = "Cần theo dõi"; cap_so = 0

    # Cấp độ từ tốc độ gió
    m_cap = re.search(r"cấp\s*(\d+)", all_text, re.IGNORECASE)
    if m_cap:
        c = int(m_cap.group(1))
        if c >= 12: cap_so = 5
        elif c >= 11: cap_so = 4
        elif c >= 8: cap_so = 3
        elif c >= 6: cap_so = max(cap_so, 2)

    m_gio = re.search(r"(\d+)\s*km/h", all_text, re.IGNORECASE)
    gio_str = f" — {m_gio.group(1)} km/h" if m_gio else ""
    cap_gio = CAP_GIO_VI.get(cap_so,"?") + gio_str

    # Hướng di chuyển
    huong = "Chưa xác định"
    t = all_text.lower()
    for kw, val in [
        ("tây bắc","Tây Bắc"),("tây nam","Tây Nam"),
        ("đông bắc","Đông Bắc"),("đông nam","Đông Nam"),
        ("hướng tây ","Tây"),("hướng bắc","Bắc"),
        ("hướng nam","Nam"),("hướng đông","Đông"),
    ]:
        if kw in t: huong = val; break

    # Khu vực ảnh hưởng
    kv_found = []
    for kw, ten_tinh in TINH_VEN_BIEN.items():
        if kw in t and ten_tinh not in kv_found:
            kv_found.append(ten_tinh)
    khu_vuc = ", ".join(kv_found[:4]) if kv_found else "Biển Đông"

    # Dự kiến đổ bộ
    do_bo = ""
    patterns = [
        r"dự kiến[^.]{0,120}(?:đổ bộ|ảnh hưởng|vào đất liền)[^.]{0,100}",
        r"(?:đổ bộ|ảnh hưởng trực tiếp)[^.]{0,80}(?:ngày|giờ|đêm|sáng)[^.]{0,80}",
        r"(?:đêm nay|sáng mai|hôm nay|ngày mai)[^.]{0,80}(?:đổ bộ|ảnh hưởng)[^.]{0,60}",
        r"sẽ\s+(?:đổ bộ|ảnh hưởng)[^.]{0,150}",
        r"trong\s+\d+[^.]{0,20}giờ[^.]{0,60}",
    ]
    for pat in patterns:
        m = re.search(pat, all_text, re.IGNORECASE)
        if m:
            do_bo = re.sub(r'\s+',' ', m.group(0).strip())[:180]
            break
    if not do_bo:
        if kv_found:
            do_bo = f"⚡ Đang ảnh hưởng / sắp đổ bộ vào {', '.join(kv_found[:2])}"
        else:
            do_bo = "Đang theo dõi — xem bản tin chi tiết"

    return {
        "ten": ten, "loai": loai, "cap_so": cap_so,
        "cap_gio": cap_gio, "huong": huong,
        "khu_vuc": khu_vuc, "do_bo": do_bo,
    }

# ── Gửi Telegram ─────────────────────────────────────────────────────────────
def _gui_mot(chat_id, method, payload, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    for i in range(1, retries+1):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                print(f"[TG/{method}] ✅ → {chat_id}"); return True
            print(f"[TG/{method}] ❌ {r.text[:100]}"); return False
        except requests.exceptions.Timeout:
            print(f"[TG] ⏱ Timeout {i}/{retries}"); time.sleep(3)
        except Exception as e:
            print(f"[TG] ❌ {e}"); return False
    return False

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg); return
    ids = [i.strip() for i in TELEGRAM_CHAT_ID.split(",") if i.strip()]
    for cid in ids:
        _gui_mot(cid, "sendMessage", {
            "chat_id": cid, "text": msg,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        })
        if len(ids)>1: time.sleep(0.3)

def send_telegram_photo(img_url, caption):
    """Gửi ảnh đường đi bão kèm chú thích."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[IMG] {img_url}"); return
    ids = [i.strip() for i in TELEGRAM_CHAT_ID.split(",") if i.strip()]
    for cid in ids:
        _gui_mot(cid, "sendPhoto", {
            "chat_id": cid,
            "photo": img_url,
            "caption": caption,
            "parse_mode": "HTML",
        })
        if len(ids)>1: time.sleep(0.3)

# ── Scrape NCHMF ──────────────────────────────────────────────────────────────
def scrape_nchmf():
    """
    Quét trang NCHMF:
    1. Vào trang danh mục → tìm các bản tin bão/ATNĐ mới nhất
    2. Đọc từng bản tin → kiểm tra nội dung thật
    3. Nếu có 'Đang cập nhật' → không có sự kiện
    4. Nếu có nội dung thật → trích xuất + tìm ảnh đường đi
    """
    results = []   # [(thông tin bão, url bản tin, ảnh đường đi)]
    ban_tin_urls = []

    for listing_url in NCHMF_LISTING:
        soup = get_soup(listing_url)
        if not soup: continue
        text_listing = get_text_sach(soup)

        # Nếu trang danh mục hiện "Đang cập nhật" → không có sự kiện
        if la_khong_co_su_kien(text_listing):
            print(f"[NCHMF] '{listing_url[-40:]}': Đang cập nhật — không có sự kiện")
            continue

        # Tìm link đến các bản tin cụ thể
        for a in soup.find_all("a", href=True):
            href = a.get("href","")
            link_text = a.get_text(strip=True)
            if not link_text or len(link_text) < 5: continue

            # Chỉ lấy link bài viết thật (có chữ về bão/ATNĐ trong tiêu đề)
            if not any(k in link_text.lower() for k in
                       ["bão","áp thấp","tropical","typhoon"]): continue

            full = href if href.startswith("http") else BASE_NCHMF + href
            # Bỏ qua link listing
            if any(k in full for k in ["-2049-15","-2050-15","post.html",
                                        "/tag/","/category/"]): continue
            if full not in [u for u,_ in ban_tin_urls]:
                ban_tin_urls.append((full, link_text))

    print(f"[NCHMF] Tìm thấy {len(ban_tin_urls)} link bản tin")

    for url, tieu_de in ban_tin_urls[:6]:
        try:
            soup = get_soup(url)
            if not soup: continue
            text = get_text_sach(soup)

            # Bỏ qua nếu "Đang cập nhật"
            if la_khong_co_su_kien(text):
                print(f"[NCHMF] Bỏ qua (đang cập nhật): {tieu_de[:50]}")
                continue

            # Bỏ qua nếu không có cụm từ bão thật
            if not co_bao_that(text):
                print(f"[NCHMF] Bỏ qua (không có từ khoá bão): {tieu_de[:50]}")
                continue

            # Bỏ qua nếu ít nội dung khí tượng
            if not du_noi_dung_khi_tuong(text):
                print(f"[NCHMF] Bỏ qua (ít nội dung khí tượng): {tieu_de[:50]}")
                continue

            print(f"[NCHMF] ✅ Bản tin hợp lệ: {tieu_de[:50]}")

            # Trích xuất thông tin
            info = trich_xuat_bao(text, tieu_de)

            # Tìm ảnh đường đi bão
            anh_url = tim_anh_duong_di(soup, url)
            if anh_url:
                print(f"[NCHMF] 🖼 Tìm thấy ảnh: {anh_url[:60]}")

            results.append({
                "id":     make_id(tieu_de + url),
                "tieu_de": tieu_de,
                "url":    url,
                "anh":    anh_url,
                **info,
            })
            time.sleep(0.5)

        except Exception as e:
            print(f"[NCHMF bài] {e}")

    return results

# ── Format báo cáo ────────────────────────────────────────────────────────────
def format_bao_cao_co_su_kien(items, gio):
    """Báo cáo khi có bão/ATNĐ."""
    msg  = f"🚨 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
    msg += f"🕐 {fmt_time_vn()}\n{'━'*24}\n\n"

    # Đánh giá tổng thể
    cap_max = max(x["cap_so"] for x in items)
    if cap_max >= 5:   msg += "🔴 <b>RẤT NGUY HIỂM — SIÊU BÃO</b>\n\n"
    elif cap_max >= 3: msg += "🟠 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>\n\n"
    elif cap_max >= 1: msg += "🟡 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>\n\n"
    else:              msg += "🟡 <b>THEO DÕI — HỆ THỐNG THỜI TIẾT NGUY HIỂM</b>\n\n"

    for i, x in enumerate(items[:3], 1):
        cap_so = x["cap_so"]
        icon = "🌀🌀" if cap_so>=5 else "🌀" if cap_so>=3 else "⚠️" if cap_so>=1 else "🔵"
        msg += (
            f"{icon} <b>{i}. {x['loai'].upper()}</b>\n"
            f"{'─'*22}\n"
            f"1️⃣ <b>Tên:</b> {x['ten']}\n"
            f"2️⃣ <b>Cấp độ:</b> {x['loai']} ({x['cap_gio']})\n"
            f"3️⃣ <b>Hướng di chuyển:</b> {x['huong']}\n"
            f"4️⃣ <b>Khu vực ảnh hưởng:</b> {x['khu_vuc']}\n"
            f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {x['do_bo']}\n"
            f"📡 Nguồn: Trung tâm Khí tượng Thủy văn Quốc gia\n"
            f"🔗 <a href='{x['url']}'>Xem bản tin đầy đủ</a>\n\n"
        )

    msg += f"{'━'*24}\n⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    return msg

def format_bao_cao_khong_co(gio):
    """Báo cáo khi không có sự kiện."""
    return (
        f"📋 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
        f"🕐 {fmt_time_vn()}\n"
        f"{'━'*24}\n\n"
        f"🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ SỰ KIỆN BẤT THƯỜNG</b>\n\n"
        f"✅ Không ghi nhận sự kiện nào:\n"
        f"  • Không có bão\n"
        f"  • Không có áp thấp nhiệt đới\n"
        f"  • Biển Đông và vùng biển VN ổn định\n\n"
        f"📡 Nguồn: Trung tâm Khí tượng Thủy văn Quốc gia (nchmf.gov.vn)\n"
        f"{'━'*24}\n"
        f"⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))
    gio      = gio_bao_cao_hien_tai()

    # Quét NCHMF
    items = scrape_nchmf()
    print(f"[Bot] Tìm thấy {len(items)} bản tin hợp lệ")

    if not items:
        # Không có sự kiện → gửi báo cáo bình thường
        send_telegram(format_bao_cao_khong_co(gio))
        print("[Bot] Gửi báo cáo: không có sự kiện")
    else:
        # Có sự kiện → gửi báo cáo + ảnh đường đi
        send_telegram(format_bao_cao_co_su_kien(items, gio))

        # Gửi ảnh đường đi cho từng bản tin (nếu có)
        for item in items[:3]:
            anh = item.get("anh")
            if anh:
                caption = (
                    f"🗺 <b>Đường đi dự báo: {item['ten']}</b>\n"
                    f"📡 Nguồn: nchmf.gov.vn"
                )
                print(f"[Bot] Gửi ảnh: {anh[:60]}")
                send_telegram_photo(anh, caption)
                time.sleep(1)

        # Lưu ID bản tin đã gửi
        new_ids = [x["id"] for x in items if x["id"] not in sent_ids]
        state["sent_ids"] = (list(sent_ids) + new_ids)[-200:]

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

