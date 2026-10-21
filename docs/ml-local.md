# FoodLens ML local — baseline theo ngân sách8 giờ train

Hiện hành16/10 sau lựa chọn owner: backend đang dùng model75 foodlens-yolo11n-20261016-extension4h-v2-dual75 qua backend-ml75.json; live ready/scan=true. Trang http://127.0.0.1:8765 đã nhận ảnh thật và hiện Táo67,3%/328,2ms. Local preview được owner cho phép dù quality gate71 trước đó chưa đạt; số liệu được giữ nguyên trong [kết quả ML-05](reviews/ML-05-local-result.md). Không train lại. Nếu cần khởi động lại model75 qua activation helper, phải dùng đúng bundle với --activate --owner-preview, giữ record quyết định owner và951 API checks; không reset budget/gates. Helper trang chạy module scripts.local_scan_test bằng ML venv. Các trạng thái model67 active hoặc75 đang chờ phía dưới là lịch sử.

Kết quả mới nhất16/10 lúc13:20 UTC+7: ML-05 train xong70 full epochs/1h15m7s, đánh giá xong12:50 và951 real API checks/151 ảnh đạt. Khoai lang test AP50~0,1648 chưa đạt gate0,25 nên model75 chưa activate. Backend67 đã khôi phục/scan=true, trang75 đang chờ lựa chọn owner về bản thử có hạn chế. Không train thêm hoặc đổi checkpoint theo test. Xem [kết quả ML-05](reviews/ML-05-local-result.md) và [metrics75](dataset/model-evaluation-v2.json); các trạng thái training phía dưới là lịch sử.

Cập nhật16/10: owner đã cho resume và mở màn hình train. Cùng jobML-05 chạy lại11:45:10 UTC+7 sau pause được xác minh, cap3 giờ tích lũy và hard cutoff13:00 UTC+7; giữ704,047054 giây đã dùng và loại đúng3380,034637 giây pause. Không chạy lệnh train thứ hai. Monitor là cửa sổ FoodLens - ML-05 training progress. Database local hiện75 món, backend0.5.0; model75 chưa activate. Bản67/weights cũ giữ nguyên. Xem [review hiện hành](reviews/ML-05-extension.md). Mốc14:37/budget4 giờ/PAUSED phía dưới là lịch sử superseded.

Ngày 2026-10-15. Owner cho phép train trên máy local cắm sạc, ưu tiên thời gian, giới hạn train tối đa8 giờ. Chuẩn bị/export/evaluation/API integration có thời gian riêng. Đây là baseline thực nghiệm; chất lượng được báo bằng metrics thật, không cam kết một % accuracy trước evaluation. Frontend và nutrition approval độc lập.

## Lượt bổ sung ML-05 đang chạy riêng

Quyết định ngày16/10 cho phép thêm8 lớp, tổng75, với một budget mới tối đa4 giờ: Chuối, Táo, Gà nướng (mọi phần), Cá hồi nướng, Khoai lang (mọi cách chế biến xác định được củ), Khóm, Cà phê, Nước ngọt. Không resume/tăng lượt8 giờ đã xong. Xem [ML-05 review](reviews/ML-05-extension.md) và candidate map75 trong docs/dataset/food-identities-v2.json. Chưa activate model/catalog75; server đang phục vụ bản67.

Job độc lập foodlens-yolo11n-20261016-extension4h-v2 bắt đầu tính budget10:37:06 UTC+7 ngày16/10; dừng train chậm nhất14:37:06, có thể sớm hơn theo early-stop. Lỗi callback trước batch đầu đã sửa, downtime vẫn tính trong cùng budget. Ledger ML-05-budget.json chống tự tạo job khác/reset giờ. Không khởi động lại lệnh train trong lúc job đang chạy.

Xem trạng thái, không chứa credentials:

