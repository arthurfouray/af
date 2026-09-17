#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import dataclasses
import gzip
import importlib.util
import json
import math
import os
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

UPSTREAM_ROOT = Path(os.environ.get("UPSTREAM_ROOT", "upstream_artifact")).resolve()
INPUT_B64 = Path(os.environ.get("INPUT_B64", "data/nytft_final_candidates.csv.gz.b64")).resolve()
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "nytft_final_verification")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_GEOCODES = int(os.environ.get("MAX_GEOCODES", "0"))  # 0 = no limit

PUBLIC_HEADER = [
    "Name", "Address", "Latitude and longitude", "Guide", "Category",
    "Description", "Source URL", "Priority", "Year", "Google Maps URL",
]


def load_crawler():
    candidates = list(UPSTREAM_ROOT.rglob("crawler.py"))
    if not candidates:
        raise FileNotFoundError(f"crawler.py not found below {UPSTREAM_ROOT}")
    path = sorted(candidates, key=lambda p: ("nytft_runner" not in str(p), len(str(p))))[0]
    spec = importlib.util.spec_from_file_location("nytft_upstream_crawler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load crawler module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, path


C, CRAWLER_PATH = load_crawler()


def decode_input() -> list[dict[str, str]]:
    raw = base64.b64decode(INPUT_B64.read_bytes())
    csv_bytes = gzip.decompress(raw)
    decoded_path = OUTPUT_DIR / "decoded_final_candidates_input.csv"
    decoded_path.write_bytes(csv_bytes)
    with decoded_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def coords_valid(lat: Any, lon: Any) -> bool:
    try:
        latf, lonf = float(lat), float(lon)
        return -90 <= latf <= 90 and -180 <= lonf <= 180
    except Exception:
        return False


def coords_region_ok(lat: Any, lon: Any, hint: str) -> bool:
    if not coords_valid(lat, lon):
        return False
    latf, lonf = float(lat), float(lon)
    if "Pocantico" in hint:
        return 40.85 <= latf <= 41.20 and -74.15 <= lonf <= -73.65
    # New York City and immediate inner metro; prevents Chicago and other branch substitutions.
    return 40.45 <= latf <= 41.05 and -74.35 <= lonf <= -73.55


def full_postal(address: str) -> bool:
    return bool(
        re.search(r"\b\d{5}(?:-\d{4})?\b", address or "")
        and re.search(r"\b(?:United States|USA|U\.S\.)\b", address or "", re.I)
    )


def normalize_full_address(address: str) -> str:
    address = C.country_complete_address(clean(address))
    address = re.sub(r"\s+,", ",", address)
    address = re.sub(r",\s*,+", ", ", address)
    return address.strip(" ,")


def map_search_url(name: str, address: str) -> str:
    query = f"{name}, {address}"
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query, safe="")


def source_address_agrees(source: str, full: str) -> tuple[bool, float, str]:
    try:
        return C.address_similarity(source, full)
    except Exception as exc:
        return False, 0.0, f"address comparison error: {type(exc).__name__}"


