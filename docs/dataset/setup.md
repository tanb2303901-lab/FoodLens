# Thiết lập cho bước dữ liệu backend

Đã chọn backend data trước. Bước này chạy local bằng Python standard library; chưa cần API keys hoặc project Supabase.

## Hiện trạng máy ngày 2026-10-14

- Git 2.55.0.windows.5 và uv 0.12.18 chạy được.
- Python Launcher báo chưa có Python cài riêng; lệnh python trên PATH là WindowsApps alias.
- Đã tạo `.venv` bằng runtime Python 3.12.14 của Codex. Dùng trực tiếp interpreter trong .venv; không cần activate hoặc thay ExecutionPolicy.
- Chưa thấy docker, supabase, npm hoặc claude trên PATH ở lần kiểm tra này. Điều đó không chứng minh chúng chưa được cài ở nơi khác.
- Đây là thư mục scaffold chưa khởi tạo Git. Không tự init/commit/push trong bước này.

Kiểm tra môi trường trong PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Nienluan\FoodLens'
& '.\.venv\Scripts\python.exe' --version
```

Môi trường local được tạo bằng lệnh sau (chỉ dùng lại khi .venv chưa tồn tại):

```powershell
& 'C:\Users\Admin\.local\bin\uv.exe' --cache-dir '.\data\processed\.uv-cache' venv --python 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .venv
```

Đường dẫn interpreter trên phụ thuộc runtime của app tại máy này. Máy khác dùng Python riêng tương thích rồi tạo .venv mới; không copy .venv sang máy khác. Chọn/pin dependencies FastAPI và ML trong task sau, không cài chúng chỉ để đọc CSV.

## Nguồn và cấu hình

- CSV root hiện tại: `D:\Tonghop Dataset\Tonghop Dataset`.
- Chủ dự án cung cấp vision root: `E:\DataNLCN\VietFood\dataset`; đã truy cập được và thấy thư mục images/labels. Chưa kiểm tra nội dung ảnh; không bắt buộc cho bước backend.
- `data/data-config.example.json` là template portable.
- `data/processed/data-local.json` là cấu hình máy này, đã nằm trong vùng được .gitignore bỏ qua. File này không chứa credentials.
- Đọc CSV tại nguồn; không cần copy 7 CSV vào repository hoặc thay source paths.

## Chạy validator DATA-01

Theo yêu cầu mới nhất của chủ dự án, Codex đã trực tiếp triển khai DATA-01. Không cần cài Claude Code để chạy validator. Prompt Claude trong docs/tasks được giữ làm tài liệu chuẩn bị trước đây, chưa từng gửi/chạy tự động.

Các lệnh sau đã chạy đạt trên máy này:

```powershell
& '.\.venv\Scripts\python.exe' '.\scripts\validate_dataset.py' --config '.\data\processed\data-local.json' --baseline '.\docs\dataset\source-baseline.json' --report '.\data\processed\DATA-01-validation.json'
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_validate_dataset.py' -v
```

Report JSON nằm trong data/processed. Exit 0 cho cấu trúc hợp lệ (có thể còn review findings), 1 cho lỗi dữ liệu/baseline/ghi report, 2 cho CLI/config sai. Khi nguồn thay đổi, không tự cập nhật checksum để bỏ qua sai lệch. Kết quả hiện tại: 44 tests passed và CLI passed_with_review; xem docs/reviews/DATA-01-implementation.md. DB-01 thiết kế schema/API là bước tiếp theo.

## Thiết lập ở bước Supabase sau DATA-01

DB-01 đã hoàn tất thiết kế và chủ dự án chọn local Docker/WSL2. Hướng dẫn cụ thể cho DB-02 tại `supabase-local-setup.md`; máy hiện báo chưa cài WSL và chưa tìm thấy Docker/Supabase CLI trong các vị trí đã kiểm tra.

Đề xuất ưu tiên stack Supabase local để kiểm thử migration/RLS/Auth/Storage trên database riêng. Cần Supabase CLI và container runtime tương thích, thường là Docker Desktop trên Windows. Chọn cách cài và kiểm tra cấu hình máy trước khi cài; chưa chạy init/start hoặc tạo project cloud ở bước này.

Tài liệu chính thức đã đối chiếu: https://supabase.com/docs/guides/local-development/cli/getting-started

Project Supabase cloud riêng cho phát triển/kiểm thử có thể chuẩn bị sau. Credentials chỉ ghi vào file local được ignore; không gửi secret key vào prompt, docs hoặc Git. Không cần project cloud để kiểm tra CSV. Frontend cần Node/toolchain Expo ở giai đoạn bàn giao, không phải điều kiện của DATA-01.
