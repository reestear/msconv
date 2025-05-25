import os
import sys
import curses
import time
import click
from typing import List
from .models import InputSource, InputType
from .backends import FFmpegBackend
from .listers import NginxRtmpLister
from .players import VLCPlayer, FFplayPlayer
from .utils import (
    get_default_variants,
    parse_variants,
    get_log_file,
    is_stream_active,
    start_ffmpeg_process,
    stop_stream_process,
    tail_logs,
)


def interactive_select(stream_descriptions: List[str]) -> int:
    """
    Use curses to let the user navigate up/down through `stream_keys` (a list of strings)
    and press ENTER to choose one. Returns the selected key (string).
    """

    def _inner(stdscr):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        stdscr.bkgd(" ", curses.color_pair(0))
        idx = 0
        n = len(stream_descriptions)
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "Select a stream (↑↓ to move, ENTER to select):")
            h, w = stdscr.getmaxyx()
            win_size = h - 2
            start = max(0, idx - win_size // 2)
            end = min(n, start + win_size)
            for i, key in enumerate(stream_descriptions[start:end], start):
                if i == idx:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(i - start + 1, 0, f"> {key}")
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(i - start + 1, 0, f"  {key}")
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (curses.KEY_UP, ord("k")) and idx > 0:
                idx -= 1
            elif ch in (curses.KEY_DOWN, ord("j")) and idx < n - 1:
                idx += 1
            elif ch in (curses.KEY_ENTER, 10, 13):
                return idx
            else:
                # немного ждем, чтобы не нагружать процессор
                time.sleep(0.01)

    return curses.wrapper(_inner)


@click.group()
def cli():
    """CLI Stream Manager for RTMP publishing and RTSP playback."""
    pass


@cli.command()
@click.option("--stream-key", "-s", required=True, help="Base stream key")
@click.option(
    "--input-file", "-i", type=click.Path(exists=True), help="Path to local video file"
)
@click.option("--device", "-d", help="Video device (e.g. /dev/video0 or 0)")
@click.option("--input-rtmp", "-r", help="RTMP source URL")
@click.option("--input-rtsp", help="RTSP source URL")
@click.option("--input-udp", help="UDP source (e.g. 127.0.0.1:1234)")
@click.option("--input-http", help="HTTP/HTTPS source URL")
@click.option("--original", "-o", is_flag=True, help="Stream original without variants")
@click.option("--variants", "-v", help="Custom variants (label:bitrate:width:height)")
@click.option("--no-audio", is_flag=True, help="Disable audio encoding")
@click.option("--no-loop", is_flag=True, help="Don't loop input file")
@click.option(
    "--nginx-rtmp-url",
    default="rtmp://localhost:1935/live",
    help="RTMP output URL (default: rtmp://localhost:1935/live)",
)
def publish(
    stream_key,
    input_file,
    device,
    input_rtmp,
    input_rtsp,
    input_udp,
    input_http,
    original,
    variants,
    no_audio,
    no_loop,
    nginx_rtmp_url,
):
    """Publish a new stream."""

    # Если stream_key уже активен, выводим ошибку
    if is_stream_active(stream_key):
        click.echo(f"Error: Stream '{stream_key}' is already active.", err=True)
        sys.exit(1)

    inputs = [
        bool(input_file),
        bool(device),
        bool(input_rtmp),
        bool(input_rtsp),
        bool(input_udp),
        bool(input_http),
    ]
    if sum(inputs) != 1:
        click.echo("Error: specify exactly one input source", err=True)
        sys.exit(1)

    if input_file:
        input_source = InputSource(
            InputType.FILE, os.path.abspath(input_file), not no_loop
        )
    elif device:
        input_source = InputSource(InputType.DEVICE, device)
    elif input_rtmp:
        input_source = InputSource(InputType.RTMP, input_rtmp)
    elif input_rtsp:
        input_source = InputSource(InputType.RTSP, input_rtsp)
    elif input_udp:
        input_source = InputSource(InputType.UDP, input_udp)
    elif input_http:
        input_source = InputSource(InputType.HTTP, input_http)

    # парсим варианты
    stream_variants = get_default_variants()
    if variants:
        stream_variants = parse_variants(variants)

    # билдим команду для ffmpeg
    backend = FFmpegBackend()
    command = backend.build_command(
        stream_key=stream_key,
        input_source=input_source,
        variants=stream_variants,
        output_base_url=nginx_rtmp_url,
        original_only=original,
        audio_enabled=not no_audio,
    )

    click.echo(f"Starting stream '{stream_key}'...")
    click.echo(f"Command: {command}")

    process = start_ffmpeg_process(command, stream_key)
    click.echo(f"FFmpeg started (PID {process.pid}). Press Ctrl+C to stop.")

    # выводим логи в реальном времени
    log_file = get_log_file(stream_key)
    tail_logs(log_file, stream_key)


@cli.command()
@click.option("--stream-key", "-s", required=True, help="Stream key to stop")
def stop(stream_key):
    """Stop a stream."""
    try:
        stop_stream_process(stream_key)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("list")
@click.option(
    "--nginx-host",
    default="localhost",
    help="nginx-rtmp host",
    show_default=True,
)
@click.option(
    "--nginx-stat-port",
    default="8080",
    help="nginx-rtmp stat port",
    show_default=True,
)
@click.option(
    "--media-host",
    default="localhost",
    help="MediaMTX host",
    show_default=True,
)
@click.option(
    "--media-api-port",
    default="9997",
    help="MediaMTX API port",
    show_default=True,
)
@click.option(
    "--source",
    # можно дополнить другими источниками монитроинга на выбор, главное чтобы была имлпементация
    # которая реализует StreamLister, в данном случае захардкодил только nginx
    type=click.Choice(["nginx"]),
    default="nginx",
    show_default=True,
    help="Source to list streams from",
)
def list_streams(nginx_host, nginx_stat_port, media_host, media_api_port, source):
    """List all active streams."""

    combined_streams = {}

    if source in ["nginx"]:
        try:
            nginx_lister = NginxRtmpLister(nginx_host, nginx_stat_port)
            nginx_streams = nginx_lister.get_active_streams()

            for stream_key, info in nginx_streams.items():
                if stream_key not in combined_streams:
                    combined_streams[stream_key] = info
                else:
                    combined_streams[stream_key]["variants"].update(info["variants"])
                    combined_streams[stream_key]["live"] = True

        except Exception as e:
            click.echo(f"Warning: Failed to get nginx streams: {e}", err=True)

    if not combined_streams:
        click.echo("No active streams found.")
        return

    click.echo("Available streams:")
    for base, data in combined_streams.items():
        variants = sorted(list(data["variants"]))
        live_status = "LIVE" if data.get("live", False) else "AVAILABLE"

        readers_info = ""
        if "readers" in data and data["readers"]:
            readers_list = [
                f"{v}: {data['readers'].get(v, 0)} viewers" for v in variants
            ]
            readers_info = f"  ({', '.join(readers_list)})"

        click.echo(
            f"  • {base:15s} [{live_status}]  variants: [{', '.join(variants)}{readers_info}]"
        )


@cli.command()
@click.option(
    "--stream-key",
    "-s",
    required=False,
    help="Stream key to play (omit if using --list)",
)
@click.option(
    "-l", "do_list", is_flag=True, help="Interactively list and choose a live stream"
)
@click.option("--original", "-o", is_flag=True, help="Play original stream")
@click.option("--variant", "-v", default="", help="Variant to play")
@click.option("--media-host", default="localhost", help="MediaMTX host")
@click.option("--media-rtsp-port", default="8554", help="MediaMTX RTSP port")
@click.option(
    "--player",
    type=click.Choice(["vlc", "ffplay"]),
    default="vlc",
    help="Player to use",
)
def play(stream_key, do_list, original, variant, media_host, media_rtsp_port, player):
    """Play a stream.

    If --list is provided, shows an interactive menu of active streams
    and lets you pick one. Otherwise you must pass --stream-key.
    """
    print("Playing a stream...")
    # Выбираем интерактивно из списка
    if do_list:
        streams = {}

        try:
            nginx_lister = NginxRtmpLister("localhost", "8080")
            nginx_streams = nginx_lister.get_active_streams()
            for key, info in nginx_streams.items():
                streams.setdefault(key, info)
        except Exception:
            pass

        if not streams:
            click.echo("No active streams found.")
            sys.exit(1)

        stream_descriptions = []
        for base, data in streams.items():
            variants = sorted(list(data["variants"]))
            live_status = "LIVE" if data.get("live", False) else "AVAILABLE"

            readers_info = ""
            if "readers" in data and data["readers"]:
                readers_list = [
                    f"{v}: {data['readers'].get(v, 0)} viewers" for v in variants
                ]
                readers_info = f"  ({', '.join(readers_list)})"

            stream_descriptions.append(
                f"  • {base:15s} [{live_status}]  variants: [{', '.join(variants)}{readers_info}]"
            )

        keys = sorted(streams.keys())
        chosen_id = interactive_select(stream_descriptions)
        chosen = keys[chosen_id]
        stream_key = chosen  # Перезапишем stream_key выбранным значением

    # Если stream_key не указан и не выбрано из списка, выводим ошибку
    if not stream_key:
        click.echo("Error: either --stream-key or --list is required.", err=True)
        sys.exit(1)

    if not original:
        stream_key = f"{stream_key}_{variant}"

    rtsp_url = f"rtsp://{media_host}:{media_rtsp_port}/{stream_key}"

    if player == "vlc":
        player_impl = VLCPlayer()
    else:
        player_impl = FFplayPlayer()

    try:
        player_impl.play_stream(rtsp_url)
    except Exception as e:
        click.echo(f"Error playing stream: {e}", err=True)
        sys.exit(1)
