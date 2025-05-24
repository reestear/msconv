import subprocess
from abc import ABC, abstractmethod
from typing import List
from .models import InputSource, StreamVariant


class StreamBackend(ABC):
    """Abstract base class for stream backends."""

    @abstractmethod
    def build_command(
        self,
        stream_key: str,
        input_source: InputSource,
        variants: List[StreamVariant],
        output_base_url: str,
        original_only: bool = False,
        audio_enabled: bool = True,
    ) -> str:
        """Build the streaming command."""
        pass


class FFmpegBackend(StreamBackend):
    """FFmpeg-based streaming backend."""

    def build_command(
        self,
        stream_key: str,
        input_source: InputSource,
        variants: List[StreamVariant],
        output_base_url: str,
        original_only: bool = False,
        audio_enabled: bool = True,
    ) -> str:
        """Build FFmpeg command string."""
        input_spec = input_source.to_ffmpeg_input()

        if original_only:
            return (
                f"ffmpeg {input_spec} " f"-c copy -f flv {output_base_url}/{stream_key}"
            )

        has_audio = audio_enabled and self._detect_audio(input_source.path)

        filter_complex = self._build_filter_complex(variants)
        mappings = self._build_mappings(
            variants, output_base_url, stream_key, has_audio
        )

        return (
            f"ffmpeg {input_spec} " f'-filter_complex "{filter_complex}" ' f"{mappings}"
        )

    def _detect_audio(self, input_path: str) -> bool:
        """Detect if input has audio streams."""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            input_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _build_filter_complex(self, variants: List[StreamVariant]) -> str:
        """Build FFmpeg filter complex for variants."""
        num_variants = len(variants)
        split_labels = [f"[v{i}]" for i in range(num_variants)]
        scale_maps = [
            f"[v{i}]scale={v.width}:{v.height}[v{i}out]" for i, v in enumerate(variants)
        ]

        split_filter = f"[0:v]split={num_variants}{''.join(split_labels)}"
        return f"{split_filter}; {'; '.join(scale_maps)}"

    def _build_mappings(
        self,
        variants: List[StreamVariant],
        base_url: str,
        stream_key: str,
        has_audio: bool,
    ) -> str:
        """Build FFmpeg output mappings."""
        mappings = []

        for i, variant in enumerate(variants):
            audio_part = (
                f"-map 0:a -c:a {variant.audio_codec} -b:a {variant.audio_bitrate}"
                if has_audio
                else "-an"
            )

            mapping = (
                f'-map "[v{i}out]" {audio_part} '
                f"-c:v {variant.video_codec} -preset {variant.preset} "
                f"-crf {variant.crf} -b:v {variant.bitrate} "
                f"-maxrate {variant.bitrate} -bufsize {variant.buffer_size} "
                f"-f flv {base_url}/{stream_key}_{variant.label}"
            )
            mappings.append(mapping)

        return " ".join(mappings)
