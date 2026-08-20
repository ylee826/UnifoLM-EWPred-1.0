#!/usr/bin/env python3
"""Build the static-site manifest from high-quality open-loop video results.

The source directory must contain ``individual_views/<layout>__<task>__episode_<id>/``
directories.  Ego samples provide left-wrist, main, and right-wrist videos; external
samples provide main-view videos.  Every sample must contain matching ``gt_*.mp4``
and ``pred_*.mp4`` files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from collections import defaultdict
from pathlib import Path


CATEGORY_SPECS = {
    "tabletop_ego": {
        "layout": "eptabletop_ego",
        "label": "Ego: Table-top Manipulation",
        "label_zh": "自我视角：桌面操作",
        "description": "Tabletop manipulation with egocentric multi-view observations.",
        "views": ("left_wrist", "main", "right_wrist"),
    },
    "wholebody_ego": {
        "layout": "epwbt_ego",
        "label": "Ego: Whole-Body Manipulation",
        "label_zh": "自我视角：全身操作",
        "description": "Whole-body mobile manipulation with egocentric multi-view observations.",
        "views": ("left_wrist", "main", "right_wrist"),
    },
    "tabletop_external": {
        "layout": "eptabletop_ext",
        "label": "External: Table-top Manipulation",
        "label_zh": "外部视角：桌面操作",
        "description": "Tabletop manipulation from external observation.",
        "views": ("main",),
    },
    "wholebody_external": {
        "layout": "epwbt_ext",
        "label": "External: Whole-Body Manipulation",
        "label_zh": "外部视角：全身操作",
        "description": "Whole-body mobile manipulation from external observation.",
        "views": ("main",),
    },
}

SAMPLE_NAME = re.compile(
    r"^(?:g1_ar_)?(eptabletop_ego|eptabletop_ext|epwbt_ego|epwbt_ext|"
    r"tabletop_ego|tabletop_ext|wbt_ego|wbt_ext)__(.+?)__episode_(\d+)(?:_.*)?$"
)
CATEGORY_FOR_LAYOUT = {
    # Current result exports use the public layout names, with a g1_ar_ prefix
    # and generator metadata after the episode number.
    "eptabletop_ego": "tabletop_ego",
    "eptabletop_ext": "tabletop_external",
    "epwbt_ego": "wholebody_ego",
    "epwbt_ext": "wholebody_external",
    # Older exports are retained for reproducible rebuilds.
    "tabletop_ego": "tabletop_ego",
    "tabletop_ext": "tabletop_external",
    "wbt_ego": "wholebody_ego",
    "wbt_ext": "wholebody_external",
}
CANONICAL_LAYOUT_FOR_CATEGORY = {
    "tabletop_ego": "tabletop_ego",
    "tabletop_external": "tabletop_ext",
    "wholebody_ego": "wbt_ego",
    "wholebody_external": "wbt_ext",
}
TITLE_OVERRIDES = {"spell_unitree": "Arrange Letter Blocks to Spell Robot"}
EXCLUDED_TASKS = {
    "pick_out_battery",
    "kitchen_organization",
    # Keep only one representative for each user-facing whole-body task.
    "make_bed_brainco_2",
    "pick_up_clothes_brainco",
    "pick_up_drinks_inspire",
}

# Different data sources may assign separate task IDs to the same user-facing
# instruction.  The featured 2×4 grid is curated by instruction, not dataset ID.
FEATURED_TASK_GROUPS = {
    "adjust_sickbed_brainco": "adjust_sickbed",
    "data_make_the_bed_brainco": "make_bed",
    "make_bed_brainco_2": "make_bed",
    "data_pick_clothes_inspire": "put_clothes_in_laundry",
    "pick_up_clothes_brainco": "put_clothes_in_laundry",
    "pick_up_drinks_inspire": "pick_up_drinks",
    "pick_up_fruit_brainco": "place_fruit_on_plate",
    "livingroom_place_fruits": "place_fruit_on_plate",
}

# Curated alternate sample for the featured 2×4 grid only.  The task's regular
# section still retains its full pair of external-view samples.
FEATURED_SAMPLE_OVERRIDES = {
    "organize_stationery": "tabletop_ext__organize_stationery__episode_000155",
}

# Chosen alternate examples for single-sample section cards.
REPRESENTATIVE_SAMPLE_OVERRIDES = {
    ("tabletop_ego", "store_earphones"): "tabletop_ego__store_earphones__episode_000438",
}


def title_for(task: str) -> str:
    return TITLE_OVERRIDES.get(task, task.replace("_", " ").title())


def featured_group_for(task: str) -> str:
    return FEATURED_TASK_GROUPS.get(task, task)


def sample_entry(sample_dir: Path, site_root: Path) -> tuple[str, dict]:
    match = SAMPLE_NAME.match(sample_dir.name)
    if not match:
        raise ValueError(f"Unexpected sample-directory name: {sample_dir.name}")
    source_layout, task, episode_number = match.groups()
    category = CATEGORY_FOR_LAYOUT[source_layout]
    spec = CATEGORY_SPECS[category]
    canonical_id = (
        f"{CANONICAL_LAYOUT_FOR_CATEGORY[category]}__{task}__episode_{episode_number}"
    )
    relative_dir = sample_dir.relative_to(site_root).as_posix()
    views = {}
    for view in spec["views"]:
        # External-camera exports use ``raw`` in their filenames; the existing
        # site presents that stream as its main view.
        source_view = "raw" if view == "main" and category.endswith("external") else view
        gt = sample_dir / f"gt_{source_view}.mp4"
        pred = sample_dir / f"pred_{source_view}.mp4"
        if not gt.is_file() or not pred.is_file():
            raise ValueError(f"{sample_dir}: missing GT or prediction for view '{view}'")
        views[view] = {
            "gt": f"videos/{relative_dir}/gt_{source_view}.mp4",
            "gen": f"videos/{relative_dir}/pred_{source_view}.mp4",
        }
    entry = {
        # Keep a stable ID across old and new generator directory schemes so
        # curated sample choices remain valid after a full video replacement.
        "id": canonical_id,
        "layout": spec["layout"],
        "category": category,
        "categoryLabel": spec["label"],
        "task": task,
        "title": title_for(task),
        "episode": f"episode_{episode_number}",
        "base": canonical_id,
        "viewMode": "all" if len(spec["views"]) > 1 else "main",
        "trimFrontHalf": False,
        "trimStartSeconds": None,
        "views": views,
    }
    return category, entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Directory containing individual_views/")
    parser.add_argument("site", type=Path, help="Website repository root")
    args = parser.parse_args()
    source = args.source.resolve()
    site = args.site.resolve()
    input_root = source / "individual_views"
    video_root = site / "videos"
    if not input_root.is_dir():
        raise SystemExit(f"Missing input directory: {input_root}")

    groups: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    sample_dirs = sorted(path for path in input_root.iterdir() if path.is_dir())
    if not sample_dirs:
        raise SystemExit(f"No sample directories found in {input_root}")
    for sample_dir in sample_dirs:
        category, entry = sample_entry(sample_dir, input_root)
        if entry["task"] in EXCLUDED_TASKS:
            continue
        groups[category].append((sample_dir, entry))

    selected_groups: dict[str, list[tuple[Path, dict]]] = {}
    for key, entries in groups.items():
        ordered = sorted(entries, key=lambda pair: (pair[1]["task"], pair[1]["episode"]))
        if key == "tabletop_external":
            # The external tabletop section compares two examples of each task.
            selected_groups[key] = ordered
            continue
        # Other sections use a single representative episode per task.
        seen_tasks = set()
        selected_groups[key] = []
        for sample_dir, entry in ordered:
            preferred_sample = REPRESENTATIVE_SAMPLE_OVERRIDES.get((key, entry["task"]))
            if preferred_sample and entry["id"] != preferred_sample:
                continue
            if entry["task"] in seen_tasks:
                continue
            seen_tasks.add(entry["task"])
            selected_groups[key].append((sample_dir, entry))

    # Assemble assets in a separate directory first.  Renaming directories is
    # reliable on the shared filesystem and prevents a partially deleted public
    # ``videos/`` directory if an interrupted build is rerun.
    staging_root = site / "videos.next"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir()
    for entries in selected_groups.values():
        for sample_dir, _ in entries:
            shutil.copytree(sample_dir, staging_root / sample_dir.name)

    categories = []
    all_entries = []
    for key, spec in CATEGORY_SPECS.items():
        tasks = [entry for _, entry in selected_groups[key]]
        all_entries.extend(tasks)
        categories.append(
            {
                "key": key,
                "layout": spec["layout"],
                "label": spec["label"],
                "label_zh": spec["label_zh"],
                "description": spec["description"],
                "tasks": tasks,
            }
        )

    # Keep the existing 24-card featured carousel, but do not show a task more
    # than once there.  The same task may exist in ego and external datasets;
    # those remain browseable in their respective sections, just not duplicated
    # in the 2×4 featured grid.
    featured = []
    featured_tasks = set()
    for category in categories:
        selected = 0
        for task in category["tasks"]:
            preferred_sample = FEATURED_SAMPLE_OVERRIDES.get(task["task"])
            if preferred_sample and task["id"] != preferred_sample:
                continue
            task_group = featured_group_for(task["task"])
            if task_group in featured_tasks:
                continue
            featured.append(task)
            featured_tasks.add(task_group)
            selected += 1
            if selected == 6:
                break
    manifest = {
        "source": "videos",
        "summary": {
            "episodes": len(all_entries),
            "tasks": len({entry["task"] for entry in all_entries}),
            "previewPoolItems": 0,
            "previewItems": 0,
            "featuredItems": len(featured),
        },
        "featured": featured,
        "categories": categories,
    }
    (site / "manifest.js").write_text(
        "window.WORLD_PRED_DATA = " + json.dumps(manifest, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )

    if video_root.exists():
        previous_root = site / f"videos.previous-{datetime.now():%Y%m%d-%H%M%S}"
        video_root.rename(previous_root)
    staging_root.rename(video_root)
    print(
        f"Built {len(all_entries)} samples / {manifest['summary']['tasks']} tasks "
        f"and copied assets to {video_root}"
    )


if __name__ == "__main__":
    main()
