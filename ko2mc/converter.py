"""Converts Knight Online map data to a Minecraft world.

Handles terrain heightmap conversion, texture-to-block mapping,
and placement of KO objects as Minecraft structures/markers.
"""

import math
import os
import re

import numpy as np

from .gtd_parser import GTDFile, parse_gtd
from .mc_world import MinecraftWorld
from .opd_parser import (
    OBJECT_ANVIL,
    OBJECT_ARTIFACT,
    OBJECT_BARRICADE,
    OBJECT_BIND,
    OBJECT_FLAG_LEVER,
    OBJECT_GATE,
    OBJECT_GATE2,
    OBJECT_GATE_LEVER,
    OBJECT_NPC,
    OBJECT_REMOVE_BIND,
    OBJECT_WARP_GATE,
    OPDFile,
    Shape,
    parse_opd,
)

# KO unit distance: 1 tile = 4 meters in KO
# We map 1 KO tile to 4 Minecraft blocks (preserving scale)
KO_TILE_TO_MC_BLOCKS = 4

# Minecraft Y base level (KO height 0.0 maps to this Y)
MC_Y_BASE = 64

# Height scale: KO heights can be large. We scale them down.
# KO height units are roughly meters; 1 KO height unit = 0.5 MC blocks
KO_HEIGHT_SCALE = 0.5

# Maximum MC Y (leave headroom)
MC_Y_MAX = 300
MC_Y_MIN = -60

# Texture ID to Minecraft block mapping.
# KO texture IDs vary by map; we use heuristics based on common patterns.
# This maps texture index ranges to block types.
DEFAULT_SURFACE_BLOCK = "minecraft:grass_block"
DEFAULT_FILL_BLOCK = "minecraft:dirt"
DEFAULT_STONE_BLOCK = "minecraft:stone"
DEFAULT_BEDROCK = "minecraft:bedrock"

# Known KO texture patterns (based on texture filenames commonly seen)
# These are best-effort mappings based on typical KO terrain textures.
TEXTURE_BLOCK_MAP = {
    # Grass/field textures
    0: "minecraft:grass_block",
    1: "minecraft:dirt",
    2: "minecraft:sand",
    3: "minecraft:stone",
    4: "minecraft:gravel",
    5: "minecraft:cobblestone",
    6: "minecraft:snow_block",
    7: "minecraft:coarse_dirt",
    8: "minecraft:sandstone",
    9: "minecraft:clay",
    10: "minecraft:podzol",
    11: "minecraft:moss_block",
    12: "minecraft:mud",
    13: "minecraft:packed_mud",
    14: "minecraft:terracotta",
    15: "minecraft:red_sand",
}

# Object name pattern to block type mapping
OBJECT_BLOCK_PATTERNS = {
    r"tree|plant|bush|flower|grass": "minecraft:oak_log",
    r"rock|stone|boulder": "minecraft:cobblestone",
    r"wall|fence|railing": "minecraft:stone_bricks",
    r"house|building|tower|castle": "minecraft:stone_bricks",
    r"bridge": "minecraft:stone_brick_slab",
    r"water|fountain|lake|river": "minecraft:water",
    r"lamp|light|torch|fire": "minecraft:lantern",
    r"flag|banner": "minecraft:white_banner",
    r"chest|box|crate": "minecraft:chest",
    r"sign|board": "minecraft:oak_sign",
    r"door": "minecraft:oak_door",
    r"stair|step": "minecraft:stone_brick_stairs",
    r"column|pillar": "minecraft:quartz_pillar",
}

# Event type to Minecraft marker block
EVENT_MARKER_BLOCKS = {
    OBJECT_BIND: "minecraft:respawn_anchor",
    OBJECT_GATE: "minecraft:iron_door",
    OBJECT_GATE2: "minecraft:iron_door",
    OBJECT_GATE_LEVER: "minecraft:lever",
    OBJECT_FLAG_LEVER: "minecraft:white_banner",
    OBJECT_WARP_GATE: "minecraft:end_portal_frame",
    OBJECT_BARRICADE: "minecraft:iron_bars",
    OBJECT_REMOVE_BIND: "minecraft:respawn_anchor",
    OBJECT_ANVIL: "minecraft:anvil",
    OBJECT_ARTIFACT: "minecraft:beacon",
    OBJECT_NPC: "minecraft:villager_spawn_egg",  # We'll use armor stands via sign
}