def best_identity_place(name: str, source_address: str, hint: str, places: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    best = None
    best_score = -1.0
    best_reason = ""
    for p in places[:15]:
        ns = C.name_similarity(name, p.get("name", ""))
        ok, addr_score, addr_reason = source_address_agrees(source_address, p.get("address", ""))
        region = coords_region_ok(p.get("latitude"), p.get("longitude"), hint)
        score = 1.35 * ns + (1.0 if ok else 0.45 * addr_score) + (0.25 if region else -1.0)
        if score > best_score:
            best, best_score = p, score
            best_reason = f"name={ns:.3f}; address={addr_score:.3f} ({addr_reason}); region={region}"
    if best is None:
        return None, "no Google Maps candidates"
    ns = C.name_similarity(name, best.get("name", ""))
    addr_ok, _, addr_reason = source_address_agrees(source_address, best.get("address", ""))
    if not coords_region_ok(best.get("latitude"), best.get("longitude"), hint):
        return None, f"geographic conflict; {best_reason}"
    if ns < 0.62:
        return None, f"identity conflict; {best_reason}"
    if not addr_ok:
        return None, f"address conflict ({addr_reason}); {best_reason}"
    return best, best_reason


def best_address_place(source_address: str, hint: str, places: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    best = None
    best_score = -1.0
    best_reason = ""
    for p in places[:20]:
        ok, score, reason = source_address_agrees(source_address, p.get("address", ""))
        region = coords_region_ok(p.get("latitude"), p.get("longitude"), hint)
        total = (1.0 if ok else score) + (0.3 if region else -1.0)
        if total > best_score:
            best, best_score = p, total
            best_reason = f"address={score:.3f} ({reason}); region={region}"
    if best is None:
        return None, "no address-only Google Maps candidates"
    addr_ok, _, reason = source_address_agrees(source_address, best.get("address", ""))
    if not addr_ok or not coords_region_ok(best.get("latitude"), best.get("longitude"), hint):
        return None, f"address-only conflict ({reason}); {best_reason}"
    return best, best_reason


def official_check(url: str, address: str, existing: str) -> str:
    if existing:
        return existing
    if not url:
        return "not available"
    try:
        fn = getattr(C, "official_site_check", None)
        if callable(fn):
            return fn(url, address)
    except Exception as exc:
        return f"official site check error: {type(exc).__name__}"
    return "official website supplied by Google Maps; no automated page check available"


def verify_one(row: dict[str, str], geocode_index: int) -> dict[str, Any]:
    name = clean(row["Name"])
    source_address = clean(row["Source Address"])
    hint = clean(row.get("Location Hint")) or "New York, NY, United States"
    result: dict[str, Any] = dict(row)
    result.update({
        "Decision": "excluded",
        "Verification Method": "",
        "Verification Basis": "",
        "Verified Name": name,
        "Verified Full Address": "",
        "Latitude": "",
        "Longitude": "",
        "Google Maps URL": "",
        "Google Result Name": "",
        "Google Result Address": "",
        "Google Categories": row.get("Original Google Categories", ""),
        "Official Website": row.get("Original Official Website", ""),
        "Official Website Check": row.get("Original Official Website Check", ""),
        "Maps URL Check": "",
        "Exclusion Reason": "",
    })

    if row.get("Source Status") not in {"200", 200, ""}:
        result["Exclusion Reason"] = f"source URL did not resolve successfully in the crawl (status {row.get('Source Status')})"
        return result
    if not name or not source_address:
        result["Exclusion Reason"] = "missing source venue name or source street address"
        return result

    # Preserve upstream exact-address/coordinate verification after source-name repair.
    if row.get("Reuse Approved") == "yes":
        full = normalize_full_address(row.get("Existing Full Address", ""))
        lat, lon = row.get("Existing Latitude", ""), row.get("Existing Longitude", "")
        agree, _, reason = source_address_agrees(source_address, full)
        if agree and full_postal(full) and coords_region_ok(lat, lon, hint):
            result.update({
                "Decision": "published",
                "Verification Method": "reused-exact-source-address-google-result",
                "Verification Basis": row.get("Reuse Basis") or reason,
                "Verified Full Address": full,
                "Latitude": float(lat),
                "Longitude": float(lon),
                "Google Maps URL": map_search_url(name, full),
                "Maps URL Check": "derived from successful upstream Google Maps verification",
                "Official Website Check": row.get("Original Official Website Check") or "not available",
            })
            return result

    if MAX_GEOCODES and geocode_index > MAX_GEOCODES:
        result["Exclusion Reason"] = "bounded verification limit reached"
        return result

    query_address = f"{source_address}, {hint}"
    lookup = C.google_maps_lookup(name, query_address)
    result["Identity Query"] = lookup.get("query", "")
    identity_place, identity_reason = best_identity_place(name, source_address, hint, lookup.get("places", []))
    if identity_place:
        full = normalize_full_address(identity_place.get("address", ""))
        if full_postal(full):
            official_url = identity_place.get("website", "") or row.get("Original Official Website", "")
            result.update({
                "Decision": "published",
                "Verification Method": "google-place-identity-and-address-match",
                "Verification Basis": identity_reason,
                "Verified Full Address": full,
                "Latitude": float(identity_place["latitude"]),
                "Longitude": float(identity_place["longitude"]),
                "Google Maps URL": identity_place.get("maps_url", "") or map_search_url(name, full),
                "Google Result Name": identity_place.get("name", ""),
                "Google Result Address": identity_place.get("address", ""),
                "Google Categories": " | ".join(identity_place.get("categories", [])),
                "Official Website": official_url,
                "Official Website Check": official_check(official_url, full, row.get("Original Official Website Check", "")),
                "Maps URL Check": "successful Google Maps identity/address query",
            })
            return result

    # Historical/closed venues often no longer have a place entity. Geocode the exact
    # source-published address, retain the source identity, and use an exact Maps search URL.
    address_lookup = C.google_maps_lookup("", query_address)
    result["Address Query"] = address_lookup.get("query", "")
    address_place, address_reason = best_address_place(source_address, hint, address_lookup.get("places", []))
    if address_place:
        full = normalize_full_address(address_place.get("address", ""))
        if full_postal(full):
            result.update({
                "Decision": "published",
                "Verification Method": "historical-source-identity-plus-google-address-geocode",
                "Verification Basis": f"source identity; {address_reason}; identity query: {identity_reason}",
                "Verified Full Address": full,
                "Latitude": float(address_place["latitude"]),
                "Longitude": float(address_place["longitude"]),
                "Google Maps URL": map_search_url(name, full),
                "Google Result Name": address_place.get("name", ""),
                "Google Result Address": address_place.get("address", ""),
                "Google Categories": " | ".join(address_place.get("categories", [])),
                "Official Website": row.get("Original Official Website", ""),
                "Official Website Check": row.get("Original Official Website Check") or "not available for historical/closed venue",
                "Maps URL Check": "successful exact-address Google Maps query; exact venue/address search URL generated",
            })
            return result

    # Last source-supported fallback: reverse-check an exact auxiliary coordinate, then
    # require the returned street address to agree with the source.
    alat, alon = row.get("Auxiliary Latitude", ""), row.get("Auxiliary Longitude", "")
    if coords_region_ok(alat, alon, hint):
        coord_lookup = C.google_maps_lookup("", f"{alat}, {alon}")
        result["Coordinate Query"] = coord_lookup.get("query", "")
        coord_place, coord_reason = best_address_place(source_address, hint, coord_lookup.get("places", []))
        if coord_place:
            full = normalize_full_address(coord_place.get("address", ""))
            if full_postal(full):
                result.update({
                    "Decision": "published",
                    "Verification Method": "source-identity-plus-auxiliary-coordinate-google-reverse-check",
                    "Verification Basis": coord_reason,
                    "Verified Full Address": full,
                    "Latitude": float(coord_place["latitude"]),
                    "Longitude": float(coord_place["longitude"]),
                    "Google Maps URL": map_search_url(name, full),
                    "Google Result Name": coord_place.get("name", ""),
                    "Google Result Address": coord_place.get("address", ""),
                    "Google Categories": " | ".join(coord_place.get("categories", [])),
                    "Official Website": row.get("Original Official Website", ""),
                    "Official Website Check": row.get("Original Official Website Check") or "not available",
                    "Maps URL Check": "successful Google Maps coordinate/address query",
                })
                return result

    result["Exclusion Reason"] = (
        f"no geographically consistent Google Maps identity or exact-address result; "
        f"identity={identity_reason}; address={address_reason}"
    )
    return result


def main() -> int:
    rows = decode_input()
    results: list[dict[str, Any]] = []
    geocode_index = 0
    for i, row in enumerate(rows, 1):
        if row.get("Reuse Approved") != "yes":
            geocode_index += 1
        result = verify_one(row, geocode_index)
        results.append(result)
        if i % 50 == 0 or i == len(rows):
            print(f"verified {i}/{len(rows)}; published={sum(r['Decision']=='published' for r in results)}", flush=True)

    # Final normalized deduplication by repaired source identity and verified location.
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for r in results:
        if r["Decision"] != "published":
            continue
        key = (C.norm_identity(r["Verified Name"]), C.norm_address(r["Verified Full Address"]))
        if not all(key):
            r["Decision"] = "excluded"
            r["Exclusion Reason"] = "empty normalized identity or verified address"
            continue
        if key in seen:
            r["Decision"] = "merged-duplicate"
            r["Exclusion Reason"] = f"duplicate of {seen[key].get('Candidate ID')}"
        else:
            seen[key] = r

    published = [r for r in results if r["Decision"] == "published"]
    excluded = [r for r in results if r["Decision"] != "published"]

    # Construct exact-schema combined public data for local bucket packaging.
    combined: list[dict[str, Any]] = []
    for r in published:
        combined.append({
            "Name": r["Verified Name"],
            "Address": r["Verified Full Address"],
            "Latitude and longitude": f"{float(r['Latitude']):.7f}, {float(r['Longitude']):.7f}",
            "Guide": r["Guide"],
            "Category": r["Category Hint"],
            "Description": r["Description"],
            "Source URL": r["Source URL"],
            "Priority": r["Priority"],
            "Year": r["Year"],
            "Google Maps URL": r["Google Maps URL"],
            "Bucket": r["Bucket Hint"],
            "Candidate ID": r["Candidate ID"],
            "Occurrence ID": r["Occurrence ID"],
            "Verification Method": r["Verification Method"],
            "Verification Basis": r["Verification Basis"],
            "Official Website": r["Official Website"],
            "Official Website Check": r["Official Website Check"],
        })
    combined.sort(key=lambda r: (int(r["Bucket"]), r["Name"].casefold(), r["Address"].casefold()))

    result_fields = list(results[0].keys()) if results else []
    write_csv(OUTPUT_DIR / "final_verification_results.csv", result_fields, results)
    write_csv(OUTPUT_DIR / "final_verified_rows_combined.csv", list(combined[0].keys()) if combined else PUBLIC_HEADER + ["Bucket"], combined)
    exclusion_fields = [
        "Candidate ID", "Name", "Source Address", "Source URL", "Guide", "Year", "Occurrence ID",
        "Decision", "Exclusion Reason", "Verification Method", "Verification Basis",
        "Google Result Name", "Google Result Address", "Evidence Excerpt",
    ]
    write_csv(OUTPUT_DIR / "final_verification_exclusions.csv", exclusion_fields, excluded)

    fetch_records = []
    for rec in getattr(C.fetcher, "records", []):
        try:
            fetch_records.append(dataclasses.asdict(rec))
        except Exception:
            fetch_records.append(dict(rec))
    if fetch_records:
        write_csv(OUTPUT_DIR / "final_verification_fetch_log.csv", list(fetch_records[0].keys()), fetch_records)

    errors: list[dict[str, Any]] = []
    duplicate_keys = set()
    for i, r in enumerate(combined, 2):
        for field in PUBLIC_HEADER:
            if not clean(r.get(field, "")):
                errors.append({"row": i, "field": field, "error": "blank required field"})
        if r.get("Source URL", "").startswith("https://www.newyorker.com/") is False:
            errors.append({"row": i, "field": "Source URL", "error": "noncanonical source URL"})
        if not full_postal(r.get("Address", "")):
            errors.append({"row": i, "field": "Address", "error": "postal code/country missing"})
        try:
            lat, lon = [float(x.strip()) for x in r["Latitude and longitude"].split(",", 1)]
            if not coords_region_ok(lat, lon, "Pocantico" if r["Name"] == "Blue Hill at Stone Barns" else "New York"):
                raise ValueError("geographic region conflict")
        except Exception as exc:
            errors.append({"row": i, "field": "Latitude and longitude", "error": str(exc)})
        if not r.get("Google Maps URL", "").startswith("https://"):
            errors.append({"row": i, "field": "Google Maps URL", "error": "malformed Maps URL"})
        key = (C.norm_identity(r["Name"]), C.norm_address(r["Address"]))
        if key in duplicate_keys:
            errors.append({"row": i, "field": "Name/Address", "error": "normalized duplicate"})
        duplicate_keys.add(key)
        agree, _, reason = source_address_agrees(next(x["Source Address"] for x in results if x["Candidate ID"] == r["Candidate ID"]), r["Address"])
        if not agree:
            errors.append({"row": i, "field": "Address", "error": f"source/verified address conflict: {reason}"})

    summary = {
        "upstream_crawler": str(CRAWLER_PATH),
        "input_candidates": len(rows),
        "published_unique_rows": len(combined),
        "excluded_or_merged_candidates": len(excluded),
        "verification_methods": dict(Counter(r["Verification Method"] or "none" for r in results)),
        "decisions": dict(Counter(r["Decision"] for r in results)),
        "published_by_bucket": dict(Counter(str(r["Bucket"]) for r in combined)),
        "years": {"min": min((int(r["Year"]) for r in combined), default=None), "max": max((int(r["Year"]) for r in combined), default=None)},
        "official_website_checks": dict(Counter(r["Official Website Check"] or "blank" for r in results)),
        "validation_valid": not errors,
        "validation_error_count": len(errors),
        "validation_errors": errors[:500],
        "fetch_count": len(fetch_records),
    }
    (OUTPUT_DIR / "final_verification_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
