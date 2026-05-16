"""Biome stream inventory view."""
from .base_view import BaseTabView


class BiomeView(BaseTabView):
    TAB_NAME = "Biome"
    COLUMNS = [
        ("label",          "Stream Type"),
        ("stream_name",    "Stream ID"),
        ("record_count",   "Records"),
        ("files",          "Files"),
        ("total_size",     "Size"),
        ("decode_status",  "Decode"),
    ]
