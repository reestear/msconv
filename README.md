# RT(M)P -> RT(S)P Converter [msconv]

This repository provides a solution for converting and streaming video from RTMP to RTSP with multi-bitrate support, alongside a client-side CLI (`msconv`) for publishers and subscribers. The core components include:

* **Publisher CLI (`msconv`)**: A Python-based command-line tool that can:

  * Publish an input (file, device, or RTMP stream) to an RTMP ingestion server, optionally splitting it into multiple bitrate variants or streaming the original.
  * List active streams and their variants.
  * Play a chosen stream and variant via `ffplay`.
  * Stop a running publisher.

* **RTMP Ingestion Server**: `nginx-rtmp`, deployed in Docker, listens for RTMP streams on port 1935 and provides a `/stat` XML endpoint for monitoring.

* **RTSP/WebRTC/HLS Server**: `MediaMTX` (formerly `rtsp-simple-server`), deployed in Docker, pulls from nginx-rtmp and serves as RTSP (port 8554), WebRTC/HLS, and exposes metrics (port 9998) and a control API (port 9997).

* **Docker Compose**: Orchestrates `nginx-rtmp`, `MediaMTX`, and supporting services (Prometheus, Grafana, exporters) for a full monitoring stack.

---

## Architecture Overview

### 1. Publisher CLI (`msconv`)

* Written in Python with Click, `msconv` runs on the client (publisher) side.
* Detects whether the input has audio via `ffprobe`.
* If `--original` is specified, runs:

  ```bash
  ffmpeg -i <input> -c copy -f flv rtmp://<nginx-host>:1935/live/<stream_key>_original
  ```
* Otherwise, splits into four bitrate variants (1080p, 720p, 480p, 360p) using a single `ffmpeg -filter_complex "split=4..."` command, pushes each to nginx-rtmp under `live/<stream_key>_<variant>`.
* Writes a PID file under `./pids/<stream_key>.pid` and logs ffmpeg output to `./logs/ffmpeg/<stream_key>.log`.
* Supports commands: `publish`, `stop`, `list`, `play`.

### 2. RTMP Ingestion: nginx-rtmp

* Docker container `tiangolo/nginx-rtmp:latest` listening on port 1935 for RTMP ingestion.
* Exposes HTTP stat page on port 80 (mapped to host 8080) at `/stat`, providing XML about active streams.
* All ffmpeg pushes go to `rtmp://nginx-rtmp:1935/live/<stream_key>_<variant>` (or `_original`).

### 3. RTSP/WebRTC/HLS Server: MediaMTX

* Docker container `bluenviron/mediamtx:latest-ffmpeg-rpi` listening on port 8554 for RTSP.
* Configured in `rtsp-simple-server.yml` to `source: rtmp://nginx-rtmp:1935/$RTSP_PATH`, so any `rtsp://<host>:8554/live/<stream_key>_<variant>` causes MediaMTX to pull from the corresponding RTMP URL.
* Exposes Metrics API on port 9998 for Prometheus scraping.
* Exposes Control API on port 9997 (if needed).
* Optionally configured for WebRTC/HLS output via `runOnReady` and `hls.enabled: yes`.

### 4. Monitoring Stack (Optional)

* **Prometheus** scrapes:

  * `MediaMTX` metrics (`:9998/metrics`).
  * `nginx-rtmp` via an RTMP XML-to-Prometheus exporter on port 9113.
  * `node_exporter` or `cAdvisor` for container/host metrics.
* **Grafana** visualizes viewers per variant, packet loss, CPU/memory usage, etc.
* **nginx-exporter** scrapes `http://nginx-rtmp:80/stat`.

---

## Prerequisites

