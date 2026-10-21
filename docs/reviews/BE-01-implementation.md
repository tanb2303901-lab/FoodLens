# BE-01 — FastAPI nền tảng/catalog

Ngày: 2026-10-15. Kết quả: DONE. Codex triển khai, kiểm thử và tự review; không có review độc lập, Claude Code hoặc Anti.

## Thay đổi và quyết định

FastAPI modular monolith tại backend/app: config validate/secrets excluded from repr; shared async HTTP connection pool qua lifespan, Authorization tạo riêng mỗi request. Runtime không cần service key. Lỗi chuẩn/request IDs/no-store và không echo token/input/SQL. Phụ thuộc được pin, Python .venv 3.12; FastAPI 0.143.1, Uvicorn 0.54.0, HTTPX 0.28.1, PyJWT 2.15.1, cryptography 50.0.2, pytest 9.1.1.

Local Auth JWKS thực tế công bố ES256. PyJWT verify signature với configured algorithm, issuer, audience, expiry/iat/nbf, UUID subject, authenticated role và required claims; reject unsigned/forged/expired/non-user tokens. JWKS lấy từ fixed origin, cache 600s, lock/refetch unknown kid không quá 1 lần/10s; rotation mới có thể chờ tối đa 10s trước refresh. Không theo jku do token cung cấp. HS256 legacy và RS256 được kiểm tra bằng synthetic keys; local chạy ES256. Theo [Supabase JWT signing](https://supabase.com/docs/guides/auth/jwts) và [PyJWT validation](https://pyjwt.readthedocs.io/en/stable/usage.html).

Readiness migration 20261015000100 dùng function core_readiness không tham số, search_path rỗng, fixed readonly queries dưới definer; anon/auth chỉ nhận boolean, vẫn không SELECT catalog. DB failure 503, process liveness độc lập DB. Model not_ready; capabilities phản ánh chỉ catalog đã có API. Không báo manual_meals/scan ready trước implementation.

Catalog active-only, UUID identity, Vietnamese search, keyset slug/id + HMAC cursor gắn filter. Raw metadata/references/candidates không có trong DTO. Nutrition giữ unavailable/NULL ở baseline; chỉ approved/current và portions verified theo variant. Default/broad/variant behavior khớp DB meal resolution; malformed approved source bị chặn 503. Synthetic profile/portion DTOs chỉ trong unit fixture, không ghi DB.

## Kết quả thực thi

- Apply readiness migration: exit 0.
- pytest tests/backend: 28 tests passed, exit 0; report data/processed/BE-01-unit.xml. 1 Starlette deprecation warning cho HTTPX TestClient adapter; adapter vẫn hoạt động ở dependencies đã pin. Không phải failure; cần đổi adapter khi nâng framework sau này.
- scripts/test_backend_local.py: 37 HTTP checks passed, exit 0, server FastAPI thật + Supabase Auth/REST thật; report data/processed/BE-01-integration.json. Login A/B thực, invalid/non-user tokens denied, 67 foods phân trang không trùng, Vietnamese/literal search, cursor/filter rejection, detail/error IDs, unavailable nutrition, concurrent A/B catalog requests và runtime OpenAPI.
- SQL supabase/tests/002_readiness.sql: 5 tests PASS, exit 0; anon probe, fixed search_path và không mở SELECT catalog.
- Sau cleanup SQL: foods=67, references=9115, links=109, import_runs=1, food_nutrition=0, portions=0, auth.users=0. Không sửa source CSV, profile approval hoặc dataset data.
- Local server mở 127.0.0.1:8000, Swagger/health/readiness được kiểm tra. Setup: docs/backend-local.md.

Unit tests kiểm JWT expired/future/wrong issuer/audience/role/sub/missing claims/algorithm/signature, ES/RS JWKS/cache/rotation/invalid key response, startup config guards, sanitized failures, outage/readiness và sequential/concurrent header isolation. Profile default/variant/broad/serving unit fixtures rõ synthetic. HTTP catalog là dữ liệu dùng chung; ownership của private profile/meal APIs sẽ được test khi endpoints đó có, không suy từ shared catalog test.

Windows sandbox khiến async TestClient stall; chạy lại ngoài sandbox đã qua. Không có auto-review rejection; elevated tools được cho phép để localhost/Docker/runtime hoạt động. Commands không in real credentials. Config/reports/log/PID nằm ignored data/processed, no cloud/reset/commit/push/deploy.

## Hợp đồng và phần còn lại

Runtime spec có đúng 5 paths đã triển khai, snapshot docs/architecture/openapi-runtime-be01.json; DB-01 openapi-v1.json tiếp tục là thiết kế đầy đủ. JSON DTOs catalog/nutrition/error khớp shape v1. Runtime thêm dependency 503 cho catalog, và readiness manual_meals=false/scan=false theo subset hiện có; sample DB-01 manual_meals=true là trạng thái mục tiêu sau BE-02. Runtime source URLs kiểm tra absolute URI và có format URI trong schema. Health/database ready không bao gồm model-ready hoặc proof toàn bộ auth dependency đang online; JWKS failure có thể trả 503 trên authenticated endpoints.

Chưa triển khai /v1/me, meals/history/stats, upload/scans hoặc model/mobile; chưa có frontend handoff. Missing model chưa có scan route để gọi, capability scan=false. Bước kế tiếp BE-02 profile + manual meals/history/stats qua owner-safe RPC đã có, với JWT/ownership/transaction/idempotency API tests.
