# FOOD-01 — Kết quả triển khai thông tin món

Ngày 2026-10-19. Claude Code triển khai và tự kiểm thử theo yêu cầu trực tiếp của chủ dự án; không có review độc lập. Nội dung mô tả là bản nháp AI hỗ trợ, **chưa có người duyệt**, nên chưa món nào hiển thị trong app.

## Kiểm kê trước khi sửa

- Dịch vụ: lúc bắt đầu cả backend 8000, trang thử 8765 và Supabase 54321 đều dừng (Docker Desktop không chạy, PID cũ không còn). Đã mở Docker Desktop; năm container Supabase local tự khởi động lại, không recreate/reset.
- Database thật trước khi sửa: 12 migrations, 75 foods (8 lớp map75), 9.115 nutrition references, 109 candidate links, 0 nutrition profile/portion, 1 user, 50 scans, 0 meals. Khớp hồ sơ ML-05.
- Chưa có bảng, endpoint, dữ liệu hay tài liệu nào về mô tả món: đây là phần việc mới, không có phần làm dở.
- Backend 0.5.0 có 14 paths/18 operations; `GET /v1/foods/{id}` và `/nutrition` là điểm nối catalog hiện có.

## Thiết kế đã triển khai

- Migration bổ sung `20261019000100_foodlens_food_descriptions` với ba bảng:
  - `content_sources`: nguồn (title, publisher, HTTPS url, language, source_kind, revision_ref, accessed_on, license_note).
  - `food_descriptions`: version theo `food_id` + locale `vi`, `content_status` draft/reviewed/published/retired, `is_current` đúng bằng trạng thái published, `content_sha256`, `authoring_method`, `drafted_by`, `source_check`, người/thời điểm duyệt và phát hành.
  - `food_description_sources`: nguồn nào hỗ trợ field nào (`supports`) và vị trí (`locator`).
- Trigger: hàng mới phải là draft; chỉ cho chuyển draft→reviewed→published→retired; nội dung, trích dẫn và bằng chứng duyệt bất biến sau draft; không xóa bản đã duyệt; chỉ duyệt được khi mọi field có nội dung có nguồn; lớp nhóm rộng phải có `scope_note`; nguồn đã được bản duyệt trích dẫn không thể bị sửa.
- RLS/quyền: `authenticated` chỉ đọc bản published hiện hành và nguồn nó trích dẫn; không đọc được tên người duyệt/soạn, review notes, draft. `anon` không đọc được. Ghi chỉ qua quyền quản trị local (importer).
- API `GET /v1/foods/{id}/description`, Bearer user JWT như catalog; trả định danh canonical, `status` available/description_unavailable, `reason`, `description` kèm `sources[]` và `notice` cố định. Backend lọc lại published/current/vi và từ chối (503) dữ liệu thiếu nguồn hay không nhất quán thay vì trả nội dung chưa đủ điều kiện. Scan, meal, nutrition và lịch sử không đổi.
- Contract: API 0.6.0, 15 paths/19 operations; thay đổi thuần bổ sung (1 path, 3 schema `FoodDescription`, `DescriptionContent`, `ContentSource`; không path/schema cũ nào đổi).

## Quy trình và dữ liệu mô tả

- Nguồn sự thật: `docs/content/food-descriptions-vi-v1.json`. Quy trình chi tiết: [food-content-workflow.md](../content/food-content-workflow.md). Độ phủ: [food-descriptions-coverage.md](../content/food-descriptions-coverage.md).
- Đợt 1: 35 bản nháp `ai_assisted_draft`, 35 nguồn, 83 liên kết nguồn. Trong đó đủ 8 lớp owner bổ sung (Chuối, Táo, Gà nướng, Cá hồi nướng, Khoai lang, Khóm, Cà phê, Nước ngọt), Phô mai và 26 món/nhóm Việt: Phở, Bánh mì, Cơm tấm, Bún bò Huế, Cao lầu, Mì Quảng, Bánh xèo, Bún chả, Xôi, Bánh bèo, Bún riêu, Gỏi cuốn, Hủ tiếu, Nộm hoa chuối, Bánh cuốn, Bún chả cá, Bò lá lốt, Bánh canh, Bánh khọt, Bánh chưng, Bò kho, Chả giò, Củ kiệu, Thịt kho, Lẩu, Ốc. 40 lớp còn lại chưa có nội dung và trả unavailable.
- Nguồn: 14 trang `vietnam.travel` (Viet Nam National Authority of Tourism) và 21 bài Wikipedia (19 tiếng Việt, 2 tiếng Anh) ghim `oldid`, giấy phép CC BY-SA 4.0. Truy cập ngày 2026-10-19. Britannica trả HTTP 403 với truy cập tự động nên không được dùng.
- Đối chiếu: Claude tải văn bản nguồn, so từng mệnh đề với đoạn ở `locator`, bỏ mệnh đề không có trong nguồn và viết lại bằng lời riêng. Nguồn gốc không chắc chắn được viết thận trọng hoặc để `null` (Xôi, Bún riêu, Gỏi cuốn, Nộm hoa chuối, Bún chả cá, Chả giò, Củ kiệu, Lẩu, Ốc, Gà nướng, Cá hồi nướng, Phô mai). Bài vi.wikipedia "Nước ngọt" nói về nước không mặn nên đã thay bằng bài "Nước ngọt có ga". Đây là kiểm tra của công cụ AI, không phải duyệt.
- Kiểm trùng nguyên văn: lần đầu phát hiện 12 câu lặp ≥8 từ liên tiếp với nguồn; đã viết lại, lần cuối 0 phát hiện.
- Hạn chế cần người duyệt chú ý: Wikipedia là bách khoa mở, một số bài ít chú thích (ví dụ Cao lầu, Bò kho); trang VNAT là nội dung quảng bá du lịch. Các nhận định nguồn gốc nên được đối chiếu thêm sách/tài liệu văn hóa khi duyệt.

