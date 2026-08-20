#!/usr/bin/env python3
"""Create a handoff package for every video rendered by the project website.

The package is organized by the five visible site sections and includes a CSV
mapping for editors.  Files are hard-linked from ``videos/`` so construction is
fast and the homepage previews do not duplicate media already used below.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path


SECTIONS = {
    "featured": ("01_首页_2x4精选", "首页 2×4 精选", "Homepage 2×4 Featured"),
    "tabletop_ego": ("02_第一视角_桌面操作", "第一视角：桌面操作", "Ego: Table-top Manipulation"),
    "wholebody_ego": ("03_第一视角_全身操作", "第一视角：全身操作", "Ego: Whole-Body Manipulation"),
    "tabletop_external": ("04_第三视角_桌面操作", "第三视角：桌面操作", "External: Table-top Manipulation"),
    "wholebody_external": ("05_第三视角_全身操作", "第三视角：全身操作", "External: Whole-Body Manipulation"),
}
VIEW_LABELS = {
    "left_wrist": ("左腕视角", "Left Wrist"),
    "main": ("主视角", "Main Camera"),
    "right_wrist": ("右腕视角", "Right Wrist"),
}
TYPE_LABELS = {"gen": ("预测", "Prediction"), "gt": ("真值", "Ground Truth")}
FILE_TYPE_LABELS = {"gen": "PREDICTION_预测", "gt": "GROUND_TRUTH_真值"}
FILE_VIEW_LABELS = {
    "left_wrist": "LEFT_WRIST_左腕视角",
    "main": "MAIN_CAMERA_主视角",
    "right_wrist": "RIGHT_WRIST_右腕视角",
}


def parse_task_labels(index: Path, language: str) -> dict[str, str]:
    text = index.read_text(encoding="utf-8")
    section = text.split(f"      {language}: {{", 1)[1]
    task_block = section.split("        taskLabels: {", 1)[1].split("\n        }\n      }", 1)[0]
    labels = {}
    for match in re.finditer(r'(?:"([^"]+)"|([A-Za-z0-9_]+)):\s*"([^"]+)"', task_block):
        labels[match.group(1) or match.group(2)] = match.group(3)
    return labels


def load_manifest(site: Path) -> dict:
    text = (site / "manifest.js").read_text(encoding="utf-8")
    return json.loads(text.removeprefix("window.WORLD_PRED_DATA = ").removesuffix(";\n"))


def link_media(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.hardlink_to(source)
    except OSError:
        shutil.copy2(source, target)


def add_row(rows: list[dict[str, str]], **row: str) -> None:
    rows.append({key: str(value) for key, value in row.items()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path, help="Website repository root")
    parser.add_argument("output", type=Path, help="New output directory")
    args = parser.parse_args()
    site = args.site.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Output path already exists: {output}")

    manifest = load_manifest(site)
    en_labels = parse_task_labels(site / "index.html", "en")
    zh_labels = parse_task_labels(site / "index.html", "zh")
    rows: list[dict[str, str]] = []
    output.mkdir(parents=True)

    def task_labels(entry: dict) -> tuple[str, str]:
        return zh_labels.get(entry["task"], entry["title"]), en_labels.get(entry["task"], entry["title"])

    # The homepage plays prediction/main only.  Each row records exactly where
    # that same media appears again in the relevant detailed section.
    featured_dir, featured_zh, featured_en = SECTIONS["featured"]
    for card_no, entry in enumerate(manifest["featured"], 1):
        title_zh, title_en = task_labels(entry)
        source_relative = entry["views"]["main"]["gen"]
        source = site / source_relative
        name = (
            f"{card_no:02d}_{entry['task']}__{entry['episode']}__"
            "PREDICTION_预测__MAIN_CAMERA_主视角.mp4"
        )
        target = output / featured_dir / name
        link_media(source, target)
        detailed_dir = SECTIONS[entry["category"]][0]
        add_row(
            rows,
            section_order="01",
            section_zh=featured_zh,
            section_en=featured_en,
            card=f"精选卡 {card_no:02d}",
            task_id=entry["task"],
            task_zh=title_zh,
            task_en=title_en,
            episode=entry["episode"],
            sample_id=entry["id"],
            view_zh="主视角",
            view_en="Main Camera",
            content_zh="预测",
            content_en="Prediction",
            role="首页自动播放预览；同一文件也在详细板块中出现",
            package_file=target.relative_to(output).as_posix(),
            corresponding_detail=f"{detailed_dir}（任务 {entry['task']}，{entry['episode']}）",
            source_file=source_relative,
        )

    for category in manifest["categories"]:
        category_key = category["key"]
        section_dir, section_zh, section_en = SECTIONS[category_key]
        by_task: dict[str, list[dict]] = defaultdict(list)
        for entry in category["tasks"]:
            by_task[entry["task"]].append(entry)
        card_no = 0
        for task_id, entries in by_task.items():
            for entry in entries:
                card_no += 1
                title_zh, title_en = task_labels(entry)
                item_dir = output / section_dir / f"{card_no:02d}_{task_id}__{entry['episode']}"
                for view, paths in entry["views"].items():
                    view_zh, view_en = VIEW_LABELS[view]
                    for media_type in ("gen", "gt"):
                        content_zh, content_en = TYPE_LABELS[media_type]
                        source_relative = paths[media_type]
                        source = site / source_relative
                        target = item_dir / (
                            f"{FILE_TYPE_LABELS[media_type]}__{FILE_VIEW_LABELS[view]}.mp4"
                        )
                        link_media(source, target)
                        add_row(
                            rows,
                            section_order=section_dir[:2],
                            section_zh=section_zh,
                            section_en=section_en,
                            card=f"任务卡 {card_no:02d}",
                            task_id=task_id,
                            task_zh=title_zh,
                            task_en=title_en,
                            episode=entry["episode"],
                            sample_id=entry["id"],
                            view_zh=view_zh,
                            view_en=view_en,
                            content_zh=content_zh,
                            content_en=content_en,
                            role="详细板块中的对比视频",
                            package_file=target.relative_to(output).as_posix(),
                            corresponding_detail="",
                            source_file=source_relative,
                        )

    fields = list(rows[0])
    with (output / "视频对应表.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    readme = f"""# UnifoLM-WorldPred-1 宣传视频素材包

