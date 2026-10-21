#!/usr/bin/env python3
"""GhostESP PCAP-over-serial recorder for the s3supermini build (no SD card needed).

Sends the CLI command "capture -wireshark" over the USB-Serial-JTAG port and
streams the PCAP bytes the firmware emits into a local .pcap file. Press
Ctrl+C to stop; the firmware is told to stop capturing on the way out.

Requires pyserial. Wireshark/tcpdump can read the resulting file directly.

Usage:
    python3 ghost_pcap_capture.py -p /dev/ttyACM0
    python3 ghost_pcap_capture.py -p /dev/ttyACM0 -c 6 --outdir ./captures
"""

import argparse
import os
import sys
import time
from datetime import datetime

import serial

PCAP_MAGIC_BYTES_LE = b"\xd4\xc3\xb2\xa1"
PCAP_MAGIC_BYTES_LE_NSEC = b"\x4d\x3c\xb2\xa1"


def sync_to_pcap_header(ser):
    """Consume serial bytes until the PCAP magic appears (same resync logic
    as the Wireshark extcap: scan a sliding window for the magic)."""
    window = bytearray()
    while True:
        b = ser.read(1)
        if not b:
            continue
        window += b
        if len(window) > 4:
            window = window[-4:]
        if bytes(window) in (PCAP_MAGIC_BYTES_LE, PCAP_MAGIC_BYTES_LE_NSEC):
            return bytes(window)


def main():
    ap = argparse.ArgumentParser(description="Record GhostESP PCAP stream to a local file")
    ap.add_argument("-p", "--port", default="/dev/ttyACM0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-c", "--channel", type=int, default=None, help="lock to a WiFi channel")
    ap.add_argument("--outdir", default="./captures")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(
        args.outdir, "capture_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pcap"
    )

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        sys.stderr.write(f"Failed to open serial port {args.port}: {e}\n")
        sys.exit(1)

    print(f"[*] Connected to {args.port} at {args.baud} baud")
    ser.reset_input_buffer()
    if args.channel:
        ser.write(f"capture -wireshark -c {args.channel}\n".encode())
        print(f"[*] Sent 'capture -wireshark -c {args.channel}'")
    else:
        ser.write(b"capture -wireshark\n")
        print("[*] Sent 'capture -wireshark'")

    print("[*] Waiting for PCAP header...")
    magic = sync_to_pcap_header(ser)
    rest = ser.read(20)  # remaining 20 bytes of the 24-byte global header
    while len(rest) < 20:
        chunk = ser.read(20 - len(rest))
        if chunk:
            rest += chunk
    header = magic + rest
    print(f"[+] PCAP stream started, DLT={int.from_bytes(header[14:16], 'little')}")

    total = 0
    try:
        with open(out_path, "wb") as out:
            out.write(header)
            total += len(header)
            while True:
                buf = ser.read(4096)
                if buf:
                    out.write(buf)
                    total += len(buf)
                    print(f"\r[*] {total/1024:.0f} KiB captured", end="", flush=True)
    except KeyboardInterrupt:
        print("\n[*] Stopping...")
    finally:
        ser.write(b"capture -stop\n")
        ser.close()
        print(f"[+] Saved {total/1024:.0f} KiB to {out_path}")
        print("[i] Read it with: tcpdump -r " + out_path)


if __name__ == "__main__":
    main()