## Kiểm thử đã chạy trong lượt này

| Kiểm tra | Kết quả |
| --- | --- |
| Preflight migration + SQL 005 trong transaction rollback | 33/33 pgTAP đạt; sau rollback không còn bảng |
| Áp migration thật | Đạt; fingerprint foods 75, references 9.115, candidates 109, nutrition 0, portions 0, profiles 1, scans 50, meals/items 0 không đổi |
| `supabase test db` 005 / 002 / 003 / 004 | 33 / 5 / 14 / 21 đạt. Không chạy SQL 001 vì cần database trống theo quy định |
| `food_content.py apply` dry-run, apply, apply lặp lại | Cùng kết quả 35 nguồn, 35 draft, 83 links; idempotent |
| `content_source_check.py fetch` / `overlap` | 35/35 nguồn HTTP 200 (Wikipedia đúng oldid); 0 phát hiện trùng nguyên văn |
| Toàn bộ pytest | 320 tests + 41 subtests đạt (gồm 8 test endpoint, 12 test quy trình nội dung, test ví dụ minh họa khớp contract) |
| `test_food_content_local.py` (HTTP + Auth + PostgREST/RLS thật, 75 món) | 389 checks đạt; review→publish chạy thử trong transaction rollback rồi xác nhận không có thay đổi được commit |
| `test_handoff_local.py --write-artifacts` rồi chạy lại không ghi | 24 ví dụ HTTP thật, 19 operations; ví dụ cũ chỉ khác `created_at/updated_at` |
| Hồi quy core `test_backend_local.py --class-count 75`, `test_meals_local.py`, `test_scans_local.py` | 54 + 76 + 50 = 180 checks đạt (hai script sau được cập nhật bộ đếm path 14/18 → 15/19) |
| Khởi động lại 8000 (ML venv, `backend-ml75.json`, model75 owner-preview) và 8765 | `/health/ready` database/model ready, scan=true; `/api/status` của trang thử ready, model `foodlens-yolo11n-20261016-extension4h-v2-dual75` |
| `test_description_scan_flow_local.py` trên backend live | Model75 trả 5 khung Phô mai → 1 `food_id` → 1 lần gọi description → `description_unavailable`; ảnh private và tài khoản tạm đã xóa |

Bằng chứng máy trong ignored `data/processed/FOOD-01-*.json`, `FOOD-01-unit.xml`, `FOOD-01-sources/`. Bản contract/ví dụ trước khi sinh lại được lưu tại `FOOD-01-openapi-before.json`, `FOOD-01-api-examples-before.json`.

## Đợt 2 nội dung (cùng ngày, theo yêu cầu "thực hiện tại đây")

