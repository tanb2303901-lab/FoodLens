# FoodLens: hướng dẫn cài đặt cho người làm frontend

Hướng dẫn dành cho laptop **Windows 10/11**. App được test trực tiếp trên **điện thoại của bạn bằng Expo Go**, chạy được trên cả iPhone lẫn Android. Không cần máy ảo hay Android Studio.

> **Quy tắc git quan trọng:** toàn bộ code app làm trên nhánh **`frontend`**, chỉ trong thư mục `mobile\`. **Không commit hay push vào `main`.** Nhánh `main` là của chủ dự án; chủ dự án sẽ review rồi merge `frontend` vào `main`. Cách làm ở Phần F và Phần G.

Bạn sẽ chạy một backend FoodLens riêng trên laptop. Database, đăng nhập và model nhận diện món đều đã có trong repo. Bạn **không cần train model, không cần GPU và không cần dataset**.

```
Điện thoại (Expo Go)  ──Wi-Fi nhà──▶  Laptop của bạn
                                         ├─ Expo (code app, cổng 8081)
                                         ├─ Backend FoodLens + model (cổng 8000)
                                         └─ Supabase local trong Docker (cổng 54321)
```

Điện thoại và laptop **phải dùng chung một Wi-Fi**. Dùng 4G hoặc Wi-Fi khác thì không chạy được.

Dữ liệu trên máy bạn và máy chủ dự án là riêng biệt: tài khoản test và lịch sử scan của bạn chỉ có trên máy bạn.

---

## Phần A. Tải và cài trước (làm ngay, khoảng 1 giờ)

Laptop nên có từ **16 GB RAM** (tối thiểu 8 GB) và **còn trống khoảng 15 GB ổ đĩa**.

| # | Cài trên | Phần mềm | Tải ở đâu | Lưu ý khi cài |
| --- | --- | --- | --- | --- |
| 1 | Laptop | **Git for Windows** | https://git-scm.com/download/win | Để mặc định |
| 2 | Laptop | **Docker Desktop** | https://www.docker.com/products/docker-desktop/ | Chọn "Use WSL 2". Cài xong khởi động lại máy, mở Docker Desktop và đợi "Engine running" |
| 3 | Laptop | **Python 3.12** (đúng bản 3.12, 64-bit) | https://www.python.org/downloads/windows/ | Tick **"Add python.exe to PATH"** và giữ tick **"py launcher"** |
| 4 | Laptop | **Node.js LTS** | https://nodejs.org | Để mặc định. Cần cho Expo và `npx` |
| 5 | Điện thoại | **Expo Go** | App Store (iPhone) hoặc CH Play (Android) | Cập nhật lên bản mới nhất |
| 6 | Laptop | VS Code (không bắt buộc) | https://code.visualstudio.com | |

Ngoài ra, hãy **chấp nhận lời mời collaborator** của repo GitHub (kiểm tra email hoặc https://github.com/notifications).

Đặt mạng Wi-Fi nhà trên laptop ở chế độ **Private**: Settings → Network & internet → Wi-Fi → (tên mạng) → Network profile type → **Private network**. Nếu để Public, Windows sẽ chặn điện thoại kết nối vào laptop.

Sau khi cài, mở **PowerShell mới** và kiểm tra:

```powershell
git --version
docker info
py -3.12 --version
node --version
npx --version
```

Lệnh nào báo lỗi thì cài lại phần mềm đó. Riêng `docker info` báo lỗi thì thường là Docker Desktop chưa mở.

---

## Phần B. Lấy code (khi chủ dự án báo đã push)

```powershell
cd D:\
git clone https://github.com/tanb2303901-lab/FoodLens.git
cd FoodLens
```

Đường dẫn thư mục nên **không có dấu tiếng Việt và không có khoảng trắng**, ví dụ `D:\FoodLens`.

Kiểm tra model đã được tải về đủ. File `weights.pt` phải nặng khoảng 21 MB và `legacy-weights.pt` khoảng 5 MB; nếu chỉ vài trăm byte là clone bị lỗi:

```powershell
dir ml\models\foodlens-yolo11n-20261016-extension4h-v2
```

---

## Phần C. Cài backend (chỉ làm một lần)

Mở Docker Desktop và đợi nó chạy. Sau đó, trong thư mục `FoodLens`, chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_dev.ps1
```

Script tự làm 7 bước. **Lần đầu mất khoảng 15–40 phút** vì phải tải thư viện Python (khoảng 1 GB) và image Docker:

