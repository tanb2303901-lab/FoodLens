# VietFood — kết quả audit ML-01

Ngày 2026-10-15. Codex thực hiện và tự review; 0 lỗi structural/file/label/CSV đối chiếu, có các giới hạn đánh giá cần giữ rõ. Không phải model accuracy hoặc semantic label acceptance.

## Đã kiểm tra trên máy hiện tại

- Inventory đệ quy171.619 ảnh, tổng26.356.021.871 bytes và172.956 file nhãn. Tất cả image paths/presence/byte sizes khớp manifest; không bỏ sót labels/train/train.
- Đọc/hash toàn bộ172.956 label copies; parse171.619 preferred labels. Có1.337 bản sao nhãn train ngoài thư mục nested; nội dung/SHA khớp preferred/source manifest.
- Đối chiếu toàn838.716 bbox CSV với nhãn gốc theo image ID, physical line, original class và tọa độ. Face original27 được bỏ; original28 map thành training27 hợp lệ. Numeric lexical forms tương đương được chuẩn hóa; bounds chấp nhận sai số floating tối đa1e-6 ở cạnh ảnh.
- Decode659 ảnh mẫu deterministic: train128, valid137, test130, review136, excluded128. Chọn128 ảnh cơ sở mỗi effective split theo SHA-256(image_id), bổ sung đại diện class/status/reason. Không lỗi decode trong mẫu; không suy thành full decode.
- SHA-256/CRC32 của662 ảnh mẫu/duplicate candidates khớp archive CRC. Hai nhóm ảnh trùng nội dung được xác nhận gồm4 ảnh đã excluded vì nhãn mâu thuẫn; không đưa chúng lại vào dataset.
- Cả7 CSV khớp baseline SHA/bytes trước và sau audit. Script không sửa source CSV/ảnh/nhãn hoặc đổi split nguồn.

| Effective split | Ảnh | Food bbox | Lớp có GT | Background |
| --- | ---: | ---: | ---: | ---: |
| train | 161247 | 822457 | 67 | 630 |
| valid | 787 | 1319 | 35 | 1 |
| test | 404 | 591 | 29 | 1 |
| review | 8493 | 14349 | 67 | 241 |

Tổng included170.931 ảnh; excluded688 gồm684 face-only và4 nhãn mâu thuẫn.873 background được giữ trong included manifest. Tổng49.468 face boxes trong raw labels được nhận diện và không vào food bbox export. Original splits vẫn train161.733/valid6.602/test3.284; effective review không phải thư mục ảnh vật lý.

## Source-group và coverage

Exact source_video_key/source_name_prefix overlap giữa train với effective valid/test là0 theo metadata hiện có. Review giữ147 video keys trùng train (1.543 ảnh) và350 name prefixes trùng train (6.963 ảnh); các tập ảnh này có thể giao nhau nên không cộng số ảnh để tính tổng.

source_video_family có overlap1 family/1 ảnh valid; family đó là `mp4_filename`, chỉ là loại quy ước đặt tên. Nó không chứng minh cùng một video; exact video key của ảnh là101 và không trùng train. Giữ findings để review provenance, không tự coi family marker là nguồn video cụ thể hoặc tự sửa split.

[Coverage từng lớp](vision-coverage-v1.json) chứa counts images/bboxes và class-map SHA. Valid/test chỉ đo được35/29 lớp hiện diện. Các lớp vắng phải hiện unmeasured/NULL trong evaluation; không dùng mean AP lấp cho chúng hoặc tuyên bố holdout đầy đủ67 lớp. Không dùng review hoặc test để lựa chọn hyperparameters.

## Giới hạn và kế tiếp

Chưa full decode/pixel/perceptual hash toàn ảnh, xác minh ngữ nghĩa mọi bbox hoặc chứng minh nguồn video độc lập tuyệt đối. Hash/CRC trong audit ban đầu chỉ662 ảnh; exporter ML-02 đọc/copy/hash/CRC toàn162.438 ảnh train/valid/test trên bản dẫn xuất và báo kết quả riêng khi hoàn tất. SHA/CRC file khác không loại được near-duplicate hoặc các frame cùng video.

Kết quả đủ để chuẩn bị baseline detector với giới hạn đã nêu. Bước ML-02 tạo ảnh/nhãn dẫn xuất67 lớp, giữ review/excluded ngoài train/eval; ML-03 đánh giá và nối model thật. Không đổi trạng thái nutrition hoặc coi 0 lỗi audit là model đã ready.
