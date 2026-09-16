"""
🤖 bot_handler.py v23
Nhận lệnh Telegram, chỉ lấy dữ liệu từ nchmf.gov.vn
"""

import os, json, time, re, requests, hashlib
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_IDS = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_F  = "bot_state.json"
API      = f"https://api.telegram.org/bot{TOKEN}"
ALLOWED  = {s.strip() for s in CHAT_IDS.split(",") if s.strip()}
VN_TZ    = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"
}

LISTING_URL = "https://nchmf.gov.vn/kttvsite/vi-VN/1/bao-ap-thap-nhiet-doi-2049-15.html"
BASE      = "https://nchmf.gov.vn"
KTTV_BASE = "https://kttv.gov.vn"
RE_BAI_VIET = re.compile(r"-post\d+\.html$", re.IGNORECASE)

KHONG_CO = [
    "đang cập nhật dữ liệu","đang cập nhật","hiện không có",
    "không có bão","không có áp thấp","currently no","no active",
]
CO_BAO = [
    "áp thấp nhiệt đới","bão số","cơn bão","bão nhiệt đới",
    "siêu bão","tropical depression","tropical storm","typhoon",
]
KW_KHI_TUONG = [
    "km/h","cấp ","sức gió","gió giật","vĩ bắc","kinh đông",
    "tây bắc","tây nam","đông bắc","đông nam","hướng tây","hướng bắc",
    "hướng nam","hướng đông","đổ bộ","ảnh hưởng","vùng biển","ven biển",
    "mbar","hpa","knot","biển đông","hoàng sa",
    "quảng ninh","hải phòng","thanh hóa","nghệ an","hà tĩnh",
    "quảng bình","quảng trị","đà nẵng","quảng nam","quảng ngãi","bình định",
]

# ── Tiện ích ──────────────────────────────────────────────────────────────────
def now_vn(): return datetime.now(VN_TZ)
def fmt_vn(): return now_vn().strftime("%d/%m/%Y %H:%M (GMT+7)")

def load_state():
    if os.path.exists(STATE_F):
        with open(STATE_F, encoding="utf-8") as f: return json.load(f)
    return {"offset": 0}

