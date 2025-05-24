import os
import sys
import signal
import subprocess
import time
import threading
import click
from typing import List
from pathlib import Path
from .models import StreamVariant


def get_default_variants() -> List[StreamVariant]:
    """Get default stream variants."""
    return [
        StreamVariant("1080p", "4000k", 1920, 1080),
        StreamVariant("720p", "2500k", 1280, 720),
        StreamVariant("480p", "1200k", 854, 480),
        StreamVariant("360p", "600k", 640, 360),
    ]


def parse_variants(variants_str: str) -> List[StreamVariant]:
    """Parse variants string into StreamVariant objects."""
    variants = []
    for variant_spec in variants_str.split(","):
        parts = variant_spec.split(":")
        if len(parts) >= 4:
            label, bitrate, width, height = parts[:4]
            variants.append(
                StreamVariant(
                    label=label, bitrate=bitrate, width=int(width), height=int(height)
                )
            )
    return variants


def get_pid_file(stream_key: str) -> Path:
    """Get PID file path for a stream."""
    pid_dir = Path("pids")
    pid_dir.mkdir(exist_ok=True)
    return pid_dir / f"{stream_key}.pid"


def get_log_file(stream_key: str) -> Path:
    """Get log file path for a stream."""
    log_dir = Path("logs/ffmpeg")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{stream_key}.log"


def is_stream_active(stream_key: str) -> bool:
    """Check if a stream is currently active."""
    return get_pid_file(stream_key).exists()


def start_ffmpeg_process(command: str, stream_key: str) -> subprocess.Popen:
    """Start FFmpeg process and save PID."""
    log_file = get_log_file(stream_key)
    pid_file = get_pid_file(stream_key)

    with open(log_file, "w") as log_fd:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )

    # Save PID
    with open(pid_file, "w") as f:
        f.write(str(process.pid))

    return process


def stop_stream_process(stream_key: str) -> None:
    """Stop a stream process by stream key."""
    pid_file = get_pid_file(stream_key)

    if not pid_file.exists():
        raise RuntimeError(f"No active stream found for '{stream_key}'")

    with open(pid_file, "r") as f:
        pid = int(f.read().strip())

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        click.echo(f"Sent SIGTERM to ffmpeg (PID {pid}).")
    except ProcessLookupError:
        click.echo(f"No process with PID {pid} found.", err=True)
    except Exception as e:
        click.echo(f"Error killing process {pid}: {e}", err=True)
    finally:
        pid_file.unlink()
        click.echo(f"Stream '{stream_key}' stopped.")


def tail_logs(log_file: Path, stream_key: str) -> None:
    """Tail logs and handle keyboard interrupt."""

    def tail_logs_thread():
        try:
            # Ждем пока log_file не появится и что-то в нем не будет записано
            while True:
                if log_file.exists() and log_file.stat().st_size > 0:
                    break
                time.sleep(0.5)

            with open(log_file, "r") as lf:
                lf.seek(0, os.SEEK_END)
                while True:
                    line = lf.readline()
                    if not line:
                        time.sleep(1)
                        continue
                    click.echo(line.rstrip())
        except Exception:
            pass

    # Создаем и запускаем поток для чтения логов
    t = threading.Thread(target=tail_logs_thread, daemon=True)
    t.start()

    try:
        # Ожидаем завершения потока
        pid_file = get_pid_file(stream_key)
        while pid_file.exists():
            time.sleep(1)
    # Если пользователь прервал выполнение то остановим поток стриминга и выйдем
    except KeyboardInterrupt:
        click.echo(f"\nStopping stream '{stream_key}'...")
        stop_stream_process(stream_key)
        sys.exit(0)
