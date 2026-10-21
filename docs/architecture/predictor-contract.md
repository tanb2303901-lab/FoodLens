# Predictor contract — BE-03 / ML-03

Default core config dùng UnavailablePredictor: status=None, analyze trả 503 MODEL_NOT_READY. ML-02 chọn YOLO11n/512 làm baseline sau benchmark; ML-03 đã thêm optional UltralyticsPredictor. Chỉ explicit absolute model_bundle_path mới yêu cầu load bundle; startup verify artifacts/map/names/evaluation và warmup thật. Bundle lỗi/thiếu dependencies/weights giữ not_ready, core vẫn hoạt động. Không có env/query flag fake detector; test doubles chỉ truyền vào create_app trong tests. Xem docs/reviews/ML-03-implementation.md để phân biệt preflight đã chạy với model chính đang train.

## Adapter thật cần cung cấp

Predictor.status() sync/nonblocking trả None hoặc PredictorInfo(model_version,class_map_version,class_map_sha256) sau khi load/verify model thành công. Predictor.predict(CanonicalImage, expected_info) async trả list RawDetection; adapter giữ model instance/version đã báo trong expected_info, fail khi version không khớp. ML-03 chạy inference trong thread và giữ model lock đến khi worker thực sự xong, kể cả HTTP request bị cancel; timeout không có nghĩa GPU work đã bị hủy.

class_map_version=vietfood-67-2026-10-12-v1; SHA-256 là exact bytes docs/dataset/food-identities-v1.json. 67 identities, slug/UUID/training IDs unique; original face 27 bị loại, training 27 là original 28. Model bundle giữ map này, thứ tự training IDs, checksum, model/preprocessing version và weights provenance. Sai/missing map -> model not_ready; core catalog/manual meals vẫn có thể ready.

RawDetection: training_class_id int 0..66, bbox normalized xyxy [x1,y1,x2,y2] finite trong [0,1] với x1<x2/y1<y2, confidence finite [0,1]. alternatives optional <=3 với training_class_id/confidence thật, không duplicate. Backend map sang food UUID/original ID, tạo detection_id riêng và không tự thêm Top-3 khi adapter không trả scores. Genuine empty list được giữ empty; invalid output không được completed.

Input predictor là cùng canonical JPEG bytes lưu trong private Storage: decode JPEG/PNG/WebP tĩnh <=10MiB, max 20M pixels/8192 dimension (config có thể giảm), EXIF orientation applied, RGB/white alpha composite, JPEG quality 90 và bỏ EXIF/ICC/XMP. Ultralytics nhận RGB PIL image, resize/letterbox nội bộ và trả boxes.xyxy theo orig_shape; adapter kiểm dimensions rồi chia x/width, y/height thành canonical xyxy_norm. Decoder upload giữ hàm Pillow gốc trước optional library import để HEIF fallback của thư viện không biến corrupt JPEG thành lỗi 500 hoặc yêu cầu codec mới.

## Pipeline và privacy

Auth -> model/map readiness -> writer credential -> bounded multipart/decode -> processing row -> private upload -> predict/validate -> completed row -> owner signed URL. Multipart được đọc thủ công sau auth/readiness để FastAPI File/Form dependency không parse body trước gate. Envelope <=10MiB+64KiB; đúng một file và optional input_source camera/gallery/share. MIME decode phải khớp, static-only; filename/URL/path/owner không từ client. Chi tiết parser/decoder dựa trên [Starlette request form limits](https://www.starlette.io/requests/) và [Pillow security](https://pillow.readthedocs.io/en/stable/handbook/security.html).

Tối đa 2 analysis pipelines mỗi process; upload/read/decode deadline 2× HTTP timeout (default 10s), inference default 30s. Status xử lý timeout là 408 upload/504 prediction, không phải latency benchmark. Worker cancellation phải được adapter thật kiểm tra khi tích hợp; test timeout không chứng minh GPU work đã bị hủy.

Privileged writer chỉ dùng server service-role key trong local private config, owner từ verified UserContext và path UUID/scan/UUID.jpg có guard. Ordinary reads/RPC confirmations và image signing dùng user JWT, không thay headers shared client. Service key runtime này là legacy service-role JWT đã kiểm role; opaque sb_secret key chưa hỗ trợ/test ở scan writer. Private bucket/RLS vẫn giữ nguyên.

On failure: mark failed trước khi xóa ảnh của chính scan đó. Nếu finish response bị mất, đọc lại theo user: completed -> giữ ảnh/kết quả thật; failed -> cleanup own image; không xác minh được state -> SCAN_STATE_UNCERTAIN + own scan_id, không xóa ảnh. Storage delete failure giữ failed row/image_path, logger chỉ scan_id; cần retry/reconciliation khi dependency hồi phục. Không có job cleanup tự động trong BE-03. Đường trace và ảnh vẫn private; không đổi failed thành completed hoặc giả predictions.

## Acceptance còn thiếu

Adapter đã được unit test mapping/bbox/artifact errors/cancellation; sau preflight riêng, bundle chính foodlens-yolo11n-20261015-budget8h-v1 đã hoàn tất budgeted train, valid/test evaluation và 51 real API checks trên tám ảnh effective test. Local ML config đã xác minh model=ready/scan=true, Swagger200. Smoke bị chặn activation server chính. Independent holdout vẫn chưa bao phủ67 lớp; semantic labels/full perceptual leakage, ảnh mới/mobile/LAN và whole-product quality acceptance còn thiếu. Không coi các chỉ số split hoặc fixture scores là bảo đảm mọi ảnh đều đúng.
