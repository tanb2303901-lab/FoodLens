# ML-02 — Kết quả lượt train 8 giờ

Ngày 2026-10-15, DONE_BUDGETED_BASELINE. Chủ dự án giới hạn train tối đa 8 giờ; Codex triển khai, kiểm thử và tự review, không có review độc lập. Model version foodlens-yolo11n-20261015-budget8h-v1. Metadata/metrics portable tại [model-evaluation-v1.json](../dataset/model-evaluation-v1.json); artifact đầy đủ nằm trong ignored ml/models và data/processed, không đưa weights/dataset vào tài liệu.

## Kết quả thực tế

Job bắt đầu 14:41:05 UTC+7; process train mất 28.642,547 giây, tương đương 7 giờ 57 phút 22,547 giây, bao gồm khởi tạo dataset/final validation/save. Đã học 14 epoch đầy đủ và 27 batches được callback ghi trong phần epoch 15 trước khi dừng; không báo thành 15 full epochs. Toàn pipeline train → evaluation → real API acceptance → activation local hoàn tất lúc 22:39:43 UTC+7, trước hạn 22:41. Không tăng budget, không chạy thêm lượt train.

YOLO11n pretrained chính thức, imgsz512/batch32/workers0/AMP/cacheFalse, RTX 4060 Laptop 8 GB; torch 2.11.0+cu126 và Ultralytics 8.4.158. Benchmark chọn cấu hình được lưu trong preflight review; tốc độ subset benchmark không dùng làm tốc độ/accuracy toàn tập.

Native training loader giữ 161.247 ảnh, 822.311 boxes, 67 classes và 630 background images. Bản export raw có 822.457 boxes; native cache loại 146 duplicate labels trong 143 ảnh, không sửa source labels/CSV. Valid giữ 787 ảnh/1.319 boxes/35 lớp; test 404 ảnh/591 boxes/29 lớp, zero images bị loại trong native evaluation. Review/excluded không vào train/eval. Original face27 bị loại, training27 là food original28.

| Split | Precision | Recall | mAP50 | mAP50-95 |
| --- | --- | --- | --- | --- |
| Validation, 35 lớp | 0,5772 | 0,7036 | 0,6705 | 0,5131 |
| Test, 29 lớp | 0,7684 | 0,6693 | 0,7406 | 0,5469 |

Metrics tính trên những lớp có ground truth trong split, không là tỷ lệ mọi ảnh/mọi món đều đúng. Test được dùng đánh giá cuối sau khi chọn cấu hình bằng benchmark train subset và chọn checkpoint bằng validation, không dùng để retune. Absent classes có metrics NULL. Full 67-class independent quality acceptance vẫn chưa có; các lớp ít ảnh chưa đủ để kết luận ổn định khi chụp thực tế.

## Artifact và tính toàn vẹn

Bundle có weights.pt, exact food-identities-v1.json, evaluation.json, model-card.md và manifest.json. SHA-256 weights a41bffd69d9c1e072583a18e5de9825e9ef6a2ba9fdde477e87037cda98440eb; class-map SHA 56e22da594d45bd750b0a0a008d596e4381dfb3e2f6c8029f12afb4e8fe7acd8; các digest còn lại nằm trong portable JSON/manifest. Sau pipeline, verify_bundle đã chạy lại và xác minh checksum/map/names/evaluation contract. Durable last-resume.pt có optimizer được giữ riêng với checkpoints; resume không tự tăng budget.

Batch-one warmed predict mean 8,96 ms qua chín mẫu trên GPU này, không gồm HTTP/Auth/Storage. Real local HTTP analyze trên tám ảnh test mean 219,92 ms, min 179,14/max 255,14 ms, gồm upload/Auth/canonicalization/model/database/private Storage. Đây là mẫu loopback nhỏ, không phải benchmark iPhone/Wi-Fi hoặc bảo đảm latency khi nhiều user.

Nguồn CSV/ảnh/nhãn được giữ nguyên, train dùng bản copy độc lập; không DB reset, cloud deploy, commit/push hoặc frontend implementation. Tiếp theo owner test ảnh mới từ iPhone, data nutrition verification và frontend/device integration theo task riêng. Technical ML baseline hoàn tất, chất lượng toàn bộ 67 lớp và toàn sản phẩm chưa được tuyên bố đạt.
