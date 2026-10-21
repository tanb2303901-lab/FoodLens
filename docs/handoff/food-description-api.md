# Hướng dẫn frontend: thông tin món sau khi nhận diện — FOOD-01

Ngày 2026-10-19, cập nhật 2026-10-20. Tài liệu chuẩn bị để chủ dự án chuyển cho người làm frontend; chưa được gửi hay bàn giao. Backend API 0.7.0, contract chính [openapi-backend-v1.json](../architecture/openapi-backend-v1.json) (10 paths/11 operations). Tổng quan toàn bộ API: [backend-v1.md](backend-v1.md). Frontend không cần train model, tải dataset hay giữ bất kỳ secret nào.

## Cấu hình

App chỉ cần ba giá trị public do chủ dự án cung cấp cho đúng môi trường test, ví dụ trong `.env` của Expo:

```bash
EXPO_PUBLIC_API_BASE_URL=http://<địa-chỉ-backend-mà-iPhone-truy-cập-được>:8000
EXPO_PUBLIC_SUPABASE_URL=http://<địa-chỉ-Supabase-Auth>:54321
EXPO_PUBLIC_SUPABASE_ANON_KEY=<publishable/anon key>
```

Tên biến chỉ là đề xuất. `127.0.0.1` là loopback của máy backend, iPhone không gọi được; hiện backend và Supabase local chỉ lắng nghe trên loopback, việc mở LAN/tunnel chưa được cấu hình hay kiểm thử và cần chủ dự án quyết định. Không đưa service-role key, JWT secret, cursor secret hay file config backend vào app.

## Xác thực

Đăng ký/đăng nhập/refresh bằng Supabase Auth SDK. Mọi request `/v1/*` gửi `Authorization: Bearer <user access token>`. Publishable/anon key không thay được user token (backend trả 401). Khi 401: refresh session một lần rồi gọi lại; vẫn lỗi thì đăng nhập lại.

## Luồng sau khi chụp/chọn ảnh

1. `GET /health/ready`: chỉ cho bấm Phân tích khi `capabilities.scan === true`.
2. `POST /v1/scans/analyze` (multipart `file`, tùy chọn `input_source` = `camera|gallery|share`). Response có `detections[]`, mỗi phần tử có `detection_id`, `predicted_food_id`, `bbox` (xyxy chuẩn hóa 0..1) và `confidence`.
3. Vẽ **mọi** bbox thật, không lọc hay gộp khung.
4. Gộp danh sách món theo `predicted_food_id`: một món xuất hiện ở nhiều khung chỉ cần một thẻ thông tin. Món khác nhau vẫn là thẻ riêng.
5. Với mỗi `food_id` duy nhất gọi `GET /v1/foods/{food_id}/description` (có thể gọi song song). Response đã có `name_vi`, `name_en`, `slug`, `scope_kind`, nên không cần gọi thêm `/v1/foods/{id}` chỉ để lấy tên.
6. Không dùng `training_class_id` làm ID món và không tự map class ID sang tên; luôn dùng UUID.

```ts
const ids = [...new Set(scan.detections.map(d => d.predicted_food_id))];
const cards = await Promise.all(ids.map(id => api.get(`/v1/foods/${id}/description`)));
```

Smoke thật trên backend live (model75): một ảnh phô mai trả 5 khung cùng một `predicted_food_id` → 1 lần gọi description → `description_unavailable`. Bằng chứng: ignored `data/processed/FOOD-01-scan-flow.json`.

## Endpoint `GET /v1/foods/{id}/description`

Không có query parameter; query lạ hoặc lặp trả 422. Luôn trả 200 nếu món tồn tại và active, kể cả khi chưa có nội dung.

| Field | Ý nghĩa |
| --- | --- |
| `food_id`, `slug`, `name_vi`, `name_en`, `scope_kind` | Định danh canonical và tên hiển thị |
| `status` | `available` hoặc `description_unavailable` |
| `reason` | `not_published` khi unavailable; `null` khi available |
| `description` | `null` khi unavailable; khi available gồm `short_intro`, `origin_text` (có thể `null`), `ingredients_summary`, `characteristics`, `scope_note` (có thể `null`), `version`, `reviewed_at`, `published_at`, `updated_at`, `authoring_method`, `sources[]` |
| `sources[]` | `title`, `publisher`, `url`, `language`, `source_kind`, `revision_ref`, `accessed_on`, `license_note`, `supports` (field mà nguồn hỗ trợ), `locator` |
| `notice` | Câu lưu ý cố định; nên hiển thị dưới thẻ thông tin |