- Phạm vi: 40 lớp còn `missing` sau đợt 1. Chỉ nối thêm vào `docs/content/food-descriptions-vi-v1.json`; đã xác nhận nội dung và nguồn đợt 1 không đổi so với bản sao lưu ignored `data/processed/FOOD-01-content-before-batch2.json`. Không sửa backend, migration, contract hay trạng thái duyệt.
- 39 bản nháp mới: Bánh tráng, Bánh tráng trộn, Bông cải, Bún, Bún đậu, Bún mắm, Cá, Cà chua, Cà pháo, Cà rốt, Chả, Chanh, Cơm, Cua, Đậu hũ, Dưa chua, Dưa leo, Hamburger, Heo quay, Khổ qua nhồi thịt, Khoai tây chiên, Lòng heo, Mì, Mực, Nấm, Ớt chuông, Rau, Salad, Thịt bò, Thịt gà, Thịt heo, Thịt nướng, Tôm, Trứng, Cơm chiên Dương Châu, Cơm chiên gà, Cháo lòng, Nui xào bò, Súp cua.
- Nguồn mới (truy cập 2026-10-19): 8 trang `vietnam.travel` (10 must-try Hanoian dishes; Explore delicious dishes in Ho Chi Minh City; A foodie guide to Vietnam's noodles; Explore the food of Hoi An; Must-Eat Specialty Dishes in Nha Trang; Famous Ha Noi Food and International Fine Dining; A vegetarian guide to Vietnam; Da Nang's special pork rolls) và 42 bài Wikipedia ghim oldid (39 tiếng Việt, 3 tiếng Anh: Fish as food, Crab meat, Squid as food). Một số nguồn VNAT/Wikipedia của đợt 1 được dùng lại.
- Thận trọng: các lớp nhóm/nguyên liệu (Cá, Cua, Mực, Nấm, Rau, Salad, Thịt bò/gà/heo, Thịt nướng, Tôm, Trứng, Dưa chua, Lòng heo, Bánh tráng, Bún, Chả, Khổ qua nhồi thịt, Cơm chiên gà) đều có `scope_note`. Chả được mô tả theo chả lụa và ghi rõ trong scope. Cơm chiên gà không có bài riêng nên chỉ dùng mô tả chung về cơm chiên, kèm ghi chú phạm vi. Nhiều nguyên liệu để trống nguồn gốc khi nguồn không nêu.
- Không dùng: Canh (chỉ có trang định hướng và bài "Nước dùng"); các câu sức khỏe/dinh dưỡng có trong nguồn (ví dụ bài Cà chua, Cà rốt, Xúp cua) bị loại khỏi bản nháp.
- Kiểm tra đã chạy: `validate` đạt; `content_source_check.py fetch` 85/85 nguồn HTTP 200; `overlap` lần đầu 25 phát hiện, sau viết lại 0; `apply` dry-run/apply/apply lặp lại cùng kết quả 85 nguồn, 74 draft, 178 links, fingerprint dữ liệu cũ không đổi; pytest 320 + 41 subtests; `test_food_content_local.py` 389 checks trên 75 món; `test_handoff_local.py` 24 ví dụ/19 operations; SQL 005 33/33; smoke scan→description trên backend live đạt (Phô mai vẫn `description_unavailable` vì chưa duyệt).
- Trạng thái nội dung sau đợt 2: 0 published, 0 reviewed, 74 draft, 1 missing (trước lượt duyệt bên dưới).

## Duyệt và phát hành lượt 1 (2026-10-19)

- Quyết định: chủ dự án Lý Thanh Tân yêu cầu trong chat "duyệt 20 món trước", chọn ghi tên mình là người duyệt/phát hành, chọn duyệt và publish ngay, ánh xạ "Bún thịt nướng" sang lớp Thịt nướng và "Cơm chiên" sang cả hai lớp cơm chiên. "Trứng" bị lặp trong danh sách nên tính một lần.
- 20 lớp đã publish: Cơm tấm, Phở, Bún riêu, Bún mắm, Bún bò Huế, Trứng, Gà nướng, Cá hồi nướng, Bánh mì, Cà phê, Bún chả, Bông cải, Ốc, Táo, Thịt nướng, Khoai tây chiên, Bún đậu, Cơm chiên Dương Châu, Cơm chiên gà, Bánh tráng trộn.
- Claude Code chạy `food_content.py review/publish` với tên chủ dự án; mỗi bản ghi review có ghi chú: chủ dự án quyết định trong chat, Claude Code chỉ chạy lệnh và không tự duyệt. Hash nội dung đã duyệt được lưu; tên người duyệt không lộ ra API. Bản sao trước khi duyệt: ignored `data/processed/FOOD-01-content-before-review1.json`.
- Đồng bộ local: dry-run, apply rồi apply lặp lại cùng kết quả 20 published, 54 draft, 85 nguồn, 178 links. `test_food_content_local.py` 389 checks đạt (20 món `available` kèm nguồn, 55 món unavailable, RLS chỉ lộ bản published). Ví dụ bàn giao được chụp lại từ HTTP thật: 25 ví dụ, thêm `food_description_available` (Phở); ví dụ unavailable chuyển sang Cơm. Ví dụ cũ lưu ở ignored `FOOD-01-api-examples-before-review1.json`. Test nội dung được chỉnh để kiểm tra quy tắc chung cho món đã duyệt thay vì giả định toàn bộ là nháp; pytest 322 + 41 subtests đạt. Trang 8765 với ảnh phở hiện thẻ "Đã duyệt" lấy từ API.
- Đây là quyết định duyệt của chủ dự án, không phải review độc lập hay thẩm định chuyên gia.

