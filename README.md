# Knight Online to Minecraft Map Converter

Convert Knight Online `.gtd` (terrain) and `.opd` (object) map files into playable Minecraft Java Edition worlds.

## What it does

- **Terrain**: Parses KO heightmaps and converts them to Minecraft terrain with appropriate block types (grass, dirt, stone, sand, etc.) based on texture IDs
- **Objects**: Converts KO game objects (buildings, trees, rocks, walls, etc.) into Minecraft structure approximations
- **Events**: Translates KO event objects (warp gates, bind points, gates, anvils, NPCs, etc.) into recognizable Minecraft markers
- **Output**: Generates a complete Minecraft Java Edition world (Anvil format, 1.18+ compatible) that you can drop into your saves folder

## Requirements

- Python 3.10+
- NumPy

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Convert terrain only
python -m ko2mc moradon.gtd --gtd-only

# Convert terrain + objects
python -m ko2mc moradon.gtd moradon.opd

# Custom output directory and world name
python -m ko2mc -o ./worlds -n Moradon moradon.gtd moradon.opd

# Scale up (2 or 4 MC blocks per KO tile for more detail)
python -m ko2mc --scale 2 moradon.gtd moradon.opd
```

### Arguments

| Argument | Description |
|----------|-------------|
| `gtd_file` | Path to `.gtd` terrain file (required) |
| `opd_file` | Path to `.opd` object file (optional) |
| `-o, --output` | Output directory (default: `./output`) |
| `-n, --name` | Minecraft world name |
| `-s, --scale` | Blocks per KO tile: 1, 2, or 4 (default: 1) |
| `--gtd-only` | Skip OPD object conversion |

### After conversion

Copy the generated world folder to your Minecraft saves directory:

- **Windows**: `%appdata%/.minecraft/saves/`
- **Linux**: `~/.minecraft/saves/`
- **macOS**: `~/Library/Application Support/minecraft/saves/`

## How it maps KO to Minecraft

### Terrain
Each KO tile (4m x 4m) becomes 1 Minecraft block (at scale=1). Heights are scaled so KO height 0 = MC Y=64. Below the surface, layers of dirt, stone, and bedrock are filled in.

### Texture mapping
KO texture IDs are mapped to Minecraft blocks: grass, dirt, sand, stone, gravel, cobblestone, snow, sandstone, clay, etc.

### Event objects
| KO Event | Minecraft Block |
|----------|----------------|
| Bind Point | Gold platform + Respawn Anchor |
| Gate | Iron Bars wall |
| Warp Gate | End Portal Frames |
| Barricade | Oak Fence wall |
| Magic Anvil | Anvil |
| Artifact | Iron Block + Beacon |
| Resurrection Point | Gold platform + Respawn Anchor |

### Structure objects
Object names are pattern-matched to place appropriate Minecraft structures:
- Trees → Oak Log + Leaves
- Rocks → Stone formations
- Buildings → Stone Brick shells
- Walls → Stone Brick Walls
- Lamps → Lanterns
- Water features → Water blocks

## Project structure

```
ko2mc/
  __init__.py       - Package init
  __main__.py       - CLI entry point
  gtd_parser.py     - GTD binary format parser
  opd_parser.py     - OPD binary format parser (with decryption)
  mc_world.py       - Minecraft Anvil world generator
  converter.py      - KO-to-MC conversion logic
```

## Sample data

The `gtd/` directory contains sample Knight Online terrain files that can be converted. Maps include Moradon, El Morad, Karus, battle zones, dungeons, and more.

## Credits

- Original SMD exporter by [Mustafa Kemal Gılor](https://github.com/mustafagilor)
- Minecraft conversion by this fork

## License

MIT
