# DATA-01 Kiểm tra CSV đầu vào cho backend

Trạng thái: DONE (2026-10-14). Theo yêu cầu mới nhất của chủ dự án, Codex trực tiếp triển khai và tự review; không sử dụng Claude Code. 44 tests passed, CLI gói thật exit 0 với review findings. Kết quả chi tiết: `../reviews/DATA-01-implementation.md`.

## Mục tiêu và phụ thuộc

Tạo validator chạy lại được cho 7 CSV, tập trung nội dung 3 CSV sẽ import catalog/nutrition. Báo cáo phải phân biệt cấu trúc hợp lệ, defects nguồn cần review và phần không kiểm tra. Không truy cập Supabase, ảnh gốc hoặc model.

Phụ thuộc: DATA-00 đã chuẩn bị yêu cầu, hợp đồng dữ liệu, checksum baseline, config local và Python .venv. Không phụ thuộc Supabase credentials hoặc việc chuyển ảnh VietFood.

## Đầu vào

- AGENTS.md và docs/requirements/leader-request.txt.
- docs/requirements/SRS_FoodLens.docx, đặc biệt mục 9, 10, 13.
- docs/dataset/data-contract.md, source-baseline.json và setup.md.
- data/processed/data-local.json (máy khác tự tạo từ template).
- 7 file CSV trong csv_root, chỉ đọc.

## File được tạo hoặc sửa

- scripts/validate_dataset.py; có thể thêm helper dưới scripts nếu việc tách giúp kiểm thử, phải liệt kê trong báo cáo.
- tests/test_validate_dataset.py; fixture nhỏ dưới tests/fixtures/data01 nếu cần.
- docs/reviews/DATA-01-implementation.md.
- Report runtime dưới data/processed/ do CLI --report chỉ định.

Không sửa baseline, hợp đồng, AGENTS.md, README, nguồn CSV, cấu hình của máy khác, backend, mobile, migrations hoặc ML. Nếu phát hiện hợp đồng mâu thuẫn, ghi finding và chờ Codex review, không tự đổi số liệu nghiệm thu.

## Giao diện CLI

```text
python scripts/validate_dataset.py --config <local-config.json> --baseline <source-baseline.json> --report <output.json>
```

Optional `--csv-root` ghi đè csv_root cho lần chạy, không sửa config. Config có config_version=1, csv_root là thư mục tồn tại; vision_root optional và không dùng kiểm tra ảnh trong task này. Relative paths trong config được resolve theo thư mục config; paths trên CLI theo working directory.

Exit 0 khi kiểm tra cấu trúc đạt, kể cả có review findings hợp lệ. Exit 1 khi có lỗi dữ liệu/baseline. Exit 2 cho CLI/config invalid. Ghi report khi có thể ngay cả khi kiểm tra fail, nhưng không nuốt lỗi IO hoặc báo thành công khi không ghi được report.

## Yêu cầu triển khai

1. Dùng Python standard library, không thêm dependencies hoặc yêu cầu pip install. Có main guard để import module không chạy CLI.
2. Parse CSV với utf-8-sig/newline phù hợp; bắt malformed quoting, số ô dư/thiếu, header thiếu/trùng. So với header baseline; báo header drift rõ ràng.
3. Với cả 7 CSV, tính SHA-256 theo chunk, byte length, số record dữ liệu qua CSV parser. So baseline chính xác. Các file lớn phải đọc streaming, không load hai manifest lớn thành list/DataFrame.
4. Validate sâu classes, references và mapping theo data-contract: bool/NULL/type, uniqueness, remap và identity consistency, candidate JSON arrays/count/parallel correspondence, references tồn tại, 109 links không duplicate, 40/27 coverage và zero selected/approved baseline.
5. Validate references theo source/basis/quality flags và giá trị thực tế. Giữ rõ reference_portion_flag khác dish approval. Numeric phải hữu hạn nếu có; raw numeric âm đã quarantine đúng là review finding, không sửa/loại dòng hay làm fail cả gói. Unsafe usable record mới là structural error.
6. Đối chiếu summary cho counts classes/references/candidates/approval và phân bố nguồn; tổng hợp audit severity/code, không quy mọi dòng audit thành failure. Không suy 873 background chỉ từ record_status vì review_holdout có thể cũng là background.
7. Report JSON có report_version, thời điểm có timezone, scope=backend_csv, baseline version, overall_status, counts, file metadata, checks/errors/review_findings và not_checked. Mỗi lỗi có code, file, row/field khi xác định được và message. Giới hạn samples nhưng giữ tổng số lỗi đầy đủ; không dump raw hàng trăm nghìn dòng.
8. Không chấp nhận file report/config/baseline trùng nguồn CSV hoặc đường dẫn nguồn đã resolve. Chỉ ghi output được yêu cầu; không sửa dữ liệu/config/baseline và không tự cập nhật checksum.
9. Chạy lại cùng đầu vào cho cùng counts/check results; timestamps có thể khác. Không tạo UUID, export training labels, approved profile, serving hoặc câu lệnh SQL.

## Kiểm thử cần chạy

Unit tests bằng unittest và fixtures nhỏ: BOM/CSV quoting; false string; blank khác zero; JSON malformed/wrong type; candidate arrays/count mismatch; duplicate keys/links; unknown references; ID remap sai và training 27 hợp lệ; mapping/class identity sai; flagged source defects khác unsafe usable record; baseline/hash drift; source-output alias bị chặn; exit codes và module import không có side effects.

Fixture không cần copy bộ nguồn lớn. Test phải bắt lỗi có ý nghĩa, không chỉ gọi implementation và kiểm tra chính constants của implementation. CLI chạy trên gói thật là kiểm tra tích hợp riêng; đối chiếu nguồn hashes trước/sau.

## Tiêu chí nghiệm thu

- Tests đạt và CLI chạy trên gói thật trả exit 0 cho cấu trúc baseline hiện tại.
- Report ghi đúng 67 classes, 9115 references, 109 links, 40 classes with candidates, 27 without, zero approved dish profiles.
- 7 file có đúng header/rows/bytes/hash baseline. Nguồn và baseline không đổi sau chạy.
- Review findings không bị giấu, NULL không thành 0, candidate không bị duyệt tự động, defects quarantine không bị sửa.
- Report ghi chưa kiểm tra database/RLS/Storage, ảnh thật, ngữ nghĩa labels, training/inference; thiếu ảnh không làm backend validator fail.
- Không thêm dependencies/code ngoài phạm vi, không sửa README và không commit/push/deploy.

## Kết quả cần bàn giao

docs/reviews/DATA-01-implementation.md phải nêu files changed, commands + exit codes, counts và finding quan trọng, test failures nếu có, report path, checksum comparison, phần còn thiếu. Ghi task là IMPLEMENTED_PENDING_REVIEW; Claude không tự ghi Codex đã nghiệm thu.
