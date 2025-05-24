from dataclasses import dataclass
from enum import Enum


class InputType(Enum):
    FILE = "file"
    DEVICE = "device"
    RTMP = "rtmp"
    RTSP = "rtsp"
    UDP = "udp"
    HTTP = "http"


@dataclass
class StreamVariant:
    """Represents a single stream variant configuration."""

    label: str
    bitrate: str
    width: int
    height: int
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    preset: str = "fast"
    crf: int = 23

    @property
    def bitrate_numeric(self) -> int:
        """Extract numeric bitrate value (e.g., '4000k' -> 4000)."""
        return int(self.bitrate.rstrip("k"))

    @property
    def buffer_size(self) -> str:
        """Calculate buffer size based on bitrate."""
        return f"{self.bitrate_numeric * 2}k"


@dataclass
class InputSource:
    """Represents an input source configuration."""

    type: InputType
    path: str
    loop: bool = True

    def to_ffmpeg_input(self) -> str:
        """Convert to FFmpeg input specification."""
        if self.type == InputType.FILE:
            loop_flag = "-stream_loop -1" if self.loop else ""
            return f"-re {loop_flag} -i {self.path}"
        elif self.type == InputType.DEVICE:
            device_path = f"/dev/video{self.path}" if self.path.isdigit() else self.path
            return f"-f v4l2 -i {device_path}"
        elif self.type in [InputType.RTMP, InputType.RTSP, InputType.HTTP]:
            return f"-i {self.path}"
        elif self.type == InputType.UDP:
            return f"-f mpegts -i udp://{self.path}"
        else:
            raise ValueError(f"Unsupported input type: {self.type}")