* **Docker** and **Docker Compose** installed on the machine that will host `nginx-rtmp` and `MediaMTX`.
* **Python 3.8+** installed on any machine that will run the `msconv` CLI.
* `ffmpeg` and `ffprobe` installed on the CLI machine.

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/msconv.git
cd msconv
```

### 2. Set Up the Publisher CLI

A helper script is provided under `scripts/setup.sh`:

```bash
cd scripts
chmod +x setup.sh
./setup.sh
```

This will:

* Create a Python virtual environment under `./venv`.
* Install all required Python packages (`click`, `requests`, etc.).

To activate the virtual environment:

```bash
source ../venv/bin/activate
```

> **Tip**: Add this line to your shell profile to auto-activate when you `cd` into the project:
>
> ```bash
> echo "source $(pwd)/venv/bin/activate" >> ~/.bashrc
> ```

### 3. Build & Run the Streaming Servers

From the project root (where `docker-compose.yml` lives), run:

```bash
docker-compose up --build -d
```

* This will pull/build:

  * `nginx-rtmp` container on port **1935** (RTMP) and **8080** (HTTP stat).
  * `MediaMTX` container on ports **8554** (RTSP), **9997** (API), **9998** (Metrics).
  * (Optional) Monitoring services: Prometheus (`9090`), Grafana (`3000`), exporters.

To tear down:

```bash
docker-compose down -v
```

Use `docker-compose down` (without `-v`) if you want to preserve volumes.

---

## CLI Usage (`msconv`)

Once your Python venv is activated, run the CLI via:

```bash
python -m msconv [COMMAND] [OPTIONS]
```

### 1. Show Help

```bash
python -m msconv --help
```

Lists global commands: `publish`, `stop`, `list`, `play`.

### 2. Publish

```bash
python -m msconv publish [OPTIONS]
```

#### Options

* `-s, --stream-key TEXT` (required): Base key used for naming variants.
* `-f, --input-file PATH`: Local video file to stream (loops indefinitely).
* `-d, --device TEXT`: Video device (e.g., `/dev/video0` or `0`).
* `-r, --input-rtmp TEXT`: RTMP source URL (e.g., `rtmp://source-server/live/stream`).
* `-o, --original`: Stream the input exactly as-is into `<stream_key>_original`.
* `--nginx-rtmp-url TEXT`: Base RTMP ingestion URL (default: `rtmp://localhost:1935/live`).
* `--variants TEXT`: Comma-separated list of variants: `label:bitrate:width:height`. (Default: `1080p:4000k:1920:1080,720p:2500k:1280:720,480p:1200k:854:480,360p:600k:640:360`)

#### Examples

* **Stream a local file into 4 variants**:

  ```bash
  python -m msconv publish \
    --stream-key=myCamera \
    --input-file=/home/alice/test.mp4
  ```

  This automatically detects audio (if present) and pushes to:

  * `rtmp://localhost:1935/live/myCamera_1080p`
  * `rtmp://localhost:1935/live/myCamera_720p`
  * `rtmp://localhost:1935/live/myCamera_480p`
  * `rtmp://localhost:1935/live/myCamera_360p`

* **Stream a webcam (video-only) into 4 variants**:

  ```bash
  python -m msconv publish \
    --stream-key=frontDoor \
    --device=0
  ```

  Since `/dev/video0` has no audio, ffmpeg omits audio (`-an`).

* **Forward an existing RTMP stream as original**:

  ```bash
  python -m msconv publish \
    --stream-key=relayCam \
    --input-rtmp=rtmp://other-server:1935/live/external \
    --original
  ```

  Produces exactly:
  `ffmpeg -i rtmp://other-server:1935/live/external -c copy -f flv rtmp://localhost:1935/live/relayCam_original`

* **Stream a file but only push one custom variant**:

  ```bash
  python -m msconv publish \
    --stream-key=newsBroadcast \
    --input-file=/home/alice/promo.mp4 \
    --variants="720p:2500k:1280:720"
  ```

  Only pushes `newsBroadcast_720p` at 1280×720, 2.5 Mbps with audio if detected.

### 3. List Active Streams

```bash
python -m msconv list [OPTIONS]
```

#### Options

* `--nginx-host TEXT`: Host where nginx-rtmp runs (default: `localhost`).
* `--nginx-stat-port TEXT`: nginx-rtmp stat port (default: `8080`).
* `--media-host TEXT`: MediaMTX host (default: `localhost`).
* `--media-api-port TEXT`: MediaMTX API port (default: `9997`).

#### Example

```bash
python -m msconv list
```

Outputs:

```
Available streams:
  • myCamera            [ LIVE   ]  variants: 1080p, 720p, 480p, 360p  (1080p: 2 viewers, 720p: 5 viewers, ...)
  • frontDoor           [ LIVE   ]  variants: 1080p, 720p, 480p, 360p  (no viewers yet)
  • relayCam            [ OFFLINE]  variants: original                 (0 viewers)
```

### 4. Play a Stream

```bash
python -m msconv play [OPTIONS]
```

#### Options

* `-s, --stream-key TEXT` (required): Base stream key.
* `-v, --variant TEXT` (default: `720p`): Which variant to play.
* `--media-host TEXT` (default: `localhost`): MediaMTX host.

#### Example

```bash
python -m msconv play --stream-key=myCamera --variant=720p
```

This runs:

```
ffplay -rtsp_transport tcp rtsp://localhost:8554/live/myCamera_720p
```

For HLS playback in a browser, you could open:

```
http://localhost:8888/hls/live/myCamera_720p/index.m3u8
```

