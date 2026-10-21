# DATA-02 — Import CSV backend vào Supabase local

Trạng thái: DONE (2026-10-15). Codex triển khai và tự review; 16 unit tests + 13 integration checks passed. Snapshot thật đã nhập 67/9115/109, zero profiles/portions. Biên bản tại docs/reviews/DATA-02-implementation.md. Chỉ dùng project foodlens-local.

## Mục tiêu và phạm vi

Importer có validate, dry-run mặc định, apply rõ ràng, transaction và import lặp lại không duplicate. Đầu vào: data-local config, source-baseline và food-identities-v1; sources chỉ đọc. Nhập 67 foods, 9.115 versioned references, 109 candidate links. Không nhập vision/audit manifests, không tạo profiles approved hoặc servings.

File được tạo/sửa: scripts/import_dataset.py, tests/test_import_dataset.py, scripts/test_import_local.py, docs/dataset/import-setup.md, docs/reviews/DATA-02-implementation.md, task/status/AGENTS. Generated reports và payloads nằm ignored data/processed. Không sửa README/CSV/class-map/baseline/backend/mobile/ML, không reset/cloud/commit/push/deploy.

## Tiêu chí nghiệm thu

- Validator DATA-01 kiểm tra cả 7 CSV trước khi lập payload; source hash được đối chiếu lại khi build để chặn source đổi giữa validate/import.
- UUID/class identity đúng artifact/remap; raw_record giữ đầy đủ strings/empty; missing normalized numeric thành NULL; raw defects/quality flags giữ nguyên. Source release version chưa biết là NULL.
- Apply foods → references → links và success provenance trong một transaction có khóa concurrent import. Khác checksum cùng version hoặc source columns khác existing data phải fail, không overwrite. Retry không đổi UUID/timestamps/review decisions/approved profiles/portions.
- Dry-run không truy cập database; apply chỉ Docker container Supabase local với fixed project/database. Không nhận URL/key cloud.
- Unit tests kiểm tra NULL/zero/precision, identity, malformed/unsafe mapping, candidate details, SQL escaping và local-only/path guards.
- Integration chứng minh dry-run không ghi DB, failed import rollback cả food/reference/link/run, initial counts, retry/concurrent retry, preservation of review decisions và rejection of drift. Test alterations rollback trên transaction; dữ liệu import thật giữ lại.
- Commands/exit codes/counts/source integrity và giới hạn ghi review; không báo nghiệm thu API/model hoặc approval thật.

## Bước tiếp theo

DATA-02 đạt → chuẩn bị BE-01 config/JWT/catalog/core APIs. Chưa triển khai FastAPI trong task này.
