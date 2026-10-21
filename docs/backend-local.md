# Chạy backend FoodLens local

Cập nhật 2026-10-20 (FOOD-02, API 0.7.0). Backend gồm profile, catalog, nhận diện ảnh, lịch sử scan và thông tin món. Dinh dưỡng, bữa ăn và thống kê đã bị gỡ.

## Điều kiện

- Docker Desktop đang chạy với stack Supabase local `foodlens-local` (5 container: db, auth, rest, storage, kong). Nếu stack chưa lên, từ thư mục project chạy lệnh dưới; output có thể chứa key nên ghi vào log bị ignore:

```powershell
& 'data/processed/tools/supabase-2.120.0/supabase.exe' start --workdir 'C:/Nienluan/FoodLens' --exclude 'realtime,imgproxy,postgres-meta,studio,edge-runtime,logflare,vector,supavisor,mailpit' *> 'data/processed/supabase-start.log'
```

- Không chạy `supabase db reset` trên database đang có dữ liệu. **Máy mới (đồng đội):** chỉ cần `scripts/setup_dev.ps1` rồi `scripts/run_dev_backend.ps1`. Hai script này cài môi trường CPU từ `ml/requirements-cpu.txt`, khởi động Supabase, áp migrations, nạp 75 món bằng `scripts/import_dataset.py --from-identities --apply` (không cần CSV) và nạp nội dung, sau đó chạy backend kèm model trong repo. Xem [hướng dẫn cho đồng đội](handoff/teammate-setup-guide.md). Máy chủ dự án vẫn có thể nhập từ CSV bằng `--config`.
- Config thật nằm trong `data/processed` (bị ignore): `backend-local.json` (core, không model) và `backend-ml75.json` (model75 owner-preview). Không gửi các file này hay key trong đó cho ai.

## Chạy server

Backend có model (dùng hằng ngày, cổng 8000):

```powershell
$env:FOODLENS_CONFIG_PATH = 'C:\Nienluan\FoodLens\data\processed\backend-ml75.json'
& 'data/processed/ml-venv/Scripts/python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Backend không model (nhận diện trả 503 `MODEL_NOT_READY`): dùng `.venv` và `backend-local.json`. Trước khi khởi động, kiểm tra cổng 8000 chưa có server khác. Trang thử ảnh: `data/processed/ml-venv/Scripts/python.exe -m scripts.local_scan_test` (cổng 8765).

Thêm `--lan` để điện thoại cùng Wi-Fi mở được trang thử tại `http://<IP Wi-Fi>:8765`. Chế độ này do chủ dự án chủ động bật. Backend và Supabase vẫn chỉ nghe trên loopback; trang thử gọi chúng hộ bằng tài khoản test riêng. Server chỉ chấp nhận đúng các origin đã khai báo. Windows phải đặt Wi-Fi là Private và cho phép cổng 8765 trong Firewall. Bất kỳ ai dùng chung Wi-Fi cũng mở được trang thử, nên chỉ bật khi ở mạng nhà.

- Swagger: http://127.0.0.1:8000/docs
- Readiness: http://127.0.0.1:8000/health/ready
- Contract: [openapi-backend-v1.json](architecture/openapi-backend-v1.json)

## Kiểm thử

```powershell
& '.venv/Scripts/python.exe' -m pytest tests -q
& '.venv/Scripts/python.exe' scripts/test_backend_local.py --class-count 75
& '.venv/Scripts/python.exe' scripts/test_scans_local.py
& '.venv/Scripts/python.exe' scripts/test_handoff_local.py
& '.venv/Scripts/python.exe' scripts/test_food_content_local.py
& '.venv/Scripts/python.exe' scripts/test_description_scan_flow_local.py
& 'data/processed/tools/supabase-2.120.0/supabase.exe' test db supabase/tests/001_foodlens.sql --workdir 'C:\Nienluan\FoodLens'
```

Các script HTTP mở server tạm trên cổng trống (trừ `test_description_scan_flow_local.py` dùng server 8000 đang chạy), tạo tài khoản Auth tạm và tự xóa. SQL test 001, 002, 004, 005 chạy trong transaction rồi rollback. `test_handoff_local.py --write-artifacts` chỉ dùng khi chủ ý sinh lại contract và ví dụ.

## Nội dung mô tả món

Quy trình soạn, duyệt và đồng bộ: [food-content-workflow.md](content/food-content-workflow.md).

## Giới hạn hiện tại

Server của chủ dự án chỉ lắng nghe `127.0.0.1`. `run_dev_backend.ps1` (mặc định chế độ điện thoại, dùng Expo Go) mở backend qua Wi-Fi (bind `0.0.0.0`) và đặt `public_supabase_url`, để link ảnh trả về dùng địa chỉ mà điện thoại truy cập được. Chế độ này chưa được kiểm thử với điện thoại thật. Tunnel, HTTPS và Supabase cloud chưa làm.
