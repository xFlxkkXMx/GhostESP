#!/usr/bin/env bash
# Flash a s3supermini.zip artifact (from GitHub Actions) onto an ESP32-S3 Super Mini.
#
# Usage:
#   ./flash_s3supermini.sh <unzipped-artifact-dir> [serial-port]
# Example:
#   unzip s3supermini.zip -d /tmp/s3fw && ./flash_s3supermini.sh /tmp/s3fw /dev/ttyACM0
#
# The zip ships a merged.bin (bootloader + partitions + app at the right
# offsets) which is written at 0x0 after a full flash erase.

set -euo pipefail

DIR="${1:?usage: flash_s3supermini.sh <artifact-dir> [port]}"
PORT="${2:-/dev/ttyACM0}"
ESPTOOL="${ESPTOOL:-/tmp/esptool-venv/bin/esptool.py}"

if [ ! -f "$DIR/merged.bin" ]; then
    echo "merged.bin not found in $DIR" >&2
    exit 1
fi

echo "[*] Erasing flash on $PORT ..."
"$ESPTOOL" --chip esp32s3 --port "$PORT" erase-flash

echo "[*] Writing merged.bin ..."
"$ESPTOOL" --chip esp32s3 --port "$PORT" -b 460800 write-flash 0x0 "$DIR/merged.bin"

echo "[+] Done. Press RST on the board if it does not boot."
echo "[i] AP: GhostNet / GhostNet -> http://192.168.4.1"