def save_state(s):
    with open(STATE_F, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def full_url(href):
    if not href: return ""
    href = href.strip()
    if href.startswith("http"): return href
    if href.startswith("//"): return "https:" + href
    if href.startswith("/"): return BASE + href
    return BASE + "/" + href

def chuan_hoa_anh(src):
    if not src: return None
    src = src.strip()
    if src.startswith("http"): return src
    if src.startswith("//"): return "https:" + src
    if src.startswith("/"): return KTTV_BASE + src
    return None

# ── Đọc trang ────────────────────────────────────────────────────────────────
def get_soup(url, timeout=12):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[HTTP] {e}"); return None

def get_text(soup):
    if not soup: return ""
    for t in soup(["script","style","nav","header","footer","aside"]): t.decompose()
    return re.sub(r'\s+', ' ', soup.get_text(separator=" ")).strip()

def la_bai_viet(url): return bool(RE_BAI_VIET.search(url))
def la_khong_co(t):   return any(k in t.lower() for k in KHONG_CO)
def co_bao_that(t):   return any(k in t.lower() for k in CO_BAO)
def du_khi_tuong(t):  return sum(1 for k in KW_KHI_TUONG if k in t.lower()) >= 3

# ── Lấy bản tin từ NCHMF ─────────────────────────────────────────────────────
def lay_ban_tin():
    """Quét listing NCHMF, trả về list bản tin hợp lệ."""
    soup = get_soup(LISTING_URL)
    if not soup: return [], False

    text = get_text(soup)
    co_su_kien = co_bao_that(text) and not (la_khong_co(text) and not co_bao_that(text))

    ket_qua = []
    seen = set()
    for a_img in soup.find_all("a", href=True):
        url = full_url(a_img.get("href",""))
        if not la_bai_viet(url): continue
        img = a_img.find("img")
        if not img: continue
        anh = chuan_hoa_anh(img.get("src",""))
        if not anh: continue
        tieu_de = ""
        for a2 in soup.find_all("a", href=True):
            if full_url(a2.get("href","")) == url and not a2.find("img"):
                tieu_de = a2.get_text(strip=True)
                if tieu_de: break
        if not tieu_de: tieu_de = img.get("alt","") or url.split("/")[-1]
        t = tieu_de.lower()
        if not any(k in t for k in ["bão","áp thấp","tropical","typhoon"]): continue
        if url not in seen:
            seen.add(url)
            ket_qua.append({"url":url,"anh":anh,"tieu_de":tieu_de})
    return ket_qua, co_su_kien

def doc_bai(url):
    """Đọc bài viết, kiểm tra nội dung thật."""
    soup = get_soup(url)
    text = get_text(soup)
    if not co_bao_that(text) or not du_khi_tuong(text):
        return None, None, None
    # Tìm ảnh trong bài
    anh = None
    if soup:
        for img in soup.find_all("img", src=True):
            src = img.get("src","")
            if "upload/Article" in src or "thoitiet" in src.lower():
                anh = chuan_hoa_anh(src); break
    return soup, text, anh

# ── Telegram API ──────────────────────────────────────────────────────────────
def tg(method, **p):
    try:
        r = requests.post(f"{API}/{method}", json=p, timeout=15)
        return r.json()
    except Exception as e:
        print(f"[TG/{method}] {e}"); return {}

def send(cid, text, kb=None, preview=True):
    p = {"chat_id":cid,"text":text,"parse_mode":"HTML",
         "disable_web_page_preview": not preview}
    if kb: p["reply_markup"] = kb
    return tg("sendMessage", **p)

def send_photo_tg(cid, img_url, caption):
    ok = tg("sendPhoto", chat_id=cid, photo=img_url,
             caption=caption, parse_mode="HTML")
    if not ok.get("ok"):
        send(cid, caption + f"\n🖼 <a href='{img_url}'>Xem ảnh đường đi</a>")

def typing(cid): tg("sendChatAction", chat_id=cid, action="typing")
def get_updates(offset): return tg("getUpdates",offset=offset,timeout=8,limit=10).get("result",[])
def co_quyen(cid): return (not ALLOWED) or (str(cid) in ALLOWED)

# ── Bàn phím ─────────────────────────────────────────────────────────────────
def kb():
    return {"keyboard":[
        [{"text":"🔍 Kiểm tra ngay"},{"text":"📊 Tóm tắt tình hình"}],
        [{"text":"🌀 Xem bản tin bão/áp thấp"},{"text":"ℹ️ Hướng dẫn"}],
    ],"resize_keyboard":True}

# ── Xử lý lệnh ───────────────────────────────────────────────────────────────
def cmd_start(cid, ten="bạn"):
    send(cid,
        f"👋 Xin chào <b>{ten}</b>!\n\n"
        "🤖 <b>Bot Cảnh báo Thời tiết Việt Nam</b>\n"
        "📡 Nguồn: Trung tâm Khí tượng Thủy văn Quốc gia (nchmf.gov.vn)\n\n"
        "<b>Các lệnh:</b>\n"
        "🔍 <b>Kiểm tra ngay</b> — quét bản tin NCHMF\n"
        "📊 <b>Tóm tắt tình hình</b> — xem có sự kiện không\n"
        "🌀 <b>Xem bản tin bão/áp thấp</b> — bản tin có ảnh đường đi\n\n"
        "⏰ Tự động báo cáo: 02h · 08h · 14h · 20h (GMT+7)\n"
        "⚠️ Phản hồi trong tối đa 10 phút.\n\n"
        f"🕐 {fmt_vn()}", kb())

def cmd_kiem_tra(cid):
    typing(cid)
    send(cid, "⏳ Đang quét nchmf.gov.vn...")
    typing(cid)

    ban_tins, co_sk = lay_ban_tin()

    if not ban_tins or not co_sk:
        send(cid,
            "✅ <b>Không có bão hoặc áp thấp nhiệt đới</b>\n\n"
            "Trang NCHMF hiện không có bản tin bão/ATNĐ.\n"
            "Biển Đông và vùng biển Việt Nam ổn định.\n\n"
            f"📡 Nguồn: nchmf.gov.vn\n🕐 {fmt_vn()}", kb())
        return

    send(cid, f"🚨 Tìm thấy <b>{len(ban_tins)}</b> bản tin — đang tải chi tiết...")
    da_gui = False

    for bt in ban_tins[:3]:
        _, text_bai, anh_bai = doc_bai(bt["url"])
        if not text_bai: continue

        anh = anh_bai or bt["anh"]
        caption = (
            f"🗺 <b>Ảnh đường đi dự báo</b>\n"
            f"📋 {bt['tieu_de']}\n"
            f"📡 nchmf.gov.vn"
        )
        send_photo_tg(cid, anh, caption)
        time.sleep(0.5)
        send(cid,
            f"📋 <b>{bt['tieu_de']}</b>\n"
            f"🕐 {fmt_vn()}\n"
            f"🔗 <a href='{bt['url']}'>Xem bản tin đầy đủ</a>", kb())
        da_gui = True
        time.sleep(0.5)

    if not da_gui:
        send(cid,
            "⚠️ Có bản tin nhưng nội dung chưa đủ thông tin khí tượng.\n"
            f"🔗 <a href='{LISTING_URL}'>Xem trực tiếp tại NCHMF</a>", kb())

def cmd_tom_tat(cid):
    typing(cid)
    ban_tins, co_sk = lay_ban_tin()

    if not co_sk or not ban_tins:
        send(cid,
            f"📊 <b>TÓM TẮT TÌNH HÌNH</b>\n"
            f"🕐 {fmt_vn()}\n{'━'*22}\n\n"
            f"🟢 <b>BÌNH THƯỜNG</b>\n\n"
            f"✅ Không có bão, không có áp thấp nhiệt đới\n"
            f"✅ Biển Đông và vùng biển VN ổn định\n\n"
            f"📡 Nguồn: nchmf.gov.vn\n"
            f"⏰ Báo cáo tiếp: xem lịch tự động 02h·08h·14h·20h", kb())
        return

    msg = (
        f"📊 <b>TÓM TẮT TÌNH HÌNH</b>\n"
        f"🕐 {fmt_vn()}\n{'━'*22}\n\n"
        f"🟡 <b>CÓ SỰ KIỆN CẦN THEO DÕI</b>\n\n"
        f"Tìm thấy <b>{len(ban_tins)}</b> bản tin:\n"
    )
    for bt in ban_tins[:3]:
        msg += f"  • <a href='{bt['url']}'>{bt['tieu_de'][:70]}</a>\n"
    msg += f"\n📡 Nguồn: nchmf.gov.vn\n"
    msg += f"🔍 Dùng lệnh <b>Xem bản tin bão/áp thấp</b> để xem chi tiết + ảnh đường đi"
    send(cid, msg, kb())

def cmd_ban_tin(cid):
    typing(cid)
    send(cid, "⏳ Đang tải bản tin và ảnh đường đi...")
    ban_tins, co_sk = lay_ban_tin()

    if not ban_tins:
        send(cid,
            "✅ <b>Hiện không có bản tin bão/áp thấp nhiệt đới</b>\n\n"
            f"📡 Nguồn: nchmf.gov.vn\n🕐 {fmt_vn()}", kb())
        return

    da_gui = False
    for bt in ban_tins[:3]:
        _, text_bai, anh_bai = doc_bai(bt["url"])
        if not text_bai:
            send(cid, f"⚠️ Bản tin chưa đủ nội dung: {bt['tieu_de'][:60]}\n"
                 f"🔗 <a href='{bt['url']}'>Xem trực tiếp</a>")
            continue
        anh = anh_bai or bt["anh"]
        send_photo_tg(cid, anh,
            f"🗺 <b>Ảnh đường đi dự báo</b>\n"
            f"📋 {bt['tieu_de']}\n📡 nchmf.gov.vn")
        time.sleep(0.5)
        send(cid,
            f"📋 <b>{bt['tieu_de']}</b>\n"
            f"🕐 {fmt_vn()}\n"
            f"🔗 <a href='{bt['url']}'>Xem bản tin đầy đủ trên NCHMF</a>", kb())
        da_gui = True
        time.sleep(0.5)

    if not da_gui:
        send(cid,
            f"⚠️ Bản tin chưa đủ dữ liệu để hiển thị.\n"
            f"🔗 <a href='{LISTING_URL}'>Xem trực tiếp tại NCHMF</a>", kb())

def cmd_huong_dan(cid):
    send(cid,
        "ℹ️ <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n"
        f"{'━'*22}\n\n"
        "🔍 <b>Kiểm tra ngay</b>\n"
        "Quét nchmf.gov.vn, hiển thị bản tin + ảnh đường đi.\n\n"
        "📊 <b>Tóm tắt tình hình</b>\n"
        "Xem nhanh có sự kiện bão/ATNĐ không.\n\n"
        "🌀 <b>Xem bản tin bão/áp thấp</b>\n"
        "Xem bản tin kèm ảnh đường đi cơn bão.\n\n"
        f"{'━'*22}\n"
        "⏰ <b>Tự động báo cáo:</b> 02h · 08h · 14h · 20h (GMT+7)\n"
        "📡 <b>Nguồn duy nhất:</b> nchmf.gov.vn\n"
        "⚠️ Phản hồi chậm tối đa 10 phút (GitHub Actions).\n\n"
        f"🕐 {fmt_vn()}", kb())

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

    MAP = {
        "/start": lambda: cmd_start(cid, ten),
        "/help":  lambda: cmd_start(cid, ten),
        "🔍 Kiểm tra ngay":          lambda: cmd_kiem_tra(cid),
        "/check":                    lambda: cmd_kiem_tra(cid),
        "📊 Tóm tắt tình hình":      lambda: cmd_tom_tat(cid),
        "/summary":                  lambda: cmd_tom_tat(cid),
        "🌀 Xem bản tin bão/áp thấp":lambda: cmd_ban_tin(cid),
        "/bao":                      lambda: cmd_ban_tin(cid),
        "ℹ️ Hướng dẫn":              lambda: cmd_huong_dan(cid),
        "/huongdan":                 lambda: cmd_huong_dan(cid),
    }
    fn = MAP.get(text)
    if fn:
        fn()
    else:
        send(cid,
            f"❓ Không hiểu lệnh: <b>{text[:30]}</b>\n"
            "Nhấn nút bên dưới hoặc gõ /help", kb())

# ── Main: polling 8 phút ─────────────────────────────────────────────────────
def main():
    if not TOKEN:
        print("❌ Chưa cấu hình TELEGRAM_BOT_TOKEN"); return
    state  = load_state()
    offset = state.get("offset", 0)
    print(f"[Bot Handler] Bắt đầu lúc {fmt_vn()}, offset={offset}")

    deadline = time.time() + 8 * 60
    processed = 0

    while time.time() < deadline:
        try:
            updates = get_updates(offset)
        except Exception as e:
            print(f"[Polling] {e}"); time.sleep(5); continue

        for upd in updates:
            try:
                xu_ly(upd)
            except Exception as e:
                print(f"[xu_ly] {e}")
            offset = upd["update_id"] + 1
            processed += 1
            state["offset"]   = offset
            state["last_run"] = fmt_vn()
            save_state(state)

        if not updates:
            state["offset"]   = offset
            state["last_run"] = fmt_vn()
            save_state(state)
            time.sleep(3)

    print(f"[Bot Handler] Xong. Xử lý {processed} cập nhật. Offset={offset}")

if __name__ == "__main__":
    main()
