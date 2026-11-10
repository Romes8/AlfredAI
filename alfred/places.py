"""Your saved Google Maps places, imported from a Google Takeout export.

Google has no API for saved places / lists, so: takeout.google.com -> select "Saved" and "Maps (your places)" ->
export -> `alfred import-places <the zip or unzipped folder>`. Alfred keeps a compact copy in ~/.alfred/places.json
and looks things up with the my_places tool (only sent to Claude when he actually searches it).
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterator

PLACES_FILE = Path.home() / ".alfred" / "places.json"


def _get(d: dict, *names: str) -> Any:
    """Case-insensitive key lookup across a few possible names."""
    low = {k.lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return low[n.lower()]
    return None


def _from_feature(f: dict, list_name: str) -> dict | None:
    p = f.get("properties") or {}
    loc = _get(p, "location", "Location") or {}
    name = _get(loc, "name", "business name") or _get(p, "name", "title")
    address = _get(loc, "address") or _get(p, "address")
    url = _get(p, "google_maps_url", "google maps url", "url")
    coords = (f.get("geometry") or {}).get("coordinates")
    if not (name or address):
        return None
    out = {"name": name or address, "list": list_name}
    if address:
        out["address"] = address
    if url:
        out["url"] = url
    note = _get(p, "comment", "note")
    if note:
        out["note"] = note
    if isinstance(coords, list) and len(coords) >= 2 and any(coords[:2]):
        out["lat"], out["lng"] = coords[1], coords[0]
    return out


def _from_csv(text: str, list_name: str) -> Iterator[dict]:
    for row in csv.DictReader(io.StringIO(text)):
        name = _get(row, "title", "name")
        if not name:
            continue
        item = {"name": name.strip(), "list": list_name}
        for key, names in (("url", ("url",)), ("note", ("note", "comment")), ("address", ("address",))):
            v = _get(row, *names)
            if v:
                item[key] = v.strip()
        yield item


def _list_name(path: str) -> str:
    stem = Path(path).stem
    return {"Saved Places": "Starred / saved", "Labeled places": "Labeled (home, work...)"}.get(stem, stem)


def _files(src: Path) -> Iterator[tuple[str, str]]:
    """(relative path, text) of every .json / .csv in a Takeout zip or folder."""
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if n.lower().endswith((".json", ".csv")):
                    yield n, z.read(n).decode("utf-8-sig", errors="replace")
    elif src.is_dir():
        for p in src.rglob("*"):
            if p.suffix.lower() in (".json", ".csv"):
                yield str(p.relative_to(src)), p.read_text(encoding="utf-8-sig", errors="replace")
    elif src.is_file():
        yield src.name, src.read_text(encoding="utf-8-sig", errors="replace")


def parse_takeout(src: Path) -> list[dict]:
    places: list[dict] = []
    for rel, text in _files(src):
        name = _list_name(rel)
        if rel.lower().endswith(".csv") and re.search(r"(^|[/\\])saved([/\\]|$)", rel, re.I):
            places.extend(_from_csv(text, name))
        elif rel.lower().endswith(".json"):
            try:
                data = json.loads(text)
            except ValueError:
                continue
            if isinstance(data, dict) and isinstance(data.get("features"), list):
                places.extend(p for p in (_from_feature(f, name) for f in data["features"]) if p)
    seen, unique = set(), []
    for p in places:
        key = (p["name"].lower(), p.get("address", "").lower(), p["list"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def import_places(src: str | Path, dest: Path = PLACES_FILE) -> int:
    places = parse_takeout(Path(src).expanduser())
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(places)


def load_places(path: Path = PLACES_FILE) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def search_places(query: str = "", list_name: str = "", limit: int = 15, path: Path = PLACES_FILE) -> dict:
    places = load_places(path)
    if not places:
        return {"places": [], "message": "No saved places imported yet - run `alfred import-places` with a Google "
                                         "Takeout export."}
    lists = sorted({p["list"] for p in places})
    hits = places
    if list_name:
        hits = [p for p in hits if list_name.lower() in p["list"].lower()]
    if query:
        words = [w for w in re.split(r"\W+", query.lower()) if w]
        hits = [p for p in hits if all(w in " ".join(str(v) for v in p.values()).lower() for w in words)]
    return {"total_saved": len(places), "lists": lists, "matches": len(hits), "places": hits[:limit]}
