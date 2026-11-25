#!/usr/bin/env python3
"""LuantiCraft - unduh base game ke games/<id>/ (lintas-platform)."""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROPS = ROOT / "luanticraft.properties"

# File/folder dev yang tidak dibutuhkan di APK
STRIP = [
    ".git", ".gitattributes", ".gitignore", ".woodpecker.yaml", ".luacheckrc",
    ".luarc.json", ".mailmap", "tools", "README_locale",
    "CONTRIBUTING.md", "DEV_TRANSLATION_WORKFLOW.md",
]


def load_props(path: Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def _on_rm_error(func, path, _exc):
    # Windows: file di .git bersifat read-only
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, onerror=_on_rm_error)


def git(*args, cwd=None) -> str:
    res = subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return res.stdout.strip()


def main() -> int:
    if not PROPS.exists():
        print(f"[ERR ] {PROPS} tidak ditemukan", file=sys.stderr)
        return 1
    p = load_props(PROPS)
    game_id, repo, ref = p["basegame.id"], p["basegame.repo"], p["basegame.ref"]

    dest = ROOT / "games" / game_id
    tmp = ROOT / "games" / f".{game_id}.tmp"
    rmtree(tmp)
    tmp.mkdir(parents=True)

    print(f"[INFO] Mengunduh {repo} @ {ref} ...")
    try:
        git("init", "-q", cwd=tmp)
        git("remote", "add", "origin", repo, cwd=tmp)
        git("fetch", "--depth", "1", "origin", ref, cwd=tmp)
        git("checkout", "-q", "FETCH_HEAD", cwd=tmp)
        sha = git("rev-parse", "HEAD", cwd=tmp)
    except subprocess.CalledProcessError as e:
        print(f"[ERR ] git gagal:\n{e.stdout}", file=sys.stderr)
        rmtree(tmp)
        return 1

    for name in STRIP:
        target = tmp / name
        if target.is_dir():
            rmtree(target)
        elif target.exists():
            target.unlink()

    if not (tmp / "game.conf").exists() or not (tmp / "mods").is_dir():
        print("[ERR ] Hasil unduhan bukan game Luanti valid (game.conf/mods hilang)",
              file=sys.stderr)
        rmtree(tmp)
        return 1

    (tmp / ".basegame-ref").write_text(f"{repo}\n{ref}\n{sha}\n", encoding="utf-8")

    rmtree(dest)
    tmp.rename(dest)
    print(f"[ OK ] Base game terpasang di {dest}  (commit {sha[:10]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