```powershell
Get-Content 'C:/Nienluan/FoodLens/data/processed/ML-05-job.json'
Get-Content 'C:/Nienluan/FoodLens/data/processed/ml-runs/foodlens-yolo11n-20261016-extension4h-v2/status.json'
```

Giữ laptop cắm sạc và không đóng nắp/tắt máy. Process train giữ máy thức trong lúc chạy, không phụ thuộc chat/Codex usage. Sau train, supervisor tự chạy evaluation riêng cho bộ cũ toàn cảnh và bộ mới dạng vùng crop; đây là thời gian ngoài train. Candidate75 chỉ được lưu vào ignored ml/models để review tiếp, không tự thay backend hiện tại. Full-scene/iPhone, nutrition và API/database75 còn chờ nghiệm thu.

## Trạng thái hoàn tất

Pipeline ready_for_owner_test lúc 22:39:43 UTC+7 ngày 2026-10-15. Train 7h57m22,547s, 14 full epochs và một phần epoch15; valid/test evaluation, 51 real API checks và activation đã hoàn tất. Backend hiện tại port8000 dùng real model foodlens-yolo11n-20261015-budget8h-v1; live readiness đã xác minh model=ready/scan=true, Swagger200. Không cần train lại khi muốn sử dụng model.

Test mAP50 0,7406/mAP50-95 0,5469 trên404 ảnh/29 lớp; validation mAP50 0,6705 trên787 ảnh/35 lớp. Đây không là accuracy mọi món/ảnh hoặc full67 quality acceptance. Kết quả tại [ML-02 training](reviews/ML-02-training.md), [ML-03 implementation](reviews/ML-03-implementation.md), [portable metrics](dataset/model-evaluation-v1.json), [món thử demo](handoff/demo-model-baseline.md). Frontend/iPhone/LAN và nutrition approval vẫn chưa nghiệm thu.

## Môi trường và cấu hình đã đo

Thử ảnh trực quan trên laptop: sau yêu cầu ngày2026-10-16, công cụ local tại http://127.0.0.1:8765/ đã được mở. Chọn ảnh JPEG/PNG/WebP từ máy và bấm Nhận diện để xem canonical bbox/tên/confidence qua backend thật. Không cần nhập token vào trang; tài khoản test riêng và session chỉ giữ phía server trong ignored data/processed. Ảnh được lưu private dưới owner test, không dùng train. Xem [ML-04 local test](reviews/ML-04-local-test.md) để khởi động lại helper khi cần. Đây không phải frontend mobile hoặc nghiệm thu ảnh mạng/thiết bị; không tính dinh dưỡng chưa được duyệt.

RTX4060 Laptop8GB, RAM khả dụng tổng khoảng15,2GiB,32 logical CPUs; CUDA matmul đã chạy thật. ML dùng venv riêng data/processed/ml-venv, PyTorch2.11.0+cu126, torchvision0.26.0+cu126, Ultralytics8.4.158 và backend dependencies pin. Venv backend .venv giữ riêng. Snapshot dependencies ml/requirements-windows-cu126.lock.txt.

Máy mới: tạo Python3.12 venv riêng; cài torch2.11.0/torchvision0.26.0 từ official index https://download.pytorch.org/whl/cu126 rồi Ultralytics8.4.158 và backend/requirements.txt. Lock là snapshot platform Windows/CUDA, cần đúng torch index để lấy local-version +cu126; không dùng làm lock cho runtime CPU/mobile. Không nâng driver/CUDA hệ thống trong task này.

Benchmark320 train images +64 validation images đều lấy từ ORIGINAL TRAIN, chỉ đo throughput/memory và kiểm tra pipeline; không là model accuracy/evaluation holdout. Candidates YOLO26n/YOLO11n,512px, batch16/32/64, workers0/AMP/cache=False. Chọn YOLO11n batch32 theo steady throughput khoảng270 images/s và peak allocated2,81GiB trong benchmark; batch64 khoảng264 images/s và5,45GiB. Tốc độ full dataset còn phụ thuộc I/O/augmentation/validation và nhiệt độ. Đây không phải ETA hoặc accuracy.

