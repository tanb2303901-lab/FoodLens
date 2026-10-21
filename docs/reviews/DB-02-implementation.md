# DB-02 — Supabase local implementation

Ngày: 2026-10-14. Kết quả: DONE. Codex triển khai, kiểm thử và tự review; không có review độc lập hoặc lượt thực thi Claude Code/Anti.

## Kết quả

7 migrations trong supabase/migrations đã áp dụng vào stack FoodLens local mới. Schema gồm catalog/reference/candidate/profile/portion, profiles, scans, meals/items và private receipts/import_runs. Auth trigger tạo profile; RLS và grants giới hạn đọc theo chủ sở hữu, chặn direct user DML. Mutation RPC dùng role foodlens_rpc không BYPASSRLS, search_path cố định; public wrappers là SECURITY INVOKER. Private schema không expose qua REST.

Meal RPC lưu meal/items/receipt trong một transaction, khóa idempotency theo user/key, trả replay trước kiểm tra revision/existence, từ chối payload khác cùng key và bảo toàn snapshots khi sửa grams. Unknown nutrients giữ NULL. Stats dùng múi giờ và ranh giới ngày địa phương.

Bucket food-scans private, tối đa 10 MiB, JPEG/PNG/WebP. Chỉ server upload; user có quyền đọc/sign ảnh thuộc scan của mình. Storage DELETE có thể trả HTTP 200 với danh sách rỗng khi không có hàng được phép xóa: test xác minh ảnh vẫn tồn tại, sign/download vẫn đúng bytes.

HTTP integration phát hiện lỗi alias JSON trùng biến PL/pgSQL trong xác nhận scan; migration 007 sửa và test xác minh confirmations đổi mà detections giữ nguyên. Auth bridge dùng SQL-standard parsed body để gọi auth.uid() dưới role RPC có quyền hạn chế, không nâng role thành BYPASSRLS. Trigger/ACL fixes nằm trong migrations 005–006. Approved synthetic nutrition chỉ tồn tại trong transaction SQL đã rollback.

## Môi trường và thực thi

- Docker Desktop 4.95.0; Engine 29.8.2, linux/amd64.
- Supabase CLI 2.120.0, pin trong supabase/cli-version.txt. Binary chính thức lưu ignored data/processed/tools/supabase-2.120.0. SHA256 archive đã đối chiếu checksums chính thức: 53920013d24bc9e66180f35ceeea9ddc20e65a7afa883421e9c0ba60ad7457ee.
- Project foodlens-local, PostgreSQL 17.11.0.004; Auth, REST, Storage, Kong chạy. Studio/Realtime/Edge/mail/analytics không bật ở bước này.
- API http://127.0.0.1:54321; database port 54322. Credentials trong ignored data/processed/supabase-local.json; không đưa vào báo cáo.
- Trước khởi tạo không có Docker containers. Không chạy db reset, không xóa volume và không kết nối cloud.

Chạy từ C:\Nienluan\FoodLens:

```powershell
& 'data/processed/tools/supabase-2.120.0/supabase.exe' migration up --local --workdir 'C:\Nienluan\FoodLens'
& 'data/processed/tools/supabase-2.120.0/supabase.exe' test db --workdir 'C:\Nienluan\FoodLens'
& '.venv/Scripts/python.exe' scripts/test_supabase_local.py --local-config data/processed/supabase-local.json --report data/processed/DB-02-integration.json
```

Migration up exit 0. pgTAP: 1 file, 72 tests, PASS, exit 0. HTTP unittest: 12 tests, 0 failures/errors, exit 0. Generated HTTP report: data/processed/DB-02-integration.json.

## Bằng chứng nghiệm thu

SQL kiểm tra grants/RLS/role/function ownership, Auth trigger, food identity, approved profile invariants, finite numerics, source evidence, unknown fields, grams/timestamp/timezone validation, rollback, partial/all-missing totals, revision, replay create/patch/delete, preservation of retired profile snapshots và mismatch profile/portion.

HTTP dùng Auth A/B đăng nhập thật, JWT sai/anon bị chặn, REST column/internal provenance grants, direct DML denied, owner-isolated meals/scans, 4 create requests đồng thời cùng key chỉ tạo 1 meal, payload conflict, rollback không chiếm key, scan confirmation, cross-owner/unknown/duplicate detection, signed image bytes, private public-URL denial, upload/overwrite/delete denial và ngày DST 23 giờ ở New York.

Sau cleanup, truy vấn SQL xác nhận foods=0, auth.users=0, approved_profiles=0, storage.objects=0, meals=0, mutation_receipts=0. Fixtures SQL rollback; HTTP chỉ dọn resources nó tạo. Script HTTP từ chối chạy khi đã có catalog/Auth accounts: sau DATA-02 không chạy lại trên database có dữ liệu mà cần một stack test mới riêng.

## Phạm vi còn lại

Chưa nhập 67 foods/9.115 references/109 candidates; đây là DATA-02. Chưa kiểm thử FastAPI endpoints, inference/model thật, mobile hoặc nutrition production được duyệt. DATA-01 sources/README không sửa. Không commit/push/deploy. Bước kế tiếp chuẩn bị importer với validate/dry-run/idempotency, zero approved profiles.
