# BE-03 — Scan APIs, image validation và predictor readiness

Ngày: 2026-10-15. Kết quả task backend: DONE. Codex triển khai/test/tự review; không có independent review/Claude Code/Anti. Model inference acceptance: NOT_READY vì chưa có detector/weights thật.

## Đã triển khai

POST /v1/scans/analyze, GET /v1/scans, GET /v1/scans/{id}, PATCH /v1/scans/{id}/result. Runtime có đủ 14 paths/18 operations của API design. Analyze production mặc định 503 MODEL_NOT_READY trước body parsing/DB/Storage; không có fake predictor ở config/HTTP. Class map portable 67 UUID/remap/digest được verify; missing/mismatch không tắt core APIs. Health core ready vẫn model not_ready, scan capability=false.

Manual bounded multipart có strict keys/source, max envelope/file/pixels/dimension, decoder/MIME/static validation; canonical RGB JPEG áp dụng orientation/white alpha composite và strip metadata. Python-multipart 0.0.32/Pillow 12.3.0 thêm vào dependencies pin/lock. 422 corrupt/multipart, 415 unsupported/mismatch/animation, 413 byte/pixel/dimension excess; new 408 upload deadline và 504 inference deadline cho pipeline ready sau này.

Predictor interface và mapper/validation, service writer owner/path guard, processing/completed/failed/compensation đã có. Optional private scan key chỉ start/finish/upload/delete; ordinary context/signing bằng user JWT. Signed URL 300s default, validate origin/path, không expose private image_path/user_id. Missing object URL NULL, storage unavailable sanitized 503. No automatic meal from confirmations; If-Match/revision/owner được enforce, predicted JSON giữ nguyên.

History created_at/id DESC, owner filter + RLS trước pagination, HMAC scope/owner/[from,to) với tie timestamp. Bổ sung scope/time-key trong cursor helper, giữ token meals format cũ. Optional alternatives field không xuất hiện khi adapter/source không cung cấp; không thêm fake Top-3 scores.

## Kiểm thử thực tế

- pytest tests/backend: 86 tests passed, exit 0 (51 existing + 35 BE-03), report data/processed/BE-03-unit.xml. Images static formats/corrupt/MIME/limits/bomb/animation/EXIF/alpha; map/remap/scores; auth/readiness before parse; strict form; server credentials/path privacy; synthetic adapter success/empty/invalid/error/timeout; upload failure, completed response lost, state uncertain, cleanup failure; own/cross-owner detail/confirm/signing và full runtime OpenAPI.
- scripts/test_scans_local.py: 50 real HTTP/Auth/Storage checks passed, exit 0; report data/processed/BE-03-integration.json. Real runtime analysis (empty/invalid/oversized/valid image) đều MODEL_NOT_READY và tạo zero rows/objects. Sau đó seeded scans explicit BE03_SYNTHETIC_FIXTURE_NOT_INFERENCE chỉ để test stored history/confirmation/Storage, không chạy detector. Owner sign/download bytes, short TTL/private URL denial/B cannot sign A, missing object NULL, owner/pending/revision/duplicate/unknown IDs, confirmations preserve predictions/no meal, tied history/filters/cursor scope, meal references owner/predicted-vs-confirmed đều đạt.
- Catalog/JWT regression script: 37 real HTTP checks passed, exit 0.
- Manual meals/profile/stats regression script: 76 real HTTP checks passed, exit 0.
- Sau cleanup query: foods=67, references=9115, links=109; auth.users/scans/storage.objects/meals/receipts/food_nutrition/portions đều 0. HTTP chỉ xóa Storage paths/Auth IDs do test tạo, catalog giữ nguyên. Không có SQL migration mới trong BE-03.

Commands từ project:

```powershell
& '.venv/Scripts/python.exe' scripts/prepare_scan_local.py
& '.venv/Scripts/python.exe' -m pytest tests/backend -q --junitxml=data/processed/BE-03-unit.xml
& '.venv/Scripts/python.exe' scripts/test_scans_local.py
& '.venv/Scripts/python.exe' scripts/test_backend_local.py
& '.venv/Scripts/python.exe' scripts/test_meals_local.py
```

86 tests có 1 Starlette deprecation warning HTTPX TestClient adapter như các task trước; không failure. Dependencies pinned. Config/backend logs/reports/PID trong ignored data/processed; service key không in/prompts/report. Không sửa README/CSV/images source/labels/weights, không cloud/reset/commit/push/deploy. Codex restart đúng local project process ở 127.0.0.1:8000 và smoke Swagger/readiness/full schema.

## Giới hạn và kế tiếp

Test adapter chỉ là unit fixture qua factory injection, không xuất hiện ở app production. Không tuyên bố real inference/accuracy/latency/weights/mobile đã hoàn thành. Adapter contract tại docs/architecture/predictor-contract.md; full runtime OpenAPI tại docs/architecture/openapi-runtime-be03.json. Client mới có thể dùng catalog/manual meals/history/stats và scan metadata; analyze còn gated.

Compensation DB+Storage không phải distributed transaction. Failed cleanup cần retry/reconciliation sau outage; state uncertain giữ ảnh cho đến khi confirmed, không xóa bất cẩn. Warning logs chỉ scan_id, no credential/path/signed URL. Real adapter cancellation behavior vẫn cần test khi chọn model. Đây là material limits cần ghi vào backend acceptance/handoff.

Bước tiếp: BE-04 backend acceptance, hợp đồng/samples/setup và handoff ghi rõ model/nutrition chưa ready. Sau đó tách ML readiness/training/evaluation và frontend theo quyết định chủ dự án; không tự báo Anti đã nhận task.