## Duyệt và phát hành lượt 2 (2026-10-19)

- Quyết định: chủ dự án yêu cầu duyệt các món chế biến, để nguyên liệu đơn thuần lại sau. Claude Code liệt kê 22 bản nháp loại `prepared_food`; chủ dự án đồng ý cả 22 và chọn thêm các món ranh giới Xôi, Lẩu, Salad, Chả, Dưa chua, Cà pháo, Củ kiệu. Nước ngọt để lại.
- 29 lớp publish thêm dưới tên Lý Thanh Tân, ghi chú quyết định trong chat như lượt 1: Cao lầu, Mì Quảng, Bánh xèo, Bánh bèo, Gỏi cuốn, Hủ tiếu, Nộm hoa chuối, Bánh cuốn, Bún chả cá, Bò lá lốt, Bánh canh, Bánh khọt, Bánh chưng, Bò kho, Chả giò, Thịt kho, Hamburger, Heo quay, Khổ qua nhồi thịt, Cháo lòng, Nui xào bò, Súp cua, Xôi, Lẩu, Salad, Chả, Dưa chua, Cà pháo, Củ kiệu. Bản sao trước lượt 2: ignored `data/processed/FOOD-01-content-before-review2.json`.
- Kết quả: 49 published, 25 draft (nguyên liệu đơn thuần và Nước ngọt), 1 missing (Canh). Đồng bộ dry-run/apply/apply lặp lại cùng kết quả; `test_food_content_local.py` 389 checks; `test_handoff_local.py` 25 ví dụ khớp contract (ví dụ unavailable vẫn là Cơm, còn nháp); pytest 322 + 41 subtests đạt.

## Lượt 3: sửa nháp, soạn Canh, duyệt toàn bộ (2026-10-19)

- **Quyết định:** chủ dự án đồng ý đề xuất sửa 6 bản nháp, yêu cầu viết Canh theo hướng "món không thể thiếu", và yêu cầu duyệt hết các bản nháp còn lại.
- **Sửa nháp:** Nước ngọt, Khoai lang, Lòng heo, Thịt heo, Cá, Rau.
- **Soạn Canh:** dùng nguồn mới `wiki-vi-am-thuc-viet-nam` (oldid 75524867, mục Canh). Nguồn này hỗ trợ trực tiếp ý canh là món cơ bản không thể thiếu.
- **Kiểm tra:** `validate` đạt; `content_source_check.py` fetch 86 nguồn và overlap 0 phát hiện.
- **Duyệt và xuất bản:** 26 lớp dưới tên Lý Thanh Tân. Ghi chú nêu rõ chủ dự án chưa đọc từng câu của bản cuối.
- **Kết quả:** 75/75 published.
  - Dry-run và `apply --apply` cho 75 published, 86 nguồn, 179 liên kết.
  - `test_food_content_local.py` đạt 389 checks. Script đã được sửa: khi không còn nháp thì kiểm tra 75/75 hiển thị, và diễn tập trong rollback việc phát hành version 2 làm version cũ chuyển sang `retired`.
  - `test_description_scan_flow_local.py`: Phô mai trả `available`.
  - `test_handoff_local.py` đạt; artifacts không sinh lại.
  - pytest 266 + 23 subtests đạt.

## Kế thừa, không chạy lại trong lượt này

Kết quả train/evaluation model75, quality gate (Khoai lang AP50 test 0,1647888459 < 0,25 trên 8 crop — vẫn FAILED), 951 real model/API checks, quyết định owner-preview, ML-01/02/03 và nghiệm thu BE-01..04 được giữ nguyên từ hồ sơ cũ. Không train, không chạy trainer khác, không đổi metric/ngưỡng/checkpoint, không reset budget. Việc khởi động lại backend dùng đúng config owner-preview đã có, không phải activation mới.

## Chưa làm / còn mở

- Mục này là lịch sử. Sau lượt 3, 75/75 đã published. Riêng các bài dựa trên Wikipedia (nguyên liệu chung, Canh) vẫn nên được đối chiếu thêm với nguồn chuyên môn khi có thời gian.
- Frontend chưa triển khai; hướng dẫn tại [food-description-api.md](../handoff/food-description-api.md) chưa được gửi.
- Backend/Supabase chỉ lắng nghe loopback; LAN/thiết bị/cloud chưa cấu hình hay kiểm thử.
- Chất lượng model75 vẫn chỉ là owner-authorized local preview, không phải chất lượng đã chứng nhận.