Ảnh/nhãn dẫn xuất ở ignored data/processed/vision-yolo-v1. Ảnh được copy (không symlink/hardlink), full CRC/SHA kiểm khi đọc; thư viện có thể ghi cache/repair ở bản dẫn xuất mà không đụng nguồn. Chỉ effective train/valid/test; review/excluded giữ ngoài. Pretrained COCO80 chỉ làm điểm khởi đầu; backend không dùng80 class names thay map FoodLens67.

## Job độc lập và xem tiến độ

Pipeline process được mở hidden bằng Start-Process, không gọi Codex/OpenAI API. Sau khi export hoàn tất và checkpoint smoke đạt: train → real valid/test evaluation → model bundle → real Auth/Storage/meal API checks → chỉ khi passed mới restart đúng backend process local port8000 bằng ML venv/config riêng.

```powershell
Set-Location 'C:/Nienluan/FoodLens'
& 'data/processed/ml-venv/Scripts/python.exe' -m ml.job_status
```

State/logs ignored: ML-job.json, ML-pipeline.stdout.log/.stderr.log; train status/checkpoints tại data/processed/ml-runs/foodlens-yolo11n-20261015-budget8h-v1. Log và status files không chứa tokens/passwords/signed URLs. Không khởi động một job thứ hai hoặc xóa dataset/checkpoints khi job đang chạy.

Lượt chính đã hoàn tất. Các đoạn hướng dẫn lifecycle/resume bên dưới mô tả cơ chế, không là yêu cầu khởi động lại train. Không tự dùng budget thừa để train thêm sau acceptance.

Lượt chính bắt đầu 2026-10-15 lúc 14:41 UTC+7; deadline train khoảng 22:41 cùng ngày, bao gồm khởi tạo/kiểm dataset. Đây là thời điểm dừng train tối đa, không phải cam kết toàn pipeline/app xong lúc đó. Status tool hiển thị cả deadline UTC/local và batches của epoch hiện tại.

Sau khi regression/preflight đạt, Docker Desktop dedicated được tạm dừng để nhường RAM cho train. Đã kiểm thử mở lại Docker bằng CLI và start đúng năm container hiện có về trạng thái healthy; không recreate/reset/import. Real API stage tự chạy restore này trước acceptance. Detailed resource/restore evidence ở ML-runtime-resources.json. Trong khoảng Docker dừng, API/database readiness không phải môi trường test đang mở.

Budget tính theo elapsed của process train (có cộng elapsed trước nếu resume). UL timed stop và callback wall deadline dự phòng chừa thời gian serialize/validate; supervisor có guard cho đúng child PID. Save last/best atomically mỗi epoch và giữ last-resume.pt chứa optimizer trước khi library strip inference weights. Không báo partial final epoch thành full epoch; status có epochs_with_updates/partial_final_epoch. Preflight checkpoint smoke/resume đã chạy trên subset train riêng, không được activate làm model sản phẩm.

Máy cần cắm sạc, không đóng nắp gây sleep/hibernate, tắt/restart hoặc kill process. Pipeline/train dùng process-scoped keep-awake trong lúc chạy và trả trạng thái khi kết thúc; không sửa power plan. Hết usage Codex không phải lệnh dừng Python/GPU. Nếu Codex chưa thể trả lời, job vẫn chạy theo script; sau đó xem status hoặc đưa lại job path để tiếp tục review.

Sau khi train hoàn tất, keep-awake của job đã kết thúc. Muốn dùng API local thì laptop/Docker/backend phải đang chạy; tắt máy không mất model nhưng API sẽ offline.

Resume sau lỗi dùng checkpoint optimizer và budget còn lại, không tự tăng quá8 giờ:

