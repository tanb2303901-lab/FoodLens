# Hợp đồng API FoodLens v1

Cập nhật 2026-10-20 (FOOD-02). Runtime 0.7.0, 10 paths / 11 operations; contract chính [openapi-backend-v1.json](openapi-backend-v1.json) được sinh lại từ server thật, kèm 15 ví dụ trong [api-examples-v1.json](../handoff/api-examples-v1.json). Dinh dưỡng, bữa ăn, thống kê và idempotency key đã bị gỡ; các mô tả về chúng trong review/task cũ là lịch sử.

## Quy tắc chung

- Mọi `/v1/*` cần Bearer user access token của Supabase Auth; `/health` và `/health/ready` không cần. Backend xác minh chữ ký, issuer, audience, hạn token và UUID subject; owner luôn lấy từ token, không nhận `user_id` từ client.
- Body lỗi: `{"error":{"code","message","details","request_id"}}`; không trả lỗi SQL, secret, token hay đường dẫn ảnh của người khác. Field lạ hoặc query lạ/lặp bị 422.
- UUID là định danh tài nguyên; class ID chỉ là metadata của model. `original_class_id` của 8 lớp mở rộng là `null`.
- Thời gian theo ISO 8601 có offset hoặc `Z`. Danh sách dùng `limit` 1..100 (mặc định 20), `cursor` mờ gắn với owner và bộ lọc, trả `items` + `next_cursor`.
- Mọi response có `X-Request-ID` và `Cache-Control: no-store`.

## Endpoint

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | /health | Process còn sống; không gọi database/model |
| GET | /health/ready | 200 khi database sẵn sàng (kể cả model chưa sẵn sàng), 503 khi database lỗi; `capabilities: {catalog, scan}` |
| GET/PATCH | /v1/me | Profile của chủ token: `display_name`, `timezone` IANA |
| GET | /v1/foods | Tìm theo `q` (tên Việt/Anh/slug, ≤100 ký tự), sắp theo slug, chỉ món active |
| GET | /v1/foods/{id} | Định danh món và class map |
| GET | /v1/foods/{id}/description | Bản giới thiệu published hiện hành kèm nguồn, hoặc `description_unavailable`/`not_published`; luôn 200 với món tồn tại; không bao giờ trả bản nháp |
| POST | /v1/scans/analyze | Multipart `file` + `input_source`; chỉ chạy khi model thật sẵn sàng, nếu không trả 503 `MODEL_NOT_READY` trước khi đọc ảnh. Ảnh được chuẩn hóa, lưu Storage riêng tư, kết quả lưu vào scan |
| GET | /v1/scans | Lịch sử scan của chủ token, mới nhất trước, lọc `[from,to)` |
| GET | /v1/scans/{id} | Chi tiết: detections gốc, confirmations, link ảnh ký hạn 300 giây (hoặc null) và ETag |
| PATCH | /v1/scans/{id}/result | Thay danh sách xác nhận `{detection_id, food_id}`; bắt buộc `If-Match`; không sửa detections gốc |

Chi tiết dành cho frontend: [backend-v1.md](../handoff/backend-v1.md), [food-description-api.md](../handoff/food-description-api.md), [error-codes-v1.md](../handoff/error-codes-v1.md). Giao thức model: [predictor-contract.md](predictor-contract.md).
