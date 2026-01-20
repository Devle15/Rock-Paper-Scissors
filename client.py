import socket

HOST = '127.0.0.1'
PORT = 65432

def start_client():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(('127.0.0.1', 65432))
    
    while True:
        # Nhận tin nhắn từ Server
        msg_from_server = client.recv(1024).decode('utf-8')
        print(msg_from_server)
        
        if "Tạm biệt" in msg_from_server:
            break
            
        # Nhập lệnh gửi lên Server
        cmd = input("Nhập lệnh của bạn: ")
        client.sendall(cmd.encode('utf-8'))

    client.close()

if __name__ == "__main__":
    start_client()