"""Add finished Kai episodes to the cloud queue: write queue/NNN_EP.json from the episode's Posting-Kit.md,
upload final.mp4 to the "queue" release as NNN_EP.mp4, then commit + push.

Usage (from this folder): python -X utf8 enqueue.py JV1-what-is-jev JV2-jev-vs-llm ...   (in posting order)
Numbering continues after the highest number in queue/ or posted/.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
EPISODES = HERE.parent / "Kai-influencer" / "episodes"


def field(kit, label, section):
    sec = kit.split(section, 1)[1]
    m = re.search(r"\*\*" + label + r":\*\*\s*`([^`\n]+)`", sec)
    b = re.search(r"\*\*" + label + r":\*\*\s*\n```[a-z]*\n(.*?)\n```", sec, re.S)
    hits = [x for x in (m, b) if x]
    if not hits:
        raise ValueError(f"{label} not found in {section}")
    return min(hits, key=lambda x: x.start()).group(1).strip()


def main(names):
    nums = [int(f.name[:3]) for d in ("queue", "posted") for f in (HERE / d).glob("*.json") if f.name[:3].isdigit()]
    n = max(nums, default=0)
    for name in names:
        ep = EPISODES / name
        kit = (ep / "Posting-Kit.md").read_text(encoding="utf-8")
        meta = {"episode": name,
                "ig_caption": field(kit, "Caption", "## Instagram Reel"),
                "yt_title": field(kit, "Title", "## YouTube Short"),
                "yt_description": field(kit, "Description", "## YouTube Short"),
                "yt_tags": [t.strip() for t in field(kit, "Tags", "## YouTube Short").split(",") if t.strip()]}
        c = re.search(r"\*\*Comment from Kai[^\n]*\n```[a-z]*\n(.*?)\n```", kit, re.S)
        if c:   # the kit's comment should end with a reason to follow (next part / series)
            meta["first_comment"] = c.group(1).strip()
        n += 1
        stem = f"{n:03d}_{name.split('-')[0]}"
        (HERE / "queue" / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp = Path(tempfile.gettempdir()) / f"{stem}.mp4"   # the asset is named after the file
        shutil.copy2(ep / "final.mp4", tmp)
        subprocess.run(["gh", "release", "upload", "queue", str(tmp), "--clobber"], check=True, cwd=HERE)
        tmp.unlink()
        print("queued", stem)
    subprocess.run(["git", "add", "queue"], check=True, cwd=HERE)
    subprocess.run(["git", "commit", "-m", f"Queue {', '.join(names)}"], check=True, cwd=HERE)
    subprocess.run(["git", "push"], check=True, cwd=HERE)


if __name__ == "__main__":
    main(sys.argv[1:])