1. Kiểm tra công cụ
2. Tạo môi trường Python `.venv` và cài thư viện, chạy model bằng CPU
3. Khởi động Supabase local trong Docker (database, đăng nhập, lưu ảnh)
4. Tạo file cấu hình riêng của máy trong `data\processed\`; file này không được đưa lên git
5. Nạp danh mục 75 món
6. Nạp phần giới thiệu món đã được duyệt
7. Kiểm tra: phải thấy hai dòng **`So mon trong database: 75`** và **`So mon co gioi thieu da duyet: 75`**, rồi dòng xanh `Cai dat xong`

Nếu lỗi giữa chừng, sửa nguyên nhân rồi chạy lại đúng lệnh trên. Script chạy lại an toàn và không làm mất dữ liệu.

**Mở Firewall (một lần):** lệnh này **bắt buộc chạy bằng quyền Administrator**, nếu không sẽ báo `Access is denied`. Cách mở: bấm phím Windows → gõ `PowerShell` → **chuột phải → Run as administrator** → **Yes**. Tiêu đề cửa sổ phải là **"Administrator: Windows PowerShell"**. Rồi chạy lệnh dưới. Lệnh này cho điện thoại vào được 3 cổng: Expo 8081, backend 8000 và Supabase 54321. Không mở thêm cổng nào khác; 54322 là database, không được mở.

```powershell
New-NetFirewallRule -DisplayName "FoodLens dev" -Direction Inbound -Protocol TCP -LocalPort 8000,8081,54321 -Action Allow -Profile Private
```

Thành công thì PowerShell in ra thông tin rule, có dòng `Enabled : True` và không có chữ đỏ.

---

## Phần D. Chạy backend (mỗi lần làm việc)

1. Mở Docker Desktop.
2. Mở PowerShell trong thư mục `FoodLens` và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_dev_backend.ps1
```

Script tìm IP Wi-Fi của laptop và in ra địa chỉ dạng:

```
Trong app dat:  API_BASE_URL = http://192.168.1.25:8000
                SUPABASE_URL = http://192.168.1.25:54321
```

**Giữ cửa sổ này mở** trong lúc làm việc. Nhấn `Ctrl+C` để tắt backend.

**Kiểm tra trên điện thoại:** mở trình duyệt (Safari/Chrome) trên điện thoại và vào `http://<IP vừa in>:8000/health/ready`. Trang phải hiện `"scan":true`. Nếu không mở được, xem Phần H trước khi làm app.

Trên laptop có thể mở http://127.0.0.1:8000/docs (Swagger) để xem và thử mọi API.

Nếu script lấy sai IP (máy có VPN, cắm dây mạng hoặc có nhiều card mạng):

