#!/usr/bin/env python3
"""CLI client for Rock-Paper-Scissors Multi Client-Server.

Run:
  python client.py --host 127.0.0.1 --port 8888

Commands in lobby:
  /rooms
  /create <room>
  /join <room>
  /quick
  /start (start match in current room - if you created/joined a room)
  /leaderboard
  /quit

Commands in room:
  /chat <message>
  /move rock|paper|scissors
  /leave
"""

from __future__ import annotations

import argparse
import socket
import threading
import sys
from typing import Optional

from common.protocol import JsonLineSocket, safe_close, ProtocolError


class ClientApp:
    def __init__(self, host: str, port: int, name: str):
        self.host = host
        self.port = port
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.jls: Optional[JsonLineSocket] = None
        self.running = True
        self.in_room: Optional[str] = None

    def start(self):
        self.sock.connect((self.host, self.port))
        self.jls = JsonLineSocket(self.sock)

        # reader thread
        threading.Thread(target=self._reader_loop, daemon=True).start()

        # handshake
        self._send("HELLO", {"name": self.name})

        # input loop
        self._print_help_lobby()
        while self.running:
            try:
                line = input().strip()
            except EOFError:
                break
            if not line:
                continue
            if not line.startswith("/"):
                print("Nhap lenh bat dau bang '/', vi du: /rooms hoac /quick")
                continue
            self._handle_command(line)

        self.running = False
        try:
            safe_close(self.sock)
        except Exception:
            pass

    def _send(self, msg_type: str, data: dict):
        if not self.jls:
            return
        try:
            self.jls.send({"type": msg_type, "data": data})
        except Exception:
            self.running = False

    def _handle_command(self, line: str):
        parts = line.split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            self._send("QUIT", {})
            self.running = False
            return

        if self.in_room:
            if cmd == "/start":
                self._send("START_MATCH", {"room": self.in_room})
                return
            if cmd == "/chat":
                if not arg:
                    print("Dung: /chat <noi dung>")
                    return
                self._send("CHAT", {"room": self.in_room, "message": arg})
                return
            if cmd == "/move":
                choice = arg.lower().strip()
                if choice not in ("rock", "paper", "scissors"):
                    print("Dung: /move rock|paper|scissors")
                    return
                self._send("MOVE", {"room": self.in_room, "choice": choice})
                return
            if cmd == "/leave":
                self._send("LEAVE_ROOM", {"room": self.in_room})
                return

            print("Lenh trong phong: /start, /chat, /move, /leave")
            return

        # lobby commands
        if cmd == "/rooms":
            self._send("LIST_ROOMS", {})
            return
        if cmd == "/create":
            if not arg:
                print("Dung: /create <ten_phong>")
                return
            self._send("CREATE_ROOM", {"room": arg})
            return
        if cmd == "/join":
            if not arg:
                print("Dung: /join <ten_phong>")
                return
            self._send("JOIN_ROOM", {"room": arg})
            return
        if cmd == "/quick":
            self._send("QUICKPLAY", {})
            return
        if cmd == "/leaderboard":
            self._send("GET_LEADERBOARD", {})
            return
        if cmd == "/help":
            self._print_help_lobby()
            return

        print("Lenh lobby: /rooms, /create <room>, /join <room>, /quick, /leaderboard, /quit")

    def _print_help_lobby(self):
        print("\n--- ROCK PAPER SCISSORS CLIENT ---")
        print("Lenh lobby:")
        print("  /rooms")
        print("  /create <room>")
        print("  /join <room>")
        print("  /quick")
        print("  /start  (neu dang o trong room)")
        print("  /leaderboard")
        print("  /start (neu ban dang o trong room)")
        print("  /help")
        print("  /quit")
        print("Neu da vao phong, dung: /start, /chat <msg>, /move rock|paper|scissors, /leave")
        print("---------------------------------\n")

    def _reader_loop(self):
        assert self.jls is not None
        while self.running:
            try:
                msg = self.jls.recv()
                if msg is None:
                    print("[DISCONNECT] Server dong ket noi")
                    self.running = False
                    break
                self._handle_server_msg(msg)
            except ProtocolError as e:
                print(f"[PROTO] {e}")
                self.running = False
                break
            except Exception:
                self.running = False
                break

    def _handle_server_msg(self, msg: dict):
        t = msg.get("type")
        d = msg.get("data", {})

        if t == "WELCOME":
            # server sends id + name
            print(f"[WELCOME] Xin chao {d.get('name','')} (id={d.get('id','')})")
            return
        if t == "ERROR":
            print(f"[ERROR] {d.get('message','')}")
            return
        if t == "ROOMS":
            rooms = d.get("rooms", [])
            if not rooms:
                print("(Khong co phong nao)")
            else:
                print("Danh sach phong:")
                for r in rooms:
                    print(f"  - {r}")
            return
        if t == "JOINED_ROOM":
            self.in_room = d.get("room")
            players = d.get("players", [])
            print(f"[VAO PHONG] {self.in_room} | Players: {', '.join(players) if players else ''}")
            print("Lenh phong: /start, /chat <msg>, /move rock|paper|scissors, /leave")
            return
        if t == "LEFT_ROOM":
            print("[ROI PHONG]")
            self.in_room = None
            self._print_help_lobby()
            return
        if t == "ROOM_UPDATE":
            room = d.get("room")
            players = d.get("players", [])
            print(f"[ROOM_UPDATE] {room}: {', '.join(players)}")
            return
        if t == "CHAT":
            print(f"[CHAT] {d.get('from')}: {d.get('message')}")
            return
        if t == "MATCH_START":
            players = d.get("players", [])
            print(f"[BAT DAU] Match trong room {d.get('room')} | Best-of-{d.get('best_of',3)}")
            if players:
                print(f"Players: {', '.join(players)}")
            print("Hay chon: /move rock|paper|scissors")
            return
        if t == "ROUND_START":
            print(f"[ROUND {d.get('round')}] Chon trong {d.get('timeout_s')}s: /move rock|paper|scissors")
            return
        if t == "ROUND_RESULT":
            print("\n[ROUND_RESULT]")
            print(f"- Round: {d.get('round')}")
            print(f"- Moves: {d.get('moves')}")
            print(f"- Winner: {d.get('round_winner')}")
            print(f"- Score: {d.get('score')}")
            return
        if t == "MATCH_END":
            print("\n[MATCH_END]")
            print(f"Reason: {d.get('reason')}")
            print(f"Winner: {d.get('winner')} | Loser: {d.get('loser')}")
            print(f"Final score: {d.get('final_score')}")
            return
        if t == "INFO":
            print(f"[INFO] {d.get('message','')}")
            return
        if t == "LEADERBOARD":
            lb = d.get("leaderboard", {})
            print("\n=== LEADERBOARD ===")
            if not lb:
                print("(chua co du lieu)")
            else:
                for name, st in lb.items():
                    print(f"{name}: W={st.get('wins',0)} L={st.get('losses',0)}")
            print("===================\n")
            return

        # fallback
        print(f"[SERVER] {t} {d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--name", default="")
    args = ap.parse_args()

    name = args.name.strip() or input("Nhap ten cua ban: ").strip() or "Player"
    app = ClientApp(args.host, args.port, name)
    try:
        app.start()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            safe_close(app.sock)
        except Exception:
            pass


if __name__ == "__main__":
    main()