def _texture_to_block(tex_id: int) -> str:
    """Map a KO texture ID to a Minecraft block name."""
    return TEXTURE_BLOCK_MAP.get(tex_id % 16, DEFAULT_SURFACE_BLOCK)


def _object_name_to_block(name: str) -> str | None:
    """Try to map a KO object name to a Minecraft block."""
    name_lower = name.lower()
    for pattern, block in OBJECT_BLOCK_PATTERNS.items():
        if re.search(pattern, name_lower):
            return block
    return None


def _ko_to_mc_y(ko_height: float) -> int:
    """Convert a KO height value to Minecraft Y coordinate."""
    mc_y = MC_Y_BASE + int(ko_height * KO_HEIGHT_SCALE)
    return max(MC_Y_MIN, min(MC_Y_MAX, mc_y))


def _ko_to_mc_xz(ko_coord: float) -> int:
    """Convert a KO world coordinate to Minecraft X or Z."""
    # KO tile = ko_coord / 4.0, then each tile = KO_TILE_TO_MC_BLOCKS MC blocks
    # But since KO_TILE_TO_MC_BLOCKS=4 and tile=coord/4, this simplifies to 1:1
    # We offset so the map is centered (KO maps start at 0,0)
    return int(ko_coord)


def convert_terrain(gtd: GTDFile, world: MinecraftWorld, scale: int = 1):
    """Convert GTD heightmap to Minecraft terrain blocks.

    Args:
        gtd: Parsed GTD data.
        world: Target Minecraft world.
        scale: Blocks per KO tile (default 1 for 1:1 mapping at tile level).
    """
    n = gtd.heightmap_size
    total_tiles = n * n
    print(f"  Converting {n}x{n} terrain ({total_tiles} tiles)...")

    placed = 0
    for tx in range(n):
        if tx % 64 == 0:
            pct = (tx * n) / total_tiles * 100
            print(f"    Progress: {pct:.0f}% (row {tx}/{n})")

        for tz in range(n):
            height = gtd.get_height(tx, tz)
            tex_id = int(gtd.texture_ids[tx, tz])

            mc_y = _ko_to_mc_y(height)
            surface_block = _texture_to_block(tex_id)

            # Place blocks for each scale unit
            for dx in range(scale):
                for dz in range(scale):
                    mc_x = tx * scale + dx
                    mc_z = tz * scale + dz

                    # Surface block
                    world.set_block(mc_x, mc_y, mc_z, surface_block)

                    # Fill below surface with appropriate blocks
                    # Use dirt for top 3 layers, then stone, then bedrock at bottom
                    fill_depth = min(8, mc_y - MC_Y_MIN)
                    for dy in range(1, fill_depth + 1):
                        y = mc_y - dy
                        if y < MC_Y_MIN:
                            break
                        if dy <= 3:
                            world.set_block(mc_x, y, mc_z, DEFAULT_FILL_BLOCK)
                        elif dy == fill_depth:
                            world.set_block(mc_x, y, mc_z, DEFAULT_BEDROCK)
                        else:
                            world.set_block(mc_x, y, mc_z, DEFAULT_STONE_BLOCK)

                    placed += 1

    print(f"    Placed {placed} surface blocks.")


def convert_objects(opd: OPDFile, gtd: GTDFile, world: MinecraftWorld, scale: int = 1):
    """Convert OPD objects to Minecraft structures/markers.

    Args:
        opd: Parsed OPD data.
        gtd: Parsed GTD data (for ground height reference).
        world: Target Minecraft world.
        scale: Blocks per KO tile.
    """
    print(f"  Converting {len(opd.shapes)} objects...")
    event_count = 0
    structure_count = 0

    for shape in opd.shapes:
        pos = shape.position
        # Convert KO world position to tile coordinates
        tile_x = int(pos.x / 4.0)
        tile_z = int(pos.z / 4.0)

        # Get ground height at this position
        ground_height = gtd.get_height(tile_x, tile_z) if gtd else pos.y
        mc_y = _ko_to_mc_y(ground_height)

        mc_x = int(pos.x / 4.0 * scale)
        mc_z = int(pos.z / 4.0 * scale)

        if shape.is_event_object:
            _place_event_object(shape, mc_x, mc_y, mc_z, world)
            event_count += 1
        else:
            _place_structure_object(shape, mc_x, mc_y, mc_z, world, scale)
            structure_count += 1

    print(f"    Placed {event_count} event markers, {structure_count} structures.")


