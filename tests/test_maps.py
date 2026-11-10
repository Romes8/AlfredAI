import json
import zipfile

from alfred.agent.permissions import PermissionPolicy
from alfred.config import load_config
from alfred.connectors import load_connectors
from alfred.places import import_places, search_places
from alfred.setup_google import MAPS_BLOCK, add_block

SAVED_PLACES = {"type": "FeatureCollection", "features": [
    {"geometry": {"type": "Point", "coordinates": [12.4922, 41.8902]},
     "properties": {"date": "2025-05-01T10:00:00Z", "google_maps_url": "http://maps.google.com/?cid=1",
                    "location": {"address": "Piazza del Colosseo, 1, Roma", "name": "Colosseum", "country_code": "IT"}}},
    {"geometry": {"type": "Point", "coordinates": [0, 0]},
     "properties": {"Title": "Old style place", "Location": {"Business Name": "Mikkeller Bar",
                                                             "Address": "Viktoriagade 8, Copenhagen"}}},
]}
LABELED = {"type": "FeatureCollection", "features": [
    {"geometry": {"coordinates": [12.56, 55.67]}, "properties": {"name": "Home", "address": "Example St 1, 2100 Kbh"}}]}
ROME_CSV = "Title,Note,URL,Tags,Comment\nRoscioli,Best carbonara,https://maps.google.com/?cid=2,,\nTrevi Fountain,,https://maps.google.com/?cid=3,,\n"


def make_takeout(tmp_path):
    z = tmp_path / "takeout.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Takeout/Maps (your places)/Saved Places.json", json.dumps(SAVED_PLACES))
        f.writestr("Takeout/Maps/My labeled places/Labeled places.json", json.dumps(LABELED))
        f.writestr("Takeout/Saved/Rome trip.csv", "﻿" + ROME_CSV)
        f.writestr("Takeout/Maps/Reviews.json", json.dumps({"something": "else"}))
    return z


def test_import_and_search(tmp_path):
    dest = tmp_path / "places.json"
    assert import_places(make_takeout(tmp_path), dest) == 5
    everything = search_places(path=dest)
    assert everything["total_saved"] == 5
    assert set(everything["lists"]) == {"Starred / saved", "Labeled (home, work...)", "Rome trip"}
    assert search_places("carbonara", path=dest)["places"][0]["name"] == "Roscioli"
    assert search_places("", "rome", path=dest)["matches"] == 2
    home = search_places("home", path=dest)["places"][0]
    assert home["address"].startswith("Example St") and home["lat"] == 55.67
    assert search_places("mikkeller", path=dest)["places"][0]["address"].startswith("Viktoriagade")


def test_no_places_yet(tmp_path):
    assert "Takeout" in search_places(path=tmp_path / "nope.json")["message"]


def test_google_maps_links_open_without_a_tap(tmp_path):
    p = PermissionPolicy(load_config(tmp_path / "none.yaml"))
    ok = "https://www.google.com/maps/dir/?api=1&destination=Tivoli%20Gardens&travelmode=bicycling"
    assert p.decide("mcp__alfred__open_url", {"url": ok}).action == "allow"
    assert p.decide("mcp__alfred__open_url", {"url": "https://maps.app.goo.gl/abc"}).action == "allow"
    assert p.decide("mcp__alfred__open_url", {"url": "https://google.com.evil.example/maps/x"}).action == "ask"


def test_maps_connector_is_read_only_with_route_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "AIza" + "x" * 35)
    f = tmp_path / "config.yaml"
    f.write_text("connectors: {}\n", encoding="utf-8")
    assert add_block(f, "google_maps", MAPS_BLOCK) == "added to config.yaml"
    assert add_block(f, "google_maps", MAPS_BLOCK) == "already in config.yaml"
    cfg = load_config(f)
    conn = {c.name: c for c in load_connectors(cfg)}["google_maps"]
    assert conn.server["headers"]["X-Goog-Api-Key"].startswith("AIza")
    p = PermissionPolicy(cfg)
    for t in ["search_places", "lookup_weather", "compute_routes", "resolve_names"]:
        assert p.decide(f"mcp__google_maps__{t}", {}).action == "allow", t
    assert p.decide("mcp__google_maps__create_something", {}).action == "deny"


def test_brevity_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.yaml")
    from alfred.persona import system_prompt

    assert cfg["style"]["max_spoken_sentences"] == 2 and "BE BRIEF" in system_prompt(cfg)


def test_lookalike_google_domains_still_ask(tmp_path):
    p = PermissionPolicy(load_config(tmp_path / "none.yaml"))
    for bad in ["https://google.com.evil.example/maps/x", "https://www.google.evil/maps/", "https://evil.com/google.com/maps",
                "http://www.google.com/maps/dir/?api=1&destination=x", "https://maps.google.com.evil.io/"]:
        assert p.decide("mcp__alfred__open_url", {"url": bad}).action == "ask", bad
    for good in ["https://www.google.dk/maps/search/?api=1&query=Nyhavn", "https://www.google.co.uk/maps/dir/?api=1",
                 "https://maps.google.com/?q=x"]:
        assert p.decide("mcp__alfred__open_url", {"url": good}).action == "allow", good
