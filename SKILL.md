---
name: share-mem
description: Share Claude Code memory files with teammates through a Confluence space. Use when the user says "push memory", "pull memory", "sync memory", "share memory", "what does <teammate> know about X", or wants team knowledge from other people's Claude sessions.
---

# share-mem

Memory files are the unit of sharing, never transcripts. Each teammate pushes their own
`memory/*.md` files to Confluence as one page per file under `share-mem/<author>/`.
Everyone pulls the others' pages into `memory/team/<author>/` where normal recall finds them.

Scripts do all the work. Do not use the Atlassian MCP for this; it burns tokens on page JSON.

## Commands

Memory dir is the current project's memory directory shown in the system prompt
(`~/.claude/projects/<project>/memory/`).

Push own memories (scans for secrets first, aborts on any hit):

```bash
python3 <skill-dir>/scripts/share_mem.py push <memory-dir>
```

Pull everyone else's memories into `<memory-dir>/team/` and refresh `team/INDEX.md`:

```bash
python3 <skill-dir>/scripts/share_mem.py pull <memory-dir>
```

## Rules

- Run pull at the start of a task that touches shared tickets or other people's areas.
- Run push at the end of a session in which you wrote or changed memory files.
- If push refuses because of a possible secret, remove the value from the memory file.
  Never pass `--force` without the user saying so for that specific hit.
- `team/` is read-only. Never edit or push files under it; they belong to another author.
- When answering from a team memory, say whose it is, e.g. "Tom's notes say ...".

## Setup (once per machine)

Create `~/.config/share-mem/env` with:

```
SHARE_MEM_SITE=yoursite.atlassian.net
SHARE_MEM_EMAIL=you@company.com
SHARE_MEM_TOKEN=<Atlassian API token from id.atlassian.com/manage-profile/security/api-tokens>
SHARE_MEM_SPACE=<Confluence space key>
SHARE_MEM_AUTHOR=<short name, defaults to the email local part>
```

Access control is the Confluence space's own permissions.
