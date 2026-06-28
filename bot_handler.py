"""
🤖 Telegram Bot Handler — nhận lệnh từ người dùng, trả lời thời gian thực
Chạy bằng polling (long-polling), không cần server riêng.
Tích hợp với GitHub Actions: chạy mỗi 10 phút để xử lý tin nhắn mới.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from monitor import (
    scrape_nchmf, scrape_vnexpress, scrape_24h, scrape_dantri,
    scrape_tuoitre, scrape_thanhnien, scrape_jtwc, scrape_jma, scrape_nhc,
    format_alert, fmt_time_vn, VN_TZ,
)

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_IDS = os.environ.get("TELEGRAM_CHAT_ID", "")   # có thể nhiều ID, cách nhau dấu phẩy
STATE_FILE  = "bot_state.json"
API         = f"https://api.telegram.org/bot{TOKEN}"

ALLOWED_SET = {s.strip() for s in ALLOWED_IDS.split(",") if s.strip()} if ALLOWED_IDS else set()

# ── Trạng thái ────────────────────────────────────────────────────────────────
def load_bot_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"offset": 0}

def save_bot_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ── Gọi Telegram API ──────────────────────────────────────────────────────────
def tg(method, **params):
    try:
        r = requests.post(f"{API}/{method}", json=params, timeout=20)
        return r.json()
    except Exception as e:
        print(f"[TG/{method}] Lỗi: {e}")
        return {}

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text,
                "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", **payload)

def send_typing(chat_id):
    tg("sendChatAction", chat_id=chat_id, action="typing")

# ── Lấy cập nhật ─────────────────────────────────────────────────────────────
def get_updates(offset):
    res = tg("getUpdates", offset=offset, timeout=10, limit=20)
    return res.get("result", [])

# ── Thu thập tất cả nguồn ────────────────────────────────────────────────────
def quet_tat_ca():
    print("[Bot] Đang quét tất cả nguồn...")
    alerts = []
    alerts += scrape_nchmf()
    alerts += scrape_vnexpress()
    alerts += scrape_24h()
    alerts += scrape_dantri()
    alerts += scrape_tuoitre()
    alerts += scrape_thanhnien()
    alerts += scrape_jtwc()
    alerts += scrape_jma()
    alerts += scrape_nhc()
    # Lọc trùng theo ID
    seen = set()
    unique = []
    for a in alerts:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique

# ── Xây bàn phím lệnh ────────────────────────────────────────────────────────
def keyboard_chinh():
    return {
        "keyboard": [
            [{"text": "🔍 Kiểm tra ngay"}, {"text": "📊 Tóm tắt tình hình"}],
            [{"text": "🌀 Chỉ xem bão/áp thấp"}, {"text": "📰 Tin báo VN"}],
            [{"text": "🛰 Nguồn quốc tế"}, {"text": "ℹ️ Hướng dẫn"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

# ── Các hàm xử lý lệnh ───────────────────────────────────────────────────────
def cmd_start(chat_id, ten="bạn"):
    msg = (
        f"👋 Xin chào <b>{ten}</b>!\n\n"
        f"🤖 Tôi là <b>Bot Cảnh báo Thời tiết Việt Nam</b>\n"
        f"Theo dõi áp thấp, bão từ Thái Bình Dương có khả năng vào Biển Đông.\n\n"
        f"<b>Các lệnh có thể dùng:</b>\n"
        f"🔍 <b>Kiểm tra ngay</b> — quét tất cả nguồn ngay lập tức\n"
        f"📊 <b>Tóm tắt tình hình</b> — báo cáo tổng hợp\n"
        f"🌀 <b>Chỉ xem bão/áp thấp</b> — lọc tin nghiêm trọng\n"
        f"📰 <b>Tin báo VN</b> — VnExpress, 24h, Dân Trí, Tuổi Trẻ...\n"
        f"🛰 <b>Nguồn quốc tế</b> — JTWC, JMA, NOAA\n\n"
        f"🕐 Bot tự động cảnh báo mỗi giờ nếu có hiện tượng mới.\n"
        f"📍 Giờ hiện tại: <b>{fmt_time_vn()}</b>"
    )
    send(chat_id, msg, keyboard_chinh())

def cmd_kiem_tra_ngay(chat_id):
    send_typing(chat_id)
    send(chat_id, "⏳ Đang quét tất cả nguồn tin, vui lòng chờ...")
    send_typing(chat_id)

    alerts = quet_tat_ca()

    if not alerts:
        send(chat_id,
             "✅ <b>Không có hiện tượng thời tiết bất thường</b>\n\n"
             f"Đã kiểm tra <b>9 nguồn tin</b> trong nước và quốc tế.\n"
             f"Thái Bình Dương và Biển Đông hiện không có áp thấp hay bão.\n\n"
             f"🕐 Kiểm tra lúc: {fmt_time_vn()}",
             keyboard_chinh())
        return

    # Gửi từng cảnh báo (tối đa 5)
    send(chat_id,
         f"🚨 <b>Tìm thấy {len(alerts)} thông tin cần chú ý</b>\n"
         f"Đang gửi chi tiết...", keyboard_chinh())
    for a in alerts[:5]:
        time.sleep(0.5)
        send(chat_id, format_alert(a))

    if len(alerts) > 5:
        send(chat_id,
             f"📋 Còn <b>{len(alerts) - 5}</b> thông tin khác.\n"
             f"Dùng lệnh <b>📰 Tin báo VN</b> hoặc <b>🛰 Nguồn quốc tế</b> để xem thêm.")

def cmd_tom_tat(chat_id):
    send_typing(chat_id)
    send(chat_id, "⏳ Đang tổng hợp tình hình...")

    alerts = quet_tat_ca()

    # Phân loại
    bao        = [a for a in alerts if any(k in (a.get("title","")).upper()
                   for k in ["TYPHOON","BÃO SỐ","CƠN BÃO","BÃO LỚN","BÃO MẠNH"])]
    ap_thap    = [a for a in alerts if any(k in (a.get("title","")).upper()
                   for k in ["DEPRESSION","ÁP THẤP NHIỆT ĐỚI","TROPICAL STORM","BÃO NHIỆT ĐỚI"])]
    vung_at    = [a for a in alerts if any(k in (a.get("title","")).upper()
                   for k in ["DISTURBANCE","VÙNG ÁP THẤP","NHIỄU ĐỘNG","LOW"])]
    tin_vn     = [a for a in alerts if a.get("source","") in
                   ("VnExpress 📰","24h.com.vn 📡","Dân Trí 📰","Tuổi Trẻ 📰","Thanh Niên 📰","NCHMF 🏛️")]
    tin_qt     = [a for a in alerts if a.get("source","") in
                   ("JTWC 🇺🇸","JMA 🇯🇵","NHC/NOAA 🇺🇸")]
    bien_dong  = [a for a in alerts if a.get("in_bien_dong")]

    # Đánh giá tổng thể
    if bao:
        tong_the = "🔴 <b>NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif ap_thap:
        tong_the = "🟠 <b>CẦN THEO DÕI — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    elif vung_at or alerts:
        tong_the = "🟡 <b>CÓ HIỆN TƯỢNG CẦN THEO DÕI</b>"
    else:
        tong_the = "🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ HIỆN TƯỢNG BẤT THƯỜNG</b>"

    msg = (
        f"📊 <b>BÁO CÁO TÌNH HÌNH THỜI TIẾT</b>\n"
        f"{'━' * 22}\n"
        f"{tong_the}\n\n"
        f"<b>Thống kê tin tìm được:</b>\n"
        f"🌀 Bão: <b>{len(bao)}</b> tin\n"
        f"⚠️ Áp thấp nhiệt đới / Bão nhiệt đới: <b>{len(ap_thap)}</b> tin\n"
        f"🔵 Vùng áp thấp / Nhiễu động: <b>{len(vung_at)}</b> tin\n"
        f"🇻🇳 Đang ở Biển Đông: <b>{len(bien_dong)}</b> hệ thống\n\n"
        f"<b>Theo nguồn tin:</b>\n"
        f"📰 Báo trong nước: <b>{len(tin_vn)}</b> tin\n"
        f"🛰 Nguồn quốc tế: <b>{len(tin_qt)}</b> tin\n\n"
        f"🕐 Cập nhật: {fmt_time_vn()}\n"
        f"{'━' * 22}\n"
    )

    if bien_dong:
        msg += "⚡️ <b>HỆ THỐNG ĐANG Ở BIỂN ĐÔNG:</b>\n"
        for a in bien_dong[:2]:
            msg += f"  • {a.get('title','')[:80]}\n"
    elif bao:
        msg += "🌀 <b>BÃO ĐANG THEO DÕI:</b>\n"
        for a in bao[:2]:
            msg += f"  • {a.get('title','')[:80]}\n"
    elif ap_thap:
        msg += "⚠️ <b>ÁP THẤP ĐANG THEO DÕI:</b>\n"
        for a in ap_thap[:2]:
            msg += f"  • {a.get('title','')[:80]}\n"

    send(chat_id, msg, keyboard_chinh())

def cmd_bao_ap_thap(chat_id):
    send_typing(chat_id)
    send(chat_id, "⏳ Đang lọc tin bão và áp thấp nghiêm trọng...")

    alerts = quet_tat_ca()
    keywords_nghiem_trong = [
        "TYPHOON","TROPICAL STORM","TROPICAL DEPRESSION",
        "BÃO SỐ","CƠN BÃO","BÃO MẠNH","BÃO NHIỆT ĐỚI",
        "ÁP THẤP NHIỆT ĐỚI","SUPER TYPHOON","SIÊU BÃO",
    ]
    loc = [a for a in alerts
           if any(k in (a.get("title","")).upper() for k in keywords_nghiem_trong)]

    if not loc:
        send(chat_id,
             "✅ <b>Hiện không có bão hoặc áp thấp nhiệt đới</b>\n\n"
             f"Không tìm thấy bão / áp thấp nhiệt đới đang hoạt động\n"
             f"trong khu vực Thái Bình Dương và Biển Đông.\n\n"
             f"🕐 Kiểm tra lúc: {fmt_time_vn()}",
             keyboard_chinh())
        return

    send(chat_id, f"🌀 <b>Tìm thấy {len(loc)} hệ thống bão / áp thấp:</b>")
    for a in loc[:5]:
        time.sleep(0.4)
        send(chat_id, format_alert(a))

def cmd_tin_vn(chat_id):
    send_typing(chat_id)
    send(chat_id, "⏳ Đang quét báo trong nước...")

    nguon_vn = {
        "VnExpress 📰": scrape_vnexpress,
        "24h.com.vn 📡": scrape_24h,
        "Dân Trí 📰": scrape_dantri,
        "Tuổi Trẻ 📰": scrape_tuoitre,
        "Thanh Niên 📰": scrape_thanhnien,
        "NCHMF 🏛️": scrape_nchmf,
    }
    alerts = []
    for name, fn in nguon_vn.items():
        try:
            items = fn()
            print(f"  [{name}] {len(items)} tin")
            alerts += items
        except Exception as e:
            print(f"  [{name}] Lỗi: {e}")

    # Lọc trùng
    seen = set()
    unique = [a for a in alerts if not (a["id"] in seen or seen.add(a["id"]))]

    if not unique:
        send(chat_id,
             "ℹ️ <b>Báo trong nước chưa có tin nào về thời tiết bất thường</b>\n\n"
             f"🕐 Kiểm tra lúc: {fmt_time_vn()}",
             keyboard_chinh())
        return

    send(chat_id, f"📰 <b>{len(unique)} tin từ báo trong nước:</b>")
    for a in unique[:5]:
        time.sleep(0.4)
        send(chat_id, format_alert(a))

def cmd_tin_qt(chat_id):
    send_typing(chat_id)
    send(chat_id, "⏳ Đang quét nguồn quốc tế (JTWC, JMA, NOAA)...")

    alerts = []
    for fn in [scrape_jtwc, scrape_jma, scrape_nhc]:
        try:
            items = fn()
            alerts += items
        except Exception as e:
            print(f"[QT] Lỗi: {e}")

    seen = set()
    unique = [a for a in alerts if not (a["id"] in seen or seen.add(a["id"]))]

    if not unique:
        send(chat_id,
             "✅ <b>Nguồn quốc tế không ghi nhận hệ thống thời tiết nguy hiểm</b>\n\n"
             "Đã kiểm tra: JTWC (Hải quân Mỹ), JMA (Nhật Bản), NHC/NOAA (Mỹ)\n\n"
             f"🕐 Kiểm tra lúc: {fmt_time_vn()}",
             keyboard_chinh())
        return

    send(chat_id, f"🛰 <b>{len(unique)} thông tin từ nguồn quốc tế:</b>")
    for a in unique[:5]:
        time.sleep(0.4)
        send(chat_id, format_alert(a))

def cmd_huong_dan(chat_id):
    msg = (
        "ℹ️ <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n"
        f"{'━' * 22}\n\n"
        "<b>🔍 Kiểm tra ngay</b>\n"
        "Quét tất cả 9 nguồn tin ngay lập tức và trả về kết quả.\n\n"
        "<b>📊 Tóm tắt tình hình</b>\n"
        "Báo cáo tổng hợp: số lượng bão, áp thấp, hệ thống đang theo dõi.\n\n"
        "<b>🌀 Chỉ xem bão/áp thấp</b>\n"
        "Lọc riêng tin về bão, áp thấp nhiệt đới — bỏ qua nhiễu động nhỏ.\n\n"
        "<b>📰 Tin báo VN</b>\n"
        "Chỉ xem tin từ: VnExpress, 24h, Dân Trí, Tuổi Trẻ, Thanh Niên, NCHMF.\n\n"
        "<b>🛰 Nguồn quốc tế</b>\n"
        "Chỉ xem tin từ: JTWC (Hải quân Mỹ), JMA (Nhật Bản), NHC/NOAA.\n\n"
        f"{'━' * 22}\n"
        "⏰ <b>Bot tự động cảnh báo</b> mỗi giờ nếu phát hiện hiện tượng mới.\n"
        f"🕐 Giờ VN hiện tại: {fmt_time_vn()}"
    )
    send(chat_id, msg, keyboard_chinh())

# ── Kiểm tra quyền truy cập ───────────────────────────────────────────────────
def co_quyen(chat_id):
    if not ALLOWED_SET:
        return True   # Không giới hạn nếu chưa cấu hình
    return str(chat_id) in ALLOWED_SET

# ── Xử lý từng tin nhắn ──────────────────────────────────────────────────────
def xu_ly(update):
    msg = update.get("message") or update.get("channel_post") or {}
    if not msg:
        return

    chat_id = msg.get("chat", {}).get("id")
    text    = (msg.get("text") or "").strip()
    ten     = msg.get("from", {}).get("first_name", "bạn")

    if not chat_id or not text:
        return

    if not co_quyen(chat_id):
        send(chat_id, "⛔ Bạn không có quyền sử dụng bot này.")
        return

    print(f"[Bot] Lệnh từ {chat_id}: {text[:50]}")

    # Phân loại lệnh
    if text in ["/start", "/help"]:
        cmd_start(chat_id, ten)
    elif text in ["🔍 Kiểm tra ngay", "/check", "/kiem_tra"]:
        cmd_kiem_tra_ngay(chat_id)
    elif text in ["📊 Tóm tắt tình hình", "/summary", "/tom_tat"]:
        cmd_tom_tat(chat_id)
    elif text in ["🌀 Chỉ xem bão/áp thấp", "/bao", "/storm"]:
        cmd_bao_ap_thap(chat_id)
    elif text in ["📰 Tin báo VN", "/vn", "/trongnuoc"]:
        cmd_tin_vn(chat_id)
    elif text in ["🛰 Nguồn quốc tế", "/qt", "/international"]:
        cmd_tin_qt(chat_id)
    elif text in ["ℹ️ Hướng dẫn", "/huongdan"]:
        cmd_huong_dan(chat_id)
    else:
        send(chat_id,
             f"❓ Không hiểu lệnh <b>{text[:30]}</b>\n\n"
             "Nhấn một nút bên dưới hoặc gõ /help để xem hướng dẫn.",
             keyboard_chinh())

# ── Main: polling ngắn (chạy tối đa 8 phút mỗi lần) ─────────────────────────
def main():
    if not TOKEN:
        print("[Bot] Chưa cấu hình TELEGRAM_BOT_TOKEN!")
        return

    state  = load_bot_state()
    offset = state.get("offset", 0)

    print(f"[Bot Handler] Bắt đầu polling lúc {fmt_time_vn()}, offset={offset}")

    # Polling trong 8 phút (GitHub Actions timeout = 10 phút per step)
    deadline = time.time() + 8 * 60
    processed = 0

    while time.time() < deadline:
        updates = get_updates(offset)
        for upd in updates:
            xu_ly(upd)
            offset = upd["update_id"] + 1
            processed += 1

        state["offset"]  = offset
        state["last_run"] = fmt_time_vn()
        save_bot_state(state)

        if not updates:
            time.sleep(3)   # Chờ nếu không có tin nhắn mới

    print(f"[Bot Handler] Kết thúc. Đã xử lý {processed} cập nhật. Offset mới: {offset}")

if __name__ == "__main__":
    main()