1. Gõ `ipconfig`.
2. Tìm dòng **IPv4 Address** của mục **Wireless LAN adapter Wi-Fi**.
3. Chạy lại script, chỉ định IP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_dev_backend.ps1 -HostIp 192.168.1.25
```

---

## Phần E. Cấu hình app

App chỉ cần 3 giá trị. Ghi chúng vào file `mobile\.env`:

```
EXPO_PUBLIC_API_BASE_URL=http://<IP>:8000
EXPO_PUBLIC_SUPABASE_URL=http://<IP>:54321
EXPO_PUBLIC_SUPABASE_ANON_KEY=<ANON_KEY của máy bạn>
```

Lấy `ANON_KEY` (key public của Supabase local trên máy bạn) bằng lệnh:

```powershell
(Get-Content data\processed\supabase-local.json -Raw | ConvertFrom-Json).ANON_KEY
```

Một số quy tắc:

- File `.env` **không được commit**; `.gitignore` đã chặn sẵn.
- **Tuyệt đối không** đưa vào app hay lên git các thứ sau: `SERVICE_ROLE_KEY`, `JWT_SECRET`, file `data\processed\*.json` và file `supabase-start.log`.
- **IP laptop có thể đổi** sau khi khởi động lại router hoặc đổi mạng. Khi app báo không kết nối được:
  1. Chạy lại `run_dev_backend.ps1`.
  2. Sửa `.env` theo IP mới.
  3. Khởi động lại Expo bằng `npx expo start -c`.

**Tài khoản test:** đăng ký ngay trong app bằng email bất kỳ (ví dụ `test1@example.com`) và mật khẩu từ 6 ký tự. Supabase local không gửi email xác nhận.

---

## Phần F. Làm frontend và chạy trên điện thoại

**Trước khi viết dòng code nào, chuyển sang nhánh `frontend`** (một lần), trong thư mục `FoodLens`:

```powershell
git checkout -b frontend
git branch
```

`git branch` phải hiện dấu `*` trước chữ `frontend`. Nếu nhánh `frontend` đã có sẵn trên GitHub (ví dụ bạn clone lại máy khác), dùng `git checkout frontend` thay cho `git checkout -b frontend`.

Mỗi lần mở máy làm tiếp, kiểm tra lại bằng `git branch`: phải đang ở `frontend`, không phải `main`.

Tạo app (một lần), trong thư mục `FoodLens`:

```powershell
npx create-expo-app@latest mobile --template blank-typescript
```

Chạy app (mỗi lần làm việc). Mở **cửa sổ PowerShell thứ hai**; cửa sổ backend vẫn để mở:

```powershell
cd mobile
npx expo start
```

Terminal hiện mã QR:

- **iPhone:** mở app **Camera** và quét QR.
- **Android:** mở **Expo Go** và chọn "Scan QR code".

App mở trong Expo Go. Mỗi lần lưu code, app trên điện thoại tự cập nhật. Lần đầu Windows hỏi Firewall cho Node.js thì chọn **Allow** (Private).

Nếu điện thoại không mở được app từ QR (lỗi kết nối tới 8081), dùng `npx expo start --tunnel`. Cách này chỉ đổi đường tải code app; backend vẫn phải đi qua Wi-Fi như Phần D.

Đọc tài liệu theo thứ tự:

1. [backend-v1.md](backend-v1.md): phạm vi app, danh sách API, luồng màn hình, các trạng thái lỗi
2. [food-description-api.md](food-description-api.md): thẻ giới thiệu món sau khi nhận diện
3. [api-examples-v1.json](api-examples-v1.json): 15 request/response thật
4. [error-codes-v1.md](error-codes-v1.md): mã lỗi
5. [openapi-backend-v1.json](../architecture/openapi-backend-v1.json): contract đầy đủ, có thể xem trực tiếp ở `/docs`

Quy ước:

- Stack: **React Native + Expo + TypeScript**.
- Chỉ dùng thư viện chạy được trong **Expo Go**, ví dụ:
  - `expo-image-picker` / `expo-camera` để chụp hoặc chọn ảnh
  - `@supabase/supabase-js` để đăng nhập
  - `@react-native-async-storage/async-storage` để giữ phiên đăng nhập
  - Cài bằng `npx expo install <tên>`. Thư viện cần native code riêng sẽ không chạy trong Expo Go.
- Mọi request `/v1/*` gửi header `Authorization: Bearer <access_token>`.
- Gửi ảnh lên `POST /v1/scans/analyze` dạng multipart, field `file`. Xem mục "Gửi ảnh từ app" ngay dưới.
- Vẽ **mọi** khung nhận diện. Mỗi món (`food_id`) chỉ có một thẻ thông tin. Không hiện phần trăm confidence.
- Không có dinh dưỡng, calo hay bữa ăn. Backend không có các API này.
- Không sửa `backend\`, `supabase\`, `scripts\` và `ml\`. Nếu cần backend thay đổi, hãy báo chủ dự án.

### Gửi ảnh từ app (dễ sai nhất)

Backend chỉ nhận **JPEG, PNG hoặc WebP, tối đa 10 MiB**:
- Ảnh khác loại bị trả `415 UNSUPPORTED_IMAGE`.
- Ảnh quá lớn bị trả `413 IMAGE_TOO_LARGE`.

Ảnh chụp trên **iPhone thường là HEIC** và ảnh điện thoại thường rất nặng. Vì vậy, trước khi gửi:

1. Chụp hoặc chọn ảnh bằng `expo-image-picker` (có thể đặt `quality: 0.8`).
2. **Chuyển sang JPEG và thu nhỏ** bằng `expo-image-manipulator`: định dạng JPEG, cạnh dài khoảng 2048 px. Thu nhỏ như vậy không ảnh hưởng kết quả nhận diện.
3. Gửi bằng `FormData`, **không tự đặt header `Content-Type`**; để `fetch` tự đặt kèm boundary:

```ts
const form = new FormData();
form.append('file', { uri: jpegUri, name: 'photo.jpg', type: 'image/jpeg' } as any);
form.append('input_source', 'camera'); // hoặc 'gallery'
const res = await fetch(`${process.env.EXPO_PUBLIC_API_BASE_URL}/v1/scans/analyze`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${session.access_token}` },
  body: form,
});
```

Một số lưu ý khác:
- Đặt thời gian chờ dài, khoảng 60–90 giây; lần scan đầu chậm hơn vì model mới được nạp.
- Link ảnh trong lịch sử hết hạn sau 5 phút; khi ảnh không hiện thì gọi lại chi tiết scan.
- Expo Go cho phép gọi `http://` tới IP trong mạng nhà. Nếu sau này build app riêng (không qua Expo Go) thì cần HTTPS hoặc cấu hình thêm; việc đó tính sau.

---

## Phần G. Đưa code lên GitHub

Chỉ làm trên nhánh `frontend` đã tạo ở Phần F. **Không push vào `main`.**

Lần đầu đưa code lên:

```powershell
git branch
git add mobile
git status
git commit -m "feat(mobile): ..."
git push -u origin frontend
```

Những lần sau chỉ cần:

```powershell
git add mobile
git status
git commit -m "feat(mobile): ..."
git push
```

Nếu `git branch` cho thấy đang ở `main`, **dừng lại**, chạy `git checkout frontend` rồi mới commit. Nếu lỡ commit trên `main`, đừng push; báo chủ dự án để gỡ giúp.

Trước khi commit, đọc `git status` để chắc **không có** `.env`, `node_modules`, `data\processed` hay `.venv`. Mỗi khi xong một phần, push và báo chủ dự án để review và merge.

Lấy cập nhật mới nhất của backend từ `main` vào nhánh `frontend` (đứng ở nhánh `frontend` khi chạy):

```powershell
git fetch origin
git merge origin/main
```

Sau mỗi lần lấy cập nhật, chạy lại `scripts\setup_dev.ps1`. Lần chạy lại mất khoảng 1–3 phút, an toàn và không mất dữ liệu; nó tự áp migration mới và nội dung món mới nếu có.

---

## Phần H. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| `Docker Desktop chua chay` | Mở Docker Desktop, đợi "Engine running" rồi chạy lại |
| `running scripts is disabled` | Chạy đúng lệnh có `-ExecutionPolicy Bypass` như trên |
| `Khong tim thay Python 3.12` | Cài Python 3.12 có py launcher, mở PowerShell mới |
| Supabase báo cổng 54321/54322 đang bị dùng | Tắt dự án Supabase hoặc Postgres khác đang chạy, hoặc khởi động lại máy |
| `/health/ready` có `"scan": false` | Kiểm tra thư mục model (Phần B) rồi chạy lại `run_dev_backend.ps1` |
| `New-NetFirewallRule : Access is denied` | PowerShell chưa chạy bằng quyền Administrator; mở lại theo Phần C |
| Điện thoại không mở được `http://<IP>:8000/health/ready` | Kiểm tra lần lượt: (1) cùng Wi-Fi, không dùng 4G; (2) Wi-Fi trên laptop để **Private**; (3) đã chạy lệnh Firewall ở Phần C; (4) IP đúng, xem `ipconfig`; (5) Wi-Fi khách hoặc ký túc xá có thể chặn các máy nói chuyện với nhau, khi đó dùng Wi-Fi nhà hoặc phát hotspot từ một điện thoại khác cho cả laptop và điện thoại cùng vào; (6) tạm tắt VPN trên laptop và điện thoại (Cloudflare WARP, 1.1.1.1, iCloud Private Relay…) |
| Quét QR không mở được app | Kiểm tra như trên với cổng 8081, hoặc dùng `npx expo start --tunnel` |
| Expo Go báo SDK không hợp lệ | Cập nhật Expo Go; app phải tạo bằng `create-expo-app@latest` |
| Ảnh trong lịch sử không hiện | `SUPABASE_URL` trong `.env` phải đúng IP đang in ra. Link ảnh hết hạn sau 5 phút, cần tải lại chi tiết scan |
| App gửi ảnh bị `415 UNSUPPORTED_IMAGE` hoặc `413 IMAGE_TOO_LARGE` | Chuyển ảnh sang JPEG và thu nhỏ trước khi gửi (Phần F, mục "Gửi ảnh từ app") |
| Lần scan đầu tiên chậm | Bình thường vì model mới được nạp. Các lần sau nhanh hơn |
| 401 | Token hết hạn: refresh session hoặc đăng nhập lại |

Tắt hẳn Supabase khi không dùng để tiết kiệm RAM (dữ liệu vẫn giữ):

```powershell
npx -y supabase@2.120.0 stop
```

Không chạy `supabase db reset` trừ khi chủ dự án hướng dẫn. Nếu lỡ chạy, hãy chạy lại `scripts\setup_dev.ps1`.

**Gặp lỗi khác:** chụp màn hình lỗi gửi cho chủ dự án. **Không gửi** file trong `data\processed\` vì các file đó có key.
