# DATA-00 Kết quả tiếp nhận và thiết lập dữ liệu

Ngày thực hiện: 2026-10-14, Asia/Bangkok. Reviewer: Codex. Trạng thái: DONE cho hồ sơ và thiết lập; DATA-01 vẫn READY, chưa triển khai.

## Công việc đã thực hiện

- Lưu nguyên trạng SRS và yêu cầu điều phối vào docs/requirements; SHA-256 bản sao khớp nguồn.
- Tạo AGENTS.md từ yêu cầu chủ dự án, ghi rõ không phải file bàn giao cũ được phục hồi.
- Lưu source-baseline.json với header, SHA-256, kích thước và row count của cả 7 CSV. Không copy CSV vào project hoặc sửa file nguồn.
- Ghi hợp đồng dữ liệu backend, cấu hình local/template, hướng dẫn môi trường và task/prompt DATA-01 cho Claude Code.
- Tạo .venv Python 3.12.14 từ runtime Codex; smoke check import csv/json/hashlib/unittest và interpreter chạy được.
- Chủ dự án xác nhận dữ liệu backend trước, chưa có project Supabase. Root VietFood mới cung cấp truy cập được và có images/labels; chưa kiểm tra nội dung ảnh.

## Kết quả kiểm tra thực tế

| Kiểm tra | Kết quả |
| --- | --- |
| 7 CSV: header, bytes, data row count, SHA-256 | Đã đọc/tính và lưu baseline |
| So SHA-256 cả 7 CSV sau chuẩn bị hồ sơ | Khớp baseline |
| Classes: 67 IDs liên tục, remap original/training | Đạt; training 27 vẫn là thực phẩm |
| Nutrition references: source counts và unique record_id | Đạt: 853 Việt, 469 Foundation, 7793 SR Legacy |
| Candidate arrays/count/details và reference IDs | Không thấy bất nhất trong kiểm tra đã chạy |
| Candidate links duy nhất | 109 links cho 40 lớp; 27 lớp không có candidate |
| Selected/approved mappings | 0 selected, 0 approved |
| Nguồn Việt chưa xác minh basis | Giữ trống per_100g và calculation=false đúng baseline |
| Python .venv | Python 3.12.14, chạy được modules standard library |
| Root E:\DataNLCN\VietFood\dataset | Truy cập được, thấy images và labels; chưa decode/hash ảnh |

Các kiểm tra chạy bằng Python snippets chỉ đọc ở giai đoạn tiếp nhận, chưa phải validator CLI đã được triển khai. Report local: data/processed/DATA-00-receipt.json. Dữ liệu nguồn không đổi.

Lệnh metadata/checksum và kiểm tra sau chuẩn bị hồ sơ kết thúc exit 0. Lệnh uv venv ban đầu lỗi vì cache nằm ngoài vùng ghi được; đã đổi cache sang data/processed/.uv-cache và tạo .venv thành công, exit 0. Không cần nâng quyền hoặc thay thiết lập hệ thống.

Trong lượt đọc trước, đã đối chiếu đầy đủ image_id/annotation_id, remap, bbox bounds, số bbox mỗi ảnh và class coverage giữa manifests: 170931 ảnh giữ lại, 838716 food bbox, train/valid/test/review có 67/35/29/67 lớp. Đây là kiểm tra CSV đã chạy khi tiếp nhận, không thay thế việc xác minh lại ảnh gốc hoặc kiểm thử validator DATA-01.

## Chưa thực hiện

- Chưa gửi task/chạy Claude Code; chưa có scripts/validate_dataset.py hoặc bộ unit tests DATA-01.
- Chưa tạo project Supabase, migration/import, kiểm thử DB/RLS/Auth/Storage hoặc backend.
- Chưa duyệt nutrition, tạo serving, decode/hash ảnh, kiểm tra ngữ nghĩa nhãn hoặc training/inference model.
- Chưa init Git, commit, push, deploy hoặc sửa README.

## Bước kế tiếp

Chủ dự án gửi docs/tasks/DATA-01-claude-prompt.md cho Claude Code tại project root. Sau khi có implementation report, tests và report chạy gói thật, Codex đọc code/diff và kiểm tra trước khi nghiệm thu. Chỉ sau đó chuẩn bị task DB-01 chi tiết.
