# Trạng thái công việc FoodLens

Ngày cập nhật: 2026-10-20. Chủ dự án chọn dữ liệu backend trước, làm từng bước.

Scope mới nhất 19–20/10: sau nhận diện app hiển thị thông tin giới thiệu món có nguồn theo `food_id` (FOOD-01). Ngày 20/10 chủ dự án quyết định gỡ hẳn dinh dưỡng, bữa ăn thủ công và thống kê (FOOD-02); dữ liệu cũ được backup ngoài repo. Các task/review cũ nói về dinh dưỡng là lịch sử.

| Task | Nội dung | Trạng thái | Điều kiện tiếp theo |
| --- | --- | --- | --- |
| DATA-00 | Tiếp nhận yêu cầu, lưu baseline, quy tắc và môi trường local | DONE | Hồ sơ tại docs/requirements, docs/dataset và review DATA-00 |
| DATA-01 | Validator CSV backend chạy lại được | DONE | Codex triển khai theo yêu cầu mới: 44 tests passed, CLI thật exit 0; xem review DATA-01 |
| DB-01 | Thiết kế schema, constraints, RLS và API contract | DONE | UUID map + schema/access rules + OpenAPI đã kiểm tra cấu trúc; chưa chạy DB/API |
| DB-02 | Migration/RPC/Auth/RLS/private Storage trên Supabase local | DONE | 7 migrations; 72 SQL + 12 HTTP integration tests passed, fixtures đã dọn; xem review DB-02 |
| DATA-02 | Importer CSV backend | DONE | 16 unit tests + 13 integration checks; đã nhập 67 foods, 9.115 references, 109 candidates, zero profiles/portions |
| BE-01 | Config/health/readiness/JWT/catalog FastAPI | DONE | 28 unit tests + 37 HTTP checks + 5 SQL tests; 5 runtime paths, xem review BE-01 |
| BE-02 | Profile/manual meals/history/stats API | REMOVED_BY_FOOD-02 | Profile giữ lại; bữa ăn/thống kê/dinh dưỡng đã gỡ 20/10. Task và review riêng đã xóa theo yêu cầu chủ dự án |
| BE-03 | Upload/predictor readiness/scan API | DONE | Core BE-03 có 86 Python +50 stored scan/Auth/Storage checks; real model đã tích hợp/nghiệm thu local qua ML-03 |
| BE-04 | Backend acceptance/docs/handoff | DONE_CORE_HANDOFF_READY | 160 Python +41 subtests,91 SQL,163 HTTP regressions,23 real handoff cases; full OpenAPI 3.1 validated |
| FE-01 | Mobile theo scope cũ (bữa ăn/thống kê) | SUPERSEDED | Task/prompt cũ đã xóa. Frontend mới do đồng đội làm theo [backend-v1](../handoff/backend-v1.md) khi chủ dự án chuyển |
| ML-01 | Audit ảnh/nhãn và evaluation readiness | DONE_WITH_REVIEW | 171.619 ảnh/172.956 label copies, zero audit errors; mẫu decode 659, provenance findings và holdout coverage được ghi rõ |
| ML-02 | Dataset dẫn xuất, benchmark và train tối đa 8 giờ | DONE_BUDGETED_BASELINE | 7h57m22,547s; 14 full +partial epoch15; test mAP50 0,7406 trên29 lớp, full67 quality còn mở |
| ML-03 | Evaluate bundle và real predictor/API integration | DONE_LOCAL_REAL_MODEL | 51 real model/Auth/Storage/API checks trên8 ảnh test; live model=ready/scan=true, Swagger200; mobile/nutrition chưa nghiệm thu |
| ML-04 | Mở trang thử ảnh local cho owner | DONE_LOCAL_TOOL_OPEN | Chín HTTP/security checks + browser chọn ảnh/analyze/canonical bbox thành công; trang loopback8765 đã mở, ảnh mới/quality/mobile còn chờ |
| FOOD-01 | Thông tin giới thiệu món có nguồn sau nhận diện | DONE_ALL_PUBLISHED | Claude Code: migration+RLS, `/v1/foods/{id}/description`; 75/75 published (owner duyệt 3 lượt 19/10, lượt 3 duyệt toàn bộ phần còn lại kể cả Canh mới soạn), 86 nguồn; xem review FOOD-01 |
| FOOD-02 | Gỡ dinh dưỡng, bữa ăn, thống kê | DONE | Claude Code 20/10: backup → 2 migration gỡ bảng/hàm/metadata, API 0.7.0 (10 paths/11 ops), dọn script/test/tài liệu; kiểm thử ghi trong review FOOD-02 |
| FOOD-03 | Repo cho đồng đội tự chạy backend (model trong repo, setup 1 lệnh) | DONE_NOT_PUSHED | Claude Code 20/10: cài mới tách biệt + scan thật model CPU đạt, 266 tests; chưa commit/push, chờ chủ dự án báo; xem review FOOD-03 |
| ML-05 | Bổ sung8 lớp owner chọn, cap3 giờ | DONE_LOCAL_OWNER_PREVIEW |70 epochs/4507,060s;951 real API checks,299 Python+41 subtests đạt. Owner chọn mở exact75 candidate; live backend/UI ready, real Táo smoke đạt. Quality gate cũ giữ nguyên; xem ML-05-local-result |

Các task đến ML-05 do Codex triển khai và tự review; FOOD-01, FOOD-02, FOOD-03 do Claude Code triển khai và tự kiểm thử. Không có review độc lập. Hiện tại: FastAPI 0.7.0, 10 paths/11 operations; backend 8000 chạy model75 owner-preview, trang thử 8765. Chất lượng model75 chưa được chứng nhận đầy đủ; mobile/LAN/cloud chưa làm.

Ảnh/nhãn thật đã kiểm tra trong ML-01. Supabase local, chưa có cloud project. Database hiện có 75 món, profile, scan và nội dung mô tả; không còn bảng dinh dưỡng/bữa ăn. Setup và kiểm thử: [backend-local.md](../backend-local.md); ML: [ml-local.md](../ml-local.md).
