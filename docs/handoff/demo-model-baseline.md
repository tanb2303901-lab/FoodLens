# FoodLens — Chuẩn bị demo model niên luận

Mục tiêu owner: demo/test cho giảng viên, hai iPhone và laptop Windows, không phát hành App Store/TestFlight. Backend/model local đã ready; frontend, kết nối LAN và kiểm thử camera/device vẫn chưa triển khai. Xem [portable evaluation](../dataset/model-evaluation-v1.json) và [ML-02 kết quả](../reviews/ML-02-training.md).

## Món nên thử bằng ảnh mới trước buổi demo

Đây là candidates sau evaluation, không phải cam kết đúng mọi ảnh. Ưu tiên thêm ảnh mới do hai thành viên tự chụp để kiểm tra khác biệt ánh sáng/góc chụp/bày món. Không dùng ảnh train để kết luận chất lượng thực tế.

| Món | Test images | AP50 test | AP50 validation | Ghi chú |
| --- | --- | --- | --- | --- |
| Bánh xèo | 17 | 0,9950 | 0,9245 | Kết quả hai split tốt, cần thử món thật |
| Bún đậu | 17 | 0,9922 | 0,9877 | Nhóm món chuẩn bị theo khay có thể khác cách bày trong dataset |
| Gỏi cuốn | 15 | 0,9850 | 0,7564 | Dễ chuẩn bị nhưng chênh lệch hai split, cần thử thêm |
| Khoai tây chiên | 36 | 0,9589 | 0,9197 | Candidate dễ mang để thử riêng/chung với hamburger |
| Bánh mì | 12 | 0,9212 | 0,8279 | Candidate gọn để chuẩn bị |
| Hamburger | 43 | 0,9007 | 0,8196 | Có nhiều test samples hơn các món trên |

Các số AP là chỉ số detector trên split nhận được, không là phần trăm bảo đảm khi chụp mới. Không ưu tiên demo đầu với cà chua/dưa leo sau evaluation: AP50 test tương ứng 0,1474/0,4187, thấp hơn các candidates trên. Các món chỉ có 1–4 test images dù AP cao không đủ căn cứ xếp hạng tốt nhất. 38 lớp không có test ground truth, giữ unmeasured.

## Luồng demo

1. Sau khi frontend hoàn tất, đăng nhập và chụp/chọn ảnh mới; gửi ảnh thật tới backend/model local.
2. Hiển thị bbox/tên/confidence thật. User sửa món sai nếu có, xác nhận grams và lưu meal/history.
3. Nutrition chưa approved phải hiển thị chưa có dữ liệu; không tạo calories hoặc serving giả để demo.
4. Thử ít nhất một trường hợp khó/thất bại và xử lý UI rõ. Ghi đúng phạm vi chỉ số model và phần chưa hỗ trợ.

Laptop trên lầu và iPhone ở tầng dưới có thể dùng khi cùng mạng LAN truy cập được, sóng đủ tốt, không guest/client isolation, laptop/server không sleep. Cùng tên Wi-Fi chưa tự chứng minh kết nối đã thông. Hiện chỉ bind loopback; cần task cấu hình/kiểm thử LAN cho backend và Auth trước demo. QR Expo chỉ mở frontend, không tự expose API. Không deploy/mở mạng trong lượt ML này.
