# DATA-02 — Import backend CSV

Ngày: 2026-10-15. Kết quả: DONE. Codex trực tiếp triển khai, chạy kiểm thử và tự review; không có lượt Claude Code/Anti hoặc review độc lập.

## Kết quả thực tế

Database Supabase local foodlens-local hiện có 67 foods, 9.115 nutrition_references, 109 food_nutrition_links và 1 completed import_run. Zero food_nutrition profiles và zero food_portions; toàn bộ links vẫn candidate. Không tạo profile approved hoặc serving giả. 853 bản ghi Việt giữ basis/per-100-g NULL và reference_usable=false. Training ID 27 trỏ original 28, original 27 face không có trong foods.

Importer scripts/import_dataset.py tái sử dụng validator DATA-01, mặc định dry-run và apply rõ ràng. Bộ 7 CSV qua kiểm tra file/header/hash/rows/semantics với 0 structural errors, 1.024 review findings được giữ; findings không phải approval. Chỉ nhập 3 CSV nghiệp vụ, không nhập vision manifests/audit vào MVP. Payload đọc từ bytes đã hash lại để source không đổi giữa validate/build. UUID và names/IDs/scope đối chiếu artifact portable.

Raw reference đầy đủ 50 cột giữ string/empty và cờ lỗi nguồn. Numeric normalized parse Decimal rồi nhập numeric không qua float; source release version chưa biết là NULL. Không suy basis, tính 4/9/4 hoặc sửa defects. Foods giữ raw mapping metadata; candidates giữ details JSON và matching/review reasons.

Apply dùng fixed Docker container supabase_db_foodlens-local và project config guard, không nhận cloud URL/key. SQL transaction khóa advisory source version; dữ liệu và completed import provenance commit cùng nhau. Conflict cùng version khác checksum hoặc source columns khác existing data bị từ chối. INSERT ON CONFLICT DO NOTHING kèm kiểm chứng toàn bộ source columns không ghi đè decisions, IDs, timestamps; importer không viết bảng profile/portion/meal.

## Kiểm thử và bằng chứng

Các lệnh trong docs/dataset/import-setup.md đã chạy thực tế, exit 0:

- 16 unittest tests: NULL/zero/precision/negative raw, boolean/date/nonfinite, UUID/class drift, approval/selection denial, malformed/count/duplicate/missing candidates, source bytes drift, SQL escaping, report/local target guards.
- Dry-run: passed_with_review, không truy cập DB. Sau dry-run foods/references/links/import_runs đều 0.
- Integration phase before: 3 checks. Candidate cuối tham chiếu nonexistent record gây FK failure sau foods/references insert; connection kết thúc transaction lỗi, cả 4 bảng trở về 0.
- Apply snapshot thật: completed, counts 67/9115/109/0 approved/0 portions, completed_runs=1.
- Integration phase after: 10 checks. Retry đơn và 2 concurrent retries đạt; counts và import run không tăng. Wrong checksum/same version và raw source drift bị từ chối. Review decision thay thử trong transaction rollback được giữ qua retry; UUID/timestamps và toàn bộ source columns/raw/details khớp 67/9115/109 records. Việt NULL/no approval/no serving/class remap kiểm tra bằng SQL.
- Sau import/test, SHA-256 cả 7 nguồn vẫn khớp baseline.

Reports generated, ignored: data/processed/DATA-02-dry-run.json, DATA-02-import.json và reports -validation.json; DATA-02-before.json, DATA-02-after.json, DATA-02-source-integrity.json. Reports không chứa credentials. Runtime dùng Python .venv 3.12, Docker Engine Linux 29.8.2 và stack DB-02 đã có. Hôm nay Docker chưa chạy; Codex mở Docker Desktop, stack cũ khởi động lại. Không reset, xóa volume hoặc dùng cloud.

## Giới hạn và bước tiếp

Baseline/version v1 cố định; thay nguồn cần quyết định version mới và baseline mới, không được âm thầm ghi đè. Import integration phase after được thiết kế cho snapshot ban đầu (zero profiles/portions và candidates chưa review); sau khi quản trị catalog cần stack test riêng hoặc test plan phù hợp. Không chạy DB-02 HTTP fixture suite trên catalog đã nhập.

Chưa kiểm thử FastAPI/user-facing endpoints, model/ảnh/ML hoặc mobile trong task này; chưa có hồ sơ dinh dưỡng được duyệt. Source/README/class-map/baseline giữ nguyên, không commit/push/deploy. Bước kế tiếp BE-01 cấu hình, health/readiness, xác minh JWT và catalog trước các luồng bữa ăn/scan.
