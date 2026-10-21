# Quy trình dữ liệu mô tả món — FOOD-01

Ngày 2026-10-19. Claude Code soạn quy trình, công cụ và bản nháp đợt 1, đợt 2 theo yêu cầu trực tiếp của chủ dự án. Không có review độc lập và chưa có người duyệt nội dung.

## Phạm vi nội dung

Sau khi nhận diện, ứng dụng hiển thị phần giới thiệu ngắn về món theo `food_id` canonical: giới thiệu, nguồn gốc (nếu có căn cứ), nguyên liệu thường gặp ở mức khái quát và đặc điểm. Không gồm công thức, định lượng, dinh dưỡng hay lời khuyên sức khỏe. API luôn kèm câu lưu ý cố định rằng đây là thông tin phổ thông, không phải tư vấn sức khỏe, dinh dưỡng hay y tế.

Dữ liệu dinh dưỡng chưa bao giờ được dùng làm nguồn cho nội dung mô tả. Từ FOOD-02 (2026-10-20), toàn bộ phần dinh dưỡng và bữa ăn đã bị gỡ khỏi backend theo quyết định chủ dự án; backup nằm ngoài repo.

## Nguồn sự thật và trạng thái

- Nguồn sự thật là [food-descriptions-vi-v1.json](food-descriptions-vi-v1.json): danh sách `sources` và `descriptions`. Mỗi mô tả gắn `food_id`, `slug`, `name_vi` khớp chính xác [map75](../dataset/food-identities-v2.json).
- Mỗi field có nội dung phải được ít nhất một nguồn hỗ trợ (`sources[].supports`) và có `locator` chỉ đoạn/mục trong nguồn. Field không có căn cứ để `null` (ví dụ `origin_text` của Gỏi cuốn), không tự điền.
- Lớp `broad_food_category` (Cà phê, Nước ngọt, Xôi, Lẩu, Canh, Salad, Thịt nướng) bắt buộc có `scope_note` nói rõ ảnh không xác định được biến thể. Các lớp owner mở rộng như Gà nướng, Cá hồi nướng, Khoai lang cũng có `scope_note`.
- Trạng thái: `draft` → `reviewed` → `published` → `retired`.
  - `draft`: bản nháp, kể cả bản AI hỗ trợ đã đối chiếu nguồn. API không trả nội dung này.
  - `reviewed`: một người có tên đã kiểm từng thông tin với nguồn. Hệ thống lưu `content_sha256` của đúng văn bản + trích dẫn được duyệt; sửa bất kỳ chữ nào sau đó sẽ bị validator và database từ chối, phải tạo version mới.
  - `published`: người phát hành có tên cho phép hiển thị trong app. Chỉ bản `published` hiện hành được API trả về.
  - `retired`: bản cũ khi version mới được publish; vẫn giữ lịch sử, không xóa.
- Validator từ chối người duyệt hoặc người phát hành mang tên công cụ (Claude, Codex, GPT, Gemini, Antigravity, Copilot, AI, bot…). Công cụ AI chỉ được ghi ở `drafted_by` và `source_check`.

## Chính sách nguồn

- Ưu tiên nguồn có thẩm quyền: trang du lịch chính thức `vietnam.travel` (Viet Nam National Authority of Tourism), cơ quan nhà nước, bảo tàng, trường đại học, sách.
- Bách khoa mở (Wikipedia, CC BY-SA 4.0) chỉ dùng khi ghi rõ giấy phép và ghim revision (`oldid`) để người duyệt mở đúng phiên bản đã đọc. Đây là nguồn mở, không phải chuyên gia; người duyệt nên đối chiếu thêm khi có thể.
- Không sao chép nguyên văn. Mỗi bản nháp được viết lại bằng lời riêng; công cụ kiểm trùng báo lỗi nếu một field lặp từ 8 từ liên tiếp trở lên của nguồn.
- Britannica được thử nhưng chặn truy cập tự động (HTTP 403) nên không được dùng làm nguồn đợt này; không có URL nào được ghi khi chưa tải và đọc được.

## Cách soạn đợt 1 (đã thực hiện)

1. Chọn món: tám lớp owner bổ sung, Phô mai (đã dùng trong thử UI) và các món Việt có trang `vietnam.travel` hoặc bài Wikipedia đối chiếu được trong ngày.
2. Tải văn bản nguồn: trang VNAT qua HTTPS, Wikipedia qua API với revision cụ thể.
3. Đối chiếu từng mệnh đề với đoạn nguồn; bỏ mệnh đề không tìm thấy. Nguồn gốc mơ hồ được viết thận trọng ("thường được gắn với", "được cho là") hoặc để trống.
4. Chạy kiểm trùng nguyên văn; 12 câu bị phát hiện quá sát nguồn đã được viết lại, lần chạy cuối 0 phát hiện.
5. Ghi tất cả là `draft`, `authoring_method=ai_assisted_draft`, `source_check.human_review=pending`.

