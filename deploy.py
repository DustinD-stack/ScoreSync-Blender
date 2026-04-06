"""
deploy.py  –  ScoreSync deployment helper
==========================================
Copies source files from this workspace to their install locations,
and can build a distributable zip for Blender addon installation.

Usage:
    python deploy.py            # deploy Blender addon + FL script
    python deploy.py --blender  # Blender addon only
    python deploy.py --fl       # FL Studio script only
    python deploy.py --zip      # build ScoreSync_vX.Y.Z.zip (no deploy)
    python deploy.py --dry-run  # show what would be copied, do nothing
"""

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

# Source
BLENDER_ADDON_SRC  = ROOT / "ScoreSync"
FL_SCRIPT_SRC      = ROOT / "device_ScoreSync.py"

# Destinations
BLENDER_ADDON_DST  = (
    Path.home()
    / "AppData/Roaming/Blender Foundation/Blender/4.2/scripts/addons/ScoreSync"
)
FL_SCRIPT_DST = (
    Path.home()
    / "Documents/Image-Line/FL Studio/Settings/Hardware/ScoreSync/device_ScoreSync.py"
)

# Files/dirs to exclude from the zip
_ZIP_EXCLUDE = {"__pycache__", ".pyc", ".pyo", ".DS_Store", "Thumbs.db"}

# Specific files inside the addon folder that are dev-only and not for distribution
_ZIP_EXCLUDE_FILES = {"powershell mirroring.md"}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_version() -> str:
    """Read version tuple from __init__.py without importing it."""
    init = BLENDER_ADDON_SRC / "__init__.py"
    for line in init.read_text(encoding="utf-8").splitlines():
        if '"version"' in line and "(" in line:
            # e.g.   "version": (0, 8, 0),
            import re
            m = re.search(r"\((\d+),\s*(\d+),\s*(\d+)\)", line)
            if m:
                return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "0.0.0"


def _should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in _ZIP_EXCLUDE:
            return True
    if path.name in _ZIP_EXCLUDE_FILES:
        return True
    return any(path.name.endswith(ext) for ext in _ZIP_EXCLUDE if ext.startswith("."))


def deploy_blender(dry: bool) -> bool:
    print("\n[Blender addon]")
    print(f"  src : {BLENDER_ADDON_SRC}")
    print(f"  dst : {BLENDER_ADDON_DST}")
    if not BLENDER_ADDON_SRC.exists():
        print("  ERROR: source folder not found")
        return False
    if not dry:
        if BLENDER_ADDON_DST.exists():
            shutil.rmtree(BLENDER_ADDON_DST)
        shutil.copytree(
            BLENDER_ADDON_SRC, BLENDER_ADDON_DST,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        print("  copied OK")
    else:
        print("  [dry-run] would copy")
    return True


def deploy_fl(dry: bool) -> bool:
    print("\n[FL Studio script]")
    print(f"  src : {FL_SCRIPT_SRC}")
    print(f"  dst : {FL_SCRIPT_DST}")
    if not FL_SCRIPT_SRC.exists():
        print("  ERROR: source file not found")
        return False
    if not dry:
        FL_SCRIPT_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FL_SCRIPT_SRC, FL_SCRIPT_DST)
        print("  copied OK")
    else:
        print("  [dry-run] would copy")
    return True


def build_zip(dry: bool) -> bool:
    version = _get_version()
    zip_name = f"ScoreSync_v{version}.zip"
    zip_path = ROOT / zip_name

    print(f"\n[Build zip]  {zip_path}")
    if not BLENDER_ADDON_SRC.exists():
        print("  ERROR: ScoreSync/ folder not found")
        return False

    if dry:
        # Just list what would go in
        count = 0
        for f in sorted(BLENDER_ADDON_SRC.rglob("*")):
            if f.is_file() and not _should_exclude(f):
                rel = f.relative_to(ROOT)
                print(f"  [dry-run] would add: ScoreSync/{rel.relative_to('ScoreSync')}")
                count += 1
        print(f"  [dry-run] {count} files -> {zip_name}")
        return True

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        count = 0
        for f in sorted(BLENDER_ADDON_SRC.rglob("*")):
            if f.is_file() and not _should_exclude(f):
                # Archive path: ScoreSync/<relative path inside addon>
                arcname = Path("ScoreSync") / f.relative_to(BLENDER_ADDON_SRC)
                zf.write(f, arcname)
                count += 1

    print(f"  {count} files -> {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    return True


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deploy ScoreSync to Blender and FL Studio, or build a release zip."
    )
    parser.add_argument("--blender", action="store_true", help="Deploy Blender addon only")
    parser.add_argument("--fl",      action="store_true", help="Deploy FL Studio script only")
    parser.add_argument("--zip",     action="store_true", help="Build distributable zip only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    dry = args.dry_run

    if args.zip:
        ok = build_zip(dry)
        sys.exit(0 if ok else 1)

    do_blender = args.blender or not (args.blender or args.fl)
    do_fl      = args.fl      or not (args.blender or args.fl)

    ok = True
    if do_blender:
        ok &= deploy_blender(dry)
    if do_fl:
        ok &= deploy_fl(dry)

    if not dry:
        print("\nReminder: reload the addon in Blender (disable then enable) and restart FL Studio.")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
