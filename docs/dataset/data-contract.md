# Hợp đồng dữ liệu backend FoodLens

Phiên bản hợp đồng: 1. Baseline nguồn: 2026-10-12; ngày tiếp nhận: 2026-10-14.

Mục đích bước này là xác nhận dữ liệu có thể làm đầu vào cho thiết kế/import backend. Cập nhật 2026-10-20 (FOOD-02): dinh dưỡng đã bị gỡ khỏi sản phẩm; hai CSV dinh dưỡng vẫn nằm nguyên trong gói nguồn và baseline nhưng không còn được đọc, kiểm tra hay import.

## Phân loại 7 CSV

| File | Vai trò | Baseline số dòng dữ liệu |
| --- | --- | ---: |
| foodlens_classes.csv | Danh mục thực phẩm cho foods | 67 |
| nutrition_reference.csv | Ngoài scope từ FOOD-02; không đọc | 9115 |
| food_nutrition_mapping.csv | Ngoài scope từ FOOD-02; không đọc | 67 |
| foodlens_images.csv | Manifest ảnh phục vụ ML; không seed MVP | 171619 |
| foodlens_dataset.csv | Manifest bbox phục vụ ML; không seed MVP | 838716 |
| dataset_issues.csv | Audit nguồn; không phải danh sách mọi lỗi đang mở | 4134 |
| dataset_summary.csv | Summary để đối chiếu; không thay thế bản ghi nguồn | 595 |

Header, byte length và SHA-256 chính xác được ghi trong `source-baseline.json`.

## Parse và định danh

- Đọc CSV UTF-8 có thể có BOM; dùng parser CSV thật, không split dấu phẩy hoặc đếm newline thô.
- Boolean chỉ nhận giá trị rõ ràng true/false; chuỗi "false" không được chuyển thành true qua truthiness.
- Class IDs là integer: original 0..67 trừ 27; training 0..66. Original <27 giữ nguyên, >27 giảm 1. Training 27 là Củ kiệu, original 28.
- Slug và training/original IDs phải duy nhất trong class map. UUID ổn định và class_map_version sẽ được chốt trong task schema; validator không tự tạo UUID theo một quy tắc chưa chốt.

## Manifest và mức kiểm tra

Baseline giữ 170931 ảnh, 838716 food bbox; 873 ảnh background. 684 ảnh face-only và 4 ảnh có annotations mâu thuẫn bị loại trong manifest; giữ nguyên file nguồn.

| Split hiệu lực | Ảnh | Food bbox | Lớp xuất hiện |
| --- | ---: | ---: | ---: |
| train | 161247 | 822457 | 67 |
| valid | 787 | 1319 | 35 |
| test | 404 | 591 | 29 |
| review | 8493 | 14349 | 67 |

Validator hiện kiểm tra file/header/hash/row count của 5 CSV trong scope, kiểm tra nội dung `foodlens_classes.csv`, dòng summary `food_classes` và audit nguồn. Không yêu cầu ảnh gốc, weights hoặc xuất nhãn training. Các kiểm tra join/bbox từng dòng đã thực hiện khi tiếp nhận được ghi rõ là kiểm tra CSV, không phải kiểm tra ảnh.

Đường dẫn ảnh/label/source_file cũ là provenance, không phải điều kiện để import catalog. Khi làm ML, dùng root cấu hình mới và giữ đường dẫn tương đối đúng, không sửa CSV hoặc dùng TXT gốc 68 IDs trực tiếp với model 67 lớp.

## Mức kết quả

- Structural errors: file/header/CSV/JSON hỏng, boolean sai, duplicate key, class remap sai, summary lệch hoặc baseline thay đổi không được ghi nhận.
- Review findings: audit nguồn được giữ nguyên, thiếu độ phủ holdout, nguồn ảnh chưa xác minh.
- Not checked: database/RLS/Storage, decode/hashing ảnh thật, ngữ nghĩa nhãn, training/inference. Không báo các mục này là passed.
- Nguồn thay đổi hợp lệ cần baseline mới và ghi quyết định riêng; không âm thầm cập nhật checksum để bỏ qua sai lệch.
