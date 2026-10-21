# Import catalog backend

Cập nhật 2026-10-20 (FOOD-02). Importer chỉ nhập 67 món VietFood từ `foodlens_classes.csv`, đối chiếu với [food-identities-v1.json](food-identities-v1.json). 8 món mở rộng được tạo bởi migration `20261016000100`. Nutrition references và candidate links không còn được nhập; hai CSV dinh dưỡng trong gói nguồn giữ nguyên, không đọc. Source version `foodlens-source-2026-10-12-v1`, class map `vietfood-67-2026-10-12-v1`.

Cấu hình máy nằm trong ignored `data/processed/data-local.json`; `csv_root` có thể đổi theo máy, CSV nguồn giữ nguyên.

```powershell
# Validate CSV trong scope và lập payload trong bộ nhớ; không truy cập DB.
& '.venv/Scripts/python.exe' scripts/import_dataset.py --config data/processed/data-local.json --report data/processed/import-dry-run.json

# Chạy import trên DB thật trong transaction rồi rollback (kiểm tra khớp dữ liệu hiện có).
& '.venv/Scripts/python.exe' scripts/import_dataset.py --config data/processed/data-local.json --report data/processed/import-check.json --check-database

# Nhập thật vào container cố định supabase_db_foodlens-local.
& '.venv/Scripts/python.exe' scripts/import_dataset.py --config data/processed/data-local.json --report data/processed/import-apply.json --apply
```

Import chạy trong một transaction có khóa advisory: INSERT ON CONFLICT DO NOTHING, nhưng trước đó đối chiếu toàn bộ cột với món đã có; dữ liệu lệch thì dừng thay vì ghi đè. `source_mapping_metadata` chỉ chứa khóa định danh (slug, scope, tên, class ID). Báo cáo phải nằm trong ignored `data/processed`. Script chỉ dùng `docker exec psql` trong container local, không nhận URL hay credentials.

Lịch sử lần import đầu (gồm cả dinh dưỡng khi đó): [DATA-02](../reviews/DATA-02-implementation.md).