def _place_event_object(shape: Shape, mc_x: int, mc_y: int, mc_z: int, world: MinecraftWorld):
    """Place an event object as a Minecraft marker."""
    marker_block = EVENT_MARKER_BLOCKS.get(shape.event_type, "minecraft:glowstone")

    # Place marker block on top of terrain
    world.set_block(mc_x, mc_y + 1, mc_z, marker_block)

    # For warp gates, create a small portal-like structure
    if shape.event_type == OBJECT_WARP_GATE:
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                world.set_block(mc_x + dx, mc_y + 1, mc_z + dz, "minecraft:end_portal_frame")
        world.set_block(mc_x, mc_y + 2, mc_z, "minecraft:end_portal_frame")
        world.set_block(mc_x, mc_y + 3, mc_z, "minecraft:end_portal_frame")

    # For gates, create a wall-like structure
    elif shape.event_type in (OBJECT_GATE, OBJECT_GATE2):
        for dy in range(4):
            world.set_block(mc_x - 1, mc_y + 1 + dy, mc_z, "minecraft:iron_bars")
            world.set_block(mc_x, mc_y + 1 + dy, mc_z, "minecraft:iron_bars")
            world.set_block(mc_x + 1, mc_y + 1 + dy, mc_z, "minecraft:iron_bars")

    # For barricades, create a wall
    elif shape.event_type == OBJECT_BARRICADE:
        for dx in range(-2, 3):
            for dy in range(3):
                world.set_block(mc_x + dx, mc_y + 1 + dy, mc_z, "minecraft:oak_fence")

    # For bind/resurrection points, create a small platform
    elif shape.event_type in (OBJECT_BIND, OBJECT_REMOVE_BIND):
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                world.set_block(mc_x + dx, mc_y, mc_z + dz, "minecraft:gold_block")
        world.set_block(mc_x, mc_y + 1, mc_z, "minecraft:respawn_anchor")

    # For anvils
    elif shape.event_type == OBJECT_ANVIL:
        world.set_block(mc_x, mc_y + 1, mc_z, "minecraft:anvil")

    # For artifacts/beacons
    elif shape.event_type == OBJECT_ARTIFACT:
        # Create beacon-like structure
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                world.set_block(mc_x + dx, mc_y, mc_z + dz, "minecraft:iron_block")
        world.set_block(mc_x, mc_y + 1, mc_z, "minecraft:beacon")


def _place_structure_object(shape: Shape, mc_x: int, mc_y: int, mc_z: int,
                            world: MinecraftWorld, scale: int):
    """Place a non-event object as a Minecraft structure approximation."""
    # Try to determine block type from object name
    block = _object_name_to_block(shape.name)

    if block is None:
        # Use object scale to determine size; place as a generic cobblestone structure
        block = "minecraft:cobblestone"

    # Estimate object size from scale values
    sx = max(1, int(abs(shape.scale.x) * 2))
    sy = max(1, int(abs(shape.scale.y) * 2))
    sz = max(1, int(abs(shape.scale.z) * 2))

    # Cap structure size to reasonable limits
    sx = min(sx, 16)
    sy = min(sy, 16)
    sz = min(sz, 16)

    # For tree-like objects
    name_lower = shape.name.lower()
    if re.search(r"tree", name_lower):
        _place_tree(mc_x, mc_y + 1, mc_z, world, sy)
    elif re.search(r"rock|stone|boulder", name_lower):
        _place_rock(mc_x, mc_y + 1, mc_z, world, max(sx, sz))
    elif re.search(r"house|building|castle|tower", name_lower):
        _place_building(mc_x, mc_y + 1, mc_z, world, sx, sy, sz)
    elif re.search(r"wall|fence", name_lower):
        _place_wall(mc_x, mc_y + 1, mc_z, world, sx, sy)
    elif re.search(r"lamp|light|torch", name_lower):
        world.set_block(mc_x, mc_y + 1, mc_z, "minecraft:lantern")
    elif re.search(r"water|fountain", name_lower):
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                world.set_block(mc_x + dx, mc_y, mc_z + dz, "minecraft:water")
    else:
        # Generic small structure placeholder
        for dy in range(min(sy, 3)):
            world.set_block(mc_x, mc_y + 1 + dy, mc_z, block)


