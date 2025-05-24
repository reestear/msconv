import os
import click
from abc import ABC, abstractmethod


class StreamPlayer(ABC):
    """Abstract base class for stream players."""

    @abstractmethod
    def play_stream(self, stream_url: str) -> None:
        """Play a stream at the given URL."""
        pass


class VLCPlayer(StreamPlayer):
    """VLC-based stream player."""

    def play_stream(self, stream_url: str) -> None:
        """Play stream using VLC."""
        click.echo(f"Playing {stream_url} with VLC...")
        os.execvp("vlc", ["vlc", stream_url])


class FFplayPlayer(StreamPlayer):
    """FFplay-based stream player."""

    def play_stream(self, stream_url: str) -> None:
        """Play stream using FFplay."""
        click.echo(f"Playing {stream_url} with FFplay...")
        os.execvp("ffplay", ["ffplay", stream_url])
