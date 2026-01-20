#!/usr/bin/env python3
"""Rock-Paper-Scissors Multi Client-Server (Python 3, TCP).

Designed for coursework submission: clear protocol, logs, and "feature ăn điểm".

Run:
  python server.py --host 127.0.0.1 --port 8888
"""

from __future__ import annotations

import argparse
import threading
import time
import socket
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

from common.protocol import JsonLineSocket, safe_close, ProtocolError

CHOICES = {"rock", "paper", "scissors"}


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_ts()}] {msg}", flush=True)


@dataclass
class PlayerConn:
    id: str
    name: str
    sock: socket.socket
    jls: JsonLineSocket
    addr: Tuple[str, int]
    room: Optional[str] = None
    in_quickplay: bool = False
    alive: bool = True


@dataclass
class RoomState:
    name: str
    players: List[str] = field(default_factory=list)  # player ids
    created_by: str = ""
    chat_log: List[Tuple[str, str]] = field(default_factory=list)  # (name, msg)

    # Match state
    active_match: bool = False
    round_no: int = 0
    best_of: int = 3
    wins: Dict[str, int] = field(default_factory=dict)
    moves: Dict[str, str] = field(default_factory=dict)  # player id -> choice
    round_deadline: float = 0.0
    move_timeout_s: int = 10


class RpsServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.lock = threading.RLock()
        self.players: Dict[str, PlayerConn] = {}
        self.rooms: Dict[str, RoomState] = {}
        self.quickplay_queue: List[str] = []
        self.leaderboard: Dict[str, Dict[str, int]] = {}  # name -> {wins, losses}

        self._stop = threading.Event()

    def start(self):
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(100)
        log(f"RPS Server listening on {self.host}:{self.port}")

        tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        tick_thread.start()

        try:
            while not self._stop.is_set():
                client_sock, addr = self.server_sock.accept()
                client_sock.settimeout(None)
                # Spawn a new thread for each client to handle concurrent requests
                threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
        finally:
            safe_close(self.server_sock)

    def stop(self):
        self._stop.set()

    # ------------------- protocol helpers --------------------
    def _send(self, pid: str, msg_type: str, data: Optional[dict] = None) -> None:
        p = self.players.get(pid)
        if not p or not p.alive:
            return
        try:
            p.jls.send({"type": msg_type, "data": data or {}})
        except Exception:
            p.alive = False

    def _broadcast_room(self, room_name: str, msg_type: str, data: dict) -> None:
        r = self.rooms.get(room_name)
        if not r:
            return
        for pid in list(r.players):
            self._send(pid, msg_type, data)

    # ----------------------- matchmaking & game -----------------------
    def _try_match_quickplay(self) -> None:
        with self.lock:
            # remove dead players
            self.quickplay_queue = [pid for pid in self.quickplay_queue if pid in self.players and self.players[pid].alive]
            if len(self.quickplay_queue) < 2:
                return
            p1 = self.quickplay_queue.pop(0)
            p2 = self.quickplay_queue.pop(0)

            room_name = f"quick_{uuid.uuid4().hex[:6]}"
            r = RoomState(name=room_name, created_by="system")
            self.rooms[room_name] = r
            self._join_room_locked(p1, room_name)
            self._join_room_locked(p2, room_name)
            self._start_match_locked(room_name)

    def _join_room_locked(self, pid: str, room_name: str) -> None:
        p = self.players.get(pid)
        r = self.rooms.get(room_name)
        if not p or not r:
            return
        # leave current room if any
        if p.room:
            self._leave_room_locked(pid, p.room, notify=True)

        if pid not in r.players:
            if len(r.players) >= 2:
                self._send(pid, "ERROR", {"message": "Phong da du 2 nguoi."})
                return
            r.players.append(pid)
        p.room = room_name
        p.in_quickplay = False

        self._send(pid, "JOINED_ROOM", {"room": room_name, "players": [self.players[x].name for x in r.players]})
        self._broadcast_room(room_name, "ROOM_UPDATE", {"room": room_name, "players": [self.players[x].name for x in r.players]})

    def _leave_room_locked(self, pid: str, room_name: str, *, notify: bool) -> None:
        r = self.rooms.get(room_name)
        p = self.players.get(pid)
        if not r or not p:
            return
        if pid in r.players:
            r.players.remove(pid)
        p.room = None

        # if match active, end it (opponent wins by forfeit)
        if r.active_match:
            self._end_match_locked(room_name, reason="player_left")

        if notify:
            self._send(pid, "LEFT_ROOM", {"room": room_name})
            self._broadcast_room(room_name, "ROOM_UPDATE", {"room": room_name, "players": [self.players[x].name for x in r.players]})

        # cleanup empty room (except quick rooms)
        if len(r.players) == 0:
            del self.rooms[room_name]

    def _start_match_locked(self, room_name: str) -> None:
        r = self.rooms.get(room_name)
        if not r:
            return
        if len(r.players) != 2:
            self._broadcast_room(room_name, "INFO", {"message": "Can du 2 nguoi de bat dau."})
            return
        r.active_match = True
        r.round_no = 0
        r.wins = {pid: 0 for pid in r.players}
        r.moves = {}
        self._broadcast_room(room_name, "MATCH_START", {
            "room": room_name,
            "best_of": r.best_of,
            "players": [self.players[x].name for x in r.players]
        })
        self._next_round_locked(room_name)

    def _next_round_locked(self, room_name: str) -> None:
        r = self.rooms.get(room_name)
        if not r or not r.active_match:
            return
        r.round_no += 1
        r.moves = {}
        r.round_deadline = time.time() + r.move_timeout_s
        self._broadcast_room(room_name, "ROUND_START", {
            "round": r.round_no,
            "timeout_s": r.move_timeout_s,
            "deadline_ts": r.round_deadline
        })

    def _resolve_round_locked(self, room_name: str) -> None:
        r = self.rooms.get(room_name)
        if not r or not r.active_match:
            return
        if len(r.players) != 2:
            self._end_match_locked(room_name, reason="not_enough_players")
            return

        p1, p2 = r.players[0], r.players[1]
        m1 = r.moves.get(p1)
        m2 = r.moves.get(p2)

        # update timeout logic
        if m1 is None and m2 is None:
            winner = None
            result = "draw_timeout"
        elif m1 is None:
            winner = p2
            result = "p1_timeout"
        elif m2 is None:
            winner = p1
            result = "p2_timeout"
        else:
            winner = self._winner(p1, m1, p2, m2)
            result = "normal"

        if winner is not None:
            r.wins[winner] += 1

        payload = {
            "round": r.round_no,
            "result_type": result,
            "moves": {
                self.players[p1].name: m1,
                self.players[p2].name: m2,
            },
            "round_winner": self.players[winner].name if winner else None,
            "score": {self.players[pid].name: r.wins.get(pid, 0) for pid in r.players},
        }
        self._broadcast_room(room_name, "ROUND_RESULT", payload)

        # check match end
        need = (r.best_of // 2) + 1
        match_winner: Optional[str] = None
        for pid, w in r.wins.items():
            if w >= need:
                match_winner = pid
                break

        if match_winner:
            self._end_match_locked(room_name, reason="winner", winner_pid=match_winner)
        else:
            self._next_round_locked(room_name)

    def _end_match_locked(self, room_name: str, reason: str, winner_pid: Optional[str] = None) -> None:
        r = self.rooms.get(room_name)
        if not r:
            return

        # decide winner for forfeit case
        if winner_pid is None and len(r.players) == 2:
            # if one player left, other wins
            pass

        if winner_pid is None:
            # try infer
            if len(r.players) == 2:
                p1, p2 = r.players
                # if one socket dead, other wins
                alive1 = self.players.get(p1) and self.players[p1].alive
                alive2 = self.players.get(p2) and self.players[p2].alive
                if alive1 and not alive2:
                    winner_pid = p1
                elif alive2 and not alive1:
                    winner_pid = p2

        loser_pid: Optional[str] = None
        if winner_pid and winner_pid in r.players:
            for pid in r.players:
                if pid != winner_pid:
                    loser_pid = pid

        winner_name = self.players[winner_pid].name if winner_pid and winner_pid in self.players else None
        loser_name = self.players[loser_pid].name if loser_pid and loser_pid in self.players else None

        self._broadcast_room(room_name, "MATCH_END", {
            "reason": reason,
            "winner": winner_name,
            "loser": loser_name,
            "final_score": {self.players[pid].name: r.wins.get(pid, 0) for pid in r.players if pid in self.players},
        })

        # update leaderboard (session)
        if winner_name:
            self.leaderboard.setdefault(winner_name, {"wins": 0, "losses": 0})
            self.leaderboard[winner_name]["wins"] += 1
        if loser_name:
            self.leaderboard.setdefault(loser_name, {"wins": 0, "losses": 0})
            self.leaderboard[loser_name]["losses"] += 1

        r.active_match = False
        r.round_no = 0
        r.moves = {}
        r.wins = {pid: 0 for pid in r.players}
        r.round_deadline = 0.0

        # After match, keep room but in lobby state
        self._broadcast_room(room_name, "LEADERBOARD", {"leaderboard": self.leaderboard})

    @staticmethod
    def _winner(p1: str, m1: str, p2: str, m2: str) -> Optional[str]:
        if m1 == m2:
            return None
        if (m1, m2) in [("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")]:
            return p1
        return p2

    # ----------------------- tick loop -----------------------
    def _tick_loop(self):
        # periodic matchmaking + timeout checks
        while not self._stop.is_set():
            try:
                with self.lock:
                    self._try_match_quickplay()
                    now = time.time()
                    # check room deadlines
                    for room_name, r in list(self.rooms.items()):
                        if r.active_match and r.round_deadline > 0 and now >= r.round_deadline:
                            # resolve round with current moves
                            self._resolve_round_locked(room_name)
            except Exception as e:
                log(f"Tick error: {e}")
            time.sleep(0.2)

    # ----------------------- client handling -----------------------
    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]):
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        jls = JsonLineSocket(client_sock)
        pid = uuid.uuid4().hex
        player: Optional[PlayerConn] = None
        try:
            # expect HELLO
            msg = jls.recv()
            if msg is None:
                safe_close(client_sock)
                return
            if msg.get("type") != "HELLO":
                jls.send({"type": "ERROR", "data": {"message": "Must send HELLO first"}})
                safe_close(client_sock)
                return
            name = (msg.get("data") or {}).get("name") or f"Player-{pid[:4]}"

            with self.lock:
                player = PlayerConn(id=pid, name=name, sock=client_sock, jls=jls, addr=addr)
                self.players[pid] = player
                self.leaderboard.setdefault(name, {"wins": 0, "losses": 0})

            log(f"CONNECT {name} ({addr[0]}:{addr[1]})")
            jls.send({"type": "WELCOME", "data": {"id": pid, "name": name}})
            jls.send({"type": "INFO", "data": {"message": "Dung /help de xem lenh."}})

            while True:
                msg = jls.recv()
                if msg is None:
                    break
                self._on_message(pid, msg)

        except ProtocolError as e:
            log(f"Protocol error from {addr}: {e}")
        except Exception as e:
            log(f"Client handler error: {e}")
        finally:
            with self.lock:
                if player:
                    player.alive = False
                    # remove from queue
                    if pid in self.quickplay_queue:
                        self.quickplay_queue = [x for x in self.quickplay_queue if x != pid]
                    # remove from room
                    if player.room:
                        self._leave_room_locked(pid, player.room, notify=False)
                    # remove player
                    if pid in self.players:
                        del self.players[pid]
            safe_close(client_sock)
            if player:
                log(f"DISCONNECT {player.name}")

    def _on_message(self, pid: str, msg: dict) -> None:
        mtype = msg.get("type")
        data = msg.get("data") or {}

        with self.lock:
            p = self.players.get(pid)
            if not p or not p.alive:
                return

            if mtype == "HELP":
                self._send(pid, "HELP", {
                    "commands": [
                        "/rooms", "/create <room>", "/join <room>", "/quick", "/start", "/move <rock|paper|scissors>", "/chat <msg>", "/leave", "/quit"
                    ]
                })
                return

            if mtype == "LIST_ROOMS":
                self._send(pid, "ROOMS", {"rooms": sorted(self.rooms.keys())})
                return

            if mtype == "LEADERBOARD":
                # client requests current session leaderboard
                self._send(pid, "LEADERBOARD", {"leaderboard": self.leaderboard})
                return

            if mtype == "CREATE_ROOM":
                room = data.get("room")
                if not room or not isinstance(room, str):
                    self._send(pid, "ERROR", {"message": "Room name invalid"})
                    return
                if room in self.rooms:
                    self._send(pid, "ERROR", {"message": "Room da ton tai"})
                    return
                self.rooms[room] = RoomState(name=room, created_by=p.name)
                self._join_room_locked(pid, room)
                return

            if mtype == "JOIN_ROOM":
                room = data.get("room")
                if room not in self.rooms:
                    self._send(pid, "ERROR", {"message": "Khong tim thay room"})
                    return
                self._join_room_locked(pid, room)
                return

            if mtype == "LEAVE_ROOM":
                if p.room:
                    self._leave_room_locked(pid, p.room, notify=True)
                else:
                    self._send(pid, "INFO", {"message": "Ban chua o room nao"})
                return

            if mtype == "QUICKPLAY":
                if pid not in self.quickplay_queue:
                    # leave room if any
                    if p.room:
                        self._leave_room_locked(pid, p.room, notify=True)
                    self.quickplay_queue.append(pid)
                    p.in_quickplay = True
                self._send(pid, "INFO", {"message": f"Da vao hang doi QuickPlay. Dang cho doi thu... (queue={len(self.quickplay_queue)})"})
                return

            if mtype == "START_MATCH":
                if not p.room:
                    self._send(pid, "ERROR", {"message": "Ban chua o room"})
                    return
                self._start_match_locked(p.room)
                return

            if mtype == "CHAT":
                if not p.room:
                    self._send(pid, "ERROR", {"message": "Ban chua o room"})
                    return
                txt = (data.get("message") or "").strip()
                if not txt:
                    return
                r = self.rooms.get(p.room)
                if r:
                    r.chat_log.append((p.name, txt))
                self._broadcast_room(p.room, "CHAT", {"from": p.name, "message": txt})
                return

            if mtype == "MOVE":
                if not p.room:
                    self._send(pid, "ERROR", {"message": "Ban chua o room"})
                    return
                r = self.rooms.get(p.room)
                if not r or not r.active_match:
                    self._send(pid, "ERROR", {"message": "Chua bat dau tran. Dung /start hoac doi QuickPlay"})
                    return
                choice = (data.get("choice") or "").lower()
                if choice not in CHOICES:
                    self._send(pid, "ERROR", {"message": "Choice khong hop le"})
                    return
                r.moves[pid] = choice
                self._send(pid, "INFO", {"message": f"Da chon {choice}."})
                # if both have moves, resolve immediately
                if len(r.moves) == 2:
                    self._resolve_round_locked(p.room)
                return

            if mtype == "QUIT":
                self._send(pid, "INFO", {"message": "Bye"})
                p.alive = False
                safe_close(p.sock)
                return

            self._send(pid, "ERROR", {"message": f"Unknown message type: {mtype}"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    # allow import from project root
    srv = RpsServer(args.host, args.port)
    srv.start()


if __name__ == "__main__":
    main()
