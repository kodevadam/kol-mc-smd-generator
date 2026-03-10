"""Minecraft world generator using the Anvil region file format.

Generates a Minecraft Java Edition world from block data.
Supports Minecraft 1.18+ data version (chunk format with sections at Y=-64 to 319).
"""

import gzip
import io
import math
import os
import struct
import time
import zlib
from dataclasses import dataclass, field

# Minecraft data version for 1.20.4
MC_DATA_VERSION = 3700
MIN_SECTION_Y = -4  # Y=-64 in section coords
MAX_SECTION_Y = 19   # Y=319 in section coords


def _write_nbt_tag(buf: io.BytesIO, tag_type: int, name: str | None, value):
    """Write an NBT tag to the buffer."""
    if name is not None:
        buf.write(struct.pack(">bH", tag_type, len(name)))
        buf.write(name.encode("utf-8"))
    else:
        # Inside a list, no type/name header
        pass

    if tag_type == 1:  # TAG_Byte
        buf.write(struct.pack(">b", value))
    elif tag_type == 2:  # TAG_Short
        buf.write(struct.pack(">h", value))
    elif tag_type == 3:  # TAG_Int
        buf.write(struct.pack(">i", value))
    elif tag_type == 4:  # TAG_Long
        buf.write(struct.pack(">q", value))
    elif tag_type == 5:  # TAG_Float
        buf.write(struct.pack(">f", value))
    elif tag_type == 6:  # TAG_Double
        buf.write(struct.pack(">d", value))
    elif tag_type == 7:  # TAG_Byte_Array
        buf.write(struct.pack(">i", len(value)))
        buf.write(bytes(value))
    elif tag_type == 8:  # TAG_String
        encoded = value.encode("utf-8")
        buf.write(struct.pack(">H", len(encoded)))
        buf.write(encoded)
    elif tag_type == 11:  # TAG_Int_Array
        buf.write(struct.pack(">i", len(value)))
        for v in value:
            buf.write(struct.pack(">i", v))
    elif tag_type == 12:  # TAG_Long_Array
        buf.write(struct.pack(">i", len(value)))
        for v in value:
            buf.write(struct.pack(">q", v))


def _pack_block_states(indices: list[int], palette_size: int) -> list[int]:
    """Pack block state indices into a long array for MC chunk sections.

    Uses the compacted format: bits per entry = max(4, ceil(log2(palette_size))).
    Each long holds floor(64 / bits_per_entry) entries, entries don't span longs.
    """
    if palette_size <= 1:
        # Single block type, no block states array needed in modern format
        # but we still provide it for compatibility
        bits_per_entry = 4
    else:
        bits_per_entry = max(4, math.ceil(math.log2(palette_size)))

    entries_per_long = 64 // bits_per_entry
    num_longs = math.ceil(4096 / entries_per_long)
    longs = []

    for long_idx in range(num_longs):
        val = 0
        for entry_idx in range(entries_per_long):
            block_idx = long_idx * entries_per_long + entry_idx
            if block_idx < 4096:
                idx = indices[block_idx]
                val |= (idx & ((1 << bits_per_entry) - 1)) << (entry_idx * bits_per_entry)
        # Convert to signed 64-bit
        if val >= (1 << 63):
            val -= (1 << 64)
        longs.append(val)

    return longs


@dataclass
class ChunkSection:
    """A 16x16x16 section of blocks within a chunk."""
    y: int  # Section Y coordinate
    palette: list[str] = field(default_factory=lambda: ["minecraft:air"])
    blocks: list[int] = field(default_factory=lambda: [0] * 4096)

    def set_block(self, x: int, y: int, z: int, block_name: str):
        """Set a block at local coordinates (0-15)."""
        if block_name not in self.palette:
            self.palette.append(block_name)
        idx = self.palette.index(block_name)
        self.blocks[y * 256 + z * 16 + x] = idx

    def is_empty(self) -> bool:
        return all(b == 0 for b in self.blocks)


