# CelestJux Front Shop

**Nine AI coding agents, working, in a 16-bit office you can walk around.**

→ **[celest-front-shop.mojavedev.sh](https://celest-front-shop.mojavedev.sh/)**

Every desk in this room belongs to a real Claude Code or Codex session. When one
of them fires a tool call, that agent's monitor lights up and a bubble over their
head says what they're doing — `read`, `edit`, `build`. When the house goes quiet
they give up on their desks and drift to the couch. Open the page and you walk in
as a visitor; press Enter next to someone and they'll tell you what they're
actually working on. If anyone else has the page open, you'll see them walking
around too.

It is not a dashboard. It's a *place* — and the difference is the whole project.

---

## What you're looking at

| | |
|---|---|
| **The room** | 30×22 tiles, four pods of desks, a walled pantry, a lounge, and a butler's room in the corner you can only see by going to look. |
| **The agents** | Nine named seats. Eight have desks; one is a field agent whose chair is empty on purpose, and one is the butler, who has no desk at all. |
| **The whiteboard** | The house's running token and tool-call totals, read from the agents' own transcripts. |
| **The right wall** | A column of light through the server racks. Its brightness and pulse rate are the mean load across everyone present — a quiet house is a quiet server, never a dead one. |
| **You** | A body, a name, and a text box. Arrows or WASD; Enter to talk. |

The **desks are a published snapshot** and the **visitors are live**. The page
says which is which in the hint line, every time, because a room that quietly
implies more than it knows is worse than one that says less.

---

## How it works

```
Claude Code PostToolUse hook  →  POST /event  →  in-memory ring  →  the room
     (arena_hook.sh)              (server.py)      (500 entries)     (index.html)
```

- **`tools/arena_hook.sh`** is a `PostToolUse` hook — one line in a
  `~/.claude/settings.json`. That's the entire install. **No daemon, no agent, no
  sidecar.**
- **`server.py`** is stdlib-only Python. It serves the page, takes tool events,
  keeps a chat ring, and answers the visitor position relay. `requirements.txt` is
  deliberately empty, so a cold start installs nothing.
- **`tools/publish_arena.py`** freezes the room into `data/arena.json` and pushes
  it, so the public page has something honest to show when it isn't wired to a
  live house.

---

## The decisions worth reading

Most of the work in here wasn't drawing. It was the small number of places where
the obvious implementation is quietly wrong.

**A `PostToolUse` hook runs *inside* somebody else's tool call.** Block, hang, or
print to stdout and you have broken a stranger's editor. So the hook is
backgrounded, `timeout 3`, `curl -m 2`, everything swallowed, and it exits `0`
unconditionally — including when the server is dead. Measured against nothing
listening: **28ms, exit 0.** That number is the feature; the JSON is the easy part.

**The payload doesn't say which seat you are.** A hook is handed `tool_name`,
`tool_input`, `tool_response`, `session_id` and `cwd` — nothing that identifies
the agent. Guessing from `cwd` works in exactly one house. So the seat name is an
*argument*, the user names their own agents, and a seat nobody in the room answers
to is dropped rather than guessed at. A tool call on the wrong desk is worse than
no tool call.

**One probe had to become three flags.** The page used to ask a single question —
"is a server answering?" — and infer everything from the answer. That was fine
while the only server in the world was the one at home. But a *hosted* server also
answers, and the old logic would have concluded the room was live, switched on the
idle-animation ticker, and published **invented tool calls under real people's
names** to the open internet. Now `MODE` (are the desks live or a recording),
`RELAY` (is anyone answering for presence) and `SIMULATE` (may this page invent
anything — never when hosted) are separate, because the desks being a recording
and the people being live are both true at once and only three flags can say so.

**The server's word is a position, not a move.** Positions land 5×/second and the
screen draws 60, so a body placed straight onto the number teleports in visible
steps. Each visitor has a *drawn* position chasing its *reported* one, and the
chase — not the packet — animates the legs. Walking is also derived from the chase,
so a stale "still moving" flag can never march someone on the spot.

**Two timeouts guarding the same fact is one timeout too many.** A server-side TTL
and a client-side grace period ran in series, so a closed laptop stood in the room
for eighteen seconds. The server already decides who is present; the client number
is only a cushion for a couple of dropped fetches.

**Everyone spawned on the same tile.** With one visitor that's a spawn point. With
two it's one body hiding another, and the whole feature reads as broken. The fix
needed floor that is standable *and* has nothing drawing over it — and the second
half is the trap, because an object sorts at `y + 0.9`, so a bench a whole row
above still paints over someone standing in the lane.

**A slide that never wedges is worse than a wedge.** Agents walk with the same
hitbox the player uses, sliding along a desk face instead of through it, with a
four-second bail so nobody freezes. But an agent oscillating along a sofa back
*moves every frame* — so the bail never fires and it stands there all night looking
like a crowd. Every seat now carries its own approach waypoints. The tell in a
state dump was `stuckFor: 0` on a body that hadn't changed tile in a minute.

**The number was already computed one layer below.** The token board doesn't sum
transcripts itself; it imports a calculator that already knew the two hard things —
where each agent's transcripts live, and that one of the nine isn't Claude Code at
all but Codex, in a different format entirely. A reader written from scratch would
have reported a confident house total with the single largest agent silently
missing.

**Deploying needed one file.** Without a `mojave.json` the host builds this as a
static site: the page loads, the house is there, and every visitor is alone
forever because the relay 404s. With it, one process serves the page *and* answers
the relay from one origin — which is also what dissolves the mixed-content wall
that killed an earlier plan to host the page and the relay separately.

---

## Running your own

```bash
python3 server.py            # stdlib only; serves the page and the relay
```

Then point an agent at it by adding one entry to `~/.claude/settings.json`:

```json
{ "hooks": { "PostToolUse": [ { "matcher": "*", "hooks": [
    { "type": "command", "command": "/path/to/tools/arena_hook.sh celeste http://your-host:8960" }
] } ] } }
```

The name you pass is the desk that lights up. Names the room doesn't recognise are
ignored.

---

## Building the art yourself

**The art is not in this repo, and that is deliberate.** The tileset is LimeZu's
and its licence allows using and editing it in a project but forbids distributing
it — so what ships here is the *pipeline*, not the pixels. Buy the pack (it costs
about the same as a coffee), run two commands, and you get byte-identical art to
what's on screen.

Pack: **[LimeZu — Modern Interiors](https://limezu.itch.io/moderninteriors)**
(complete v4.1.4). What's in the download, and what this project uses:

| File | Used here |
|---|---|
| `moderninteriors-win.zip` | ✅ **This is the one.** The complete pack — interiors, animated objects, and the character generator layers. Everything below is cut from it. |
| `Character Generator 2.0 Linux Build.zip` / `Character Generator 2.0 Setup.exe` | LimeZu's own GUI character maker. Not needed — `compose_character.py` composes from the raw layers instead, so characters are reproducible from code rather than clicked by hand. |
| `Modern_Interiors_RPG_Maker_Version.zip` | RPG Maker export. Not used. |
| `Modern_Interiors_Free_v2.2x.zip` | The free subset. Not enough for this room. |

Then:

```bash
export MODERN_INTERIORS=/path/to/modern-interiors-full   # where you unpacked it
export MODERN_EXTERIORS=/path/to/modern-exteriors-full   # for the lake, outside
python3 tools/cut_room_tiles.py     # floors and wall bands  -> sprites/room-tiles.png
python3 tools/cut_objects.py        # furniture atlas        -> sprites/objects.png + .json
python3 tools/cut_lake_tiles.py     # grass + animated water -> sprites/lake-tiles.png
python3 tools/compose_character.py  # a cast member          -> sprites/<name>-sheet.png
```

Run any of them without that variable set and they stop and tell you why, rather
than half-building against a path that isn't there.

The office is cut from **Modern Interiors**; the lake through the side door is cut
from **Modern Exteriors**, a second pack by the same artist on the same 16px grid.
Exteriors ships every prop pre-cut as its own PNG, so `cut_objects.py` names the
file rather than hunting a row and column.

`cut_objects.py` is the record of every prop in the room — re-run it to rebuild the
atlas after adding one. `sprites/handmade/` is ours: a mop, a broom and a wall
clock, hand-drawn at 16px in the pack's own palette, because after banding every
row of every sheet at 5× it turned out none of the three exist anywhere in it.

**Making your own room?** Fork it, buy the pack, and go. If you get stuck on the
art pipeline or want to compare notes, open an issue — happy to help.

---

## Credits

Art is **LimeZu — "Modern Interiors"** and **"Modern Exteriors"**, licensed, credit
required; see [`sprites/CREDITS.md`](sprites/CREDITS.md). Characters are composed from
the pack's own layers (body → eyes → outfit → hair → accessory) by
`tools/compose_character.py`, with a hue-and-saturation pass that deliberately skips
near-greys — recolour those too and a garment flattens into a blob.

The mop, the broom and the wall clock are hand-drawn, because they genuinely do not
exist anywhere in the pack. Both were confirmed missing by banding every row at 5×,
not by assuming.

Built by Juxtapo & Celeste.
