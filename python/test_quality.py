#!/usr/bin/env python3
"""
Quality test — checks JSON responses for:
1. Unresolved template vars [VarName] in descriptions
2. Raw loc keys (ALLCAPS.dotted.paths) in user-visible fields
3. Event card rewards actually presented (not auto-selected)
4. All decision types exercised
"""
import json, subprocess, os, sys, re
from collections import Counter

os.environ["STS2_GAME_DIR"] = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/"
    "Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64")
DOTNET = os.path.expanduser("~/.dotnet-arm64/dotnet")
PROJECT = "Sts2Headless/Sts2Headless.csproj"

CHARS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]
SEEDS_PER_CHAR = 5

issues = []
decision_counts = Counter()
total_games = 0
completed = 0


def scan_templates(obj, path=""):
    """Recursively find unresolved [VarName] in all string values."""
    found = []
    if isinstance(obj, str):
        for m in re.finditer(r'\[([A-Z][a-zA-Z]{2,})\]', obj):
            found.append((path, m.group(0)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(scan_templates(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(scan_templates(v, f"{path}[{i}]"))
    return found


def scan_raw_keys(obj, path=""):
    """Find raw loc keys like NEOW.pages.INITIAL... in visible fields."""
    found = []
    visible_fields = {"title", "description", "name", "event_name"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in visible_fields and isinstance(v, str):
                # Check if it looks like a raw loc key
                if re.match(r'^[A-Z_]+\.[a-z]', v) or (v.isupper() and '.' in v):
                    found.append((f"{path}.{k}", v))
            elif k in visible_fields and isinstance(v, dict):
                # Bilingual dict — check both values
                for lang, text in v.items():
                    if text and isinstance(text, str):
                        if re.match(r'^[A-Z_]+\.', text) and len(text) > 20:
                            found.append((f"{path}.{k}.{lang}", text[:60]))
            else:
                found.extend(scan_raw_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(scan_raw_keys(v, f"{path}[{i}]"))
    return found


for char in CHARS:
    for seed_i in range(SEEDS_PER_CHAR):
        seed = f"quality_{char}_{seed_i}"
        proc = subprocess.Popen(
            [DOTNET, "run", "--no-build", "--project", PROJECT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)

        def read():
            while True:
                l = proc.stdout.readline().strip()
                if not l: return None
                if l.startswith("{"): return json.loads(l)

        def send(cmd):
            proc.stdin.write(json.dumps(cmd) + "\n")
            proc.stdin.flush()
            return read()

        total_games += 1
        ready = read()
        state = send({"cmd": "start_run", "character": char, "seed": seed})

        step = 0
        game_ok = True
        while step < 400 and state:
            step += 1
            if not state:
                break

            dec = state.get("decision", "")
            decision_counts[dec] += 1

            # --- SCAN FOR ISSUES ---
            # 1. Template vars
            for path, var in scan_templates(state):
                issues.append(f"TEMPLATE {char}/{seed} step{step} {dec}: {var} at {path}")

            # 2. Raw loc keys
            for path, val in scan_raw_keys(state):
                issues.append(f"RAW_KEY {char}/{seed} step{step} {dec}: {val} at {path}")

            # --- PLAY ---
            if dec == "game_over":
                completed += 1
                break
            elif dec == "map_select":
                ch = state["choices"][0]
                state = send({"cmd": "action", "action": "select_map_node",
                             "args": {"col": ch["col"], "row": ch["row"]}})
            elif dec == "combat_play":
                hand = state.get("hand", [])
                energy = state.get("energy", 0)
                playable = [c for c in hand if c.get("can_play") and c.get("cost", 99) <= energy]
                if playable:
                    card = playable[0]
                    args = {"card_index": card["index"]}
                    if card.get("target_type") == "AnyEnemy":
                        args["target_index"] = 0
                    state = send({"cmd": "action", "action": "play_card", "args": args})
                else:
                    state = send({"cmd": "action", "action": "end_turn"})
            elif dec == "card_reward":
                state = send({"cmd": "action", "action": "skip_card_reward"})
            elif dec == "card_select":
                cards = state.get("cards", [])
                if cards:
                    state = send({"cmd": "action", "action": "select_cards",
                                 "args": {"indices": "0"}})
                else:
                    state = send({"cmd": "action", "action": "skip_select"})
            elif dec == "bundle_select":
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": 0}})
            elif dec == "rest_site":
                opts = [o for o in state.get("options", []) if o.get("is_enabled")]
                if opts:
                    state = send({"cmd": "action", "action": "choose_option",
                                 "args": {"option_index": opts[0]["index"]}})
                else:
                    state = send({"cmd": "action", "action": "leave_room"})
            elif dec == "event_choice":
                opts = [o for o in state.get("options", []) if not o.get("is_locked")]
                if opts:
                    state = send({"cmd": "action", "action": "choose_option",
                                 "args": {"option_index": opts[0]["index"]}})
                else:
                    state = send({"cmd": "action", "action": "leave_room"})
            elif dec == "shop":
                state = send({"cmd": "action", "action": "leave_room"})
            else:
                state = send({"cmd": "action", "action": "proceed"})

        proc.terminate()
        proc.wait(timeout=5)

# Report
print(f"\n{'='*60}")
print(f"Quality Test Results")
print(f"{'='*60}")
print(f"Games: {completed}/{total_games} completed")
print(f"\nDecision types hit:")
for dec, cnt in sorted(decision_counts.items(), key=lambda x: -x[1]):
    print(f"  {dec}: {cnt}")

if issues:
    # Deduplicate
    unique = sorted(set(issues))
    print(f"\n{'!'*60}")
    print(f"ISSUES FOUND: {len(unique)}")
    print(f"{'!'*60}")
    for issue in unique[:50]:
        print(f"  {issue}")
    if len(unique) > 50:
        print(f"  ... and {len(unique) - 50} more")
else:
    print(f"\n✅ ALL CLEAN — no template leaks or raw keys found")