本包按网站的五个可见板块整理，适合直接交给剪辑同学。`视频对应表.csv` 是逐文件映射表，包含任务中英文、episode、视角、预测/真值和来源。

## 目录说明

1. `01_首页_2x4精选`：首页每张精选卡实际自动播放的预测主视角，共 {len(manifest['featured'])} 条。它们是下方详细板块素材的复用，不是额外任务。
2. `02_第一视角_桌面操作`：每个任务均含预测与真值的左腕、主、右腕三视角。
3. `03_第一视角_全身操作`：每个任务均含预测与真值的左腕、主、右腕三视角。
4. `04_第三视角_桌面操作`：每个任务有两条 episode；每条均含预测与真值主视角。
5. `05_第三视角_全身操作`：每个任务一条 episode；每条均含预测与真值主视角。

## 文件命名（剪辑用）

- `PREDICTION_预测`：模型预测（Prediction）
- `GROUND_TRUTH_真值`：真实视频（Ground Truth）
- `LEFT_WRIST_左腕视角` / `MAIN_CAMERA_主视角` / `RIGHT_WRIST_右腕视角`：对应视角
- 每个目录中的任务 ID 和 episode 与 `视频对应表.csv` 一一对应。

总计：{len(rows)} 个网站展示媒体文件映射（其中首页 {len(manifest['featured'])} 个为详细板块的复用预览）。
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    print(f"Created {output} with {len(rows)} mapped media files.")


if __name__ == "__main__":
    main()
