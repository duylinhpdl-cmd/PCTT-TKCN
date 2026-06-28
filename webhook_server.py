"""
🌐 Webhook Server — nhận tin nhắn Telegram & trả lời NGAY LẬP TỨC
Deploy lên Render.com (miễn phí). Telegram gọi thẳng vào server này.

Luồng hoạt động:
  Người dùng nhắn → Telegram → POST /webhook → Flask xử lý → trả lời ngay
"""

import os
import time
import threading
import logging
from flask import Flask, request, jsonify

from monitor import (
    scrape_nchmf, scrape_vnexpress, scrape_24h, scrape_dantri,
    scrape_tuoitre, scrape_thanhnien, scrape_jtwc, scrape_jma, scrape_nhc,
    format_alert, fmt_time_vn,
)
import requests as req

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Cấu hình ──────────────────────────────────────────────────────────────────
TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_IDS   = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET     = os.environ.get("WEBHOOK_SECRET", "storm_secret_2025")
RENDER_URL = os.environ.get("RENDER_URL", "")   # VD: https://storm-bot.onrender.com

API = f"https://api.telegram.org/bot{TOKEN}"

# Chat ID được phép dùng bot (để trống = cho phép tất cả)
ALLOWED = {s.strip() for s in CHAT_IDS.split(",") if s.strip()} if CHAT_IDS else set()

app = Flask(__name__)

# ── Cache kết quả (tránh quét lại quá nhanh) ──────────────────────────────────
_cache = {"data": None, "time": 0}
CACHE_TTL = 300   # giây — 5 phút

def quet_co_cache():
    now = time.time()
    if _cache["data"] is not None and (now - _cache["time"]) < CACHE_TTL:
        log.info("Dùng cache (còn %.0f giây)", CACHE_TTL - (now - _cache["time"]))
        return _cache["data"]

    log.info("Quét tất cả nguồn...")
    alerts = []
    nguon = [
        ("NCHMF",       scrape_nchmf),
        ("VnExpress",   scrape_vnexpress),
        ("24h",         scrape_24h),
        ("Dân Trí",     scrape_dantri),
        ("Tuổi Trẻ",    scrape_tuoitre),
        ("Thanh Niên",  scrape_thanhnien),
        ("JTWC",        scrape_jtwc),
        ("JMA",         scrape_jma),
        ("NHC/NOAA",    scrape_nhc),
    ]
    for name, fn in nguon:
        try:
            items = fn()
            log.info("  [%s] %d tin", name, len(items))
            alerts += items
        except Exception as e:
            log.warning("  [%s] Lỗi: %s", name, e)

    # Lọc trùng
    seen, unique = set(), []
    for a in alerts:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)

    _cache["data"] = unique
    _cache["time"] = time.time()
    log.info("Quét xong: %d tin duy nhất", len(unique))
    return unique

