# FOOD-02 — Gỡ dinh dưỡng, bữa ăn và thống kê

Trạng thái: DONE. Ngày 2026-10-20. Người thực hiện: Claude Code theo yêu cầu trực tiếp của chủ dự án; tự kiểm thử, không có review độc lập.

## Quyết định của chủ dự án

- "Loại bỏ hết phần dinh dưỡng; có thể xóa hết những thứ không cần thiết" (19/10), thay thế chỉ thị trước đó về giữ lại dữ liệu dinh dưỡng.
- Lựa chọn đã chốt: gỡ cả bữa ăn và thống kê; backup dữ liệu ra file rồi xóa; giữ file migration cũ và thêm migration xóa (không reset); xóa thêm tài liệu/task dinh dưỡng, file OpenAPI/export cũ và phần import CSV dinh dưỡng. Log/thư mục tạm giữ nguyên.

## Phạm vi đã sửa

- Database: `supabase/migrations/20261020000100_foodlens_remove_nutrition_meals.sql`, `20261020000200_foodlens_strip_nutrition_metadata.sql`; SQL test 001 viết lại, 004 bỏ phần bữa ăn, 003 xóa; script áp dụng `scripts/apply_remove_nutrition.py`.
- Backend: xóa `backend/app/meals.py`; thêm `profiles.py`; chuyển cursor/parse helper sang `cursor.py`/`errors.py`; gỡ model, route, OpenAPI header và mã lỗi của dinh dưỡng/bữa ăn/thống kê; API 0.7.0.
- Script/test: sửa test backend, scan, handoff, model; xóa `test_meals_local.py`, `test_supabase_local.py`, `test_import_local.py`, `tests/backend/test_meals.py`; validator và importer bỏ phần dinh dưỡng; test tương ứng viết lại.
- Tài liệu: xóa `docs/dataset/nutrition-source-inventory.md`, `docs/tasks/BE-02.md`, `docs/reviews/BE-02-implementation.md`, `docs/tasks/FE-01.md`, `docs/handoff/anti-fe01-prompt.md`, `docs/architecture/backend-v1-contract-review.md` và 4 file OpenAPI cũ; viết lại tài liệu bàn giao, API, schema, phân quyền, mã lỗi, cách chạy, import.

Không sửa: CSV nguồn, ảnh/nhãn, model/weights, cấu hình rollback, bằng chứng ML, README, SRS gốc, các review/task lịch sử khác.

## Tiêu chí nghiệm thu

1. Không còn bảng, hàm, endpoint, schema hay metadata dinh dưỡng/bữa ăn; dữ liệu đã backup trước khi xóa.
2. Món, profile, scan và nội dung mô tả không đổi; không reset database.
3. Contract và ví dụ sinh lại từ server thật; toàn bộ kiểm thử còn lại đạt.
4. Tài liệu bàn giao đủ để frontend làm việc mà không cần dataset, model hay secret.

Kết quả: [review FOOD-02](../reviews/FOOD-02-implementation.md).
