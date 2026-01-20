import socket
import threading

HOST = "127.0.0.1"
PORT = 12345

clients = []
lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[NEW] Client connected: {addr}")
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                print(f"[DISCONNECT] {addr}")
                break

            message = data.decode().strip()
            print(f"[{addr}] {message}")

            # TODO: xử lý Rock-Paper-Scissors tại đây
            response = f"Server received: {message}"
            conn.sendall(response.encode())

    except ConnectionResetError:
        print(f"[ERROR] Client {addr} disconnected abruptly")

    finally:
        with lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()
        print(f"[CLEANUP] Closed connection {addr}")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()

    print(f"[START] Server listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        with lock:
            clients.append(conn)

        thread = threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        )
        thread.start()

if __name__ == "__main__":
    start_server()
