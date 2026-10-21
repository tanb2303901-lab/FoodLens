# FOOD-03: chuẩn bị repo để đồng đội tự chạy backend

Ngày 2026-10-20. Người thực hiện: Claude Code, theo yêu cầu trực tiếp của chủ dự án. Chỉ tự kiểm thử, không có review độc lập. **Chưa commit, chưa push.** Chủ dự án sẽ tự báo khi nào push.

## Quyết định của chủ dự án

- Repo GitHub `tanb2303901-lab/FoodLens` để **public**; đồng đội đã là collaborator.
- Đưa model đã train vào repo để đồng đội chỉ cần clone, không phải train lại.
- Khi được phép, push thẳng lên `main`.
- Viết hướng dẫn từng bước cho đồng đội. Chủ dự án tự gửi hướng dẫn này; Claude Code không liên hệ đồng đội.

## Thay đổi

- `.gitignore`: chỉ theo dõi đúng bundle `ml/models/foodlens-yolo11n-20261016-extension4h-v2/`, gồm 6 file, khoảng 26 MB. Không đưa dataset, các checkpoint khác, `data/processed`, `.venv` hay `.env` lên repo.
- `scripts/import_dataset.py --from-identities`: nạp danh mục món từ `docs/dataset/food-identities-v2.json`, không cần CSV. Lệnh `--check-database` trên database của chủ dự án cho kết quả khớp.
- `backend/app/config.py`: thêm `public_supabase_url` (tùy chọn). `scans.py` chỉ đổi origin của link ảnh trả về cho app; host dùng để gọi Supabase giữ nguyên. Test thêm: `test_public_supabase_origin_rewrites_only_returned_image_url`.
- `ml/requirements-cpu.txt`: phiên bản giống bộ lock của chủ dự án nhưng dùng torch CPU.
- `scripts/prepare_dev_config.py`, `scripts/setup_dev.ps1`, `scripts/run_dev_backend.ps1`:
  - Cài và chạy backend kèm model bằng một lệnh, với tùy chọn `-Device phone|local` và `-HostIp`. Sau quyết định của chủ dự án dùng Expo Go trên điện thoại ngay từ đầu, mặc định là `phone`; chế độ máy ảo Android đã bị bỏ.
  - `-SupabaseCli` cho phép dùng `supabase.exe` có sẵn thay cho `npx`.
  - Script kiểm tra exit code thay vì coi mọi dòng stderr là lỗi. Windows PowerShell 5.1 làm hỏng bước `supabase start` khi dùng `Stop`.
- Tài liệu:
  - [teammate-setup-guide.md](../handoff/teammate-setup-guide.md)
  - Cập nhật [backend-local.md](../backend-local.md) và [backend-v1.md](../handoff/backend-v1.md)

## Kiểm thử đã chạy

1. **Cài mới tách biệt.**
   - **Thiết lập:** sao chép đúng các file sẽ lên git (`git ls-files -co --exclude-standard`, 209 file) vào thư mục tạm. Bản sao đổi `project_id` thành `foodlens-fresh` và chuyển các cổng 5432x sang 5532x; repo thật không bị sửa. Chạy `setup_dev.ps1 -SupabaseCli ...` từ đầu.
   - **Kết quả:**
     - `.venv` mới cài đủ `requirements-cpu.txt` (torch 2.11.0, ultralytics 8.4.158).
     - Supabase mới áp đủ migrations.
     - Nạp danh mục bằng `--from-identities` và nạp nội dung (lúc thử: 49 published, 25 draft, 85 nguồn; sau đó FOOD-01 lượt 3 đưa lên 75/75 published, 86 nguồn); database có 75 món.
   - **Lần chạy đầu thất bại** ở bước Supabase vì lỗi stderr của PowerShell 5.1. Sau khi sửa, lần chạy lại đạt.
