# Schema FoodLens v1

Cập nhật 2026-10-20 (FOOD-02). Schema hiện hành là kết quả của 15 migrations trong `supabase/migrations`, áp trên Supabase local, không reset. Hai migration `20261020000100` và `20261020000200` đã gỡ toàn bộ bảng, hàm và metadata dinh dưỡng/bữa ăn; các migration cũ được giữ làm lịch sử. Backup dữ liệu đã gỡ nằm ngoài repo trong `data/processed/FOOD-02-backup/`.

## Định danh

- Món dùng UUIDv5: `uuid5(NAMESPACE_URL, 'urn:foodlens:food:' + slug)`. Slug, UUID, class ID và class map version bất biến (trigger `food_identity`).
- 67 món VietFood: `class_map_version = vietfood-67-2026-10-12-v1`, original ID 0..67 trừ 27 (face), training ID 0..66 (training 27 là thực phẩm hợp lệ).
- 8 món mở rộng: `foodlens-75-2026-10-16-v2`, training ID 67..74, `original_class_id` NULL, metadata `source_namespace` + `source_class_id`.
- Danh sách chuẩn: [food-identities-v1.json](../dataset/food-identities-v1.json) và [food-identities-v2.json](../dataset/food-identities-v2.json).

## Bảng

| Bảng | Nội dung |
| --- | --- |
| `auth.users` | Do Supabase Auth quản lý; app không lưu mật khẩu |
| `public.profiles` | `id` → auth.users, `display_name` ≤100, `timezone` IANA; tạo tự động khi có user |
| `public.foods` | 75 món; `source_mapping_metadata` chỉ còn khóa định danh/provenance, không đọc được từ phía user |
| `public.scans` | Một lần phân tích: owner, `image_path` riêng tư `user_id/scan_id/...`, trạng thái, model/class map version, `detections` (bất biến khi completed), `confirmations`, `revision` |
| `public.food_descriptions` | Giới thiệu món theo version và trạng thái draft/reviewed/published/retired; nội dung bất biến sau khi duyệt |
| `public.content_sources`, `public.food_description_sources` | Nguồn tham khảo và field mà từng nguồn hỗ trợ |
| `foodlens_private.import_runs` | Provenance lần import catalog |
| `storage.objects` (bucket `food-scans`) | Ảnh scan riêng tư, chỉ chủ sở hữu đọc qua link ký |

Đã gỡ (FOOD-02): `nutrition_references`, `food_nutrition_links`, `food_nutrition`, `food_portions`, `meals`, `meal_items`, `foodlens_private.mutation_receipts` cùng các RPC bữa ăn/thống kê.

## Ràng buộc chính

- Timestamp dùng `timestamptz`; `updated_at`/`revision` do database quản lý.
- `detections` được kiểm tra trong trigger `guard_scan`: UUID món tồn tại, class ID khớp map, bbox 0..1 hợp lệ, confidence 0..1, tối đa 100 detection, `alternatives` ≤3 và chỉ khi model trả thật.
- Nội dung mô tả: tạo mới phải là draft, chỉ chuyển tiến, mỗi field có nội dung phải có nguồn trước khi duyệt; một bản published hiện hành cho mỗi món.
