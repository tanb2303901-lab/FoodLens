# ML-05 — bổ sung tám lớp, cap hiện hành3 giờ

## Cập nhật hiện hành — resume theo lệnh owner

Owner đã nhắn bắt đầu train và mở màn hình. Resume cùng job11:45:10 UTC+7 ngày16/10;704,047054 giây đã dùng được giữ nguyên,3380,034637 giây pause được loại bằng chứng cứ khớp checkpoint/ledger/control. Không tạo job mới/reset budget. Cap3 giờ tích lũy, hard cutoff13:00 UTC+7; 180 giây dự phòng dừng/lưu.25 source/resume tests đã đạt trước khi khởi chạy. Monitor PowerShell hiện cửa sổ riêng theo yêu cầu; đóng monitor không dừng job. Các mục paused/four-hour bên dưới là lịch sử.

Backend0.5.0 và canonical OpenAPI hỗ trợ75, giữ UUID/ID67 cũ và original_class_id=NULL cho8 lớp nguồn mới. Migration20261016000100 đã áp dụng đúng stack local, không reset; dấu vân tay foods67,9115 references,109 links và dữ liệu người dùng trước/sau giữ nguyên.21 pgtap SQL checks rollback đạt;180 HTTP core checks và23 HTTP handoff examples đạt, dùng fixture riêng và đã dọn. Không chạy DB02 empty-catalog fixtures hoặc SQL001. Không tạo approved nutrition/portion. Config model đang dùng chưa thay sang75.

Validation tạm thời của một checkpoint (không dùng test): pure75 đạt extension8 crop mAP50~0,7975/mAP50-95~0,7223, nhưng legacy full-scene mAP50~0,3935 so với baseline~0,6705. Vì vậy không kích hoạt pure75. Pipeline inference giữ model67 nguyên bytes, chỉ lấy outputs67..74 của extension, áp dụng ưu tiên subtype gà/cá hồi lên parent khi IoU≥0,5 và confidence đủ. Kiểm tra raw inference CPU cho phần cũ maxdiff0,0, tên/shape75 đúng; GPU validator và predict thật chạy được. Đây là kiểm tra kỹ thuật, chưa chứng minh chất lượng. Checkpoint sẽ chọn bằng validation8 mới, sau đó đánh giá riêng legacy_valid/test và extension_valid/test của cả cặp. Không dùng test để chọn hoặc chỉnh model. Không train thêm để tạo cặp này. Model/API acceptance vẫn chờ kết quả cuối; Codex tự review, không có reviewer độc lập.

## Cập nhật ưu tiên — đã dừng theo yêu cầu owner

Owner giảm giới hạn tổng lượt bổ sung xuống3 giờ, yêu cầu dừng ngay, chỉ chạy lại khi owner nói bắt đầu. Đã xác minh đúng process tree của job rồi dừng root101100 cùng children, không đụng backend/Docker hoặc job8 giờ cũ. Dừng10:48:50 UTC+7 ngày16/10, elapsed704.047 giây (số chính xác trong ignored pause.json), khoảng11,73 phút; last-resume.pt21.448.355bytes, ZIP CRC đạt, SHA256d379472dd09b0ca2e96890054f210ec8c10af679f983124068e1b2b5095c3807. pause/status/ledger ghi paused_by_owner, restart_authorized=false. Không có train/evaluation nào được khởi động sau yêu cầu dừng.

Owner dự kiến ra lệnh resume11:30–12:00. Mục tiêu công việc hiện tại: hoàn tất phần8 món/tích hợp backend/kiểm thử trong14:00–14:30, không vượt14:30. Vì còn chờ giờ bắt đầu và kết quả kiểm thử, không có bảo đảm quality hoặc toàn bộ acceptance sẽ đạt đúng giờ. Kế hoạch khi được lệnh: train thêm đến khoảng13:00 (ít hơn3 giờ), dành phần còn lại cho đánh giá/tích hợp/test. Không bỏ kiểm thử để gắn nhãnDONE.

Code budget hiện chặn mức>3 giờ. Trước resume phải cập nhật cách tính elapsed để loại đúng khoảng pause đã xác minh và đặt hard cutoff mới; không dùng lệnh resume4 giờ cũ hoặc tự reset ledger. Các mốc4 giờ/14:37 bên dưới là lịch sử đã bị thay thế. Không chạy lại khi chưa có yêu cầu mới.

