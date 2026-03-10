"""Parser for Knight Online .gtd (Game Terrain Data) files.

GTD files contain heightmap data and texture IDs for terrain tiles.
Binary format (little-endian):
  - uint32 string_size
  - If string_size > 2: NEW format
      - char[string_size] map_name
      - uint32 unknown
  - Else: OLD format
      - uint32 string_size (re-read)
      - char[string_size] map_name
  - uint32 heightmap_size (NxN grid)
  - For z in 0..heightmap_size, x in 0..heightmap_size:
      - float height
      - uint32 texture_id (dxtid)
"""

import struct
import numpy as np


class GTDFile:
    """Parsed GTD terrain data."""

    def __init__(self):
        self.map_name: str = ""
        self.heightmap_size: int = 0
        self.heights: np.ndarray | None = None
        self.texture_ids: np.ndarray | None = None

    def get_height(self, x: int, z: int) -> float:
        if x < 0 or x >= self.heightmap_size or z < 0 or z >= self.heightmap_size:
            return 0.0
        return float(self.heights[x, z])


def parse_gtd(filepath: str) -> GTDFile:
    """Parse a .gtd file and return terrain data."""
    gtd = GTDFile()

    with open(filepath, "rb") as fp:
        # Read map name header
        (string_size,) = struct.unpack("<I", fp.read(4))

        if string_size > 2:
            # New format
            gtd.map_name = fp.read(string_size).decode("ascii", errors="replace").rstrip("\x00")
            # Unknown value in new format
            fp.read(4)
        else:
            # Old format - re-read string size
            (string_size,) = struct.unpack("<I", fp.read(4))
            gtd.map_name = fp.read(string_size).decode("ascii", errors="replace").rstrip("\x00")

        # Read heightmap size
        (gtd.heightmap_size,) = struct.unpack("<I", fp.read(4))
        n = gtd.heightmap_size

        # Allocate arrays
        gtd.heights = np.zeros((n, n), dtype=np.float32)
        gtd.texture_ids = np.zeros((n, n), dtype=np.uint32)

        # Read height + texture data (z-major, then x)
        for z in range(n):
            for x in range(n):
                (height,) = struct.unpack("<f", fp.read(4))
                (tex_id,) = struct.unpack("<I", fp.read(4))
                gtd.heights[x, z] = height
                gtd.texture_ids[x, z] = tex_id

    print(f"  GTD: map='{gtd.map_name}', heightmap={n}x{n}")
    h = gtd.heights
    print(f"  GTD: height range [{h.min():.1f}, {h.max():.1f}]")

    return gtd
