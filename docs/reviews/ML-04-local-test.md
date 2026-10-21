# ML-04 — Trang thử ảnh local đã mở

2026-10-16. DONE_LOCAL_TOOL_OPEN. Codex triển khai và tự review, không có review độc lập. Owner yêu cầu mở chỗ test ảnh; không yêu cầu train thêm hoặc triển khai frontend mobile.

## Thực hiện

Khôi phục Docker và đúng năm container FoodLens hiện có bằng ml.local_stack.ensure_local_stack; không recreate/reset/import. Dùng ml.activate_local với bundle foodlens-yolo11n-20261015-budget8h-v1 đã được nghiệm thu trước đó để khởi động lại backend 127.0.0.1:8000. Readiness thật model=ready, database=ready, scan=true. Không chạy pipeline train/evaluation lại.

Thêm scripts/local_scan_test.py và local_scan_test.html. Trang 127.0.0.1:8765 chọn ảnh, gọi multipart POST analyze qua một tài khoản test local riêng và hiển thị tên món từ catalog thật, bbox/confidence từ model thật. Preview lấy ảnh canonical từ private Storage qua server; signed URL không được gửi ra HTML, JSON hoặc log của công cụ. Backend vẫn xác minh JWT/RLS; helper không inject predictor, không dùng admin token thay user JWT. Admin key chỉ dùng tạo tài khoản test riêng khi chưa có session; credentials được giữ trong ignored scan-test-session.json phía server. Login được tái sử dụng/làm mới khi hết hạn.

Helper chỉ bind loopback, chặn Host/Origin/cross-site khác, không CORS và yêu cầu header riêng cho POST. Không fetch URL tùy ý từ browser; upstream cố định backend local, preview chỉ từ signed object path của Supabase local. Không public static folder, không cho tải config/log/session. JSON response không có token, password hoặc private signed URL.

Chỉ là công cụ chẩn đoán local, không thay frontend Expo/React Native, không mở LAN/iPhone. Ảnh upload tạo scan/private object thật dưới owner test và được giữ để thử lại; không thêm vào dataset/train. Chưa duyệt nutrition, không bịa kcal/grams/Top-3. Source CSV/images/labels, README, migrations và canonical API không đổi.

## Kiểm chứng

Syntax compile đạt. Chín kiểm tra HTTP thật đều đạt: page200; credentials không ở page; không public admin/access token; model readiness; foreign Host403; foreign Origin403; thiếu local header403; sai Content-Type415; multipart ảnh hỏng qua backend thật trả422 INVALID_IMAGE. Evidence chỉ chứa bool/status ở ignored data/processed/ML-04-local-test.json.

Browser in-app đã chọn một ảnh effective test qua file chooser, bấm Nhận diện và hiển thị kết quả thật: năm vùng Phô mai, confidence lần lượt83,9/44,3/32,7/29,3/26,1%, canvas canonical640×640. Lượt API đo1172,2ms; đây là một mẫu tương tác, không phải benchmark/SLA. Trạng thái thành công, nút bật lại và không có console error/warning. Screenshot ignored ML-04-local-test.png. Ảnh smoke đã tồn tại trong holdout, không phải ảnh mạng mới và không phải independent quality acceptance.

Trang được mở và giữ trong browser để owner chọn ảnh tải từ mạng. Lượt user upload tiếp theo và nhận diện ảnh mới chưa được chạy thay owner. Hồ sơ runtime/PID nằm trong ignored scan-test-server.json, stdout/stderr chỉ ghi trạng thái an toàn.

## Sử dụng

Mở http://127.0.0.1:8765/ → Chọn ảnh từ máy → Nhận diện. JPEG/PNG/WebP tĩnh, tối đa10MiB; backend kiểm thêm20M pixels/dimension8192. Docker/backend/helper phải chạy. Không dán link ảnh vào ô file; tải ảnh về máy trước. Không cần tự nhập token vào trang này.

Nếu helper đã dừng, xác nhận backend ML đang ready rồi chạy từ root project:

```powershell
& 'data/processed/ml-venv/Scripts/python.exe' -X utf8 scripts/local_scan_test.py
```

Không mở thêm helper khi port8765 đang dùng. Tắt laptop dừng API nhưng không làm mất weights đã train. Không gửi scan-test-session.json hoặc backend/Supabase config cho đồng đội.