def _place_tree(x: int, y: int, z: int, world: MinecraftWorld, height: int):
    """Place a simple tree."""
    trunk_height = max(3, min(height, 8))
    for dy in range(trunk_height):
        world.set_block(x, y + dy, z, "minecraft:oak_log")

    # Leaves
    leaf_start = trunk_height - 2
    for dy in range(leaf_start, trunk_height + 2):
        radius = 2 if dy < trunk_height else 1
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx == 0 and dz == 0 and dy < trunk_height:
                    continue
                if abs(dx) + abs(dz) <= radius + 1:
                    world.set_block(x + dx, y + dy, z + dz, "minecraft:oak_leaves")


def _place_rock(x: int, y: int, z: int, world: MinecraftWorld, size: int):
    """Place a rock formation."""
    r = max(1, min(size // 2, 3))
    for dx in range(-r, r + 1):
        for dz in range(-r, r + 1):
            for dy in range(r + 1):
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist <= r + 0.5:
                    world.set_block(x + dx, y + dy, z + dz, "minecraft:stone")


def _place_building(x: int, y: int, z: int, world: MinecraftWorld,
                    sx: int, sy: int, sz: int):
    """Place a simple building outline."""
    half_x = max(1, sx // 2)
    half_z = max(1, sz // 2)
    height = max(3, min(sy, 10))

    for dx in range(-half_x, half_x + 1):
        for dz in range(-half_z, half_z + 1):
            is_wall = abs(dx) == half_x or abs(dz) == half_z
            for dy in range(height):
                if is_wall or dy == 0 or dy == height - 1:
                    world.set_block(x + dx, y + dy, z + dz, "minecraft:stone_bricks")


def _place_wall(x: int, y: int, z: int, world: MinecraftWorld, length: int, height: int):
    """Place a wall segment."""
    half_len = max(1, length // 2)
    h = max(2, min(height, 6))
    for dx in range(-half_len, half_len + 1):
        for dy in range(h):
            world.set_block(x + dx, y + dy, z, "minecraft:stone_brick_wall")


def convert_map(gtd_path: str, opd_path: str | None, output_dir: str,
                world_name: str = "KnightOnline", scale: int = 1) -> str:
    """Convert KO map files to a Minecraft world.

    Args:
        gtd_path: Path to .gtd file.
        opd_path: Path to .opd file (optional).
        output_dir: Output directory for the Minecraft world.
        world_name: Name for the Minecraft world.
        scale: MC blocks per KO tile (1=compact, 4=full scale).

    Returns:
        Path to the generated world directory.
    """
    print(f"Knight Online -> Minecraft Converter")
    print(f"=" * 50)

    # Parse input files
    print(f"\nParsing GTD: {gtd_path}")
    gtd = parse_gtd(gtd_path)

    opd = None
    if opd_path and os.path.exists(opd_path):
        print(f"\nParsing OPD: {opd_path}")
        try:
            opd = parse_opd(opd_path)
        except Exception as e:
            print(f"  Warning: Failed to parse OPD file: {e}")
            print(f"  Continuing with terrain only...")

    # Create world
    world_dir = os.path.join(output_dir, world_name)
    world = MinecraftWorld(world_dir, world_name)

    # Set spawn point near center of map
    center = gtd.heightmap_size // 2
    center_height = _ko_to_mc_y(gtd.get_height(center, center))

    # Convert terrain
    print(f"\nConverting terrain (scale={scale})...")
    convert_terrain(gtd, world, scale)

    # Convert objects
    if opd:
        print(f"\nConverting objects...")
        convert_objects(opd, gtd, world, scale)

    # Save world
    print(f"\nSaving Minecraft world...")
    world.save()

    # Print summary
    print(f"\n{'=' * 50}")
    print(f"Conversion complete!")
    print(f"  World: {world_dir}")
    print(f"  Map: {gtd.map_name}")
    print(f"  Terrain: {gtd.heightmap_size}x{gtd.heightmap_size} tiles")
    if opd:
        print(f"  Objects: {len(opd.shapes)}")
    print(f"  Scale: 1 KO tile = {scale} MC block(s)")
    print(f"\nTo use: Copy '{world_name}' folder to your Minecraft saves directory.")
    print(f"  Windows: %appdata%/.minecraft/saves/")
    print(f"  Linux:   ~/.minecraft/saves/")
    print(f"  macOS:   ~/Library/Application Support/minecraft/saves/")

    return world_dir
