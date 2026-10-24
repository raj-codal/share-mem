#!/usr/bin/env python3
"""Sync Claude Code memory files with a Confluence space.

push: upload changed memory files as code-block pages under <root>/<author>/.
pull: download every other author's pages into <memory>/team/<author>/.

Config is read from ~/.config/share-mem/env (KEY=VALUE lines), then the
environment. Never commit that file.
"""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "share-mem" / "env"
STATE_FILE = Path.home() / ".config" / "share-mem" / "state.json"
ROOT_TITLE = "share-mem"

# Patterns that must never leave the machine. Match is fatal unless --force.
SECRET_PATTERNS = [
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    r"\bgithub_pat_[A-Za-z0-9_]{40,}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\bsk-[A-Za-z0-9_-]{20,}\b",
    r"\bsk[A-Za-z0-9]{40,}\b",  # Sanity tokens
    r"\bATATT3[A-Za-z0-9_=-]{20,}",  # Atlassian API tokens
    r"\bAIza[0-9A-Za-z_-]{35}\b",
    r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b",  # JWT
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{12,}",
    r"(?i)\bbearer\s+[A-Za-z0-9_\-.=]{20,}",
    r"(?i)DOTENV_PRIVATE_KEY\w*\s*=\s*[0-9a-f]{20,}",
]


def load_config():
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    cfg = {k: os.environ.get(k) for k in ("SHARE_MEM_SITE", "SHARE_MEM_EMAIL", "SHARE_MEM_TOKEN", "SHARE_MEM_SPACE")}
    cfg["SHARE_MEM_AUTHOR"] = os.environ.get("SHARE_MEM_AUTHOR") or (cfg["SHARE_MEM_EMAIL"] or "").split("@")[0]
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        sys.exit(f"missing config: {', '.join(missing)} (see {CONFIG_FILE})")
    return cfg


class Confluence:
    def __init__(self, cfg):
        self.base = f"https://{cfg['SHARE_MEM_SITE']}/wiki/rest/api"
        self.space = cfg["SHARE_MEM_SPACE"]
        auth = b64encode(f"{cfg['SHARE_MEM_EMAIL']}:{cfg['SHARE_MEM_TOKEN']}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json", "Accept": "application/json"}

    def req(self, method, path, body=None, params=None):
        url = self.base + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method, headers=self.headers)
        try:
            with urllib.request.urlopen(r) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")

    def find(self, title, parent_id=None):
        res = self.req("GET", "/content", params={"spaceKey": self.space, "title": title, "expand": "version,ancestors", "limit": 25})
        for p in res.get("results", []):
            if parent_id is None or (p["ancestors"] and p["ancestors"][-1]["id"] == parent_id):
                return p
        return None

    def upsert(self, title, storage, parent_id=None):
        page = self.find(title, parent_id)
        body = {"type": "page", "title": title, "space": {"key": self.space}, "body": {"storage": {"value": storage, "representation": "storage"}}}
        if parent_id:
            body["ancestors"] = [{"id": parent_id}]
        if page:
            body["version"] = {"number": page["version"]["number"] + 1, "minorEdit": True}
            return self.req("PUT", f"/content/{page['id']}", body)
        return self.req("POST", "/content", body)

    def children(self, page_id, expand=""):
        out, start = [], 0
        while True:
            res = self.req("GET", f"/content/{page_id}/child/page", params={"limit": 100, "start": start, "expand": expand})
            out += res.get("results", [])
            if "next" not in res.get("_links", {}):
                return out
            start += 100


def to_storage(text):
    safe = text.replace("]]>", "]]]]><![CDATA[>")
    return ('<ac:structured-macro ac:name="code" ac:schema-version="1">'
            '<ac:parameter ac:name="language">markdown</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{safe}]]></ac:plain-text-body></ac:structured-macro>")


def from_storage(storage):
    return "".join(re.findall(r"<!\[CDATA\[(.*?)\]\]>", storage, re.S))


def scan_secrets(path, text):
    hits = [p for p in SECRET_PATTERNS if re.search(p, text)]
    return [f"{path}: matches {p}" for p in hits]


def memory_files(mem):
    for p in sorted(mem.glob("*.md")):
        if p.name != "MEMORY.md":
            yield p


def push(mem, cfg, force=False):
    files = list(memory_files(mem))
    problems = [h for p in files for h in scan_secrets(p.name, p.read_text())]
    if problems and not force:
        sys.exit("refusing to push, possible secrets:\n  " + "\n  ".join(problems))
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    api = Confluence(cfg)
    root = api.find(ROOT_TITLE) or api.upsert(ROOT_TITLE, "<p>Shared Claude Code memories. One child page per author.</p>")
    author_title = f"{ROOT_TITLE}/{cfg['SHARE_MEM_AUTHOR']}"
    author = api.find(author_title, root["id"]) or api.upsert(author_title, f"<p>Memories of {cfg['SHARE_MEM_AUTHOR']}.</p>", root["id"])
    pushed = 0
    for p in files:
        text = p.read_text()
        digest = hashlib.sha256(text.encode()).hexdigest()
        if state.get(p.name) == digest:
            continue
        api.upsert(f"{author_title}/{p.stem}", to_storage(text), author["id"])
        state[p.name] = digest
        pushed += 1
        print(f"pushed {p.name}")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1))
    print(f"done: {pushed} pushed, {len(files) - pushed} unchanged")


def pull(mem, cfg):
    api = Confluence(cfg)
    root = api.find(ROOT_TITLE)
    if not root:
        sys.exit("no share-mem root page in space yet; someone must push first")
    team = mem / "team"
    index = []
    for author_page in api.children(root["id"]):
        author = author_page["title"].split("/", 1)[-1]
        if author == cfg["SHARE_MEM_AUTHOR"]:
            continue
        out = team / author
        out.mkdir(parents=True, exist_ok=True)
        seen = set()
        for page in api.children(author_page["id"], expand="body.storage"):
            slug = page["title"].rsplit("/", 1)[-1]
            text = from_storage(page["body"]["storage"]["value"])
            if not text.strip():
                continue
            (out / f"{slug}.md").write_text(text)
            seen.add(f"{slug}.md")
            m = re.search(r"^description:\s*(.+)$", text, re.M)
            index.append(f"- [{author}: {slug}]({author}/{slug}.md) — {m.group(1).strip() if m else ''}")
        for stale in out.glob("*.md"):
            if stale.name not in seen:
                stale.unlink()
    team.mkdir(exist_ok=True)
    (team / "INDEX.md").write_text("# Team memories (pulled from Confluence, read-only)\n\n" + "\n".join(index) + "\n")
    memory_md = mem / "MEMORY.md"
    pointer = "- [Team memories](team/INDEX.md) — pulled from Confluence by share-mem"
    if memory_md.exists() and pointer not in memory_md.read_text():
        memory_md.write_text(memory_md.read_text().rstrip("\n") + "\n\n" + pointer + "\n")
    elif not memory_md.exists():
        memory_md.write_text(pointer + "\n")
    print(f"done: {len(index)} team memories in {team}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 2 or args[0] not in ("push", "pull"):
        sys.exit("usage: share_mem.py push|pull <memory-dir> [--force]")
    mem = Path(args[1]).expanduser().resolve()
    if not mem.is_dir():
        sys.exit(f"not a directory: {mem}")
    cfg = load_config()
    (push if args[0] == "push" else pull)(mem, cfg, **({"force": "--force" in flags} if args[0] == "push" else {}))


if __name__ == "__main__":
    main()
