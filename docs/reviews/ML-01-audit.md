# ML-01 — Image/label audit implementation và kết quả

2026-10-15. DONE_WITH_REVIEW. Codex triển khai/tests/tự review, không review độc lập. Input root local do owner cung cấp; sources giữ nguyên. Mục tiêu audit hoàn thành, model readiness/accuracy không thuộc kết luận này.

scripts/audit_vision.py kiểm baseline7 CSV, immutable67 identities, manifest joins/flags/boxes/physical line, path containment/root relocation và symlink/reparse guards. Inventory toàn image/label trees; hash mọi label copy, parse preferred labels và đối chiếu canonical bbox fingerprints (SHA-256 theo physical line/original class/numeric coordinates). Bounds tolerance1e-6 chỉ xử lý floating source rounding, không sửa annotation.

Decode/hash sampling có seed deterministic và class/status/reason representatives; CRC-size chỉ để tìm candidate, SHA xác nhận content trong phạm vi đọc. Issues chi tiết JSONL và machine-specific config/report nằm ignored data/processed. Output path cấm alias config/CSV bằng resolved path và hardlink; không writer tới sources.

Kết quả thực tế:171.619 ảnh,172.956 physical labels,171.619 preferred parses,838.716 bbox đối chiếu,659 decodes và662 image SHA/CRC,0 errors. Findings source-group review được giải thích trong docs/dataset/vision-audit-v1.md; portable per-class coverage ở docs/dataset/vision-coverage-v1.json. Source CSV checksums trước/sau khớp baseline. Không có full image decode/semantic label/model acceptance.

38 tests audit/exporter passed, exit0: remap food training27/face exclusion, path traversal/case/root relocation/nested labels, YOLO invalid class/NaN/geometry/row width, duplicate label integrity, changed file, sampling/order/background/exclusion, coarse family vs exact video group và source/config hardlink protections. Regression sau thêm optional detector factory:198 tests +41 subtests passed, exit0 (trước20 adapter tests bổ sung ở ML-03).

Commands:

```powershell
& '.venv/Scripts/python.exe' -m pytest tests/test_audit_vision.py -q --junitxml=data/processed/ML-01-unit.xml
& '.venv/Scripts/python.exe' -u scripts/audit_vision.py --config data/processed/data-local.json --report data/processed/ML-01-vision.json
```

Portable audit không đưa absolute machine paths/individual image IDs vào docs; report đầy đủ và issue JSONL ignored. Không sửa backend migrations/mobile/README hoặc sources để làm audit pass. ML-02 được owner mở rộng sang train local tối đa8 giờ; GPU/CUDA/benchmark và train logs có evidence riêng, không tính là kết quả của ML-01.