Kết quả đợt 1: 35 bản nháp, 35 nguồn, 83 liên kết nguồn.

## Đợt 2 (đã thực hiện cùng ngày)

Áp dụng cùng quy trình cho 40 lớp còn thiếu, chỉ nối thêm entry mới vào JSON (đợt 1 giữ nguyên từng byte nội dung). Nguồn mới: 8 trang `vietnam.travel` và 42 bài Wikipedia ghim revision (39 tiếng Việt, 3 tiếng Anh). Kiểm trùng lần đầu báo 25 câu quá sát nguồn, sau hai lượt viết lại còn 0. Kết quả: 39 bản nháp mới. **Canh** để `missing`: chỉ tìm được trang định hướng "Canh (định hướng)" và bài "Nước dùng", không đủ căn cứ mô tả lớp này; lý do được ghi trong `batches[1].missing_with_reason`.

Tổng sau hai đợt: 74 bản nháp, 85 nguồn, 178 liên kết nguồn, 1 lớp thiếu. Xem [bảng độ phủ](food-descriptions-coverage.md).

## Đọc bản nháp trên trang thử

Mở `http://127.0.0.1:8765/`, chọn ảnh và bấm Nhận diện. Phần "Thông tin món" hiện trạng thái API thật cho từng món; với món chưa duyệt, mở "Xem bản nháp chưa duyệt" để đọc nội dung và bấm vào từng nguồn để đối chiếu. Trang chỉ để xem; việc duyệt vẫn dùng các lệnh bên dưới.

## Lệnh cho người duyệt và chủ dự án

Từ thư mục project, dùng `.venv` hiện có:

```powershell
# Kiểm tra cấu trúc, nguồn, câu chữ ngoài phạm vi và hash đã duyệt
& '.venv/Scripts/python.exe' scripts/food_content.py validate
# Tải lại nguồn đã trích dẫn vào data/processed/FOOD-01-sources (ignored) và kiểm trùng nguyên văn
& '.venv/Scripts/python.exe' scripts/content_source_check.py fetch
& '.venv/Scripts/python.exe' scripts/content_source_check.py overlap
# Sau khi tự đọc nguồn và đồng ý với từng câu của một món
& '.venv/Scripts/python.exe' scripts/food_content.py review --slug pho --reviewer "Họ tên người duyệt" --notes "Đã đối chiếu VNAT và Wikipedia oldid"
& '.venv/Scripts/python.exe' scripts/food_content.py publish --slug pho --publisher "Họ tên người phát hành"
# Đồng bộ vào Supabase local: mặc định chạy thử rồi rollback; thêm --apply để ghi
& '.venv/Scripts/python.exe' scripts/food_content.py apply
& '.venv/Scripts/python.exe' scripts/food_content.py apply --apply
& '.venv/Scripts/python.exe' scripts/food_content.py status --write-coverage
```

Muốn sửa câu chữ của một món đã `reviewed`/`published`: thêm entry mới cùng `slug`, `version` tăng 1, trạng thái `draft`, rồi duyệt lại. Bản cũ tự chuyển `retired` khi bản mới được publish. Không xóa entry đã duyệt khỏi JSON; `apply` không bao giờ xóa hàng trong database và từ chối nếu nội dung đã duyệt bị thay đổi.

## Đợt 3 (2026-10-19, theo yêu cầu chủ dự án)

Sửa 6 bản nháp để bỏ chi tiết lạc đề hoặc nhạy cảm:

- Nước ngọt: bỏ lịch sử châu Âu và danh sách phụ gia; nguồn gốc để trống.
- Khoai lang: bỏ ý "nhiều tinh bột".
- Lòng heo: bỏ chi tiết tiết canh.
- Thịt heo: không lặp lại nội dung của lớp Heo quay.
- Cá: bỏ số lượng loài.
- Rau: bỏ phần định nghĩa học thuật.

Soạn **Canh** từ mục "Canh" của bài Wikipedia "Ẩm thực Việt Nam" (oldid 75524867). Mục này nêu canh là món cơ bản không thể thiếu, từ bữa cơm gia đình đến bữa tiệc. Kiểm trùng nguyên văn cho 0 phát hiện.

Chủ dự án quyết định trong chat duyệt và phát hành toàn bộ 26 bản nháp còn lại, không đọc lại từng câu của bản cuối; quyết định được ghi trong `review.notes`. Kết quả: 75/75 published, 86 nguồn.

## Việc tiếp theo cho nội dung

Đã đủ 75/75 món. Với nguyên liệu chung và Canh, bài Wikipedia là nguồn mở ít chú thích; khi duyệt nên đối chiếu thêm nguồn đại học hoặc cơ quan nông nghiệp. Mỗi lần mở rộng: thêm nguồn → soạn draft → `validate` → `content_source_check.py fetch/overlap` → người duyệt → `publish` → `apply --apply` → `status --write-coverage`.
