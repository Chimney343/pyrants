"""One-off script: match catalog.json against cards_OCR.json, inject flavor text."""

import json
import shutil
from pathlib import Path


def load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_ocr_index(ocr_path: Path) -> dict[str, str | None]:
    ocr = load_json(ocr_path)
    index: dict[str, str | None] = {}
    for set_block in ocr:
        for card in set_block["cards"]:
            key = card["name"].strip().lower()
            index[key] = card.get("flavor")
    return index


def enrich() -> None:
    base = Path("data/cards")
    catalog_path = base / "catalog.json"
    ocr_path = base / "cards_OCR.json"
    superseded_dir = base / "superseded"

    catalog = load_json(catalog_path)
    flavor_index = build_ocr_index(ocr_path)

    matched = 0
    missing = 0
    for card in catalog["cards"]:
        key = card["name"].strip().lower()
        flavor = flavor_index.get(key)
        card["flavor"] = flavor
        if flavor:
            matched += 1
        else:
            missing += 1

    superseded_dir.mkdir(exist_ok=True)
    backup_path = superseded_dir / "superseded_catalog.json"
    shutil.copy2(catalog_path, backup_path)
    catalog_path.unlink()
    save_json(catalog_path, catalog)

    print(f"Backed up to {backup_path}")
    print(f"Enriched: {matched} matched, {missing} no flavor found")


if __name__ == "__main__":
    enrich()
