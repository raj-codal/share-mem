# share-mem

A Claude Code skill that shares memory files between teammates through a Confluence space.

Each person's Claude keeps one-fact memory files. This skill pushes them to Confluence as
code-block pages under `share-mem/<author>/` and pulls everyone else's into
`memory/team/<author>/`, so every Claude on the team recalls what the others learned.
Transcripts are never shared, only the distilled memory files.

## Install

```bash
git clone https://github.com/raj-codal/share-mem ~/.claude/skills/share-mem
cp ~/.claude/skills/share-mem/env.example ~/.config/share-mem/env
```

Fill in `~/.config/share-mem/env`: Atlassian site, email, an API token, and the space key.
The space's permissions decide who can read and write.

## Use

Tell Claude "push memory" or "pull memory", or run the script directly:

```bash
python3 ~/.claude/skills/share-mem/scripts/share_mem.py push ~/.claude/projects/<project>/memory
python3 ~/.claude/skills/share-mem/scripts/share_mem.py pull ~/.claude/projects/<project>/memory
```

Push uploads only files that changed since the last push and refuses to run if any file
looks like it contains a key, token, or password. Pull is idempotent and removes team files
whose pages were deleted.

## Layout in Confluence

```
share-mem                 root page
  share-mem/raj           one page per author
    share-mem/raj/<slug>  one page per memory file, body is a markdown code block
```

Python 3 standard library only, no dependencies.
