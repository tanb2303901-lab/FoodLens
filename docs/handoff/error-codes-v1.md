# Mã lỗi backend FoodLens

Cập nhật 2026-10-20 (API 0.7.0, sau FOOD-02). Lỗi trả body `{"error":{"code","message","details":[{"field","message"}],"request_id"}}`, header `X-Request-ID` trùng `request_id`, và `Cache-Control: no-store`. Xử lý theo `code`/HTTP status; `message`/`details` có thể đổi, không parse chữ. Khi báo lỗi chỉ cần gửi `request_id`, không gửi token, ảnh hay link ảnh riêng tư.

Ngoại lệ có chủ ý: `/health/ready` khi database lỗi trả 503 với body Readiness (không phải body lỗi). `description_unavailable` không phải lỗi: đó là 200 với trạng thái thiếu nội dung.

| HTTP / code | Khi nào | Client nên làm |
| --- | --- | --- |
| 401 `UNAUTHENTICATED` | Thiếu/sai/hết hạn user token, hoặc gửi public key thay token | Refresh session một lần, rồi đăng nhập lại; không retry vòng lặp |
| 404 `NOT_FOUND` | Món không có/không active, scan không tồn tại hoặc thuộc user khác, path không tồn tại | Hiện "không tìm thấy"; không suy ra dữ liệu của tài khoản khác |
| 405 `HTTP_ERROR` | Sai method | Sửa request |
| 408 `UPLOAD_TIMEOUT` | Upload ảnh quá chậm | Cho thử lại |
| 409 `SCAN_NOT_COMPLETED` | Xác nhận kết quả cho scan chưa xong | Tải lại scan rồi thử lại |
| 409 `RESOURCE_CONFLICT` | Dữ liệu xung đột | Tải lại trạng thái |
| 412 `VERSION_CONFLICT` | `If-Match` đã cũ | `GET /v1/scans/{id}` lấy ETag mới rồi làm lại |
| 413 `IMAGE_TOO_LARGE` | Ảnh > 10 MiB, quá 20 triệu pixel hoặc cạnh > 8192 | Chọn/thu nhỏ ảnh |
| 415 `UNSUPPORTED_IMAGE` | Không phải JPEG/PNG/WebP tĩnh | Chọn ảnh khác |
| 422 `INVALID_IMAGE` | Ảnh hỏng, không giải mã được | Chọn ảnh khác |
| 422 `INVALID_MULTIPART` | Form upload sai (thiếu/thừa field `file`) | Sửa request |
| 422 `INVALID_INPUT` | Sai schema, UUID, query lạ/lặp, field thừa (ví dụ `user_id`) | Sửa input; xem `details.field` |
| 422 `INVALID_TIMEZONE` | `timezone` không phải tên IANA hợp lệ | Cho chọn lại múi giờ |
| 422 `INVALID_CURSOR` | Cursor bị sửa hoặc dùng sai bộ lọc/tài khoản | Tải lại từ trang đầu |
| 422 `INVALID_TIME_RANGE` | `from` ≥ `to` khi lọc lịch sử | Sửa khoảng thời gian |
| 422 `INVALID_CONFIRMATION`, `DUPLICATE_DETECTION` | Xác nhận detection không có hoặc lặp | Sửa danh sách xác nhận |
| 428 `IF_MATCH_REQUIRED` | Thiếu `If-Match` khi sửa kết quả scan | Lấy ETag rồi gửi lại |
| 503 `MODEL_NOT_READY` | Model chưa sẵn sàng (kiểm tra trước khi đọc ảnh) | Báo nhận diện tạm thời không dùng được |
| 503 `PREDICTION_FAILED`, `PREDICTION_INVALID_OUTPUT` | Model lỗi khi chạy | Cho thử lại sau |
| 504 `PREDICTION_TIMEOUT` | Model chạy quá lâu | Cho thử lại |
| 503 `SCAN_STATE_UNCERTAIN` | Không chắc scan đã lưu | Mở lịch sử scan để kiểm tra trước khi gửi lại |
| 503 `DEPENDENCY_UNAVAILABLE` | Database/Storage không truy cập được hoặc dữ liệu nội dung không nhất quán | Thử lại sau |
| 500 `INTERNAL_ERROR` | Lỗi bất ngờ đã được làm sạch | Thử lại; báo `request_id` |

Các mã liên quan dinh dưỡng, bữa ăn và idempotency (`IDEMPOTENCY_KEY_REUSED`, `INVALID_GRAMS`…) đã không còn từ API 0.7.0.
