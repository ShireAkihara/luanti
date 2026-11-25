#!/usr/bin/env python3
"""LuantiCraft - Fase 1: rebranding Android (idempotent, aman diulang).

Disesuaikan dengan struktur Luanti 5.18.0:
  - android/app/build.gradle  (applicationId, versi, ABI splits, pengemasan aset)
  - res/values*/strings.xml   (nama aplikasi)
  - src/defaultsettings.cpp   (game default)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROPS = ROOT / "luanticraft.properties"
warnings = []


def load_props(path: Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def wr(p: Path, s: str):
    p.write_bytes(s.encode("utf-8"))


def backup(p: Path):
    b = p.with_name(p.name + ".orig")
    if not b.exists():
        b.write_bytes(p.read_bytes())


def ok(msg):
    print(f"[ OK ] {msg}")


def warn(msg):
    print(f"[WARN] {msg}")
    warnings.append(msg)


def save_if_changed(p: Path, old: str, new: str, label: str):
    if new != old:
        backup(p)
        wr(p, new)
        ok(f"{label}: diubah ({p.relative_to(ROOT).as_posix()})")
    else:
        ok(f"{label}: sudah sesuai")


# ------------------------------------------------------------ android/app/build.gradle
def patch_app_gradle(abis):
    p = ROOT / "android" / "app" / "build.gradle"
    if not p.exists():
        warn("android/app/build.gradle tidak ditemukan")
        return
    s = rd(p)
    old = s
    nl = "\r\n" if "\r\n" in s else "\n"

    # 1) Loader properti (sekali, sebelum blok `android {`)
    if "LUANTICRAFT-BEGIN" not in s:
        block = nl.join([
            "// LUANTICRAFT-BEGIN (dikelola oleh tools/luanticraft/apply_branding.py)",
            "def lcProps = new Properties()",
            'file("${rootDir}/../luanticraft.properties").withInputStream { lcProps.load(it) }',
            "// LUANTICRAFT-END",
            "",
        ])
        m = re.search(r"(?m)^android\s*\{", s)
        if not m:
            warn("Blok `android {` tidak ditemukan; patch app/build.gradle dibatalkan")
            return
        s = s[:m.start()] + block + s[m.start():]

    # 2) applicationId / versionName / versionCode
    s, n = re.subn(r"(?m)^(\s*)applicationId(?:\s*=\s*|\s+)[^\r\n]+",
                   r"\1applicationId lcProps.getProperty('app.applicationId')", s)
    if n == 0:
        warn("Baris applicationId tidak ditemukan")
    s, n = re.subn(r"(?m)^(\s*)versionName(?:\s*=\s*|\s+)[^\r\n]+",
                   r"\1versionName lcProps.getProperty('app.versionName')", s)
    if n == 0:
        warn("Baris versionName tidak ditemukan")
    s, n = re.subn(r"(?m)^(\s*)versionCode(?:\s*=\s*|\s+)[^\r\n]+",
                   r"\1versionCode lcProps.getProperty('app.versionCode').toInteger()", s)
    if n == 0:
        warn("Baris versionCode tidak ditemukan")

    # 3) ABI pada blok splits { abi { include ... } }
    quoted = ", ".join(f"'{a}'" for a in abis)
    s, n = re.subn(r"(?m)^(\s*)include\s+'(?:armeabi-v7a|arm64-v8a|x86|x86_64)'[^\r\n]*",
                   rf"\1include {quoted}", s)
    if n == 0:
        warn("Baris `include 'armeabi-v7a', ...` (splits.abi) tidak ditemukan")

    # 4) Sematkan base game ke assets.zip (prepareAssets tidak menyalin games/)
    if "LUANTICRAFT-GAME" not in s:
        m = re.search(r'(?m)^([ \t]*)file\("\$\{assetsFolder\}/\.nomedia"\)', s)
        if not m:
            warn("Titik sisip di prepareAssets tidak ditemukan; base game BELUM dikemas")
        else:
            ind = m.group(1)
            gid = "${lcProps.getProperty('basegame.id')}"
            lines = [
                f"{ind}// LUANTICRAFT-GAME: sematkan base game ke APK",
                f"{ind}copy {{",
                f'{ind}        from "${{projRoot}}/games/{gid}" into "${{assetsFolder}}/games/{gid}"',
                f"{ind}}}",
                "",
            ]
            s = s[:m.start()] + nl.join(lines) + s[m.start():]

    save_if_changed(p, old, s, "app/build.gradle")
    if re.search(r"(?m)^\s*namespace\s", s):
        ok("namespace/package Java sengaja DIBIARKAN (dibutuhkan oleh JNI)")


# ------------------------------------------------------------ native/build.gradle
def patch_native_abis(abis):
    p = ROOT / "android" / "native" / "build.gradle"
    if not p.exists():
        warn("android/native/build.gradle tidak ditemukan")
        return
    s = rd(p)
    quoted = ", ".join(f"'{a}'" for a in abis)
    new, n = re.subn(r"(?m)^(\s*)include\s+'(?:armeabi-v7a|arm64-v8a|x86|x86_64)'[^\r\n]*",
                     rf"\1include {quoted}", s)
    if n:
        save_if_changed(p, s, new, "native/build.gradle (ABI)")
    else:
        warn("Baris `include 'armeabi-v7a', ...` tidak ditemukan di native/build.gradle")


# ------------------------------------------------------------ strings.xml
def patch_strings(name):
    res = ROOT / "android" / "app" / "src" / "main" / "res"
    patched = False
    for p in sorted(res.glob("values*/strings.xml")):
        s = rd(p)
        new, n = re.subn(
            r'(<string\s+name="(?:label|app_name)"[^>]*>)[^<]*(</string>)',
            rf"\g<1>{name}\g<2>", s)
        if n:
            save_if_changed(p, s, new, f"nama aplikasi [{p.parent.name}]")
            patched = True
    if not patched:
        warn('<string name="label"> tidak ditemukan di res/values*/strings.xml')


# ------------------------------------------------------------ default game
def patch_default_game(game_id):
    """Opsional. Luanti 5.18 tidak punya setting default_game; pemain memilih
    game dari menu. Hanya diubah jika setting-nya memang ada."""
    p = ROOT / "src" / "defaultsettings.cpp"
    if not p.exists():
        return
    s = rd(p)
    new, n = re.subn(r'(setDefault\(\s*"(?:default_game|menu_last_game)"\s*,\s*")[^"]*(")',
                     rf"\g<1>{game_id}\g<2>", s)
    if n:
        save_if_changed(p, s, new, f"game default = {game_id}")
    else:
        print("[INFO] Tidak ada setting game default di defaultsettings.cpp "
              "(normal di 5.18); pilih Mineclonia dari menu saat pertama jalan.")


def patch_gitignore():
    p = ROOT / ".gitignore"
    s = rd(p) if p.exists() else ""
    if "*.orig" not in s.split("\n"):
        wr(p, s.rstrip("\r\n") + "\n*.orig\n")
        ok(".gitignore diperbarui (*.orig)")


def main() -> int:
    if not PROPS.exists():
        print(f"[ERR ] {PROPS} tidak ditemukan", file=sys.stderr)
        return 1
    props = load_props(PROPS)
    abis = [a.strip() for a in props["android.abis"].split(",") if a.strip()]

    patch_app_gradle(abis)
    patch_native_abis(abis)
    patch_strings(props["app.name"])
    patch_default_game(props["basegame.id"])
    patch_gitignore()

    print()
    if warnings:
        print(f"Selesai dengan {len(warnings)} peringatan. Tempel seluruh output ini ke chat.")
    else:
        print("Selesai tanpa peringatan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