class Chunk:
    """A 16x16 column of blocks."""

    def __init__(self, cx: int, cz: int):
        self.cx = cx
        self.cz = cz
        self.sections: dict[int, ChunkSection] = {}

    def get_section(self, section_y: int) -> ChunkSection:
        if section_y not in self.sections:
            self.sections[section_y] = ChunkSection(y=section_y)
        return self.sections[section_y]

    def set_block(self, x: int, y: int, z: int, block_name: str):
        """Set a block at chunk-local x,z and world y."""
        section_y = y >> 4
        local_y = y & 0xF
        section = self.get_section(section_y)
        section.set_block(x, local_y, z, block_name)

    def to_nbt_bytes(self) -> bytes:
        """Serialize this chunk to NBT bytes (gzip compressed)."""
        buf = io.BytesIO()

        # Root compound tag
        _write_nbt_tag(buf, 10, "", None)  # TAG_Compound root

        # DataVersion
        _write_nbt_tag(buf, 3, "DataVersion", MC_DATA_VERSION)

        # xPos, yPos, zPos
        _write_nbt_tag(buf, 3, "xPos", self.cx)
        _write_nbt_tag(buf, 3, "yPos", MIN_SECTION_Y)
        _write_nbt_tag(buf, 3, "zPos", self.cz)

        # Status
        _write_nbt_tag(buf, 8, "Status", "minecraft:full")

        # LastUpdate
        _write_nbt_tag(buf, 4, "LastUpdate", 0)

        # sections list
        sections_to_write = []
        for sy in range(MIN_SECTION_Y, MAX_SECTION_Y + 1):
            if sy in self.sections and not self.sections[sy].is_empty():
                sections_to_write.append(self.sections[sy])
            else:
                # Write empty section
                sections_to_write.append(ChunkSection(y=sy))

        # TAG_List of TAG_Compound
        buf.write(struct.pack(">bH", 9, len("sections")))
        buf.write(b"sections")
        buf.write(struct.pack(">bi", 10, len(sections_to_write)))

        for section in sections_to_write:
            # Y
            _write_nbt_tag(buf, 1, "Y", section.y)

            # block_states compound
            _write_nbt_tag(buf, 10, "block_states", None)

            # palette
            buf.write(struct.pack(">bH", 9, len("palette")))
            buf.write(b"palette")
            buf.write(struct.pack(">bi", 10, len(section.palette)))

            for block_name in section.palette:
                _write_nbt_tag(buf, 8, "Name", block_name)
                buf.write(b"\x00")  # End compound

            # data (packed long array)
            if len(section.palette) > 1:
                longs = _pack_block_states(section.blocks, len(section.palette))
                _write_nbt_tag(buf, 12, "data", longs)

            buf.write(b"\x00")  # End block_states compound

            # biomes compound (simplified - plains everywhere)
            _write_nbt_tag(buf, 10, "biomes", None)
            buf.write(struct.pack(">bH", 9, len("palette")))
            buf.write(b"palette")
            buf.write(struct.pack(">bi", 8, 1))
            encoded = "minecraft:plains".encode("utf-8")
            buf.write(struct.pack(">H", len(encoded)))
            buf.write(encoded)
            buf.write(b"\x00")  # End biomes compound

            buf.write(b"\x00")  # End section compound

        # Heightmaps compound (empty - MC will recalculate)
        _write_nbt_tag(buf, 10, "Heightmaps", None)
        buf.write(b"\x00")  # End Heightmaps

        buf.write(b"\x00")  # End root compound

        return buf.getvalue()


