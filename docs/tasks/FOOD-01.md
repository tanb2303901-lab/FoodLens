# FOOD-01 — Thông tin giới thiệu món sau nhận diện

Trạng thái: DONE_BACKEND_CONTENT_DRAFTS (backend/schema/API/công cụ xong; nội dung chưa có người duyệt). Ngày 2026-10-19. Người thực hiện: Claude Code theo yêu cầu trực tiếp của chủ dự án; tự kiểm thử, không có review độc lập.

## Quyết định scope mới nhất của chủ dự án (2026-10-19)

- Dinh dưỡng không còn là đầu ra cần hoàn thành trong scope hiện tại. Không xóa dữ liệu, bảng, migration hay tài liệu dinh dưỡng; giữ an toàn để có thể quay lại.
- Sau khi nhận diện, ứng dụng cung cấp giới thiệu ngắn, nguồn gốc (nếu có căn cứ), nguyên liệu thường gặp ở mức khái quát và đặc điểm của món. Không công thức, không nguyên liệu chi tiết, không tư vấn sức khỏe.
- Nhận diện vẫn dùng kết quả thật của model và ID món canonical; mọi khung thật được giữ, mô tả gắn theo món canonical, một bản cho mỗi `food_id`.
- Chủ dự án phụ trách backend; đồng đội làm frontend riêng. Task này không triển khai React Native/Expo và không tự gửi tin hay bàn giao.

## Phạm vi đã sửa

- Database: migration mới `supabase/migrations/20261019000100_foodlens_food_descriptions.sql`, SQL test `supabase/tests/005_food_descriptions.sql`, script áp dụng `scripts/apply_food_content_schema.py`.
- Backend: `backend/app/models.py`, `backend/app/catalog.py`, `backend/app/main.py` (API 0.6.0, endpoint `GET /v1/foods/{id}/description`).
- Nội dung và công cụ: `docs/content/*`, `scripts/food_content.py`, `scripts/content_source_check.py`.
- Kiểm thử: `tests/backend/test_descriptions.py`, `tests/test_food_content.py`, cập nhật `tests/backend/test_contract.py`, `test_core.py`, `test_scans.py`; script thật `scripts/test_food_content_local.py`, `scripts/test_description_scan_flow_local.py`; cập nhật bộ đếm path ở `scripts/test_meals_local.py`, `scripts/test_scans_local.py` và case mới trong `scripts/test_handoff_local.py`.
- Contract và tài liệu: `docs/architecture/openapi-backend-v1.json`, `docs/handoff/api-examples-v1.json` (sinh lại từ HTTP thật), `docs/handoff/food-description-api.md`, `docs/handoff/food-description-shape-example.json`, các tài liệu trạng thái liên quan.

Không sửa: ảnh, labels, CSV nguồn, model bundle/weights, cấu hình rollback, evaluation, budget train, README, UI `scripts/local_scan_test.*`, dữ liệu dinh dưỡng, foods, scans, meals hay lịch sử người dùng.

## Đầu vào

Map75 `docs/dataset/food-identities-v2.json`; trang `vietnam.travel` của Viet Nam National Authority of Tourism; bài Wikipedia (CC BY-SA 4.0) ghim revision. Không dùng nutrition references hay candidate links làm nội dung mô tả.

## Tiêu chí nghiệm thu

1. Mô tả nối detection bằng `food_id` canonical; chỉ bản `published` hiện hành mới hiển thị với user (backend lọc + RLS).
2. Mỗi field có nội dung có nguồn hỗ trợ; nội dung đã duyệt bất biến theo hash; publish cần người duyệt và người phát hành có tên, không phải công cụ AI.
3. Thiếu nội dung trả `description_unavailable`, không tạo nội dung giả.
4. Migration chỉ bổ sung, không reset; fingerprint foods/nutrition/scans/meals không đổi.
5. Contract, ví dụ thật và hướng dẫn frontend được cập nhật; kiểm thử cũ vẫn đạt.

## Kết quả và phần còn thiếu

Xem [review FOOD-01](../reviews/FOOD-01-implementation.md). Đã duyệt và publish 49 món theo quyết định của chủ dự án (2 lượt). Còn thiếu: duyệt 25 bản nháp nguyên liệu/đồ uống; nội dung cho lớp Canh; cấu hình LAN/thiết bị và tích hợp frontend thật.
