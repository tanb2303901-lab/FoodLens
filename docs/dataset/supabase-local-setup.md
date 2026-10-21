# Chuẩn bị Supabase local cho FoodLens

Ngày 2026-10-14, chủ dự án chọn Supabase local với Docker/WSL2. DB-01 thiết kế làm được ngay; DB-02 chạy migration/RLS/Auth/Storage cần container runtime hoạt động. Không cần tạo project Supabase cloud hoặc gửi keys cho bước local.

## Hiện trạng đã kiểm tra

Cập nhật sau DB-02: WSL2/Docker đã cài; Docker Engine Linux 29.8.2 chạy được. Supabase CLI 2.120.0 đã pin và stack foodlens-local đã khởi chạy. 72 SQL + 12 HTTP integration tests passed. Các ghi chú thiếu công cụ dưới đây là hiện trạng trước setup; biên bản tại docs/reviews/DB-02-implementation.md.

- Python .venv, Git và uv chạy được.
- `wsl --status` báo WSL chưa được cài. Chưa tìm thấy docker/supabase/npm trên PATH hoặc Docker ở đường dẫn all-users mặc định; chưa xác minh mọi vị trí cài đặt khác.
- Registry báo build 26300, nhưng tên product cũ không đủ xác nhận edition Windows thực tế. Dùng winver/System About khi kiểm tra điều kiện Docker. Chưa kiểm tra RAM, BIOS virtualization hoặc quyền quản trị; không tự thay các thiết lập này.

## Phần chủ dự án cần chuẩn bị trước DB-02

1. Mở PowerShell bằng Run as administrator, cài WSL:

```powershell
wsl --install
```

Khởi động lại nếu Windows yêu cầu; hoàn tất tạo Linux user nếu được nhắc. Cập nhật và kiểm tra:

```powershell
wsl --update
wsl --version
wsl --status
wsl --list --verbose
```

Chọn WSL2 backend; nếu có distro đang version 1, đổi đúng distro được liệt kê, không đoán tên. Docker hiện yêu cầu WSL >=2.1.5, Windows được hỗ trợ, RAM >=8 GB và hardware virtualization bật. Nếu install báo lỗi, gửi nguyên thông báo lỗi trước khi sửa BIOS/features theo phỏng đoán.

2. Cài Docker Desktop từ trang chính thức, chọn WSL2 backend và Linux containers, rồi mở Docker Desktop và đợi engine running:

https://docs.docker.com/desktop/setup/install/windows-install/

3. Mở PowerShell mới sau khi cài để nhận PATH; kiểm tra:

```powershell
docker version
docker info --format '{{.OSType}}'
```

`docker version` phải có cả Client và Server không báo engine connection error; OSType phải linux. Không chỉ báo đã cài installer: DB-02 cần engine chạy được. Khi hai kiểm tra này đạt, báo lại để Codex chuẩn bị CLI/project local.

## Phần Codex sẽ làm trong DB-02

- Chuẩn bị Supabase CLI phiên bản stable được pin ở project. Máy hiện thiếu npm/Scoop, nên ưu tiên binary từ release chính thức vào ignored data/processed/tools; không yêu cầu cài Node chỉ cho CLI. Chọn và ghi chính xác version sau khi kiểm tra release/checksum, chưa có binary/version được cài ở DB-01.
- Initialize project Supabase local trong thư mục hiện có, cấu hình exposed schema/public/private bucket và pin version. Kiểm tra CLI init không ghi đè migration/config có sẵn.
- Start stack local, tạo migration và chạy tests trên môi trường riêng của FoodLens. Auth test users A/B và Storage local được tạo cho nghiệm thu; secrets/token chỉ lưu local được ignore, không paste vào chat/docs.
- Không dùng lệnh reset/delete volumes nếu phát hiện database có dữ liệu không rõ nguồn. Trước khi cần reset local phải chứng minh đó là DB test mới/disposable; không reset database cloud hoặc project có dữ liệu người dùng.

## Nguồn chính thức

Để chạy lại stack sau khi mở Docker Desktop, từ C:\Nienluan\FoodLens:

```powershell
& 'data/processed/tools/supabase-2.120.0/supabase.exe' start --workdir 'C:\Nienluan\FoodLens' --exclude 'realtime,imgproxy,postgres-meta,studio,edge-runtime,logflare,vector,supavisor,mailpit'
```

CLI có thể in local credentials; không gửi nguyên output vào chat. API http://127.0.0.1:54321; Studio chưa bật. Không cần npm/Node hoặc Supabase cloud cho DATA-02. Không reset database đã import; HTTP fixture suite yêu cầu catalog/Auth trống, cần stack test riêng khi đã có dữ liệu.

- Microsoft WSL: https://learn.microsoft.com/en-us/windows/wsl/install
- Docker Windows/WSL requirements: https://docs.docker.com/desktop/setup/install/windows-install/
- Supabase CLI/local stack: https://supabase.com/docs/guides/local-development/cli/getting-started
- CLI releases: https://github.com/supabase/cli/releases

Các lệnh cài WSL/Docker ở trên dành cho chủ dự án chạy khi chuẩn bị máy; Codex chưa chạy chúng hoặc cài Docker trong DB-01. Khi lỗi setup xuất hiện, kiểm tra dựa trên lỗi thực tế, không coi việc chưa cài Docker là lỗi schema.