class MinecraftWorld:
    """Manages a Minecraft world (region files)."""

    def __init__(self, world_dir: str, world_name: str = "KnightOnline"):
        self.world_dir = world_dir
        self.world_name = world_name
        self.chunks: dict[tuple[int, int], Chunk] = {}

    def set_block(self, x: int, y: int, z: int, block_name: str):
        """Set a block at world coordinates."""
        cx = x >> 4
        cz = z >> 4
        key = (cx, cz)
        if key not in self.chunks:
            self.chunks[key] = Chunk(cx, cz)
        self.chunks[key].set_block(x & 0xF, y, z & 0xF, block_name)

    def save(self):
        """Write all chunks to region files and create level.dat."""
        region_dir = os.path.join(self.world_dir, "region")
        os.makedirs(region_dir, exist_ok=True)

        # Group chunks by region
        regions: dict[tuple[int, int], list[Chunk]] = {}
        for (cx, cz), chunk in self.chunks.items():
            rx = cx >> 5
            rz = cz >> 5
            key = (rx, rz)
            if key not in regions:
                regions[key] = []
            regions[key].append(chunk)

        print(f"  Saving {len(self.chunks)} chunks across {len(regions)} region files...")

        for (rx, rz), chunks in regions.items():
            self._write_region(region_dir, rx, rz, chunks)

        self._write_level_dat()
        print(f"  World saved to {self.world_dir}")

    def _write_region(self, region_dir: str, rx: int, rz: int, chunks: list[Chunk]):
        """Write a .mca region file."""
        filepath = os.path.join(region_dir, f"r.{rx}.{rz}.mca")

        # Region file: 8KiB header (4KiB locations + 4KiB timestamps) + chunk data
        locations = [0] * 1024  # offset(3 bytes) + sector_count(1 byte)
        timestamps = [0] * 1024

        chunk_data_parts = []
        current_sector = 2  # First 2 sectors are header

        for chunk in chunks:
            local_x = chunk.cx & 31
            local_z = chunk.cz & 31
            idx = local_x + local_z * 32

            # Serialize chunk
            nbt_data = chunk.to_nbt_bytes()
            compressed = zlib.compress(nbt_data)

            # Chunk data: length(4) + compression_type(1) + data
            chunk_bytes = struct.pack(">iB", len(compressed) + 1, 2) + compressed

            # Pad to 4KiB sectors
            padded_len = math.ceil(len(chunk_bytes) / 4096) * 4096
            chunk_bytes = chunk_bytes.ljust(padded_len, b"\x00")
            sector_count = padded_len // 4096

            locations[idx] = (current_sector << 8) | (sector_count & 0xFF)
            timestamps[idx] = int(time.time())

            chunk_data_parts.append(chunk_bytes)
            current_sector += sector_count

        with open(filepath, "wb") as f:
            # Write location table
            for loc in locations:
                f.write(struct.pack(">I", loc))
            # Write timestamp table
            for ts in timestamps:
                f.write(struct.pack(">I", ts))
            # Write chunk data
            for data in chunk_data_parts:
                f.write(data)

    def _write_level_dat(self):
        """Write a minimal level.dat file."""
        buf = io.BytesIO()

        # Root compound
        _write_nbt_tag(buf, 10, "", None)

        # Data compound
        _write_nbt_tag(buf, 10, "Data", None)

        _write_nbt_tag(buf, 3, "DataVersion", MC_DATA_VERSION)
        _write_nbt_tag(buf, 8, "LevelName", self.world_name)
        _write_nbt_tag(buf, 3, "SpawnX", 0)
        _write_nbt_tag(buf, 3, "SpawnY", 100)
        _write_nbt_tag(buf, 3, "SpawnZ", 0)
        _write_nbt_tag(buf, 3, "GameType", 1)  # Creative
        _write_nbt_tag(buf, 1, "hardcore", 0)
        _write_nbt_tag(buf, 1, "allowCommands", 1)
        _write_nbt_tag(buf, 3, "version", 19133)  # Anvil format
        _write_nbt_tag(buf, 8, "generatorName", "flat")
        _write_nbt_tag(buf, 4, "Time", 6000)
        _write_nbt_tag(buf, 4, "LastPlayed", int(time.time() * 1000))
        _write_nbt_tag(buf, 1, "Difficulty", 0)  # Peaceful

        # WorldGenSettings
        _write_nbt_tag(buf, 10, "WorldGenSettings", None)
        _write_nbt_tag(buf, 4, "seed", 0)
        _write_nbt_tag(buf, 1, "generate_features", 0)
        buf.write(b"\x00")  # End WorldGenSettings

        buf.write(b"\x00")  # End Data compound
        buf.write(b"\x00")  # End root compound

        level_dat_path = os.path.join(self.world_dir, "level.dat")
        with gzip.open(level_dat_path, "wb") as f:
            f.write(buf.getvalue())
