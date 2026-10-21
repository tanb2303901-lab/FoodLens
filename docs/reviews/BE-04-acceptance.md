# BE-04 — Nghiệm thu backend và bàn giao

Ngày 2026-10-15. Kết quả: DONE_CORE_HANDOFF_READY. Codex triển khai/kiểm thử/tự review, không có review độc lập hoặc lượt Claude Code/Anti. Model, production nutrition và mobile chưa nghiệm thu.

## Kết quả và thay đổi

Backend 0.4.0 có đủ 14 paths/18 operations; Swagger local port 8000 khớp snapshot chính docs/architecture/openapi-backend-v1.json. Catalog/profile/manual meals/history/stats hoạt động với Supabase Auth/PostgreSQL thật. Scan stored APIs/private Storage được kiểm thử với fixtures synthetic; production analyze giữ 503 MODEL_NOT_READY và không ghi scan/ảnh khi model thiếu.

Sửa các sai lệch metadata trước bàn giao: mutation headers Idempotency-Key/If-Match required trong OpenAPI, JSON input timestamp/date patterns khớp parser, loại original face 27 trong Food schema, mô tả 500 Error và các response headers thực tế. Giữ runtime lỗi thiếu key422/If-Match428 và nghiệp vụ cũ. Không có migration hoặc thay đổi schema DB trong BE-04.

Bộ docs/handoff gồm backend-v1.md, api-examples-v1.json, error-codes-v1.md và anti-fe01-prompt.md; FE-01 task ở docs/tasks. 23 samples bao phủ 18 operations được lấy từ HTTP local thật: health/readiness/Auth/catalog/nutrition/profile/create/retry/edit/history/stats/delete/scan-empty/404/model gate. Thay user/meal/item/request IDs và cursor bằng placeholders; không có token/password/private paths/signed URLs, fake bbox/confidence/calories hoặc serving đề xuất. Bộ này sẵn để chủ dự án chuyển, chưa thực sự gửi cho Anti.

Full OpenAPI 3.1 validated bằng openapi-spec-validator 0.9.0; request/response samples validated theo JSON Schema Draft 2020-12/jsonschema 4.26.0. Validator dùng Decimal để kiểm multipleOf 0.001 chính xác. 14 tests mới kiểm contract/golden artifact, invalid inputs, required headers, missing nutrition/empty-day semantics, face exclusion và không xuất credentials. Dependencies chỉ thêm development validators; có requirements-dev.lock.txt, uv pip check đạt tương thích 44 packages.

Các integration scripts cũ trước đây ghi đè file docs openapi-runtime-be03.json; lần regression BE-04 đã cập nhật export đó. Đã đổi đích generated exports sang ignored data/processed để lần chạy sau không âm thầm thay contract portable. Dùng test_handoff_local --write-artifacts khi chủ ý cập nhật canonical contract/samples, default chỉ verify và chạy flows. Không tuyên bố file tên BE-03 còn là snapshot bất biến của version 0.3.0. Đã sửa ghi chú stale “chưa triển khai JWT/schema” và signed URL600s thành runtime default 300s; đối chiếu ở architecture/backend-v1-contract-review.md.

## Evidence thực tế

| Kiểm tra | Kết quả |
| --- | --- |
| Toàn bộ Python tests | 160 passed + 41 subtests passed, exit 0; gồm 60 data/import,86 backend cũ,14 acceptance mới |
| SQL 001/002/003 | 3 files,91 tests PASS, exit 0; 001 guard đã thỏa state trống, synthetic fixtures rollback |
| Catalog/JWT HTTP | 37 checks passed, exit 0 |
| Profile/meals/history/stats HTTP | 76 checks passed, exit 0 |
| Scan/Auth/private Storage HTTP | 50 checks passed, exit 0; production predictor unavailable |
| Handoff samples/full schema | 23 HTTP cases/18 operations validated, exit 0; chạy lại default không cập nhật artifacts cũng đạt |
| Local server sau restart đúng PID project | /docs200, /health200, readiness200 DBready/modelnot_ready, scan capabilityfalse; live OpenAPI bằng canonical |
| Source integrity | Cả 7 CSV khớp byte size/SHA-256 baseline; giữ nguồn nguyên trạng |

160 là số test functions/cases pytest báo; JUnit XML có 201 testcases do gồm 41 subtests, không cộng thành201 test functions. Một Starlette deprecation warning về HTTPX TestClient như các task trước; không failure. Test dependencies được pin, chưa thay HTTP client adapter theo warning vì cần task migration riêng khi cần.

Reports/config/logs chỉ trong ignored data/processed: BE-04-unit.xml, BE-04-handoff.json, BE-04-live-smoke.json, BE-04-acceptance.json và các BE-01/02/03-integration.json. Evidence SQL là CLI output trong lượt nghiệm thu. Tests tạo tài khoản tạm/scan objects riêng rồi dọn đúng resources; không reset hoặc xóa catalog. DB-02 empty-catalog HTTP suite không chạy lại.

Commands từ root project:

```powershell
& '.venv/Scripts/python.exe' -m pytest tests -q --junitxml=data/processed/BE-04-unit.xml
& 'data/processed/tools/supabase-2.120.0/supabase.exe' test db --workdir 'C:/Nienluan/FoodLens'
& '.venv/Scripts/python.exe' scripts/test_backend_local.py
& '.venv/Scripts/python.exe' scripts/test_meals_local.py
& '.venv/Scripts/python.exe' scripts/test_scans_local.py
& '.venv/Scripts/python.exe' scripts/test_handoff_local.py
```

Không chạy toàn bộ SQL suite nếu guard 001 chưa thỏa; không reset để vượt guard. SQL source/approval fixtures chỉ tồn tại trong transaction rollback, không tạo approved profile production. Samples lần đầu export có chủ ý bằng `scripts/test_handoff_local.py --write-artifacts`; default verify so sánh với snapshot được chốt.

Sau tất cả cleanup: foods 67, references 9115, candidate links 109, import_runs 1, applied migrations11; nutrition profiles/portions/Auth users/user profiles/meals/items/scans/Storage objects/mutation receipts đều 0. Không thay source CSV/ảnh/nhãn/weights, README/mobile/ML, không cloud/reset/commit/push/deploy. Workspace hiện không có Git repository nhận diện được để báo git diff; review dựa trên file/code/runtime/evidence, không giả lập Git review.

## Điều kiện chấp nhận và phần tiếp theo

Core backend đủ điều kiện FE-01: manual flow, Auth, dữ liệu thiếu, concurrency/retry và owner isolation được mô tả/kiểm thử. Đồng đội vẫn cần setup Node/Expo theo task và môi trường test có thể truy cập từ thiết bị; localhost backend không phải địa chỉ chia sẻ. Chưa cài mobile hoặc mở LAN/tunnel.

AI còn thiếu detector/weights/loader/preprocessing, evaluation dataset/leakage/coverage, accuracy/latency/cancellation và real inference integration. Production nutrition còn zero approved profiles/portions, cần xác minh nguồn/basis/units/equivalence và approval trước tính khẩu phần. Chưa có background DB/Storage reconciliation, retention/account-delete workflow hoặc production deployment acceptance. Các giới hạn đã bàn giao rõ; không coi toàn bộ FoodLens/AI hoàn tất.

FE-01 và prompt Anti đã chuẩn bị, chưa gửi. Công việc backend tiếp theo đề xuất ML-01 kiểm tra ảnh/nhãn gốc và evaluation readiness trước chọn/train/tích hợp model; không tự duyệt nutrition hoặc thay model vì muốn có demo.
