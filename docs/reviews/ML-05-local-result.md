# ML-05 — Train và API đã xong, chất lượng75 chưa được chấp nhận

## Quyết định mới nhất — mở bản75 theo lựa chọn owner

Sau báo cáo13:20, owner trực tiếp yêu cầu mở75 và giữ giao diện nhận diện gọn, không hiển thị ghi chú riêng về Khoai lang. Đã kích hoạt đúng fixed bundle với chế độ `owner_authorized_local_preview`; đây là lựa chọn dùng local, không ghi lại failed gate thành passed. Internal metrics/gates/candidate hashes giữ nguyên. Backend dùng ignored backend-ml75.json, model_version foodlens-yolo11n-20261016-extension4h-v2-dual75, live database/model ready và scan=true. Bản67/config cũ vẫn được giữ để quay lại khi cần. Không train thêm.

Giao diện8765 đã mở, không còn card tiến độ/danh sách8 món hoặc ghi chú chưa hoàn thiện. Không lọc hoặc giả detection; vẫn dùng kết quả thật của model75 và ảnh canonical từ private Storage. Browser chọn ảnh crop táo cố định, bấm Nhận diện và nhận đúng Táo67,3% confidence, một bbox,328,2ms qua API; nút hoạt động trở lại, không console error/warning. Đây là một smoke case UI, không đánh giá accuracy mới.299 Python tests+41 subtests đạt, gồm exact owner-preview candidate binding và readiness75. Evidence máy ML-05-owner-preview.json/ML-05-live-smoke.json/ML-05-test-ui75-live.png. Trạng thái task hiện là DONE_LOCAL_OWNER_PREVIEW; những mô tả chưa mở75 phía dưới là kết quả lịch sử trước lựa chọn này.

Ngày16/10/2026, kiểm tra lại13:17–13:20 UTC+7 theo yêu cầu owner. Codex triển khai và tự review, không có reviewer độc lập. Một job được cấp phép đã kết thúc70 full epochs;4507,060314 giây tính budget (1 giờ15 phút7 giây), dưới cap3 giờ và trước cutoff13:00. Khoảng pause được xác minh vẫn bị loại đúng, không reset counters hoặc chạy thêm train. Evaluation xong12:50:18 UTC+7.

Model cố định được chọn bằng validation8 mới: `epoch45.pt`, sau đó ghép chỉ8 outputs mới với model67 nguồn nguyên vẹn. Không đổi checkpoint, ngưỡng hoặc dữ liệu sau khi xem test để tìm kết quả đẹp hơn. Bản75 chưa activate vì một trong18 quality checks tối thiểu không đạt: Khoai lang test AP50=0,164788846, dưới mức0,25 được ghi trước evaluation trong extension-quality-gates-v2.json. Đây là AP trên8 ảnh crop test, không phải khẳng định độ chính xác16,5% trên mọi ảnh. Cả7 lớp còn lại vượt mức tối thiểu thực nghiệm; không đồng nghĩa đã tốt trên mọi cách chụp.

| Split | Ảnh | Lớp có GT | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Legacy validation, toàn cảnh |787|35|0,6639|0,5050|
| Legacy test, toàn cảnh |404|29|0,7410|0,5447|
| Extension validation, crop vùng |171|8|0,8111|0,7726|
| Extension test, crop vùng |143|8|0,6627|0,6243|

| Món mới | Số ảnh crop test | AP50 |
| --- | ---: | ---: |
| Chuối |37|0,7820|
| Táo |31|0,8065|
| Gà nướng |6|0,3825|
| Cá hồi nướng |6|0,5942|
| Khoai lang |8|0,1648|
| Khóm |30|0,7729|
| Cà phê |15|0,8512|
| Nước ngọt |10|0,9476|

API vẫn được kiểm tra độc lập chất lượng bằng server tạm loopback, đúng fixed bundle, user A/B và Storage riêng.951 checks đạt trên151 ảnh (8 legacy test scenes+143 crop mới), đủ8 lớp đều có ít nhất một detection đúng GT/IoU≥0,5 qua API. Các checks gồm exact UUID/map75/NULL original IDs, không fabricated alternatives, upload/private signed image, owner isolation, confirmation, user-confirmed100g fixture, nutrition NULL, meals/idempotency và scan history có phân trang. Các fixture Auth/Storage được dọn, không sửa dữ liệu owner hoặc danh mục. Một ảnh nhận đúng không đủ chứng minh lớp Khoai lang ổn định. Không vì951 functional checks mà đổi quality gate thành passed.

Latency151 request local: trung bình236,8ms, nhỏ nhất158,2ms, lớn nhất288,2ms; gồm upload/Auth/decode/inference/database/Storage, không phải SLA hoặc benchmark điện thoại. Snapshot kết quả thật, hashes, coverage và per-class ở docs/dataset/model-evaluation-v2.json. Báo cáo máy: ML-05-quality-gates.json, ML-05-model-integration.json và ML-05-finish.json trong ignored data/processed.

Backend8000 đã khôi phục model67 đã nghiệm thu, live database/model ready và scan=true. Trang thử8765 vẫn chặn75, hiển thị cần kiểm tra thêm; chưa mở thử bản75 và chưa ghi nhận owner chấp nhận chất lượng. Đã hỏi lựa chọn dùng bản75 như bản thử có ghi hạn chế hoặc giữ67. Không tự train thêm, hạ gate, đổi test hoặc báo DONE_ALL75. Nutrition approval,75-class independent holdout, ảnh toàn cảnh8 món mới/iPhone/LAN vẫn chưa nghiệm thu.
