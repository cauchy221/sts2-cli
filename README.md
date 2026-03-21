# sts2-cli

Headless Slay the Spire 2 CLI. Play the full game from a terminal — no GPU, no UI, no Godot runtime needed.

**Use cases:**
- Play interactively in your terminal
- Build an LLM agent that plays the game
- RL training environment
- Automated testing / game balance analysis

**Performance:** 100/100 games complete, ~1s/game, 0 crashes.

## Quick Start

```bash
# Build (requires ARM64 .NET SDK + game DLLs in lib/)
~/.dotnet-arm64/dotnet build Sts2Headless/Sts2Headless.csproj

# Play interactively
python3 python/play.py

# Auto-play (simple AI)
python3 python/play.py --auto --seed test123

# Run 100 games with random agent
python3 python/play_full_run.py 100 Ironclad
```

## Interactive Mode

```
$ python3 python/play.py --character Ironclad

Slay the Spire 2 — Headless CLI
Character: Ironclad  Seed: random

═══════════════════════════════════════════════════
  Overgrowth(密林) Floor 0
  The Ironclad(铁甲战士)  HP ████████████████████ 80/80  Gold 99  Deck 10
  Relics: Burning Blood(燃烧之血)

  [3,0] ⚔ Monster
  [2,1] ⚔ Monster
  [5,1] ❓ Unknown

> Choose node (col,row): 3,0

──────────────────────────────────────────────────
  Round 1  Energy 3/3  Draw 5  Discard 0

  [0] Nibbit(小啃兽)  ████████████████████ 44/44  ⚔ ATK

  ● [0] Defend(防御) (1) Skill
  ● [1] Strike(打击) (1) Attack  → AnyEnemy
  ● [2] Strike(打击) (1) Attack  → AnyEnemy
  ● [3] Defend(防御) (1) Skill
  ● [4] Bash(痛击)   (2) Attack  → AnyEnemy

> Play card [index] or (e)nd turn: 4
> Target enemy [index]: 0
```

## JSON Protocol

For programmatic use, communicate via JSON over stdin/stdout:

### Commands (stdin)

```jsonc
// Start a new run
{"cmd": "start_run", "character": "Ironclad", "seed": "my_seed", "ascension": 0}

// Perform an action (response is always the next decision point)
{"cmd": "action", "action": "<action_name>", "args": {...}}

// Quit
{"cmd": "quit"}
```

### Decision Points (stdout)

The CLI drives the game forward and pauses at every **decision point** — a moment where the player must choose. Each response is a JSON object with `"decision"` field:

| Decision | When | Available Actions |
|---|---|---|
| `map_select` | At the map, choose next room | `select_map_node` |
| `combat_play` | Your turn in combat | `play_card`, `end_turn` |
| `card_reward` | After combat, pick a card | `select_card_reward`, `skip_card_reward` |
| `rest_site` | At a campfire | `choose_option` |
| `event_choice` | Random event | `choose_option`, `leave_room` |
| `shop` | At the merchant | `buy_card`, `buy_relic`, `buy_potion`, `remove_card`, `leave_room` |
| `game_over` | Run ended | *(terminal state)* |

### Actions Reference

```jsonc
// Map: select a node from the choices list
{"cmd": "action", "action": "select_map_node", "args": {"col": 3, "row": 1}}

// Combat: play a card (target_index required for AnyEnemy cards)
{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}

// Combat: end your turn
{"cmd": "action", "action": "end_turn"}

// Card Reward: pick a card by index
{"cmd": "action", "action": "select_card_reward", "args": {"card_index": 1}}

// Card Reward: skip (take no card)
{"cmd": "action", "action": "skip_card_reward"}

// Rest Site / Event: choose an option by index
{"cmd": "action", "action": "choose_option", "args": {"option_index": 0}}

// Shop: buy items
{"cmd": "action", "action": "buy_card", "args": {"card_index": 2}}
{"cmd": "action", "action": "buy_relic", "args": {"relic_index": 0}}
{"cmd": "action", "action": "buy_potion", "args": {"potion_index": 1}}
{"cmd": "action", "action": "remove_card"}

// Leave current room (shop, event)
{"cmd": "action", "action": "leave_room"}
```

### Example: combat_play Response

All names are bilingual `{"en": "...", "zh": "..."}`:

```json
{
  "type": "decision",
  "decision": "combat_play",
  "round": 1,
  "energy": 3,
  "max_energy": 3,
  "hand": [
    {
      "index": 0,
      "id": "CARD.STRIKE_IRONCLAD",
      "name": {"en": "Strike", "zh": "打击"},
      "cost": 1,
      "type": "Attack",
      "can_play": true,
      "target_type": "AnyEnemy",
      "description": {"en": "Deal {Damage:diff()} damage.", "zh": "造成{Damage:diff()}点伤害。"}
    }
  ],
  "enemies": [
    {
      "index": 0,
      "name": {"en": "Nibbit", "zh": "小啃兽"},
      "hp": 44,
      "max_hp": 44,
      "block": 0,
      "intends_attack": true
    }
  ],
  "player": {
    "name": {"en": "The Ironclad", "zh": "铁甲战士"},
    "hp": 80,
    "max_hp": 80,
    "block": 0,
    "gold": 99,
    "relics": [{"en": "Burning Blood", "zh": "燃烧之血"}],
    "potions": [],
    "deck_size": 10
  },
  "draw_pile_count": 5,
  "discard_pile_count": 0
}
```

## Architecture

```
Your Code (Python/JS/LLM/anything)
    │  JSON stdin/stdout
    ▼
Sts2Headless (C# .NET)
    │  Uses RunSimulator.cs for game lifecycle
    ▼
sts2.dll (game engine, IL-patched for headless)
    +  GodotStubs (GodotSharp.dll replacement)
    +  Harmony patches (localization fallbacks)
```

The game engine runs real STS2 game logic — all damage calculations, card effects, enemy AI, relic triggers, and RNG are identical to the actual game. The only differences:

- No rendering/audio (GodotStubs provides no-op implementations)
- `Task.Yield()` patched for synchronous execution
- Localization uses fallback keys (no PCK decryption at runtime)

## Game Data

Bilingual localization data extracted from the game:

- `localization_eng/` — 45 tables, English
- `localization_zhs/` — 45 tables, Simplified Chinese

## Prerequisites

- ARM64 .NET 9+ SDK at `~/.dotnet-arm64/`
- Game DLLs in `lib/` (from Steam installation of STS2)
- Python 3.9+ (for play.py)

## Characters

| Character | EN | ZH | Starting HP | Starting Relic |
|---|---|---|---|---|
| Ironclad | The Ironclad | 铁甲战士 | 80 | Burning Blood (燃烧之血) |
| Silent | The Silent | 沉默猎手 | 70 | Ring of the Snake (蛇戒) |
| Defect | The Defect | 故障机器人 | 75 | Cracked Core (破碎核心) |
| Regent | The Regent | 摄政王 | 75 | Royal Decree (皇家法令) |

## Map Structure

The game has 4 Acts, each with 13-15 floors + boss:

| Act | EN | ZH | Floors |
|---|---|---|---|
| 1 | Overgrowth | 密林 | 15 + Boss |
| 2 | Hive | 巢穴 | 14 + Boss |
| 3 | Underdocks | 暗港 | 15 + Boss |
| 4 | Glory | 荣耀 | 13 + Boss |
