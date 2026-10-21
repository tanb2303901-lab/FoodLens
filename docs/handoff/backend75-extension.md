# Bổ sung backend75 — FoodLens

Cập nhật16/10:75 đã được kích hoạt cho local theo lựa chọn trực tiếp của owner, chế độ owner-authorized preview.951 real API checks và299 Python+41 subtests đạt; UI8765 đã nhận đúng Táo qua model75. Dùng OpenAPI0.5.0, đúng food UUID/map nullable như dưới. Gate chất lượng đã đo giữ nguyên trong model-evaluation-v2; việc bật local không đổi thành full75/mobile/nutrition acceptance. Xem ML-05-local-result cho quyết định hiện hành; các ghi chú chưa activate bên dưới là lịch sử.

Ngày16/10/2026, Codex triển khai và tự review, không có review độc lập. Runtime và canonical OpenAPI hiện0.5.0, vẫn14 paths/18 operations. Danh mục local75 đã áp dụng migration và kiểm thử; model mới chưa được kích hoạt tại lúc lập tài liệu này. Trạng thái model cuối phải đối chiếu `model-evaluation-v2.json` và ML-05 review khi có kết quả thật.

Tám món được nối thêm: Chuối67, Táo68, Gà nướng69, Cá hồi nướng70, Khoai lang71, Khóm72, Cà phê73, Nước ngọt74. `training_class_id` tối đa74; `original_class_id` của tám lớp mới làNULL vì không thuộc VietFood. Không tạo original IDs giả.67 entry và UUID cũ giữ nguyên; original27 face vẫn bị loại, training27 vẫn hợp lệ. Mỗi food cũ giữ class_map_version v1, food mới dùng `foodlens-75-2026-10-16-v2`. Scan mới có map75 chỉ khi đúng predictor đã được activate; scan lịch sử map67 vẫn đọc được.

Frontend dùng food UUID để chọn món, xác nhận kết quả và lưu bữa ăn. Không dùng class ID làm UUID hoặc suy index từ vị trí danh sách; catalog có phân trang. Chấp nhận `original_class_id: null` ở foods/detections, giữ NULL khi hiển thị/chuyển kiểu.23 ví dụ v1 cũ tiếp tục hợp lệ; schema hiện hành là [OpenAPI](../architecture/openapi-backend-v1.json).

Cập nhật 20/10 (FOOD-02): dinh dưỡng, bữa ăn và thống kê đã bị gỡ khỏi backend. Cà phê/nước ngọt/gà/khoai lang là nhóm rộng; phần giới thiệu món có ghi chú phạm vi cho các lớp này.

Kiểm tra đã đạt trước model integration:21 SQL rollback checks,180 HTTP core checks,23 HTTP handoff examples,275 Python tests+41 subtests. Dữ liệu user/history và nguồn cũ được bảo toàn. Model75 đang đánh giá theo cặp inference: model67 nguyên vẹn cộng8 outputs mới, không cần người làm frontend train hoặc tải dataset. New8 holdout là vùng crop, chưa là nghiệm thu ảnh toàn cảnh/iPhone/LAN. Chỉ chuyển trạng thái scan75 thành dùng được sau real model/Auth/private Storage/meal checks và live readiness.

Đồng đội cần source mobile/API contract, public Supabase URL/key và backend URL của môi trường đã cấu hình. Không chuyển service keys, config backend riêng, dataset hay training environment. Hai iPhone dùng Expo theo kế hoạch riêng; loopback laptop không phải URL điện thoại. Việc kết nối LAN và chụp camera thật vẫn phải kiểm thử khi tích hợp frontend.
