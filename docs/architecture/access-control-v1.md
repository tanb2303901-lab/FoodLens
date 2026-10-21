# Quyền truy cập FoodLens v1

Cập nhật 2026-10-20 (FOOD-02). Kiểm thử hiện hành: SQL test `supabase/tests/001`, `002`, `004`, `005` và các script HTTP thật; xem [review FOOD-02](../reviews/FOOD-02-implementation.md).

## Danh tính

App đăng nhập qua Supabase Auth SDK và gửi Bearer access token tới FastAPI. Backend xác minh token (thuật toán theo cấu hình, issuer, audience, hạn, UUID subject) rồi gọi Supabase bằng chính token đó cho từng request, nên RLS luôn có ngữ cảnh người dùng. Public key không thay user token. Service-role key chỉ ở phía server, dùng cho ghi kết quả model và ảnh sau khi backend đã xác minh owner; không bao giờ có trong app.

## Quyền theo bảng

| Đối tượng | anon | authenticated | Server/admin |
| --- | --- | --- | --- |
| profiles | Không | Đọc của mình; sửa qua RPC `patch_profile` | Trigger tạo khi có user |
| foods | Không | Đọc các cột catalog của món active (không có metadata) | Import/admin |
| scans | Không | Đọc của mình; xác nhận qua RPC `confirm_scan` | `start_scan`/`finish_scan` chỉ service_role |
| food_descriptions, content_sources, food_description_sources | Không | Chỉ bản published hiện hành và nguồn nó trích; không thấy người duyệt/ghi chú | Importer nội dung local |
| import_runs | Không | Không | Import/admin |
| Storage `food-scans` | Không | Chỉ ảnh thuộc scan của mình, qua link ký có hạn | Server upload/xóa |

## Nguyên tắc

- RLS bật trên mọi bảng app; quyền table được thu hồi trước rồi cấp đúng cột cần thiết.
- Hàm ghi riêng nằm trong schema `foodlens_private`, SECURITY DEFINER thuộc role `foodlens_rpc` (NOLOGIN, NOBYPASSRLS), cố định `search_path`; wrapper public là SECURITY INVOKER.
- Chặn đọc/sửa chéo tài khoản: scan khác owner trả 404, xác nhận của người khác bị từ chối.
- `/health/ready` dùng hàm `core_readiness()` chỉ trả boolean, không lộ dữ liệu.
