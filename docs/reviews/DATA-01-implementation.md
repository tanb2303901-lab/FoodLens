# DATA-01 Kết quả triển khai và kiểm tra

Ngày: 2026-10-14. Trạng thái: DONE trong phạm vi backend CSV.

Chủ dự án đã yêu cầu Codex trực tiếp triển khai do chưa có Claude Code. Codex viết code, chạy tests và tự review; đây không phải một lượt review độc lập của công cụ/người khác. Không có task nào được gửi hoặc chạy bằng Claude Code.

## Thay đổi

- `scripts/validate_dataset.py`: CLI standard library đọc 7 CSV, kiểm tra header/bytes/row count/SHA-256; validate sâu classes, references, candidate mapping; đối chiếu summary và tổng hợp audit.
- `tests/test_validate_dataset.py`: 44 tests với fixtures nhỏ tạo trong vùng ignored `data/processed/.data01-tests/` và dọn sau khi chạy.
- Cập nhật task/status, bối cảnh yêu cầu và hướng dẫn setup để ghi nhận Codex trực tiếp thực hiện DATA-01 và validator đã có thể chạy.
- Reports local: `data/processed/DATA-01-validation.json`, `data/processed/DATA-01-verification.json`.

Các manifest lớn được đọc streaming; chỉ 3 bảng backend và 2 bảng summary/audit nhỏ được giữ trong bộ nhớ. Report giới hạn samples nhưng giữ tổng số findings đầy đủ. JSON report được ghi qua temporary file rồi atomic replace, bảo toàn báo cáo cũ nếu ghi thất bại.

## Lệnh đã chạy và kết quả cuối

Chạy từ project root bằng PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_validate_dataset.py' -v
& '.\.venv\Scripts\python.exe' '.\scripts\validate_dataset.py' --config '.\data\processed\data-local.json' --baseline '.\docs\dataset\source-baseline.json' --report '.\data\processed\DATA-01-validation.json'
```

| Kiểm tra | Kết quả |
| --- | --- |
| Unit/CLI tests | 44/44 passed, exit 0 |
| CLI trên 7 CSV thật | passed_with_review, 0 structural errors, exit 0 |
| Chạy lại gói thật | Counts, checks, file metadata và findings giống nhau; chỉ timestamp khác |
| SHA-256 nguồn sau chạy | Cả 7 CSV vẫn khớp baseline |
| Baseline/config/README/.gitignore/AGENTS/data-contract qua lượt xác minh | Không đổi |
| Bảo vệ source-output | Chặn cùng path, resolved path, vị trí bên trong csv_root và filesystem identity alias; config/baseline cũng được bảo vệ |
| Thiếu ảnh/weights/Supabase | Không cần cho task này; không được báo là đã kiểm thử |

Exit 0 nghĩa cấu trúc baseline hợp lệ; exit 1 cho lỗi dữ liệu/baseline hoặc ghi report; exit 2 cho CLI/config/path không hợp lệ. Lỗi config không ghi report khi chưa xác minh được đường dẫn ghi an toàn.

## Counts và findings

| Chỉ số | Giá trị |
| --- | ---: |
| Foods / mapping rows | 67 / 67 |
| References | 9115 |
| Việt / Foundation / SR Legacy | 853 / 469 / 7793 |
| USDA reference-ready | 8160 |
| Candidate links duy nhất | 109 |
| Lớp có / chưa có candidates | 40 / 27 |
| Selected / approved mappings | 0 / 0 |
| Candidate dùng source_id khi source_code trống | 24 |

1024 review findings của validator gồm 955 references cần review, 67 mapping chưa approved, một ghi nhận audit nguồn và một ghi nhận độ phủ holdout. Đây không phải 1024 lỗi mới hoặc 1024 dòng trong dataset_issues.csv. File audit nguồn có 4134 dòng được tổng hợp riêng theo domain/severity/code.

## Quy ước được đối chiếu và sửa trong implementation

Lần chạy đầu báo 24 candidate_details_mismatch. Đối chiếu từng trường xác nhận cả 24 thuộc USDA: `candidate_source_codes` dùng source_id khi source_code trống, trong khi `candidate_details.source_code` vẫn giữ chuỗi trống nguyên trạng. Validator nay kiểm tra chính xác `source_code or source_id` cho mảng code, đồng thời giữ kiểm tra source_code gốc trong details. Test riêng bao phủ fallback USDA và source code Việt có số 0 đầu. Không thay CSV, checksum baseline hoặc hợp đồng để làm validation pass.

Các lỗi test môi trường ban đầu do thư mục temp sandbox không ghi được đã được xử lý bằng fixture directory trong workspace. Sandbox không cho tạo hard link vật lý; test alias dùng mô phỏng `Path.samefile` để kiểm tra nhánh filesystem identity, còn path/resolved-path protection được chạy trực tiếp. Chưa kiểm chứng thao tác tạo hard link vật lý trên máy này; không có test bị skip trong bộ 44 tests cuối.

## Phạm vi tự review

Đã đọc lại các nhánh parser, semantic checks, ownership của output path, error exit codes và report IO. Tests bao phủ false/NULL/0, JSON và CSV lỗi, finite numeric, remap face/training 27, duplicate/FK, candidate arrays/details, source units/basis/energy selection, quarantine khác unsafe calculation, summary lệch, checksum drift, import không side effect và report failure.

Chưa import hoặc kiểm thử database/RLS/Auth/Storage, chưa decode/hash ảnh, kiểm tra đầy đủ vision joins/bbox/leakage trong validator này, training/inference hoặc endpoint backend. Chưa duyệt dinh dưỡng/serving. Snapshot hiện tại vẫn chưa có profile món approved để tính khẩu phần.

## Bước tiếp theo

DATA-01 đủ điều kiện chuyển sang DB-01: thiết kế schema/constraints, ownership/RLS và hợp đồng API. Chưa thực hiện DB-01 hoặc tạo project Supabase trong lượt này.