Ví dụ thật cho món chưa duyệt (case `food_description_unavailable` trong [api-examples-v1.json](api-examples-v1.json), món Cơm):

```json
{
  "food_id": "89cde1f5-b817-541d-b122-a6084f566261",
  "slug": "com",
  "name_vi": "Cơm",
  "name_en": "Rice",
  "scope_kind": "ingredient_or_component",
  "status": "description_unavailable",
  "reason": "not_published",
  "description": null,
  "notice": "Thông tin giới thiệu phổ thông về món ăn; không phải tư vấn sức khỏe, dinh dưỡng hay y tế."
}
```

Ví dụ thật cho món đã duyệt: case `food_description_available` (Phở) trong cùng file, có đủ `description` và `sources[]`.

Ngoài ra [food-description-shape-example.json](food-description-shape-example.json) minh họa cấu trúc bằng chuỗi giữ chỗ, được test kiểm tra khớp schema OpenAPI.

## Hiển thị đề xuất

- `available`: hiện các đoạn có nội dung; ẩn mục có giá trị `null` (không ghi "không rõ" thay cho nguồn gốc). Có `scope_note` thì hiện dạng ghi chú nhỏ, ví dụ với Cà phê/Nước ngọt/Gà nướng. Hiện danh sách nguồn (tên + nhà xuất bản, mở `url`) và `notice`.
- `description_unavailable`: hiện tên món và câu như "Chưa có phần giới thiệu đã được duyệt cho món này". Không tự sinh nội dung, không gọi AI, không lấy text từ nơi khác.
- Không hiển thị calories/macro hoặc lời khuyên sức khỏe: dinh dưỡng đã bị gỡ khỏi backend (không còn endpoint `/nutrition`).
- Có thể cache theo `food_id` trong phiên, nhưng không cache vĩnh viễn: nội dung có thể chuyển từ unavailable sang available sau khi được duyệt, hoặc có version mới. Xóa cache khi đăng xuất.

## Lỗi có thể gặp

| HTTP / code | Khi nào | Xử lý |
| --- | --- | --- |
| 401 `UNAUTHENTICATED` | Thiếu/sai/hết hạn user token, hoặc gửi anon key | Refresh một lần, rồi đăng nhập lại |
| 404 `NOT_FOUND` | UUID không thuộc catalog hoặc món inactive | Hiện "không tìm thấy món"; không suy từ class ID |
| 422 `INVALID_INPUT` | `id` không phải UUID, có query lạ/lặp | Sửa request |
| 503 `DEPENDENCY_UNAVAILABLE` | Database không truy cập được hoặc dữ liệu nội dung không nhất quán (backend từ chối trả nội dung thiếu nguồn) | Cho phép thử lại; vẫn hiện kết quả nhận diện |
| 500 `INTERNAL_ERROR` | Lỗi bất ngờ đã được làm sạch | Thử lại; báo `request_id` |

Mọi lỗi có body `{"error":{"code","message","details","request_id"}}` và header `X-Request-ID`. Xem thêm [mã lỗi](error-codes-v1.md).

## Trạng thái dữ liệu

Ngày 2026-10-19 chủ dự án Lý Thanh Tân duyệt và publish đủ **75/75 món** qua ba lượt (xem [bảng độ phủ](../content/food-descriptions-coverage.md)); hiện mọi món đều trả `available`. Frontend vẫn phải xử lý `description_unavailable`, vì trạng thái này sẽ xuất hiện khi có món mới hoặc khi một bài bị gỡ. Ví dụ `food_description_unavailable` trong [api-examples-v1.json](api-examples-v1.json) được ghi lại khi Cơm còn là bản nháp, chỉ dùng để minh họa hình dạng response.