2026-10-16. IN PROGRESS. Codex triển khai, kiểm thử và tự review; không có review độc lập. Owner cho phép một lượt train bổ sung tối đa4 giờ, chuẩn bị ảnh/nhãn/evaluation tính riêng. Quyết định mới nhất: Gà nướng gồm mọi phần của gà, không chỉ ức; Khoai lang gộp hấp/luộc/nướng và các cách chế biến xác định được củ khoai lang.

## Định danh và phạm vi

Candidate map `docs/dataset/food-identities-v2.json` có75 lớp: giữ nguyên từng entry0..66, nối Chuối67, Táo68, Gà nướng69, Cá hồi nướng70, Khoai lang71, Khóm72, Cà phê73, Nước ngọt74. Tám original_class_id mới làNULL, dùng namespace owner-extension riêng. UUID của Gà nướng chốt theo slug ga_nuong trước export/train, chưa được import/activate. Face original27 vẫn bị loại; training27 vẫn Củ kiệu.

Backend/database/config đang phục vụ67 giữ nguyên. Không sửa README/source CSV/ảnh/nhãn VietFood, không reset, cloud, commit/push hoặc tự duyệt nutrition. Lượt8 giờ trước và ML-job.json vẫn giữ riêng.

## Nguồn và nhãn

FoodSeg103: bốn parquet mirror được đối chiếu đủ byte/SHA với metadataLFS. Dùng mask người gán nhãn cho chuối/táo/khóm, chuyển connected semantic regions thành bbox; đây không phải annotation instance gốc. Kiểm geometry và xem43 ảnh mẫu trên ba QA sheets. Không dùng generic chicken/fish hoặc potato làm các lớp món nướng/khoai lang. Coffee mask chỉ vùng chất lỏng nên không dùng cho lớp cà phê đựng trong ly của lượt này.

Wikimedia Commons: giữ pageURL/originalURL/license/artist/capture date/SHA trong manifest. Kết quả tìm kiếm không tự là annotation;585 ảnh candidate đã được Codex xem trên contact sheets và ghi quyết định, gồm nhiều ảnh bị loại. Hai source JPEG hỏng bị loại, giữ nguyên bytes nguồn. Source tags grilled_chicken_breast là lịch sử truy vấn, không phải giới hạn lớp69 sau quyết định mới. FFML thêm ba ảnh lớp GRILLED CHICKEN BREAST của tác giả, đối chiếu Git blobSHA và giữ licenseMIT; ba góc chụp cùng một nhóm, chỉ vào train.

GroundingDINO-tiny từ IDEA-Research chỉ tạo bbox gợi ý bằng inference; safetensors được pin revision/checkSHA. Các bbox public-source được chọn bằng visual self-review, loại ly nước/trà, máy pha, menu/logo, đồ ăn khác, gà sống/chiên/luộc và cá không xác định. Không gọi đây là nhãn do người kiểm duyệt độc lập. Không dùng ảnh AI sinh để giả dữ liệu thật.

Food region/portion có thể gồm các miếng cùng thực phẩm; không hứa từng củ/miếng chạm nhau là một instance riêng. Ảnh train/holdout mới là crop từ bbox được chọn với8% context, bbox được biến đổi hình học đúng; không tự gán toàn khung hình làm bbox. Việc crop hạn chế đưa nguyên liệu/đồ uống chưa gán nhãn vào ảnh mới. Holdout này đo khả năng nhận diện vùng món đã khoanh; chưa là nghiệm thu ảnh toàn cảnh/iPhone.

