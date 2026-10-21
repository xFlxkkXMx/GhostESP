#!/usr/bin/env python3
"""GhostESP WebSocket logger for the s3supermini build.

Connects to the WebSocket endpoint (/ws) exposed by the modified GhostESP
firmware, writes every log line with a local timestamp to a file, and can
optionally send CLI commands over the same socket.

Stdlib only -- no pip dependencies.

Usage:
    python3 ghost_ws_logger.py                     # log only
    python3 ghost_ws_logger.py --cmd               # log + interactive commands
    python3 ghost_ws_logger.py --host 192.168.4.1 --outdir ./logs
"""

import argparse
import base64
import os
import select
import socket
import struct
import sys
import time
from datetime import datetime

WS_PATH = "/ws"
RECONNECT_MIN = 1
RECONNECT_MAX = 30


def ws_handshake(sock, host, port, path):
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("handshake: connection closed")
        resp += chunk
    status = resp.split(b"\r\n", 1)[0]
    if b"101" not in status:
        raise ConnectionError(f"handshake rejected: {status.decode(errors='replace').strip()}")
    # Anything past the header belongs to the first frame(s)
    return resp.split(b"\r\n\r\n", 1)[1]


def ws_send_text(sock, text):
    payload = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _parse_frames(buffered):
    """Extract every complete frame from buffered; return (frames, buffered)."""
    frames = []
    while True:
        if len(buffered) < 2:
            break
        b0, b1 = buffered[0], buffered[1]
        opcode = b0 & 0x0F
        masked = b1 & 0x80
        length = b1 & 0x7F
        idx = 2
        if length == 126:
            if len(buffered) < 4:
                break
            length = struct.unpack(">H", buffered[2:4])[0]
            idx = 4
        elif length == 127:
            if len(buffered) < 10:
                break
            length = struct.unpack(">Q", buffered[2:10])[0]
            idx = 10
        mask_key = b""
        if masked:
            if len(buffered) < idx + 4:
                break
            mask_key = buffered[idx:idx + 4]
            idx += 4
        if len(buffered) < idx + length:
            break
        payload = buffered[idx:idx + length]
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        buffered = buffered[idx + length:]
        frames.append((opcode, payload))
    return frames, buffered


def ws_recv_frames(sock, buffered):
    """Read available data, return (frames, buffered). Each frame is (opcode, payload).
    Returns (None, buffered) only when the peer closed the connection."""
    frames, buffered = _parse_frames(buffered)
    if frames:
        return frames, buffered
    try:
        data = sock.recv(65536)
    except socket.timeout:
        return [], buffered  # idle tick, connection still alive
    if not data:
        return None, buffered  # peer closed
    buffered += data
    more, buffered = _parse_frames(buffered)
    frames += more
    return frames, buffered


def main():
    ap = argparse.ArgumentParser(description="GhostESP WebSocket logger")
    ap.add_argument("--host", default="192.168.4.1", help="ESP32 IP (default: 192.168.4.1)")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--outdir", default="./logs")
    ap.add_argument("--cmd", action="store_true", help="read commands from stdin and send them over the WS")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    log_path = os.path.join(
        args.outdir, "ghostesp_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
    )
    log_file = open(log_path, "a", buffering=1)
    print(f"[*] Logging to {log_path}")

    backoff = RECONNECT_MIN
    pending = b""
    interactive = args.cmd and sys.stdin.isatty()
    if interactive:
        print("[*] Interactive mode: type commands and press Enter ('quit' to exit)")

    sock = None
    while True:
        if sock is None:
            try:
                sock = socket.create_connection((args.host, args.port), timeout=10)
                sock.settimeout(0.5)
                pending = ws_handshake(sock, args.host, args.port, WS_PATH)
                print(f"[+] Connected to ws://{args.host}:{args.port}{WS_PATH}")
                backoff = RECONNECT_MIN
            except (OSError, ConnectionError) as e:
                print(f"[!] Connect failed: {e} (retry in {backoff}s)")
                time.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)
                continue

        try:
            frames, pending = ws_recv_frames(sock, pending)
        except OSError as e:
            frames = None
            pending = b""
            print(f"[!] Socket error: {e}")

        if frames is None:
            print("[!] Connection closed, reconnecting...")
            sock.close()
            sock = None
            time.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX)
            continue

        text_buf = ""
        for opcode, payload in frames:
            if opcode == 0x8:  # close
                sock.close()
                sock = None
                break
            elif opcode == 0x9:  # ping -> pong
                mask = os.urandom(4)
                masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + mask + masked)
            elif opcode in (0x1, 0x2, 0x0):
                text_buf += payload.decode(errors="replace")
        if text_buf:
            log_file.write(text_buf)

        if interactive:
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                line = sys.stdin.readline().strip()
                if line.lower() in ("quit", "exit"):
                    break
                if line:
                    try:
                        ws_send_text(sock, line)
                    except OSError as e:
                        print(f"[!] Send failed: {e}")

    if sock:
        sock.close()
    log_file.close()
    print(f"[*] Done. Log saved at {log_path}")


if __name__ == "__main__":
    main()
