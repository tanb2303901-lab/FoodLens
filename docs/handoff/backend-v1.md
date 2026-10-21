# Bàn giao backend FoodLens cho frontend

Cập nhật 2026-10-20 (FOOD-02). Tài liệu chuẩn bị để chủ dự án chuyển cho người làm frontend; chưa được gửi. Backend API **0.7.0**, 10 paths / 11 operations. Contract chính: [openapi-backend-v1.json](../architecture/openapi-backend-v1.json); 15 request/response thật: [api-examples-v1.json](api-examples-v1.json).

## Phạm vi sản phẩm hiện tại

Người dùng đăng nhập → chụp/chọn ảnh → backend nhận diện món bằng model thật → app hiện khung nhận diện và thẻ giới thiệu món đã được duyệt → xem lại lịch sử scan. **Không có** dinh dưỡng, calo, bữa ăn hay thống kê: các phần này đã bị gỡ khỏi backend theo quyết định chủ dự án ngày 2026-10-19 (dữ liệu cũ được backup ngoài repo).

| Nhóm | Endpoint | Ghi chú |
| --- | --- | --- |
| Sức khỏe dịch vụ | `GET /health`, `GET /health/ready` | Không cần token. Chỉ bật nút phân tích khi `capabilities.scan` là `true` |
| Hồ sơ | `GET /v1/me`, `PATCH /v1/me` | `display_name` (≤100 ký tự), `timezone` IANA, ví dụ `Asia/Ho_Chi_Minh` |
| Danh mục món | `GET /v1/foods?q=&limit=&cursor=`, `GET /v1/foods/{id}` | 75 món; dùng UUID làm định danh, không dùng class ID |
| Thông tin món | `GET /v1/foods/{id}/description` | `available` hoặc `description_unavailable`; xem [hướng dẫn riêng](food-description-api.md) |
| Nhận diện | `POST /v1/scans/analyze` | Multipart `file` (JPEG/PNG/WebP ≤10 MiB) + tùy chọn `input_source` = `camera`/`gallery`/`share` |
| Lịch sử scan | `GET /v1/scans?limit=&cursor=&from=&to=`, `GET /v1/scans/{id}` | Chỉ của chính user; chi tiết có link ảnh riêng tư hết hạn sau 300 giây |
| Sửa kết quả | `PATCH /v1/scans/{id}/result` | Body `{"confirmations":[{"detection_id","food_id"}]}`, header `If-Match: "<revision>"` lấy từ ETag |

## Cấu hình app

App chỉ cần ba giá trị public cho đúng môi trường test: URL backend, URL Supabase và public (anon/publishable) key. Ví dụ biến Expo: `EXPO_PUBLIC_API_BASE_URL`, `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_ANON_KEY` (tên chỉ là đề xuất). Không đưa service-role key, JWT secret, cursor secret hay file config backend vào app.

Người làm frontend tự chạy backend trên laptop của mình theo [hướng dẫn cài đặt](teammate-setup-guide.md) và test app trên điện thoại thật bằng **Expo Go**, với điện thoại và laptop dùng chung Wi-Fi. Script `run_dev_backend.ps1` in sẵn URL theo IP Wi-Fi của laptop. Chế độ này chưa được kiểm thử với điện thoại thật; tunnel và cloud chưa làm.

## Đăng nhập và token

Đăng ký, đăng nhập, refresh, đăng xuất dùng Supabase Auth SDK; backend không có endpoint đăng nhập riêng. Mọi request `/v1/*` gửi `Authorization: Bearer <user access token>`; public key không thay được user token. Khi 401: refresh session một lần rồi gọi lại, vẫn lỗi thì đăng nhập lại. Khi đăng xuất hoặc đổi tài khoản: hủy request đang chạy, xóa cache, cursor và link ảnh. Không đưa token vào query string hay log.

## Luồng màn hình chính

1. **Khởi động:** chưa có session → màn đăng nhập; có session → `GET /v1/me`, rồi `GET /health/ready`.
2. **Scan:** chụp hoặc chọn ảnh → xem trước → `POST /v1/scans/analyze`. Thời gian xử lý trên máy local khoảng vài trăm ms tới vài giây; đặt timeout dài (ví dụ 60–90 giây) và cho thử lại.
3. **Kết quả:** vẽ **mọi** khung `bbox` (tọa độ xyxy chuẩn hóa 0..1 trên ảnh đã chuẩn hóa hướng). Gộp theo `predicted_food_id`, mỗi món một thẻ. Gọi `GET /v1/foods/{id}/description` một lần cho mỗi món (có thể song song); response đã có tên món.
4. **Sửa món sai (tùy chọn):** chọn món đúng từ catalog → `PATCH /v1/scans/{id}/result` với `If-Match`. Kết quả dự đoán gốc vẫn được giữ; chỉ thêm xác nhận của user. 412 nghĩa là scan vừa đổi: tải lại rồi làm lại.
5. **Lịch sử:** `GET /v1/scans` (mới nhất trước, phân trang bằng `next_cursor`) → mở `GET /v1/scans/{id}` để xem lại ảnh, khung và thẻ thông tin.

Không hiển thị phần trăm confidence nếu không cần; không tự tạo gợi ý Top-3 (API chỉ trả `alternatives` khi model thật có). Không dùng `training_class_id` hay vị trí trong danh sách để suy ra món.

## Trạng thái cần xử lý trên UI

| Tình huống | Cách hiển thị |
| --- | --- |
| `capabilities.scan = false` hoặc 503 `MODEL_NOT_READY` | "Dịch vụ nhận diện tạm thời chưa sẵn sàng" |
| Ảnh sai định dạng/quá lớn (415/413/422) | Báo lỗi, cho chọn ảnh khác |
| Không có detection nào | Gợi ý chụp rõ hơn hoặc chọn món từ catalog |
| `description_unavailable` | "Chưa có phần giới thiệu đã được duyệt cho món này" |
| Mất mạng / timeout | Giữ ảnh xem trước, cho "Thử lại" |
| 404 ở scan | Scan không tồn tại hoặc thuộc tài khoản khác |

Danh sách mã lỗi đầy đủ: [error-codes-v1.md](error-codes-v1.md).

## Dữ liệu hiện có

- 75 món: 67 lớp VietFood gốc + 8 lớp bổ sung (Chuối, Táo, Gà nướng, Cá hồi nướng, Khoai lang, Khóm, Cà phê, Nước ngọt). 8 lớp mới có `original_class_id: null`.
- Model 75 chạy ở chế độ preview local do chủ dự án cho phép; chất lượng chưa được chứng nhận đầy đủ (lớp Khoai lang dưới ngưỡng).
- Thông tin món: 75/75 đã duyệt và hiển thị ([bảng độ phủ](../content/food-descriptions-coverage.md)). App vẫn phải xử lý `description_unavailable`, vì trạng thái này sẽ xuất hiện khi thêm món mới hoặc khi một bài bị gỡ.

## Kiểm thử phía backend

Danh sách kiểm thử đã chạy và kết quả nằm trong [review FOOD-02](../reviews/FOOD-02-implementation.md). Chưa kiểm thử với app mobile hay iPhone thật.