# ── Gọi Telegram API ──────────────────────────────────────────────────────────
def tg_send(chat_id, text, markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if markup:
        payload["reply_markup"] = markup
    try:
        r = req.post(f"{API}/sendMessage", json=payload, timeout=15)
        if r.status_code != 200:
            log.warning("Telegram lỗi %s: %s", r.status_code, r.text[:100])
    except Exception as e:
        log.error("Gửi Telegram thất bại: %s", e)

def tg_typing(chat_id):
    try:
        req.post(f"{API}/sendChatAction",
                 json={"chat_id": chat_id, "action": "typing"},
                 timeout=5)
    except Exception:
        pass

def tg_answer(callback_id, text=""):
    try:
        req.post(f"{API}/answerCallbackQuery",
                 json={"callback_query_id": callback_id, "text": text},
                 timeout=5)
    except Exception:
        pass

# ── Bàn phím inline ───────────────────────────────────────────────────────────
def ban_phim_chinh():
    return {
        "inline_keyboard": [
            [
                {"text": "🔍 Kiểm tra ngay",      "callback_data": "check"},
                {"text": "📊 Tóm tắt",            "callback_data": "summary"},
            ],
            [
                {"text": "🌀 Bão / Áp thấp",       "callback_data": "storm"},
                {"text": "📰 Báo trong nước",       "callback_data": "vn"},
            ],
            [
                {"text": "🛰 Nguồn quốc tế",        "callback_data": "intl"},
                {"text": "ℹ️ Hướng dẫn",            "callback_data": "help"},
            ],
        ]
    }

# ── Xử lý các lệnh ───────────────────────────────────────────────────────────
def xu_ly_check(chat_id):
    tg_typing(chat_id)
    tg_send(chat_id, "⏳ Đang quét <b>9 nguồn tin</b>, vui lòng chờ...")

    alerts = quet_co_cache()

    if not alerts:
        tg_send(chat_id,
            "✅ <b>Không có hiện tượng thời tiết bất thường</b>\n\n"
            "Đã kiểm tra đầy đủ báo trong nước và nguồn quốc tế.\n"
            "Thái Bình Dương và Biển Đông hiện <b>bình thường</b>.\n\n"
            f"🕐 Kiểm tra lúc: <b>{fmt_time_vn()}</b>",
            ban_phim_chinh())
        return

    tg_send(chat_id,
        f"🚨 <b>Tìm thấy {len(alerts)} thông tin đáng chú ý</b>\n"
        f"Đang gửi chi tiết...",
        ban_phim_chinh())
    for a in alerts[:5]:
        time.sleep(0.3)
        tg_send(chat_id, format_alert(a))
    if len(alerts) > 5:
        tg_send(chat_id,
            f"📋 Còn <b>{len(alerts) - 5}</b> tin nữa.\n"
            "Nhấn 📰 hoặc 🛰 để xem theo từng nguồn.")

def xu_ly_summary(chat_id):
    tg_typing(chat_id)
    alerts = quet_co_cache()

    bao       = [a for a in alerts if any(k in a.get("title","").upper()
                 for k in ["TYPHOON","BÃO SỐ","CƠN BÃO","BÃO LỚN","BÃO MẠNH","SUPER TYPHOON","SIÊU BÃO"])]
    ap_thap   = [a for a in alerts if any(k in a.get("title","").upper()
                 for k in ["TROPICAL DEPRESSION","TROPICAL STORM","ÁP THẤP NHIỆT ĐỚI","BÃO NHIỆT ĐỚI"])]
    nhieu_dong= [a for a in alerts if any(k in a.get("title","").upper()
                 for k in ["DISTURBANCE","NHIỄU ĐỘNG","LOW","VÙNG ÁP THẤP"])]
    bien_dong = [a for a in alerts if a.get("in_bien_dong")]
    tin_vn    = [a for a in alerts if "📰" in a.get("source","") or "🏛️" in a.get("source","") or "📡" in a.get("source","")]
    tin_qt    = [a for a in alerts if any(x in a.get("source","") for x in ["🇺🇸","🇯🇵"])]

    if bao:           danh_gia = "🔴 <b>RẤT NGUY HIỂM — CÓ BÃO ĐANG HOẠT ĐỘNG</b>"
    elif ap_thap:     danh_gia = "🟠 <b>NGUY HIỂM — CÓ ÁP THẤP NHIỆT ĐỚI</b>"
    elif nhieu_dong or alerts: danh_gia = "🟡 <b>CÓ HIỆN TƯỢNG CẦN THEO DÕI</b>"
    else:             danh_gia = "🟢 <b>BÌNH THƯỜNG — KHÔNG CÓ HIỆN TƯỢNG BẤT THƯỜNG</b>"

    msg = (
        f"📊 <b>BÁO CÁO TÌNH HÌNH THỜI TIẾT</b>\n"
        f"{'━'*22}\n"
        f"{danh_gia}\n\n"
        f"<b>📌 Chi tiết hệ thống:</b>\n"
        f"  🌀 Bão: <b>{len(bao)}</b>\n"
        f"  ⚠️ Áp thấp / Bão nhiệt đới: <b>{len(ap_thap)}</b>\n"
        f"  🔵 Nhiễu động / Vùng áp thấp: <b>{len(nhieu_dong)}</b>\n"
        f"  🇻🇳 Đang ở Biển Đông: <b>{len(bien_dong)}</b>\n\n"
        f"<b>📡 Nguồn tin:</b>\n"
        f"  📰 Báo trong nước: <b>{len(tin_vn)}</b> tin\n"
        f"  🛰 Quốc tế: <b>{len(tin_qt)}</b> tin\n\n"
    )

    if bien_dong:
        msg += "⚡️ <b>ĐANG Ở BIỂN ĐÔNG:</b>\n"
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

    msg += f"\n🕐 Cập nhật: {fmt_time_vn()}"
    tg_send(chat_id, msg, ban_phim_chinh())

def xu_ly_storm(chat_id):
    tg_typing(chat_id)
    alerts = quet_co_cache()

    kw = ["TYPHOON","TROPICAL STORM","TROPICAL DEPRESSION","BÃO SỐ",
          "CƠN BÃO","BÃO MẠNH","BÃO NHIỆT ĐỚI","ÁP THẤP NHIỆT ĐỚI","SIÊU BÃO"]
    loc = [a for a in alerts if any(k in a.get("title","").upper() for k in kw)]

    if not loc:
        tg_send(chat_id,
            "✅ <b>Không có bão hoặc áp thấp nhiệt đới</b>\n\n"
            "Khu vực Tây Thái Bình Dương và Biển Đông hiện không ghi nhận\n"
            "bão hoặc áp thấp nhiệt đới nào đang hoạt động.\n\n"
            f"🕐 Kiểm tra lúc: <b>{fmt_time_vn()}</b>",
            ban_phim_chinh())
        return

    tg_send(chat_id, f"🌀 <b>Tìm thấy {len(loc)} hệ thống bão / áp thấp:</b>")
    for a in loc[:5]:
        time.sleep(0.3)
        tg_send(chat_id, format_alert(a))

def xu_ly_vn(chat_id):
    tg_typing(chat_id)
    alerts = quet_co_cache()
    loc = [a for a in alerts
           if any(x in a.get("source","") for x in ["📰","🏛️","📡"])]
    if not loc:
        tg_send(chat_id,
            "ℹ️ <b>Báo trong nước chưa có tin thời tiết bất thường</b>\n\n"
            f"🕐 Kiểm tra lúc: <b>{fmt_time_vn()}</b>",
            ban_phim_chinh())
        return
    tg_send(chat_id, f"📰 <b>{len(loc)} tin từ báo trong nước:</b>")
    for a in loc[:5]:
        time.sleep(0.3)
        tg_send(chat_id, format_alert(a))

def xu_ly_intl(chat_id):
    tg_typing(chat_id)
    alerts = quet_co_cache()
    loc = [a for a in alerts
           if any(x in a.get("source","") for x in ["🇺🇸","🇯🇵"])]
    if not loc:
        tg_send(chat_id,
            "✅ <b>Nguồn quốc tế không ghi nhận hệ thống nguy hiểm</b>\n\n"
            "Đã kiểm tra: JTWC, JMA, NHC/NOAA\n\n"
            f"🕐 Kiểm tra lúc: <b>{fmt_time_vn()}</b>",
            ban_phim_chinh())
        return
    tg_send(chat_id, f"🛰 <b>{len(loc)} tin từ nguồn quốc tế:</b>")
    for a in loc[:5]:
        time.sleep(0.3)
        tg_send(chat_id, format_alert(a))

def xu_ly_help(chat_id):
    msg = (
        "ℹ️ <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n"
        f"{'━'*22}\n\n"
        "🔍 <b>Kiểm tra ngay</b>\n"
        "Quét 9 nguồn tin và trả kết quả ngay lập tức.\n\n"
        "📊 <b>Tóm tắt</b>\n"
        "Báo cáo tổng hợp: bão, áp thấp, nhận định mức độ.\n\n"
        "🌀 <b>Bão / Áp thấp</b>\n"
        "Lọc riêng tin bão, áp thấp nhiệt đới nghiêm trọng.\n\n"
        "📰 <b>Báo trong nước</b>\n"
        "VnExpress · 24h · Dân Trí · Tuổi Trẻ · Thanh Niên · NCHMF\n\n"
        "🛰 <b>Nguồn quốc tế</b>\n"
        "JTWC (Hải quân Mỹ) · JMA (Nhật) · NHC/NOAA (Mỹ)\n\n"
        f"{'━'*22}\n"
        "⏰ Bot <b>tự động cảnh báo</b> mỗi giờ nếu phát hiện hiện tượng mới.\n"
        "💾 Kết quả quét được cache <b>5 phút</b> để phản hồi nhanh hơn.\n\n"
        f"🕐 Giờ VN hiện tại: <b>{fmt_time_vn()}</b>"
    )
    tg_send(chat_id, msg, ban_phim_chinh())

def xu_ly_start(chat_id, ten="bạn"):
    msg = (
        f"👋 Xin chào <b>{ten}</b>!\n\n"
        "🤖 Tôi là <b>Bot Cảnh báo Thời tiết Việt Nam</b>\n"
        "Theo dõi áp thấp, bão từ Thái Bình Dương\ncó khả năng vào Biển Đông.\n\n"
        "👇 <b>Nhấn một nút bên dưới để bắt đầu:</b>"
    )
    tg_send(chat_id, msg, ban_phim_chinh())

# ── Router lệnh ──────────────────────────────────────────────────────────────
LENH_MAP = {
    "/start": xu_ly_start, "start": xu_ly_start,
    "/help":  xu_ly_help,  "help":  xu_ly_help,
    "check":   xu_ly_check,   "/check":   xu_ly_check,
    "summary": xu_ly_summary, "/summary": xu_ly_summary,
    "storm":   xu_ly_storm,   "/storm":   xu_ly_storm,
    "vn":      xu_ly_vn,      "/vn":      xu_ly_vn,
    "intl":    xu_ly_intl,    "/intl":    xu_ly_intl,
}

def dispatch(chat_id, cmd, ten="bạn"):
    fn = LENH_MAP.get(cmd)
    if fn:
        if cmd in ("/start", "start"):
            fn(chat_id, ten)
        else:
            fn(chat_id)
    else:
        tg_send(chat_id,
            f"❓ Không hiểu lệnh <b>{cmd[:20]}</b>\n"
            "Nhấn một nút bên dưới để chọn chức năng:",
            ban_phim_chinh())

# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "bot": "Storm Monitor Bot",
        "time": fmt_time_vn(),
    })

