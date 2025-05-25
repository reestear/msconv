# RT[M]P-RT[S]P Converter (msconv)

## Содержание

1. [Введение и архитектура](#введение-и-архитектура)
2. [Предварительные требования](#предварительные-требования)
3. [Установка и запуск](#установка-и-запуск)
4. [CLI msconv](#cli-msconv)

   * [Команда `publish`](#команда-publish)
   * [Команда `list`](#команда-list-интерактивная)
   * [Команда `play`](#команда-play)
   * [Команда `stop`](#команда-stop)
5. [Примеры использования](#примеры-использования)
6. [Логи](#логи)
7. [Мониторинг](#мониторинг)

---

## Введение и архитектура

Этот проект позволяет конвертировать RTMP-потоки в RTSP с поддержкой нескольких битрейтов и предоставляет клиентский CLI для публикации и просмотра потоков. Основные компоненты:

* **CLI (`msconv`)** на Python:

  * Публикует локальный файл, устройство или RTMP-источник на `nginx-rtmp`.
  * Делит поток на несколько битрейтов (1080p, 720p, 480p, 360p) или пересылает оригинал (не требует высоких требований в ЦПУ).
  * Позволяет интерактивно выбрать поток через `--list`.
  * Запускает `vlc` для просмотра выбранного RTSP.
* **nginx-rtmp (Docker)**

  * Принимает RTMP на порту 1935.
  * Предоставляет XML-статус на `:8080/stat`.
* **rtsp-simple-server (MediaMTX)** (Docker)

  * Принимает RTSP на порту 8554, конвертирует RTMP → RTSP без рекодирования.
  * Метрики Prometheus на порту 9998.

Архитектура гарантирует, что деление на вариативные потоки можно выполнять как на уровне паблишера (как сделано), так и на уровне конвертера (дополнительная нагрузка на CPU/GPU). Также возможно рекодирование в другие кодеки на уровне конвертер-сервера или RTSP-клиента.

---

## Предварительные требования

* **Docker** и **Docker Compose** (для серверов).
* **Python 3.8+** (для CLI).
* **ffmpeg** и **ffprobe** (для анализа входа и трансляции).
* **VLC** (для просмотра RTSP-потоков).

---

## Установка и запуск

1. Распаковать проект и открыть директории проекта (converter):

   ```bash
   cd converter
   ```
2. Настроить CLI:

   ```bash
   bash scripts/setup.sh
   ```
3. Запустить серверы:

   ```bash
   docker-compose up --build -d
   ```
4. Остановить:
   ```bash
   docker-compose down -v
   ```


---

## CLI msconv

Запускается командой:

```bash
python -m msconv [COMMAND] [OPTIONS]
```

### Команда `publish`

Публикация потока.

```bash
python -m msconv publish --help
```

**Опции:**

* `-s, --stream-key TEXT` (обязательный) — ключ потока.
* `-f, --input-file PATH` — локальный файл (будет зациклен).
* `-d, --device TEXT` — устройство (например `/dev/video0`).
* `-r, --input-rtmp TEXT` — RTMP-источник (например `rtmp://src/live/stream`).
* `-o, --original` — стримить оригинал без деления.
* `--nginx-rtmp-url TEXT` — URL nginx-rtmp (по умолчанию `rtmp://localhost:1935/live`).
* `--variants TEXT` — формат `label:bitrate:width:height`, разделён запятой.

В зависимости от входа (файл, устройство или RTMP) выбирается источник. При `--original` выполняется:

```
ffmpeg -i <input> -c copy -f flv rtmp://<nginx-host>:1935/live/<stream_key>
```
который будет просто копировать входящий поток в исходящий (нету никакого конвертинга кодеков или разрешений, поэтому не требует больших затратов CPU)

**Иначе (дефолтно)**:

```
ffmpeg -i <input> -filter_complex "[0:v]split=4[v0][v1][v2][v3]; \
[v0]scale=1920:1080[v0out]; \
[v1]scale=1280:720[v1out]; \
[v2]scale=854:480[v2out]; \
[v3]scale=640:360[v3out]" \
  -map "[v0out]" -map 0:a -c:v libx264 -preset fast -crf 23 -b:v 4000k -maxrate 4000k \
    -bufsize 8000k -c:a aac -b:a 128k -f flv rtmp://<nginx-host>:1935/live/<stream_key>_1080p \
  -map "[v1out]" ... (аналогично для 720p, 480p, 360p)
```
который будет уже брать входящий поток и конвертировать по заданным variants (можно почитать поподробнее в `python -m msconv publish --help`)

### Команда `list`

Показ списка активных потоков:

```
python -m msconv list -l
```

* `-l, --list` — интерактивный режим: стрелками вверх/вниз выбирать поток, ENTER — подтвердить.

### Команда `play`

## Воспроизведение выбранного потока через VLC:

* ### Определенным вариантом: 
   ```
   python -m msconv play --stream-key=stream1 --variant=720p (или -v 720p)
   ```
* ### Оригинальный поток: 
   ```
   python -m msconv play --stream-key=stream1 --original (или -o)
   ```
* ### Интерактивно опеределенным вариантом: 
   ```
   python -m msconv play --list (или -l) -v 720p
   ```
* ### Интерактивно оригинальный поток: 
   ```
   python -m msconv play -l -0
   ```


### Команда `stop`

Остановка публикации:

```
python -m msconv stop --stream-key=stream1
```

Читает PID из `./pids/stream1.pid`, посылает SIGTERM ffmpeg.

---

## Примеры использования

1. **Файл в 4 варианта с аудио**:

   ```bash
   python -m msconv publish -s stream1 -f ./videos/test.mp4
   ```
3. **RTMP-источник → оригинал**:

   ```bash
   python -m msconv publish -s relayCam -r rtmp://remote/live/cam -o
   ```
4. **Показать стримы**:

   ```bash
   python -m msconv list
   ```
5. **Воспроизвести 480p (если он существует)**:

   ```bash
   python -m msconv play -l -v 480p
   ```
6. **Остановить публикацию**:

   ```bash
   python -m msconv stop -s stream1
   ```

---

## Логи

* Публишер записывает логи ffmpeg в `./logs/ffmpeg/<stream_key>.log`.
* PID-файлы лежат в `./pids/<stream_key>.pid`.
* Логи `nginx-rtmp` (access, error) монтируются в `./logs/nginx/`.
* Логи `rtsp-simple-server` в `./logs/mediamtx/mediamtx.log`.

---

## Мониторинг

Так же хорошо было бы рассказать, что можно легко заимплементить монитроинг сервисов при помощи промитея (Prometheus).

Так же можно поверх промитея подключить графану для детальных метрик. К счасть порты в `MediaMTX (rtsp-simple-convert)` открыты с валидными метриками промитея.

Для `nginx-rtmp` можно установить готовое решение который будет собирать метрики и опять же выдавать в `/metrics`.

Ну и конечно можно добавить метрики в сам сервер (OS метрики).

Чуть более собранно и детально описано ниже:
* **MediaMTX**: Prometheus-метрики доступны на `http://<media-host>:9998/metrics`.
* **nginx-rtmp**: установить [nginx\_rtmp\_prometheus](https://github.com/mauricioabreu/nginx_rtmp_prometheus) и собирать метрики с `/metrics`.
* **OS метрики**: можно запустить `node_exporter` или `cAdvisor` на сервере конвертера (`rtsp-simple-server`).

---