Nguồn gốc: [FoodSeg103 tác giả](https://github.com/LARC-CMU-SMU/FoodSeg103-Benchmark-v1), [mirror](https://huggingface.co/datasets/EduardoPacheco/FoodSeg103), [Wikimedia Commons](https://commons.wikimedia.org/), [FFML tác giả và license](https://github.com/cristeaioan/ffml_dataset), [GroundingDINO docs](https://huggingface.co/docs/transformers/v4.57.1/model_doc/grounding-dino). License của source dataset/repository không phải xác minh riêng quyền của từng ảnh Recipe1M; provenance/điều kiện nhận được được giữ để review khi cần chia sẻ dữ liệu.

## Dữ liệu đã export và kiểm tra

Ignored export cuối: data/processed/food-extension-v2/yolo-75-v3. 3.021 ảnh train duy nhất;5.599 lượt lấy mẫu mỗi epoch do lặp sampling lớp mới, không tính lặp thành ảnh nguồn mới. Replay gồm2.369 ảnh toàn cảnh lớp cũ và30 crop parent đã xem để loại chồng lấn với gà/cá hồi nướng. Candidate replay nhầm ID51/53 được sửa trước export;51 là Thịt heo,53 mới là Thịt nướng. Không tự đổi parent generic thành lớp nướng.

| Lớp mới | Vùng train | Vùng validation | Vùng test |
| --- | ---: | ---: | ---: |
| Chuối |124|59|37|
| Táo |166|36|31|
| Gà nướng |27|4|6|
| Cá hồi nướng |28|7|6|
| Khoai lang |49|5|8|
| Khóm |114|29|30|
| Cà phê |54|14|15|
| Nước ngọt |60|17|10|

Tổng622 crop train mới từ385 ảnh nguồn;171 crop validation từ91 ảnh;143 crop test từ93 ảnh. Các số vùng/crop khác số ảnh nguồn. Khoanh theo creator/capture-day và pHashHamming≤6, aspect log-difference<0,12; nguồn/cụm trùng nằm một partition. FoodSeg original holdout không vào train. Một ảnh replay gần giống legacy holdout bị loại. pHash không bảo đảm bắt mọi ảnh gần trùng.

Giữ đủ787 ảnh validation và404 test cũ, byte và nhãn đối chiếu nguyên vẹn; độ phủ cũ35/29 lớp, cộng8 lớp mới thành43/37 lớp ở hai split kết hợp. Không có independent full75-class holdout. Export sơ bộ yolo-75-v2 bị preflight loại do thư mục validation cũ tên val, không phải valid; đã chặn trước train và dựng v3 đúng cả hai split. Không có train nào dùng export thiếu validation đó.

Preflight cuối: decode ảnh, nhãn finite/in-range, hash3.335 cặp ảnh/nhãn manifest, đối chiếu1.191 ảnh/nhãn holdout cũ; paths, source photos và groups disjoint giữa train/validation/test. Replay cũ dùng native label cache đã tin cậy của job local, không mở pickle tải từ ngoài. Chưa audit semantic toàn bộ legacy replay.

18 unit tests đạt: resume tải ngắnEOF/Range, checksum drift không ghi đè nguồn,67 identity bất biến/newNULL IDs, budget≤4 giờ/elapsed, crop geometry, invalid bbox và callback trước epoch đầu. Classifier expansion CPU check bảo toàn outputs67 cũ tại khởi tạo, maxdiff5,684e-14; không phải evidence giữ chất lượng sau fine-tune.

## Job train đang chạy

Job foodlens-yolo11n-20261016-extension4h-v2. Đồng hồ budget bắt đầu10:37:06 UTC+7 ngày16/10; hard deadline14:37:06 cùng ngày. YOLO11n,75classes,512px,batch32,AdamW,workers0,AMP,cacheFalse. Epoch là động theo time/early-stop, không hứa chạy cố định bao nhiêu epoch. Supervisor độc lập hidden, không gọi Codex/OpenAI API, có ledger chống tạo job mới để reset4 giờ, checkpoint atomic và guard đúng child process tree. Resume tính cả downtime trong cùng mốc kết thúc.

Lần khởi tạo đầu lỗi callback do Ultralytics chưa có trainer.epoch tại on_train_start, trước batch gradient đầu tiên. Đã sửa callback/getattr, thêm regression test và chạy tiếp từ baseline vì chưa có updates/checkpoint; giữ nguyên budget/deadline, không tạo lượt4 giờ mới. Sau sửa đã quan sát165/175 batch epoch0 với loss thật và GPU hoạt động. Chưa có kết luận model cuối.

Sau train, supervisor tự evaluate best checkpoint đã chọn bằng mixed validation: tách legacy full scenes và extension region crops, ghi75 dòng per-class với absent=NULL. Evaluation có thời gian riêng. Candidate artifact schema2 không tự được loader67 chấp nhận, không activate server/database. Xem ML-05-job.json, job/status.json và logs ignored để biết trạng thái mới nhất; tài liệu này là checkpoint lúc khởi chạy.

## Phần còn lại

Chờ train/checkpoint/evaluation; đọc so sánh giữ lớp cũ và8 lớp mới, nhất là holdout gà/cá hồi rất nhỏ. Sau đó mới cập nhật nullable original IDs/range/map75 ở backend, migration append8 foods giữ UUID/lịch sử, OpenAPI/handoff và chạy real model/Auth/Storage/RLS/API checks. Chưa bàn giao model75 hoặc kết luận đủ chất lượng demo. Nutrition approval và full mobile/LAN acceptance vẫn riêng, chưa hoàn thành.
