# Prompt gửi Claude Code cho DATA-01

Bạn triển khai task DATA-01 trong C:\Nienluan\FoodLens. Codex là lead/reviewer; tôi là chủ dự án phụ trách backend. Chỉ làm task này và dừng sau khi bàn giao kết quả.

Đọc AGENTS.md, docs/requirements/leader-request.txt, SRS ở docs/requirements/SRS_FoodLens.docx, docs/dataset/data-contract.md, docs/dataset/source-baseline.json, docs/dataset/setup.md và toàn bộ docs/tasks/DATA-01.md. Các tài liệu này là đầu vào chung; không giả định có lịch sử chat Codex.

Mục tiêu: viết validator Python standard library cho 7 CSV, với validation sâu classes, nutrition references và candidate mapping; 4 CSV còn lại kiểm tra metadata/baseline và đối chiếu summary/audit liên quan. Không làm import Supabase, backend, training hay approval. Người dùng đã chốt backend data trước, chưa tạo project Supabase, ảnh gốc không phải điều kiện của task.

Nguồn CSV hiện tại là D:\Tonghop Dataset\Tonghop Dataset; cấu hình local ở data/processed/data-local.json. Dataset có 67 classes, 9115 references, 109 candidate links trong 67 mapping rows, zero approved dish profiles. Original class 27 là face bị loại; training class 27 là Củ kiệu, hợp lệ. Nguồn Việt chưa xác minh basis/energy units. Giữ NULL, raw values và quarantine/review flags; không sửa dữ liệu hay biến candidate thành approved.

Chỉ tạo/sửa files trong phạm vi DATA-01: scripts/validate_dataset.py và helpers cần thiết, tests/test_validate_dataset.py/fixtures nhỏ, docs/reviews/DATA-01-implementation.md, output report được chỉ định dưới data/processed/. Không sửa README, AGENTS.md, baseline, hợp đồng, nguồn CSV, migrations, backend, mobile hoặc ML. Không thêm dependencies, commit, push, deploy hoặc reset database.

Đã có .venv Python 3.12.14. Dùng PowerShell ở project root:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_validate_dataset.py' -v
& '.\.venv\Scripts\python.exe' '.\scripts\validate_dataset.py' --config '.\data\processed\data-local.json' --baseline '.\docs\dataset\source-baseline.json' --report '.\data\processed\DATA-01-validation.json'
```

Hai lệnh trên là lệnh nghiệm thu sau khi bạn triển khai, hiện chưa có scripts/tests tương ứng. Tuân thủ CLI, schema report, source-output protection và tiêu chí nghiệm thu chi tiết trong DATA-01.md. Các manifest lớn phải đọc streaming. Baseline/checksum drift là finding cần báo, không được tự cập nhật baseline để làm test pass.

Chạy tests, CLI trên dữ liệu thật và đối chiếu SHA-256 nguồn trước/sau. Ghi files changed, commands thực tế cùng exit codes, kết quả, review findings, report path và phần còn thiếu vào docs/reviews/DATA-01-implementation.md. Nếu thiếu điều kiện, báo rõ thay vì giả kết quả. Ghi trạng thái IMPLEMENTED_PENDING_REVIEW, rồi trả kết quả để tôi chuyển cho Codex review. Không tự chuyển task tiếp theo.
