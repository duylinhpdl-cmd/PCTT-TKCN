"""
🔧 test_bot.py — Kiểm tra kết nối Telegram và toàn bộ hệ thống
Chạy thủ công trên GitHub Actions để xác nhận bot hoạt động đúng.
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))
TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

def check(label, ok, detail=""):
    status = PASS if ok else FAIL
    msg    = f"{status} {label}"
    if detail: msg += f" — {detail}"
    print(msg)
    return ok

def test_env():
    print("\n── 1. Kiểm tra biến môi trường ──")
    t = check("TELEGRAM_BOT_TOKEN tồn tại", bool(TOKEN),
              f"{'Có' if TOKEN else 'THIẾU — kiểm tra GitHub Secrets'}")
    c = check("TELEGRAM_CHAT_ID tồn tại", bool(CHAT_ID),
              f"{'Có' if CHAT_ID else 'THIẾU — kiểm tra GitHub Secrets'}")
    if TOKEN:
        masked = TOKEN[:8] + "..." + TOKEN[-4:]
        print(f"   Token: {masked}")
    if CHAT_ID:
        print(f"   Chat ID: {CHAT_ID}")
    return t and c

def test_token():
    print("\n── 2. Xác thực token với Telegram ──")
    if not TOKEN:
        print(f"{WARN} Bỏ qua — không có token")
        return False
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getMe",
            timeout=10)
        data = r.json()
        ok   = data.get("ok", False)
        if ok:
            bot = data["result"]
            check("Token hợp lệ", True,
                  f"Bot: @{bot['username']} ({bot['first_name']})")
        else:
            check("Token hợp lệ", False,
                  data.get("description","Token sai hoặc đã bị thu hồi"))
        return ok
    except Exception as e:
        check("Kết nối Telegram API", False, str(e))
        return False

def test_send():
    print("\n── 3. Gửi tin nhắn thử ──")
    if not TOKEN or not CHAT_ID:
        print(f"{WARN} Bỏ qua — thiếu token hoặc chat_id")
        return False
    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M (GMT+7)")
    msg = (
        "🔧 <b>KIỂM TRA HỆ THỐNG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot kết nối thành công!\n"
        f"🕐 Thời gian: {now_vn}\n"
        f"🤖 Nguồn: GitHub Actions\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Bot sẽ tự động gửi báo cáo lúc:\n"
        "  • 02:00 sáng (GMT+7)\n"
        "  • 08:00 sáng (GMT+7)\n"
        "  • 14:00 chiều (GMT+7)\n"
        "  • 20:00 tối (GMT+7)"
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg,
                  "parse_mode": "HTML"},
            timeout=10)
        ok = r.status_code == 200 and r.json().get("ok", False)
        if ok:
            check("Gửi tin nhắn thành công", True)
        else:
            err = r.json().get("description","")
            check("Gửi tin nhắn", False, err)
            if "chat not found" in err.lower():
                print(f"   {WARN} Chat ID sai. Bạn đã nhắn /start cho bot chưa?")
            if "blocked" in err.lower():
                print(f"   {WARN} Bạn đã block bot. Vào Telegram → unblock bot.")
        return ok
    except Exception as e:
        check("Gửi tin nhắn", False, str(e))
        return False

def test_imports():
    print("\n── 4. Kiểm tra thư viện Python ──")
    libs = ["requests","bs4","lxml"]
    all_ok = True
    for lib in libs:
        try:
            __import__(lib)
            check(f"import {lib}", True)
        except ImportError:
            check(f"import {lib}", False, "Chạy: pip install " + lib)
            all_ok = False
    return all_ok

def test_monitor_import():
    print("\n── 5. Kiểm tra monitor.py ──")
    try:
        import monitor  # noqa
        check("import monitor", True)
        funcs = ["scrape_jma","scrape_jtwc","scrape_nchmf",
                 "format_bao_cao","send_telegram","main"]
        for fn in funcs:
            ok = hasattr(monitor, fn)
            check(f"Hàm {fn}()", ok,
                  "" if ok else "Thiếu hàm — file monitor.py có thể cũ")
        return True
    except Exception as e:
        check("import monitor", False, str(e))
        return False

def main():
    print("=" * 45)
    print("   KIỂM TRA HỆ THỐNG STORM MONITOR BOT")
    print("=" * 45)

    results = []
    results.append(("Biến môi trường",  test_env()))
    results.append(("Token Telegram",   test_token()))
    results.append(("Gửi tin nhắn",     test_send()))
    results.append(("Thư viện Python",  test_imports()))
    results.append(("File monitor.py",  test_monitor_import()))

    print("\n── Kết quả tổng hợp ──")
    all_pass = True
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok: all_pass = False

    print()
    if all_pass:
        print("🎉 Tất cả kiểm tra đạt! Bot sẵn sàng hoạt động.")
    else:
        print("⚠️  Có lỗi cần sửa trước khi bot hoạt động đúng.")
        print("   Xem chi tiết từng bước ở trên để khắc phục.")
        sys.exit(1)

if __name__ == "__main__":
    main()