(if HLS is enabled in `rtsp-simple-server.yml`).

### 5. Stop Publishing

```bash
python -m msconv stop --stream-key YOUR_KEY
```

This reads `./pids/YOUR_KEY.pid`, sends SIGTERM to the ffmpeg process group, and removes the PID file. The RTMP streams under nginx-rtmp will drop.

---

## Logs

* **Publisher logs** are written to `./logs/ffmpeg/<stream_key>.log`. This includes ffmpeg’s `frame=… fps=… bitrate=…` messages.
* **PID files** are stored under `./pids/<stream_key>.pid`. If the file exists, `msconv` refuses to start another ffmpeg for the same key.
* **nginx-rtmp logs** (access and error) live in `logs/nginx/` on the Docker host (mounted from `docker-compose.yml`).
* **MediaMTX logs** are in `logs/mediamtx/mediamtx.log` (stdout/stderr from the container).

Use these logs to troubleshoot: connection errors, codec mismatches, packet drops, etc.

---

## Examples

### Publish a Local File with Audio → 4 Variants

```bash
source venv/bin/activate
python -m msconv publish \
  --stream-key=myEvent \
  --input-file=/home/alice/videos/event.mp4
```

### Publish a Webcam (No Audio) → 4 Variants

```bash
python -m msconv publish \
  --stream-key=frontDoor \
  --device=0
```

### Forward an RTMP Source as Original

```bash
python -m msconv publish \
  --stream-key=relayCam \
  --input-rtmp=rtmp://remote-server/live/cam \
  --original
```

### Publish Only One Custom Variant (e.g., 480p)

```bash
python -m msconv publish \
  --stream-key=newsRecap \
  --input-file=/home/alice/media/news.mp4 \
  --variants="480p:1200k:854:480"
```

### List Active Streams

```bash
python -m msconv list
```

### Play a 360p Stream

```bash
python -m msconv play --stream-key=myEvent --variant=360p
```

### Stop a Publisher

```bash
python -m msconv stop --stream-key=myEvent
```

---

## Architecture Details & Technical Choices

1. **CLI Language & Dependencies**

   * Written in Python 3 with [Click](https://click.palletsprojects.com/) for argument parsing, [requests](https://docs.python-requests.org/) to fetch nginx-rtmp stats and MediaMTX API, and `subprocess` for launching `ffmpeg`/`ffprobe`.
   * Dependencies are pinned in `requirements.txt`; `scripts/setup.sh` automates venv creation and installation.

2. **Transcoding Approach**

   * Single `ffmpeg` process with `-filter_complex "split=4…"` to minimize I/O: splits video into four outputs at once.
   * Audio detection via `ffprobe`; if no audio, `-an` is added.
   * Bitrates and resolutions are configurable via `--variants`.
   * `--original` flag bypasses transcoding, doing `ffmpeg -c copy`.

3. **Streaming Servers**

   * **nginx-rtmp** (Docker): receives RTMP on port 1935, provides `/stat` XML. No re-encoding.
   * **MediaMTX** (Docker): listens on 8554 RTSP, pulls H.264/AAC from `rtmp://nginx-rtmp:1935/live/...` when a client connects.

     * Exposes Prometheus metrics on 9998.
     * Config in `rtsp-simple-server.yml` uses `paths:
         all:
           source: rtmp://nginx-rtmp:1935/$RTSP_PATH
       ` to route all `rtsp://…/live/...` to RTMP.
   * Optional WebRTC/HLS configured in `mediamtx.yml` for browser playback.

4. **Container Orchestration**

   * `docker-compose.yml` brings up:

     * `nginx-rtmp` (1935, 8080)
     * `MediaMTX` (8554, 9997, 9998)
     * (Optional) `Prometheus` (9090), `Grafana` (3000), `nginx-exporter` (9113), `node-exporter` (9100), and `cAdvisor` (8082).
   * Use `docker-compose up --build -d` to start, `docker-compose down -v` to stop & remove volumes.

5. **Monitoring & Observability**

   * **Prometheus** scrapes:

     * `MediaMTX` (`:9998/metrics`) for `mediamtx_stream_readers`, `mediamtx_stream_packets_lost`, etc.
     * `nginx-exporter` (`:9113/metrics`) for `nginx_rtmp_stream_*` metrics.
     * `node-exporter` and/or `cAdvisor` for CPU/Memory/Network usage.
   * **Grafana** visualizes active streams, viewer counts, packet loss, CPU/memory, and can alert on high packet loss or resource exhaustion.

---

## License & Contributing

This project is released under the MIT License. Contributions and issues are welcome via GitHub.

---

*Generated by msconv CLI README template.*
