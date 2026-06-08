"""清理 backend/outputs/ 根目录的散落文件，移入 _legacy/ 目录。"""

import os
import re
import shutil
from pathlib import Path

OUTPUTS = Path(__file__).resolve().parent / "outputs"
LEGACY = OUTPUTS / "_legacy"

# UUID 格式的目录是正规 task 目录，保留
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def main():
    LEGACY.mkdir(exist_ok=True)

    moved = 0
    skipped = 0

    for entry in sorted(OUTPUTS.iterdir()):
        name = entry.name

        # 跳过 gitkeep 和 _legacy 自身
        if name in (".gitkeep", "_legacy", "__clean__"):
            continue

        # 正规 task UUID 目录 — 保留
        if entry.is_dir() and UUID_PATTERN.match(name):
            skipped += 1
            continue

        # 非 UUID 目录 + 所有根级文件 — 移到 _legacy
        dest = LEGACY / name
        if dest.exists():
            # 同名已存在，加时间戳防冲突
            ts = int(entry.stat().st_mtime)
            dest = LEGACY / f"{name}.{ts}"

        try:
            shutil.move(str(entry), str(dest))
            print(f"  ✓ {name} → _legacy/{dest.name}")
            moved += 1
        except (PermissionError, OSError) as e:
            print(f"  ✗ {name}: 跳过 ({e})")
            skipped += 1

    print(f"\n完成：移动 {moved} 个，保留 {skipped} 个正规 task 目录")


if __name__ == "__main__":
    main()
