# S3 Super Mini tools (GhostESP headless, no SD card)

Herramientas para la build `s3supermini` de GhostESP (ESP32-S3 Super Mini 4MB,
headless, WebSocket habilitado). Todo el logging y las capturas se hacen en el
PC porque la placa no tiene tarjeta SD.

## Flasheo

Descarga `artifact-s3supermini.zip` desde la pestaña Actions del fork
(workflow "Compile Ghost ESP") y:

```sh
unzip artifact-s3supermini.zip -d /tmp/s3fw
./flash_s3supermini.sh /tmp/s3fw /dev/ttyACM0   # BOOT+RST para modo download
```

## Log por WebSocket (guardado en el PC)

Conéctate al AP `GhostNet` (pass `GhostNet`) y ejecuta:

```sh
python3 ghost_ws_logger.py                # guarda ./logs/ghostesp_*.log
python3 ghost_ws_logger.py --cmd          # además envía comandos (help, scanap, ...)
```

## Capturas PCAP sin SD (stream por USB)

Con la placa conectada por USB (consola serie):

```sh
python3 ghost_pcap_capture.py -p /dev/ttyACM0        # todos los canales
python3 ghost_pcap_capture.py -p /dev/ttyACM0 -c 6   # canal fijo
# Ctrl+C para parar; leer con:
tcpdump -r captures/capture_*.pcap
```

## Consola serie (respaldo)

```sh
screen /dev/ttyACM0 115200   # Ctrl+A K para salir
```
