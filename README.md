# NhomX - Rock Paper Scissors (Socket Multi Client-Server)

Mini game **Rock–Paper–Scissors** sử dụng kỹ thuật **lập trình Socket** theo mô hình **Multi Client–Server**.

## Điểm nổi bật
- ✅ Multi-client TCP server (nhiều client kết nối đồng thời)
- ✅ Lobby + quản lý **phòng (room)**: list/create/join/leave
- ✅ **QuickPlay**: xếp hàng (queue) để ghép cặp tự động
- ✅ Luật chơi **best-of-3**
- ✅ **Timeout chọn** (mặc định 10s): không chọn sẽ thua round
- ✅ Xử lý **disconnect**: báo cho đối thủ + reset phòng/ghép người mới
- ✅ Chat trong phòng
- ✅ Leaderboard (thắng/thua theo phiên chạy server)

## Yêu cầu môi trường
- Python **3.10+** (khuyến nghị)

## Cách chạy (Windows PowerShell)
Mở 2 (hoặc nhiều) cửa sổ terminal.

### 1) Chạy Server
```powershell
cd <thu_muc_du_an>
python -m server.server --host 127.0.0.1 --port 8888
```

### 2) Chạy Client (mỗi người chơi mở 1 terminal)
```powershell
cd <thu_muc_du_an>
python -m client.client --host 127.0.0.1 --port 8888 --name Hau
```

## Lệnh client
### Lobby
- `/rooms` : xem danh sách phòng
- `/create <room>` : tạo phòng
- `/join <room>` : vào phòng
- `/quick` : vào hàng chờ QuickPlay (ghép cặp)
- `/leaderboard` : xem bảng thắng/thua
- `/quit` : thoát

### Trong phòng
- `/chat <message>` : chat
- `/move rock|paper|scissors` : chọn nước đi
- `/leave` : rời phòng

## Ảnh chụp sản phẩm (để nộp bài)
Chụp tối thiểu:
1. 1 ảnh Server đang chạy (log match/queue)
2. 2–3 ảnh Client: (1 đang chơi, 1 đang chờ queue, 1 chat/leaderboard)

Thư mục gợi ý: `screenshots/`

## Nộp bài
Nén thư mục dự án thành file:
**`NhomX-TenDeTai.zip`**

Gợi ý tên: `NhomX-RockPaperScissors-Socket.zip`

## Gợi ý Git history (nhóm 6 người)
Xem `docs/GIT_WORKFLOW.md` và `docs/COMMIT_PLAN.md`.
