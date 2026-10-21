# DB-01 Kết quả thiết kế

Ngày 2026-10-14. Trạng thái: DONE trong phạm vi thiết kế. Chủ dự án chọn Supabase local với Docker/WSL2 và tiếp tục để Codex thực hiện trực tiếp.

## Kết quả

- schema-v1.md chốt 9 bảng public theo SRS và 2 bảng private cho receipts/import provenance. Có kiểu dữ liệu, identity, FK composite, versioning, constraints/indexes và luồng RPC/transaction cụ thể.
- access-control-v1.md chốt grants + RLS, limited writer role, public invoker/private definer RPC, server-only prediction writes và private Storage.
- api-v1.md/openapi-v1.json chốt 14 paths, 18 operations, 37 schemas, Bearer auth, nullable nutrition, class metadata, request validation, idempotency/revision/pagination và mã lỗi.
- food-identities-v1.json chốt 67 food UUIDv5, namespace/name template bất biến, class map/version và checksum class source.
- supabase-local-setup.md hướng dẫn phần người dùng chuẩn bị; DB-02.md ghi implementation boundaries và ma trận kiểm thử migration/RLS/RPC/Auth/Storage sau setup.

## Quyết định cụ thể từ SRS

1. Không tự tạo nutrient profile hoặc serving trong seed đầu. Reference-usable khác approved dish. 109 candidate links nằm riêng; nutrition_references versioned để source cũ không bị overwrite.
2. Dinh dưỡng cần explicit profile selection cho variant theo loài/trạng thái/công thức; chỉ approved default đại diện đúng food mới tự resolve. Không tự pick first profile cho class rộng.
3. Foods UUID theo slug ổn định, model index/map version giữ riêng. Scan giữ predicted UUID/class map; meal giữ confirmed food và snapshot.
4. Atomic meal mutation dùng private writer RPC, không cấp ordinary direct DML để client fake nutrients. Composite owner/profile FK bảo vệ thêm ngoài RLS. Receipt không chết theo meal khi delete, replay trước revision check.
5. Grams-only edit giữ profile/version/per100g cũ; source/catalog update không tự sửa history. Profile/variant đổi rõ ràng mới resolve version mới. Serving association không được mang grams khác serving snapshot mà vẫn giữ nhãn cũ.
6. Known totals NULL khi có items nhưng tất cả thiếu nutrition; empty day totals 0 là tổng tập rỗng. Timezone/date buckets tính theo local calendar, không giả ngày cố định 24 giờ.
7. Health core ready không bị model pending khiến catalog/manual meals thành unavailable; scan riêng trả 503 MODEL_NOT_READY. Các samples giữ trạng thái nutrition NULL, không tạo detector output giả.

## Kiểm tra đã thực hiện

| Kiểm tra | Kết quả |
| --- | --- |
| Đối chiếu SRS mục 10/11 và business rules | Thiết kế giữ tables/features/stack và đường đi account/catalog/scans/meals/stats |
| JSON parse / internal refs | 149 reference occurrences resolve được |
| Route path parameters / operation IDs / security | 14 paths, 18 operation IDs unique; path params đủ, /health public và /v1 Bearer |
| Sample shapes | 9 sample checks đạt type/required/extra-property/enum/format/precision constraints được kiểm tra |
| UUID/class map | 67 UUID duy nhất; IDs 0..66/remap face đúng; UUID tái tính từ namespace/name cho cùng kết quả; tên/scope khớp CSV |
| Class source checksum | Khớp source-baseline và artifact |
| Bộ design source files | Tạo trong docs; không viết migration hoặc API runtime |

Report local: data/processed/DB-01-contract-check.json. Kiểm tra bằng Python standard library snippets; đây không phải full OpenAPI meta-schema validation, pgTAP/RLS tests hoặc kiểm thử API runtime. Không thêm/cài thư viện chỉ để kiểm tra design docs. Không chạy lại DATA-01 tests vì không đổi validator/source trong DB-01.

Self-review owner/profile/portion/FK và idempotency đã xử lý deferred NO ACTION cho scan-item relation để account cascades không phụ thuộc thứ tự trigger, trong khi xóa scan riêng vẫn bị chặn nếu item tham chiếu. DB-02 phải kiểm chứng điều này trên PostgreSQL thật.

## Setup và phần chưa thực hiện

`wsl --status` báo WSL chưa cài. Chưa tìm thấy Docker/CLI ở PATH và all-users Docker paths; không kết luận về mọi vị trí cài khác. Chưa kiểm tra RAM/virtualization hoặc chạy Docker engine. Chủ dự án chọn local và cần cài WSL2, Docker Desktop rồi xác nhận Client+Server/OSType linux. Codex chưa chạy installer, đổi Windows features hoặc reboot.

Chưa tạo/apply migration, chưa có Supabase local chạy, không import database, chưa kiểm thử RLS/Storage/JWT/RPC/FastAPI. DB-01 DONE chỉ nói thiết kế đủ cụ thể để triển khai. DB-02 chờ local setup; Codex sẽ chuẩn bị/pin CLI trong project khi engine sẵn sàng. Không cần keys hoặc project cloud cho phần thiết kế.

## Nguồn đã đối chiếu

- Supabase RLS/grants/private definer: https://supabase.com/docs/guides/database/postgres/row-level-security
- Functions: https://supabase.com/docs/guides/database/functions
- Storage owner-folder policies: https://supabase.com/docs/guides/storage/security/access-control
- JWT verification: https://supabase.com/docs/guides/auth/jwts
- PostgreSQL FK/NO ACTION/RESTRICT: https://www.postgresql.org/docs/current/ddl-constraints.html
- OpenAPI 3.1: https://spec.openapis.org/oas/v3.1.0.html
- WSL/Docker/local runtime requirements: các links trong supabase-local-setup.md.

## Thứ tự tiếp theo

DB-02 migration/RLS/RPC/Storage trên local mới → DATA-02 importer có dry-run/transaction/idempotency và source version checks → BE-01 config/JWT/catalog. Frontend chưa được bàn giao; chỉ chuyển khi backend/API đã thực thi và kiểm thử theo SRS.
