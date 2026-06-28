# 🌀 Storm Monitor Bot — Cảnh báo Áp thấp / Bão Thái Bình Dương → Biển Đông

Bot tự động theo dõi các nguồn dữ liệu thời tiết quốc tế và trong nước,
gửi cảnh báo qua **Telegram** khi có áp thấp/bão hình thành trên Thái Bình Dương
có khả năng di chuyển vào Biển Đông — **hoàn toàn miễn phí** nhờ GitHub Actions.

---

## 📡 Nguồn dữ liệu

| Nguồn | URL | Ghi chú |
|---|---|---|
| NCHMF (VN) | nchmf.gov.vn | Bản tin khẩn cấp của Việt Nam |
| JTWC (Mỹ) | metoc.navy.mil | RSS bão Tây Thái Bình Dương |
| JMA (Nhật) | jma.go.jp | JSON vị trí bão thời gian thực |
| NHC/NOAA | nhc.noaa.gov | Danh sách sản phẩm bão |

---

## 🚀 Cài đặt (5 bước)

### Bước 1 — Tạo Telegram Bot

1. Mở Telegram → tìm **@BotFather** → gõ `/newbot`
2. Đặt tên bot (vd: `VN Storm Alert`) → đặt username (vd: `vn_storm_bot`)
3. Copy **token** nhận được (dạng `123456789:ABC...`)

### Bước 2 — Lấy Chat ID

1. Gửi `/start` cho bot vừa tạo
2. Truy cập URL này (thay YOUR_TOKEN):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Tìm `"chat":{"id":XXXXXXXXX}` → đó là **Chat ID** của bạn

> 💡 **Mẹo:** Để nhận theo nhóm — thêm bot vào nhóm Telegram, gõ bất kỳ tin nhắn trong nhóm, rồi dùng getUpdates để lấy Chat ID của nhóm (số âm).

### Bước 3 — Tạo GitHub Repository

1. Vào [github.com](https://github.com) → **New repository**
2. Tên: `storm-monitor-bot` (private hoặc public đều được)
3. Upload toàn bộ file từ thư mục này lên repo

### Bước 4 — Thêm Secrets vào GitHub

Vào repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Giá trị |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID của bạn |

### Bước 5 — Kích hoạt Actions

1. Vào tab **Actions** trong repo
2. Nếu bị hỏi → chọn **"I understand my workflows, go ahead and enable them"**
3. Click **"Storm Monitor Bot"** → **"Run workflow"** để test ngay

---

## ⚙️ Tùy chỉnh

### Thay đổi tần suất quét

Trong file `.github/workflows/storm-monitor.yml`, dòng `cron`:

```yaml
- cron: "0 * * * *"     # Mỗi giờ (mặc định)
- cron: "0 */3 * * *"   # Mỗi 3 giờ
- cron: "0 */6 * * *"   # Mỗi 6 giờ
- cron: "0 6,12,18 * * *"  # Lúc 6h, 12h, 18h UTC
```

> ⚠️ GitHub Actions miễn phí cho 2,000 phút/tháng. Mỗi lần chạy ~1-2 phút.
> - Mỗi giờ = ~48h/tháng → an toàn ✅
> - Mỗi 30 phút = ~96h/tháng → vẫn ổn ✅

### Điều chỉnh vùng theo dõi

Trong `monitor.py`, chỉnh `WATCH_ZONE` để mở rộng/thu hẹp vùng giám sát:

```python
WATCH_ZONE = {"lat_min": 5, "lat_max": 30, "lon_min": 100, "lon_max": 155}
```

---

## 📱 Ví dụ tin nhắn cảnh báo

```
🌀 CẢNH BÁO THỜI TIẾT
━━━━━━━━━━━━━━━━━━
📡 Nguồn: JMA
🕐 Thời gian: 15/09/2025 06:00 UTC
📋 JMA: TROPICAL DEPRESSION TD18W (12.5°N 128.3°E) → WNW
📍 Vị trí: 12.5°N, 128.3°E (khu vực theo dõi TBD)
━━━━━━━━━━━━━━━━━━
🔗 Xem chi tiết
```

---

## 🐛 Xem log lỗi

Vào tab **Actions** → click vào lần chạy bất kỳ → xem output chi tiết.

---

## 📜 Giấy phép

MIT — sử dụng tự do cho mục đích cá nhân và phi thương mại.
