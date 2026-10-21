# ML-03 — Adapter và kiểm tra tích hợp model thật

Ngày 2026-10-15, DONE_LOCAL_REAL_MODEL. Codex triển khai và tự review; không có review độc lập. Bundle chính đã train/evaluate, 51 real API checks đạt, activation local và live readiness/Swagger đã xác minh. Đây là nghiệm thu kỹ thuật local của model thực nghiệm, chưa phải full quality/mobile/nutrition/product acceptance.

## Thay đổi

Optional model bundle config và UltralyticsPredictor kiểm checksum weights/class map/evaluation, exact 67 names/order/version, canonical input/bbox contract và inference parameters. Thiếu/lỗi bundle giữ MODEL_NOT_READY. Inference dùng thread, lock giữ đến khi worker thật kết thúc ngay cả HTTP request bị cancel. Chỉ trả confidence/detections thật, không tự tạo alternatives. Startup warmup chỉ là technical check, không lưu hoặc trình bày như scan thực tế.

Evaluator chạy valid/test riêng, per-class coverage, precision/recall/AP và batch-one latency trên ảnh thật. Missing class metrics NULL. Bundle có training scope, provenance, version/dependency metadata và SHA. Activation chỉ chấp nhận full_audited_effective_train cùng matching passing API report; smoke/fixture models bị chặn. Chỉ restart process backend thuộc workspace, kiểm PID/create time/module/cwd, stop cả launcher children; lỗi startup có rollback về core config.

Preflight phát hiện Ultralytics 8.4.158 thay PIL.Image.open toàn cục bằng HEIF fallback. Corrupt JPEG dẫn đến import pi_heif chưa có và lỗi 500. Đã giữ strict Pillow opener của upload decoder trước library import; không cài codec ngoài contract để xử lý ảnh lỗi. Regression xác minh corrupted bytes vẫn 422 INVALID_IMAGE sau global patch; JPEG hợp lệ vẫn decode được. Unexpected backend log chỉ ghi exception class/request ID, không exception message hoặc tokens/bodies/URLs.

## Evidence đã chạy

- Toàn suite: 219 Python tests + 41 subtests passed, một warning Starlette TestClient deprecation; XML ignored ML-03-all-unit.xml. Gồm artifact tamper/wrong names/COCO80, box normalization, original/training ID distinction, genuine empty output, invalid outputs, expected version và cancellation exclusivity.
- Core HTTP chạy lại: catalog/Auth 37, meals/history/stats 76, scan/Auth/private Storage 50, tổng 163; 23 handoff cases/18 operations đạt. Canonical OpenAPI shape không đổi. SQL/migrations không sửa, không reset DB hoặc chạy empty-catalog fixtures.
- Evaluator thật đã chạy với smoke weights trên 64 ảnh original-train chia thư mục preflight. Đây không là valid/test độc lập; evidence_scope ghi train_subset_preflight_only. Dùng để kiểm API metrics của library và bundle writer, không lựa chọn model hoặc báo holdout accuracy.
- Real adapter → Auth → API → private Storage → confirmation → meal/history có 51 checks đạt trên tám ảnh original-train preflight. Có detections thật, signed owner download, A/B isolation, idempotent meal retry và cleanup đúng fixtures. Nutrition vẫn nutrition_unavailable. Report riêng ignored ML-03-preflight-model-integration.json ghi scope; không dùng làm acceptance model chính.
- Negative activation test thật xác minh smoke bundle bị chặn trước khi thay server chính. Source images/labels/CSV và base config được giữ nguyên; không commit/push/deploy hoặc gửi Anti.
- Evaluator preflight v2 đã chạy thật sau bổ sung native-label coverage và model-card writer: callback đọc đúng labels loader đã verify, missing metrics giữ NULL, readable card/SHA được tạo. Preflight config dùng backend-ml-preflight.json riêng; backend-ml.json dành cho bundle chính. Docker restore từ trạng thái đã dừng cũng đã kiểm thử thật, đúng năm existing containers healthy, rồi tạm dừng lại để nhường RAM.

## Kết quả bundle chính

Pipeline hoàn tất lúc 22:39:43 UTC+7. Model foodlens-yolo11n-20261015-budget8h-v1 qua evaluation thật trên 787 validation images/35 lớp và 404 test images/29 lớp; test mAP50 0,7406 và mAP50-95 0,5469. 14 full epochs + partial epoch15 trong 7 giờ 57 phút 22,547 giây. Xem [ML-02-training.md](ML-02-training.md) và [portable metrics](../dataset/model-evaluation-v1.json).

scripts/test_model_local.py đã chạy lại tự động với bundle chính và tám ảnh effective test, 51 checks passed: model/storage readiness, anonymous rejection, corrupt/unsupported upload, real detections/version, private signed download, owner A/B read/confirmation/meal isolation, confirmed grams, idempotent retry và history. Detections mỗi ảnh lần lượt 5/1/1/2/1/1/1/1; không dùng fixture predictions. Test users/objects đã cleanup đúng phạm vi, catalog/approved profiles không sửa. Nutrition vẫn nutrition_unavailable.

Local Docker restore sau khi tạm dừng train đã hoạt động; activation dùng backend-ml.json/ML venv, không thay base backend-local.json. Live GET /health/ready xác minh 200, database=ready, model=ready, capabilities.scan=true; /docs=200 và OpenAPI version0.4.0/14 paths. Bundle checksum verified lại sau activation. Model/server path và keys chỉ nằm trong ignored local config, không đưa vào response/portable report.

Real HTTP analyze mean219,92ms trên tám local holdout requests, khác inference-only mean8,96ms trên chín warmed samples. Chưa đo iPhone/Wi-Fi/concurrent GPU load; cancellation exclusivity là unit evidence, không báo thành device acceptance. Negative smoke-activation guard và fallback model-missing behavior vẫn giữ. Không đổi public response shape, migrations, remote/cloud hoặc mobile.

Chưa có independent 67-class holdout, agreed quality threshold acceptance, semantic-label/full perceptual-leakage review, mobile/device/cloud acceptance hoặc approved nutrition profiles. Full working product cần các điều kiện đó theo phạm vi liên quan; 8 giờ là giới hạn train, không phải bằng chứng toàn sản phẩm đã hoàn tất.