2. **Backend của bản sao** (`run_dev_backend.ps1 -Port 8100`, chạy với chế độ máy ảo Android lúc đó còn tồn tại; `public_supabase_url` là `10.0.2.2`) với model trong repo chạy trên CPU:
   - `/health/ready`: catalog và scan đều `true`.
   - Đăng ký và đăng nhập qua `/auth/v1/signup` bằng anon key, gọi theo host `localhost`; `/v1/me` trả 200.
   - `POST /v1/scans/analyze` trả 201 với model `dual75`: 5 khung, gộp thành 1 món (Phô mai, `description_unavailable` vì còn nháp).
   - Lịch sử có 1 scan.
   - Link ảnh trả về có origin `http://10.0.2.2:55321`; khi đổi về loopback, ảnh tải được (200).
   - Token lấy qua host khác vẫn có `iss` cố định là `http://127.0.0.1:55321/auth/v1`, nên cấu hình issuer không cần đổi theo thiết bị.
   - Đã xóa tài khoản tạm và 1 ảnh; sau đó gỡ stack `foodlens-fresh` bằng `stop --no-backup`.
3. **Chế độ điện thoại (mặc định mới), chạy lại trên bản sao tách biệt:**
   - Chạy lại `setup_dev.ps1` sau khi bỏ URL máy ảo: đạt, 75 món.
   - `run_dev_backend.ps1 -Port 8100` tự chọn đúng IP của card `Wi-Fi 2` (`192.168.1.12`), bỏ qua card vEthernet/WSL và các địa chỉ 169.254; backend bind `0.0.0.0`.
   - Gọi qua IP Wi-Fi: `/health/ready` trả scan=true; Supabase Auth health trả 200; luồng thật gồm đăng ký, `/v1/me` 200, analyze 201 (5 khung, 1 món), lịch sử và chi tiết scan.
   - Link ảnh trả về có origin `http://192.168.1.12:55321` và tải trực tiếp được (200).
   - Đã dọn tài khoản, ảnh và stack thử.
   - **Giới hạn:** các request này xuất phát từ chính máy chủ dự án, nên chưa đi qua Windows Firewall và chưa dùng điện thoại thật.
4. **`pytest tests`:** 266 passed, 23 subtests.
5. **Quét secret** trên các file sẽ lên git: không có key thật. Chỉ có placeholder trong `backend/config.example.json` và chuỗi giả trong `tests/backend/test_core.py`.
6. **Backend 8000** (`backend-ml75.json`) và **trang thử 8765** được khởi động lại sau khi Docker restart: `ready`, `scan=true`, UI trả 200.

## Kiểm tra lại script cài đặt trước khi giao (2026-10-21)

- **Sửa script:**
  - `prepare_dev_config.py` luôn lấy key hiện tại từ `supabase status`, vì stack có thể đã bị tạo lại; `cursor_secret` giữ nguyên.
  - `run_dev_backend.ps1` ghi lại `supabase-local.json` mỗi lần chạy.
  - Cả hai script ép Python dùng UTF-8.
  - Bước 7 của `setup_dev.ps1` báo lỗi nếu chưa đủ 75 món, 75 bài giới thiệu đã published, hoặc chưa import được backend, ultralytics và torch.
- **Cài mới trên bản sao tách biệt** (đúng các file sẽ lên git, stack mới `foodlens-fresh`):
  - Đủ 7 bước: 75 món, 75 bài giới thiệu.
  - Chạy lại lần hai trên cùng stack vẫn đạt; config được giữ, dữ liệu không đổi.
  - Chế độ điện thoại `-Port 8100`, gọi qua `192.168.1.12`:
    - `/health/ready` trả scan=true; `/v1/me` 200.
    - Analyze 201: 5 khung, Phô mai `available`.
    - Lịch sử có scan; link ảnh tải trực tiếp được.
  - Đã dọn tài khoản, ảnh và stack thử.

## Chưa kiểm thử hoặc giới hạn

- Chưa chạy trên máy của đồng đội và chưa thử qua `npx` (máy chủ dự án không có Node.js).
- Chưa thử với điện thoại thật. Phần dò IP Wi-Fi và bind `0.0.0.0` của `-Device phone` mới được kiểm tra trên máy chủ dự án (xem bên dưới). Rule Firewall chưa được tạo.
- Chất lượng model75 vẫn ở trạng thái owner-preview như trong ML-05. Đưa model lên repo không làm thay đổi kết luận chất lượng.
- Repo public nghĩa là ai cũng tải được model và nội dung mô tả.
