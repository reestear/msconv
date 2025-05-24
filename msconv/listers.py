import requests
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Any


class StreamLister(ABC):
    """Abstract base class for listing active streams."""

    @abstractmethod
    def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active streams."""
        pass


class NginxRtmpLister(StreamLister):
    """List streams from nginx-rtmp statistics."""

    def __init__(self, nginx_host: str, nginx_stat_port: str):
        self.nginx_host = nginx_host
        self.nginx_stat_port = nginx_stat_port

    def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get active streams from nginx-rtmp statistics."""
        stat_url = f"http://{self.nginx_host}:{self.nginx_stat_port}/stat"

        try:
            response = requests.get(stat_url, timeout=5)
            response.raise_for_status()
            xml_root = ET.fromstring(response.text)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch nginx-rtmp stats: {e}")

        streams = {}
        for app in xml_root.findall("server/application"):
            app_name_el = app.find("name")
            app_name = app_name_el.text if (app_name_el is not None) else "(no-name)"

            live_block = app.find("live")
            if live_block is None:
                continue

            streams_els = live_block.findall("stream")
            if not streams_els:
                continue

            if app_name == "live":
                for stream in streams_els:
                    name_el = stream.find("name")

                    if name_el is not None and name_el.text:
                        stream_name = name_el.text
                        base_key, variant = self._parse_stream_name(stream_name)

                        if base_key not in streams:
                            streams[base_key] = {
                                "variants": set(),
                                "live": True,
                                "readers": {},
                            }

                        if variant:
                            streams[base_key]["variants"].add(variant)

        return streams

    def _parse_stream_name(self, stream_name: str) -> Tuple[str, str]:
        """Parse stream name into base key and variant."""
        if "_" in stream_name:
            lst = stream_name.rsplit("_", 1)
            return lst[0], lst[1]
        return stream_name, ""
