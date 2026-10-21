# Bối cảnh dự án FoodLens

Ngày ghi nhận: 2026-10-14, múi giờ Asia/Bangkok.

FoodLens nhận diện các vùng thực phẩm, để người dùng xác nhận món và grams, rồi tra profile dinh dưỡng đã duyệt. Khi thiếu profile, vẫn lưu bữa ăn và giữ nutrient NULL. MVP có 67 lớp VietFood. Model, 13 lớp mở rộng và serving chưa được xác minh không được coi là đã hoàn thành.

## Yêu cầu được lưu

- `SRS_FoodLens.docx`: bản sao nguyên trạng của SRS người dùng cung cấp, phiên bản 2026-10-12.
- `leader-request.txt`: bản sao nguyên trạng yêu cầu vai trò, quy trình giao việc và giới hạn hành động.
- `../dataset/source-baseline.json`: header, số dòng, kích thước và SHA-256 của gói nguồn đã đọc ngày 2026-10-14.

## Quyết định mới nhất của chủ dự án

- Đã cho phép bắt đầu, nhưng làm từng bước; bước đầu là dữ liệu cho backend.
- Chưa tạo project Supabase.
- Ban đầu chủ dự án báo máy chỉ có 7 CSV; sau đó cung cấp root `E:\DataNLCN\VietFood\dataset`. Đã xác nhận root truy cập được và có images/labels. Chưa kiểm tra nội dung ảnh hoặc nhãn thật; báo cáo local ghi riêng mức kiểm tra này.
- Codex làm lead; task triển khai được soạn để chủ dự án chuyển sang Claude Code.
- Quyết định mới hơn cùng ngày: do chưa có Claude Code, chủ dự án yêu cầu Codex trực tiếp triển khai DATA-01. Codex đã thực hiện, chạy 44 tests và tự review; kết quả tại docs/reviews/DATA-01-implementation.md.
- Chủ dự án tiếp tục cho phép Codex thực hiện DB-01 và chọn Supabase local với Docker/WSL2 cho bước chạy database. DB-01 đã hoàn thành thiết kế; DB-02 cần local engine hoạt động.

## Hiện trạng và bước tiếp theo

Thư mục ban đầu chỉ có scaffold, README và .gitignore; chưa có .git, AGENTS.md, migration, backend, mobile hoặc weights. AGENTS.md hiện tại là hướng dẫn mới được tạo từ yêu cầu đã nhận, không phải file bàn giao cũ.

DATA-00 đã hoàn thành hồ sơ yêu cầu, baseline và môi trường kiểm tra local. DATA-01 đã hoàn thành validator chạy lại được cho gói CSV, chưa import Supabase và chưa duyệt dinh dưỡng. DB-01 đã chốt thiết kế schema/access/API và UUID map; chưa áp dụng migration. Bước tiếp theo là DB-02 trên Supabase local, sau đó DATA-02 importer rồi BE-01. Setup hướng dẫn trong docs/dataset/supabase-local-setup.md.

## Cập nhật scope 2026-10-19

Chủ dự án quyết định: dinh dưỡng không còn là đầu ra cần hoàn thành trong scope hiện tại; dữ liệu, bảng, migration và tài liệu dinh dưỡng được giữ nguyên để có thể quay lại. Sau khi nhận diện, ứng dụng cung cấp phần giới thiệu ngắn, nguồn gốc nếu có căn cứ, nguyên liệu thường gặp ở mức khái quát và đặc điểm của món, theo `food_id` canonical; không công thức, không tư vấn sức khỏe. Chênh lệch với SRS ở phần hiển thị và tính dinh dưỡng (FR-05, FR-14 và các quy tắc dinh dưỡng liên quan) là quyết định mới hơn của chủ dự án; luồng ghi bữa ăn theo grams vẫn còn trong backend; SRS gốc không bị sửa. Chủ dự án làm backend, đồng đội làm frontend riêng. Kết quả: [FOOD-01](../reviews/FOOD-01-implementation.md).


## Cập nhật scope 2026-10-20

Chủ dự án quyết định gỡ hẳn phần dinh dưỡng, bữa ăn thủ công và thống kê, đồng thời xóa các tài liệu/script không còn cần thiết (FOOD-02). Dữ liệu dinh dưỡng trong database đã được backup ngoài repo rồi xóa bằng migration mới; CSV nguồn và SRS gốc không bị sửa. Sản phẩm hiện gồm: đăng nhập, hồ sơ, danh mục 75 món, nhận diện ảnh, lịch sử scan và thông tin giới thiệu món. Kết quả: [FOOD-02](../reviews/FOOD-02-implementation.md).
