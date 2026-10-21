# FOOD-02 — Kết quả gỡ dinh dưỡng, bữa ăn và thống kê

Ngày 2026-10-20. Claude Code thực hiện và tự kiểm thử theo quyết định của chủ dự án; không có review độc lập.

## Backup trước khi xóa (ignored `data/processed/FOOD-02-backup/`)

| File | Nội dung | SHA-256 |
| --- | --- | --- |
| `nutrition-meals-tables.sql` | Schema + dữ liệu 7 bảng: 9.115 references, 109 candidate links, 0 profile, 0 portion, 0 meal, 0 item, 0 receipt | `bbf506ed…02b0` |
| `schema-before.sql` | Toàn bộ schema `public` và `foodlens_private` trước khi xóa | `7cf4288d…9e98` |
| `foods-metadata-before.json` | `source_mapping_metadata` gốc của 75 món | `2dae329f…143b` |

Script áp dụng đối chiếu số dòng backup với bảng thật trước khi cho phép xóa.

## Thay đổi database

- `20261020000100`: xóa 7 RPC public bữa ăn/thống kê, các hàm private liên quan, 7 bảng; viết lại `lock_owner()` (chỉ còn profile) và `core_readiness()` (đọc foods, scans, food_descriptions). Preflight 26 pgTAP checks trong transaction rollback; áp có ghi journal; fingerprint của foods (75), profiles (1), scans (59), descriptions (74), sources (85), links (178) không đổi.
- `20261020000200`: gỡ 13 khóa dinh dưỡng khỏi `foods.source_mapping_metadata`; còn lại slug, scope, tên, class ID, alias, namespace, checksum class map. Danh tính món (ID, slug, tên, class ID, map version, namespace/source class ID) được đối chiếu không đổi; các bảng khác không đổi.
- Migration cũ giữ nguyên làm lịch sử; tổng 15 migrations. Không reset.

## Thay đổi backend (API 0.7.0)

- Còn 10 paths / 11 operations: `/health`, `/health/ready`, `/v1/me` (GET/PATCH), `/v1/foods`, `/v1/foods/{id}`, `/v1/foods/{id}/description`, `/v1/scans/analyze`, `/v1/scans`, `/v1/scans/{id}`, `/v1/scans/{id}/result`.
- Đã gỡ: `/v1/foods/{id}/nutrition`, `/v1/meals*`, `/v1/stats/*`, field `Food.nutrition_status`, capability `manual_meals`, header `Idempotency-Key`, các schema dinh dưỡng/bữa ăn và mã lỗi liên quan.
- `meals.py` xóa; profile chuyển sang `profiles.py`; cursor theo thời gian (`TimeCursor`) giữ nguyên scope `scans:created_at,id:desc` nên cursor lịch sử scan cũ vẫn hợp lệ.
- Backend 8000 khởi động lại cùng `backend-ml75.json` (model75 owner-preview): database/model ready, scan=true. Trang 8765 vẫn sẵn sàng.

## Validator và importer

- Validator chỉ kiểm tra 5 CSV trong scope; hai CSV dinh dưỡng vẫn có trong gói nguồn và baseline nhưng không đọc. Chạy thật trên gói CSV ở ổ D: 0 lỗi, 2 review findings (giữ nguyên từ trước).
- Importer chỉ nhập 67 món với metadata định danh; thêm chế độ `--check-database` (chạy trong transaction rollback). Chạy thật trên DB: không xung đột, khớp chính xác dữ liệu hiện có.

## Kiểm thử đã chạy lượt này

| Kiểm tra | Kết quả |
| --- | --- |
| pytest toàn bộ | 265 tests + 23 subtests đạt |
| SQL `supabase test db` 001 / 002 / 004 / 005 | 26 / 5 / 16 / 33 đạt |
| `test_backend_local.py --class-count 75` | 54 checks đạt |
| `test_scans_local.py` | 48 checks đạt |
| `test_handoff_local.py --write-artifacts` rồi chạy lại | 15 ví dụ HTTP thật, 11 operations khớp contract |
| `test_food_content_local.py` | 389 checks đạt (49 món available, 26 unavailable) |
| `test_description_scan_flow_local.py` trên backend live | Model75 trả 5 khung Phô mai → 1 lần gọi description; ảnh và tài khoản tạm đã xóa |

Không chạy lại: `scripts/test_model_local.py` (đã bỏ bước bữa ăn, thay bằng kiểm tra description) vì script này ghi đè bằng chứng nghiệm thu ML-05 (`ML-05-model-integration.json`) mà quy định dự án yêu cầu giữ nguyên; `ml/finish_extension.py` chỉ có chữ lịch sử, không sửa. Số lượng test thấp hơn trước là do đã xóa các test bữa ăn/dinh dưỡng.

## Còn mở (không thuộc FOOD-02)

- iPhone chưa truy cập được backend/Supabase (chỉ loopback); cần chủ dự án chọn LAN, tunnel hay cloud.
- 25 bản mô tả nháp chờ duyệt; lớp Canh chưa có nội dung.
- Chất lượng model75 chưa được chứng nhận đầy đủ (Khoai lang dưới ngưỡng).
- Các review/task lịch sử (DB-01, BE-01..04, DATA, ML) vẫn nhắc dinh dưỡng/bữa ăn vì là hồ sơ quá khứ; một số link trong đó trỏ tới file đã xóa theo yêu cầu.
