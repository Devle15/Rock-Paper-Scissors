import socket
import threading

HOST = '127.0.0.1'
PORT = 65432

def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    
    # Gửi lời chào và hướng dẫn khi mới kết nối
    welcome_msg = "\n=== GAME KÉO BÚA BAO ===\nGõ /help để xem hướng dẫn.\n"
    conn.sendall(welcome_msg.encode('utf-8'))

    while True:
        try:
            # Nhận dữ liệu và "Improve parsing" (xử lý khoảng trắng, chữ hoa/thường)
            data = conn.recv(1024).decode('utf-8').strip().lower()
            
            if not data or data == '/quit':
                conn.sendall("Tạm biệt!".encode('utf-8'))
                break

            # Thêm lệnh /help (Add /help command)
            if data == '/help':
                help_menu = (
                    "\n--- HƯỚNG DẪN ---\n"
                    "Lệnh: rock, paper, scissors\n"
                    "Thoát: /quit\n"
                    "-----------------\n"
                )
                conn.sendall(help_menu.encode('utf-8'))
            
            # Phản hồi khi người dùng chọn
            elif data in ['rock', 'paper', 'scissors']:
                conn.sendall(f"Bạn đã chọn {data.upper()}. Đang đợi kết quả...".encode('utf-8'))
            
            else:
                conn.sendall("❌ Lệnh không rõ. Gõ /help để xem trợ giúp.".encode('utf-8'))
                
        except ConnectionResetError:
            break
            
    conn.close()
    print(f"[DISCONNECTED] {addr} đã thoát.")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[LISTENING] Server is listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    start_server()