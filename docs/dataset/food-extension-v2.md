# FoodLens75 — tám lớp bổ sung theo yêu cầu owner

2026-10-16. Owner chọn gộp rộng theo đúng tám tên và cho một lượt train mới tối đa4 giờ; chuẩn bị dữ liệu/kiểm thử theo dõi riêng. Task ML-05. Bản đồ chuẩn bị tại food-identities-v2.json chưa được activate trong backend/database/model. Bản67 đang phục vụ giữ nguyên.

| ID train mới | Tên | Phạm vi nhận diện |
| --- | --- | --- |
| 67 | Chuối | Quả, bó/nải, phần quả đã bóc hoặc cắt; không cây/lá/hoa chuối |
| 68 | Táo | Apple, quả hoặc phần đã cắt; không gộp jujube/táo ta chỉ vì cùng tên tiếng Việt |
| 69 | Gà nướng | Gà đã nướng/grill/roast, gồm ức, đùi, cánh và nguyên con; không gà sống, gà chỉ luộc/chiên hoặc vịt |
| 70 | Cá hồi nướng | Cá hồi đã nướng/grill/bake; không cá chung, sushi sống hoặc cá hồi hun khói chưa nướng |
| 71 | Khoai lang | Khoai lang sống/chín, nguyên củ hoặc cắt, gồm các cách chế biến; không potato/khoai tây hoặc yam chưa xác minh loài |
| 72 | Khóm | Pineapple/dứa/thơm, nguyên quả hoặc phần đã gọt/cắt; không lấy lá/cây/tranh minh họa làm quả |
| 73 | Cà phê | Đồ uống cà phê đen/sữa/nóng/đá và biến thể; không hạt/bột/máy pha hoặc ly rỗng |
| 74 | Nước ngọt | Đồ uống nước ngọt với nhiều nhãn/hương vị/biến thể; không suy có đường/zero từ ngoại hình ly |

Khóm/cà phê/nước ngọt aliases hỗ trợ tìm nguồn và hiển thị, không tạo thêm lớp. Mọi biến thể dinh dưỡng cần user xác nhận và profile đã duyệt riêng; model không suy khối lượng, đường hoặc calorie.

Cập nhật trực tiếp từ owner trong lúc chuẩn bị, trước export/train/activation: không bắt buộc phần ức, đổi lớp69 thành Gà nướng. Khoai lang gộp hấp/luộc/nướng và các cách chế biến khi xác định được củ khoai lang. Các candidate nguồn mang tag lịch sử `grilled_chicken_breast` vẫn giữ nguyên provenance; tag tìm kiếm không phải tên lớp đầu ra. Rà lại các quyết định loại chỉ vì phần thịt theo phạm vi mới, không tự duyệt bbox.

## Định danh và tương thích

Giữ nguyên từng entry của67 lớp đầu: UUID, slug, tên, scope, training0..66 và original0..67 bỏ27. Tám lớp mới nối training67..74, UUIDv5 cùng namespace/name convention theo slug. Vì không phải lớp gốc VietFood, original_class_id=NULL; source_namespace/source_class_id ghi taxonomy owner riêng, không bịa original68..75 của VietFood. Training27 vẫn Củ kiệu, face original27 vẫn bị loại.

Backend hiện v0.4.0 chỉ chấp nhận map67 và SQL/DTO IDs tương ứng; file JSON mới không tự bật model75. Thiết kế tích hợp tiếp theo phải hỗ trợ song song map67/75, nullable original chỉ cho tám lớp mới và provenance rõ; giữ catalog/lịch sử cũ, không rewrite immutable food identity hoặc scan predictions. API contract có thay đổi nullable/range phải version/cập nhật tests/handoff có chủ ý, không đổi snapshots cũ. Không mutate DB trước migration/test được chuẩn bị.

## Nhãn và evaluation

Với một vùng gà/cá hồi nướng đã xác minh, ưu tiên lớp cụ thể mới thay parent Thịt gà/Cá/Thịt nướng; không tạo hai vùng trùng vật thể. Replay cũ phải rà khả năng parent chứa món mới; sửa chỉ bản dẫn xuất và lưu provenance. Không đổi nhãn Chicken/Fish tổng quát thành món cụ thể khi chưa xác minh chế biến/loài.

Open Images có boxable Apple/Banana/Pineapple/Coffee nhưng Coffee cup/Chicken không tự là đồ uống cà phê/ức gà nướng. FoodSeg103 có mask coffee/apple/banana/pineapple; potato là khoai tây, không khoai lang. FoodSeg chicken duck/fish là generic, không được auto-map vào hai món nướng. Wikimedia results có title/license/artist nhưng vẫn là candidates, cần semantic/bbox review, loại generated images và trùng/gần trùng. File nguồn/metadata tải về giữ riêng dưới data/processed/food-extension-v2, không sửa CSV/ảnh/nhãn VietFood.

Split theo nhóm nguồn, kiểm SHA/near-duplicate và không đưa holdout cũ vào replay. Giữ evaluation bộ cũ và holdout mới đủ cả8 lớp trước khi tuyên bố coverage75; các lớp vắng giữNULL. Chưa có kết luận chất lượng75, chưa chạy train mới tại thời điểm chuẩn bị này.

Nguồn đã đọc: [Open Images V7](https://storage.googleapis.com/openimages/web/download_v7.html), [FoodSeg103 tác giả](https://github.com/LARC-CMU-SMU/FoodSeg103-Benchmark-v1), [FoodSeg103 mirror](https://huggingface.co/datasets/EduardoPacheco/FoodSeg103), [Wikimedia Commons](https://commons.wikimedia.org/). Ghi điều kiện/attribution từng asset trong manifest; không dùng Food101.
