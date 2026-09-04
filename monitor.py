"""
🌀 Storm Monitor Bot v21
- Chỉ lấy thông tin từ nchmf.gov.vn (nguồn chính thức Việt Nam)
- Chỉ thông báo khi có bản tin bão/áp thấp nhiệt đới thật sự
- Gửi kèm ảnh đường đi cơn bão từ NCHMF
- Không thông báo khi trang hiển thị "Đang cập nhật dữ liệu"
"""

import os, json, re, hashlib, requests, time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.json"
VN_TZ = timezone(timedelta(hours=7))

NCHMF_BAO_URL = "https://nchmf.gov.vn/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html"
NCHMF_BASE    = "https://nchmf.gov.vn"
KTTV_BASE     = "https://kttv.gov.vn"

HEADERS = {"User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
)}

# Khi không có bão, NCHMF hiển thị chuỗi này
KHONG_CO_BAO_KW = ["đang cập nhật dữ liệu", "chua co tin bao"]

# Từ khoá PHẢI có trong bản tin bão thật
TU_KHOA_BAN_TIN = [
    "tin bão", "tin áp thấp", "cơn bão", "bão số",
    "áp thấp nhiệt đới", "tin khẩn", "cảnh báo bão",
]

CAP_GIO = {
    5:"Cấp 12+ (≥118 km/h)", 4:"Cấp 11-12 (103-117 km/h)",
    3:"Cấp 8-12 (63-117 km/h)", 2:"Cấp 6-7 (39-62 km/h)",
    1:"Cấp 6 (39-49 km/h)", 0:"Dưới cấp 6",
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

def get_page(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def tim_tinh(text):
    t = text.lower()
    found = []
    for kw, ten in TINH_VEN_BIEN.items():
        if kw in t and ten not in found: found.append(ten)
    return ", ".join(found[:4]) if found else ""

def tim_huong(text):
    t = text.lower()
    for kw, val in [
        ("tây bắc","Tây Bắc"),("tây nam","Tây Nam"),
        ("đông bắc","Đông Bắc"),("đông nam","Đông Nam"),
        ("hướng tây ","Tây"),("hướng bắc","Bắc"),
        ("hướng nam","Nam"),("hướng đông","Đông"),
    ]:
        if kw in t: return val
    return "Chưa xác định"

def tim_cap_so(text):
    cap = 0
    m = re.search(r"cấp\s*(\d+)", text.lower())
    if m: cap = max(cap, int(m.group(1)))
    m2 = re.search(r"(\d+)\s*km/h", text, re.IGNORECASE)
    if m2:
        km = int(m2.group(1))
        if km >= 118: cap = max(cap, 5)
        elif km >= 103: cap = max(cap, 4)
        elif km >= 63: cap = max(cap, 3)
        elif km >= 39: cap = max(cap, 2)
        else: cap = max(cap, 1)
    return cap

def tim_do_bo(text):
    patterns = [
        r"dự kiến[^.]{0,80}(?:đổ bộ|ảnh hưởng|vào đất liền)[^.]{0,120}",
        r"(?:đổ bộ|ảnh hưởng trực tiếp)[^.]{0,80}(?:ngày|giờ|sáng|chiều|tối|đêm)[^.]{0,100}",
        r"(?:đêm nay|sáng mai|chiều tối|hôm nay|ngày mai)[^.]{0,80}(?:đổ bộ|ảnh hưởng)[^.]{0,60}",
        r"sẽ\s+(?:đổ bộ|ảnh hưởng)[^.]{0,150}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m: return re.sub(r'\s+', ' ', m.group(0).strip())[:200]
    return ""

def la_ban_tin_that(title, noi_dung):
    """Kiểm tra có phải bản tin bão thật không."""
    combined = (title + " " + noi_dung).lower()
    if any(k in combined for k in KHONG_CO_BAO_KW):
        return False
    return any(k in combined for k in TU_KHOA_BAN_TIN)

def lay_anh_duong_di(soup):
    """Tìm ảnh đường đi bão trong soup."""
    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if any(k in src.lower() for k in ["dbqg_", "duong_di", "thoitiet", "track_"]):
            if src.startswith("http"): return src
            if src.startswith("//"): return "https:" + src
            if src.startswith("/"): return KTTV_BASE + src
    return None

# ── Telegram API ──────────────────────────────────────────────────────────────
def gui_telegram(text, photo_url=None):
    """Gửi tin nhắn đến tất cả Chat ID, kèm ảnh nếu có."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return
    url_msg   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    ids = [i.strip() for i in TELEGRAM_CHAT_ID.split(",") if i.strip()]

    for cid in ids:
        _gui_mot_chat(cid, text, photo_url, url_msg, url_photo)
        if len(ids) > 1: time.sleep(0.3)

def _gui_mot_chat(cid, text, photo_url, url_msg, url_photo, retries=3):
    # Thử gửi ảnh + caption
    if photo_url:
        for i in range(1, retries+1):
            try:
                r = requests.post(url_photo, json={
                    "chat_id": cid, "photo": photo_url,
                    "caption": text, "parse_mode": "HTML",
                }, timeout=30)
                if r.status_code == 200:
                    print(f"[TG] ✅ Ảnh+caption → {cid}"); return
                print(f"[TG] ⚠️ Ảnh thất bại ({r.status_code}) — chuyển gửi text")
                break
            except requests.exceptions.Timeout:
                print(f"[TG] ⏱ Timeout ảnh {i}/{retries}"); time.sleep(3)
            except Exception as e:
                print(f"[TG] ❌ Lỗi ảnh: {e}"); break

    # Gửi text thuần
    for i in range(1, retries+1):
        try:
            r = requests.post(url_msg, json={
                "chat_id": cid, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": False,
            }, timeout=30)
            if r.status_code == 200:
                print(f"[TG] ✅ Text → {cid}"); return
            print(f"[TG] ❌ {cid}: {r.text[:80]}"); return
        except requests.exceptions.Timeout:
            print(f"[TG] ⏱ Timeout text {i}/{retries}"); time.sleep(3)
        except Exception as e:
            print(f"[TG] ❌ {e}"); return

# ── Scrape NCHMF ──────────────────────────────────────────────────────────────
def scrape_nchmf():
    """
    Scrape trang bão NCHMF.
    - Nếu "Đang cập nhật dữ liệu" → trả về []
    - Nếu có bản tin → trả về list [{title, url, anh}]
    """
    results = []
    try:
        soup = get_page(NCHMF_BAO_URL)
        page_text = soup.get_text(separator=" ", strip=True)

        # Kiểm tra không có bão
        if any(k in page_text.lower() for k in KHONG_CO_BAO_KW):
            print("[NCHMF] → 'Đang cập nhật dữ liệu': Không có bão")
            return []

        # Tìm link bản tin bão — có ảnh thumbnail kèm theo
        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            img   = a.find("img")

            # Chỉ lấy link có từ khoá bão
            href_l  = href.lower()
            title_l = title.lower()
            if not any(k in href_l or k in title_l for k in
                       ["bao-so","tin-bao","ap-thap","cuoi-cung","khan-cap","post5"]):
                continue
            if not title or len(title) < 5:
                continue

            full_url = href if href.startswith("http") else NCHMF_BASE + href

            # Lấy ảnh thumbnail từ thẻ <a>
            anh = None
            if img:
                src = img.get("src","")
                if src.startswith("http"): anh = src
                elif src.startswith("//"): anh = "https:" + src
                elif src.startswith("/"): anh = KTTV_BASE + src

            if full_url not in [x["url"] for x in results]:
                results.append({"title": title, "url": full_url, "anh": anh})
                print(f"[NCHMF] Bản tin: {title[:60]}")

        print(f"[NCHMF] Tổng: {len(results)} bản tin")
    except Exception as e:
        print(f"[NCHMF] Lỗi: {e}")
    return results

def doc_ban_tin_day_du(url):
    """Đọc nội dung đầy đủ của bản tin và lấy ảnh đường đi."""
    try:
        soup = get_page(url)
        for tag in soup(["script","style","nav","header","footer","aside"]):
            tag.decompose()

        anh = lay_anh_duong_di(soup)

        body = ""
        for sel in [".fck_detail",".content-detail",".article-body","article",".post-content"]:
            el = soup.select_one(sel)
            if el:
                body = el.get_text(separator=" ", strip=True)
                if len(body) > 100: break
        if not body:
            body = soup.get_text(separator=" ", strip=True)

        return body[:4000], anh
    except Exception as e:
        print(f"[doc_ban_tin] {e}")
        return "", None

# ── Format tin nhắn ───────────────────────────────────────────────────────────
def gio_tiep_theo():
    h = now_vn().hour
    for g in [2,8,14,20]:
        if g > h: return f"{g:02d}:00"
    return "02:00 (ngày mai)"

def gio_bao_cao():
    h = now_vn().hour
    if 1<=h<7:   return "02:00"
    if 7<=h<13:  return "08:00"
    if 13<=h<19: return "14:00"
    return "20:00"

def format_ban_tin(title, noi_dung, url, stt):
    """Tạo thẻ thông tin đầy đủ 5 trường từ bản tin NCHMF."""
    all_text = title + " " + (noi_dung or "")
    t_low    = all_text.lower()

    # Loại + icon
    if "siêu bão" in t_low:
        loai, cap_so, icon = "Siêu bão", 5, "🌀🌀"
    elif any(k in t_low for k in ["typhoon","bão số","cơn bão","tin bão"]):
        loai, cap_so, icon = "Bão", 3, "🌀"
    elif "bão nhiệt đới" in t_low or "tropical storm" in t_low:
        loai, cap_so, icon = "Bão nhiệt đới", 2, "🌪️"
    elif "áp thấp nhiệt đới" in t_low or "depression" in t_low:
        loai, cap_so, icon = "Áp thấp nhiệt đới", 1, "⚠️"
    else:
        loai, cap_so, icon = "Vùng áp thấp", 0, "🔵"

    # Cấp thực tế từ nội dung
    cap_thuc = tim_cap_so(all_text)
    if cap_thuc > cap_so: cap_so = cap_thuc
    cap_gio  = CAP_GIO.get(cap_so, "Không xác định")

    # Tên bão
    m_so = re.search(r"bão số\s*(\d+)", t_low)
    ten  = f"Bão số {m_so.group(1)}" if m_so else "Chưa đặt tên"

    # 5 trường
    huong = tim_huong(all_text)
    kv    = tim_tinh(all_text)
    if not kv: kv = "Biển Đông / Việt Nam"
    do_bo = tim_do_bo(all_text)
    if not do_bo:
        tinh_found = any(kw in kv.lower() for kw in TINH_VEN_BIEN)
        do_bo = f"⚡ Đang ảnh hưởng / sắp đổ bộ vào {kv}" if tinh_found \
                else "Theo dõi sát diễn biến"

    return (
        f"{icon} <b>BẢN TIN {loai.upper()} #{stt}</b>\n"
        f"📋 {title}\n"
        f"{'─'*22}\n"
        f"1️⃣ <b>Tên:</b> {ten}\n"
        f"2️⃣ <b>Cấp độ:</b> {loai} ({cap_gio})\n"
        f"3️⃣ <b>Hướng di chuyển:</b> {huong}\n"
        f"4️⃣ <b>Khu vực ảnh hưởng:</b> {kv}\n"
        f"5️⃣ <b>Dự kiến đổ bộ VN:</b> {do_bo}\n"
        f"📡 Nguồn: Trung tâm Khí tượng Thủy văn Quốc gia\n"
        f"🔗 <a href='{url}'>Xem bản tin đầy đủ</a>"
    )

def format_khong_co_bao(gio):
    return (
        f"📋 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
        f"🕐 {fmt_time_vn()}\n"
        f"{'━'*24}\n\n"
        f"🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ BÃO / ÁP THẤP</b>\n\n"
        f"✅ Trung tâm Khí tượng Thủy văn Quốc gia hiện\n"
        f"   không phát bản tin bão hoặc áp thấp nhiệt đới.\n\n"
        f"{'━'*24}\n"
        f"📡 Nguồn: <a href='{NCHMF_BAO_URL}'>nchmf.gov.vn</a>\n"
        f"⏰ Báo cáo tiếp theo: {gio_tiep_theo()} (GMT+7)"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[Bot] Bắt đầu lúc {fmt_time_vn()}")
    state    = load_state()
    sent_ids = set(state.get("sent_ids", []))
    gio      = gio_bao_cao()

    ban_tins = scrape_nchmf()

    if not ban_tins:
        # Không có bão → gửi báo cáo bình thường
        gui_telegram(format_khong_co_bao(gio))
        print("[Bot] → Không có sự kiện, đã gửi báo cáo bình thường.")
    else:
        # Có bão → gửi header + từng bản tin
        header = (
            f"🚨 <b>BÁO CÁO THỜI TIẾT {gio}</b>\n"
            f"🕐 {fmt_time_vn()}\n"
            f"{'━'*24}\n"
            f"⚠️ <b>NCHMF PHÁT {len(ban_tins)} BẢN TIN BÃO/ÁP THẤP</b>\n"
            f"{'━'*24}"
        )
        gui_telegram(header)
        time.sleep(0.5)

        new_ids = []
        for i, bt in enumerate(ban_tins[:4], 1):
            bid = make_id(bt["title"] + bt["url"])
            if bid in sent_ids:
                print(f"[Bot] Đã gửi trước đó: {bt['title'][:50]}")
                continue

            # Đọc bản tin đầy đủ
            noi_dung, anh_trong_bai = doc_ban_tin_day_du(bt["url"])

            # Kiểm tra bài có phải bản tin bão thật không
            if not la_ban_tin_that(bt["title"], noi_dung):
                print(f"[Bot] Bỏ qua (không phải bản tin bão thật): {bt['title'][:50]}")
                continue

            # Ảnh đường đi: ưu tiên thumbnail từ listing, sau đó từ trong bài
            anh = bt.get("anh") or anh_trong_bai
            if anh: print(f"[Bot] Ảnh đường đi: {anh}")

            msg = format_ban_tin(bt["title"], noi_dung, bt["url"], i)
            gui_telegram(msg, photo_url=anh)
            new_ids.append(bid)
            time.sleep(0.5)

        if not new_ids:
            print("[Bot] Tất cả bản tin đã gửi trước đó.")

        state["sent_ids"] = (list(sent_ids) + new_ids)[-300:]

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