@app.route(f"/webhook/{SECRET}", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    # Xử lý trong thread riêng để tránh timeout Telegram (5 giây)
    def process():
        # Tin nhắn văn bản
        if "message" in data:
            msg     = data["message"]
            chat_id = msg.get("chat", {}).get("id")
            text    = (msg.get("text") or "").strip()
            ten     = msg.get("from", {}).get("first_name", "bạn")
            if not chat_id:
                return
            if ALLOWED and str(chat_id) not in ALLOWED:
                tg_send(chat_id, "⛔ Bạn không có quyền dùng bot này.")
                return
            log.info("Tin nhắn từ %s: %s", chat_id, text[:50])
            dispatch(chat_id, text, ten)

        # Nhấn nút inline
        elif "callback_query" in data:
            cb      = data["callback_query"]
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            cmd     = cb.get("data", "")
            ten     = cb.get("from", {}).get("first_name", "bạn")
            cb_id   = cb.get("id")
            tg_answer(cb_id, "⏳ Đang xử lý...")
            if not chat_id:
                return
            if ALLOWED and str(chat_id) not in ALLOWED:
                return
            log.info("Callback từ %s: %s", chat_id, cmd)
            dispatch(chat_id, cmd, ten)

    threading.Thread(target=process, daemon=True).start()
    return jsonify({"ok": True})   # Trả về ngay cho Telegram

@app.route("/ping", methods=["GET"])
def ping():
    """Endpoint để UptimeRobot ping giữ server không ngủ."""
    return "pong", 200

# ── Đăng ký webhook với Telegram ─────────────────────────────────────────────
def dang_ky_webhook():
    if not RENDER_URL or not TOKEN:
        log.warning("Chưa có RENDER_URL hoặc TOKEN — bỏ qua đăng ký webhook")
        return
    url = f"{RENDER_URL}/webhook/{SECRET}"
    try:
        r = req.post(f"{API}/setWebhook",
                     json={"url": url, "allowed_updates": ["message","callback_query"]},
                     timeout=15)
        res = r.json()
        if res.get("ok"):
            log.info("✅ Webhook đã đăng ký: %s", url)
        else:
            log.error("❌ Đăng ký webhook thất bại: %s", res)
    except Exception as e:
        log.error("Lỗi đăng ký webhook: %s", e)

# ── Chạy server ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dang_ky_webhook()
    port = int(os.environ.get("PORT", 5000))
    log.info("🚀 Server khởi động trên cổng %d", port)
    app.run(host="0.0.0.0", port=port)