```powershell
& 'data/processed/ml-venv/Scripts/python.exe' -m ml.train_budget --dataset 'C:/Nienluan/FoodLens/data/processed/vision-yolo-v1' --job 'C:/Nienluan/FoodLens/data/processed/ml-runs/foodlens-yolo11n-20261015-budget8h-v1' --benchmark 'C:/Nienluan/FoodLens/data/processed/ml-benchmark/results.json' --hours 8 --resume
```

Chỉ resume khi job trước đã dừng và đã xem error/status. Nếu exhausted budget, cần quyết định mới để train thêm; không chạy song song hoặc reset counters. Mất điện giữa epoch có thể mất phần sau checkpoint gần nhất; không hứa resume từng batch.

## Kết quả và phạm vi nghiệm thu

Khi thành công: ignored ml/models/foodlens-yolo11n-20261015-budget8h-v1 chứa weights.pt, manifest.json, exact class map và evaluation.json có checksums. Default config backend-local.json không bị đổi; backend-ml.json là config riêng giữ secrets local. Startup factory kiểm checksums/names67/map/preprocessing/evaluation và warmup thật; lỗi/missing bundle vẫn503 MODEL_NOT_READY, core APIs giữ hoạt động.

Bundle còn có model-card.md đọc trực tiếp được: scope/time/epochs, aggregate metrics, coverage/AP50 từng lớp, latency và provenance. Latency prediction batch-one khác HTTP/Auth/Storage latency trong ML-03-model-integration.json. Smoke/fixture scope bị chặn activation; chỉ matching API report của full_audited_effective_train mới được bật server chính. Nếu startup model server thất bại, script khôi phục core config và ghi rollback evidence.

Config của smoke preflight ở backend-ml-preflight.json; không dùng nó làm server chủ dự án. Loader đã verify đủ train/valid images; cache native loại 146 duplicate training labels trong 143 ảnh, giữ 822.311 train boxes. Source/exported labels vẫn giữ nguyên. Evaluation report phân biệt raw exported count với native retained count để metrics phản ánh dữ liệu thực sự dùng.

valid35 classes/test29 classes được báo đúng, absent class metricsNULL; không lấy mean AP gán cho absent classes. Runtime bboxxyxy_norm theo canonical image dimensions; confidence thật, không Top-3 giả. Model baseline chưa có full independent67-class holdout/quality acceptance. Ready_for_owner_test trong job state là điều kiện kỹ thuật để owner test, không phải toàn app/product đã nghiệm thu.

Nếu API/model test fail, pipeline dừng trước activate và ghi failed_stage; không thay bằng fake detections. Docs review cuối chỉ đánh dấu complete sau khi đọc evidence thật. Giữ source và README, không cloud/reset/commit/push/deploy.

## Chạy lại backend model sau khi đã dừng server hoặc khởi động lại máy

Server đang chạy thì dùng ngay http://127.0.0.1:8000/docs; tránh khởi động thêm server cùng port. Sau khi dừng đúng process thuộc project, mở Docker Desktop và đợi stack healthy rồi dùng ML venv/config riêng:

```powershell
Set-Location 'C:/Nienluan/FoodLens'
$env:FOODLENS_CONFIG_PATH = 'C:/Nienluan/FoodLens/data/processed/backend-ml.json'
& 'data/processed/ml-venv/Scripts/python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Base .venv/backend-local.json chỉ là core runtime, không tự nạp model. Không copy config thật sang mobile hoặc gửi keys vào chat. Loopback này chưa dùng trực tiếp từ iPhone; device/LAN integration là bước riêng.

Nguồn triển khai: [PyTorch official CUDA wheels](https://pytorch.org/get-started/previous-versions/), [Ultralytics train](https://docs.ultralytics.com/modes/train), [validation](https://docs.ultralytics.com/modes/val), [YOLO11](https://docs.ultralytics.com/models/yolo11), [YOLO26](https://docs.ultralytics.com/models/yolo26). Pretrained weights từ official ultralytics/assets v8.4.0; code/weights license URL được giữ trong model manifest để review trước phát hành.
