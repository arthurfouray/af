#!/usr/bin/env python3
"""Fresh unified Tables for Two crawl.

Extends the existing fail-closed crawler by reconciling the live /magazine and
/culture archive routes, improving block-local venue-name association, and
allowing source-era historical venues to use address-level online geocoding
when a current Google business listing no longer exists.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

BASE_PATH = Path(__file__).with_name("newyorker_tables_for_two_audit.py")
spec = importlib.util.spec_from_file_location("nytft_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load base crawler: {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

ARCHIVES = [
    ("magazine", "https://www.newyorker.com/magazine/tables-for-two"),
    ("culture", "https://www.newyorker.com/culture/tables-for-two"),
]


def unified_discover():
    rows: list[dict[str, Any]] = []
    inventory: list[str] = []
    seen: set[str] = set()
    for route, archive_url in ARCHIVES:
        route_terminal = False
        for page in range(0, 260):
            url = archive_url if page == 0 else f"{archive_url}?page={page}"
            response, text, status = base.get(url, f"archive-pagination-{route}", 0.22)
            links = base.article_links(text) if status == 200 else []
            new_count = 0
            for link in links:
                if link not in seen:
                    seen.add(link)
                    inventory.append(link)
                    new_count += 1
            terminal = status == 404 or (page > 0 and status == 200 and not links)
            rows.append(
                {
                    "page": f"{route}:{page}",
                    "requested_url": url,
                    "final_url": getattr(response, "url", ""),
                    "status": status,
                    "article_links_detected": len(links),
                    "new_unique_editorial_urls": new_count,
                    "terminal": terminal,
                    "note": f"{route} archive landing page" if page == 0 else route,
                }
            )
            if page > 0 and terminal:
                route_terminal = True
                break
        if not route_terminal:
            rows.append(
                {
                    "page": f"{route}:unresolved",
                    "requested_url": archive_url,
                    "final_url": archive_url,
                    "status": 0,
                    "article_links_detected": 0,
                    "new_unique_editorial_urls": 0,
                    "terminal": False,
                    "note": "pagination safety cap reached before terminal page",
                }
            )
    return inventory, rows


NAME_TOKEN = (
    r"(?:[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’&.\-/]*|"
    r"[A-Z0-9&]{2,}|de|del|della|di|da|la|le|du|des|of|the|and|an|a)"
)
NAME_TAIL = re.compile(
    rf"({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,9}})"
    rf"\s*(?:,?\s*(?:(?:is|was|opened|reopened|has opened|has reopened|moved|located)\s+)?"
    rf"(?:at|on|to))?\s*,?\s*$"
)
CALLED_AFTER = re.compile(
    r"(?i)\b(?:called|named|known as)\s+([A-Z][A-Za-z0-9À-ÖØ-öø-ÿ&'’./ -]{1,80})"
)
BAD_NAME_WORDS = {
    "open daily", "open for", "entrées", "entrees", "telephone", "phone",
    "between", "corner", "address", "location", "tables for two",
}


def clean_name_candidate(value: str) -> str:
    value = base.clean(value).strip(" ,;:—–-")
    value = re.sub(
        r"(?i)^(?:the|a|an|and|or|also|then|there is|there are|another|this|that)\s+",
        "",
        value,
    )
    value = re.sub(r"(?i)^(?:restaurant|café|cafe|club|hotel)\s+called\s+", "", value)
    if not value or len(value) > 100 or len(value.split()) > 12:
        return ""
    folded = base.fold(value).lower()
    if any(word in folded for word in BAD_NAME_WORDS):
        return ""
    if re.fullmatch(r"[\d\W_]+", value):
        return ""
    if re.search(
        r"(?i)\b(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|"
        r"lane|drive|place|court|broadway)\s*$",
        value,
    ):
        return ""
    return value


def improved_name_from(block: str, address: str, title: str, url: str, auxname: str = ""):
    if auxname:
        return base.clean(auxname), "auxiliary exact-URL name"
    text = base.clean(block)
    match = re.search(re.escape(address), text, flags=re.I)
    if match:
        left = text[max(0, match.start() - 240): match.start()].rstrip()
        left = re.sub(r"\([^)]{0,120}\)\s*$", "", left).rstrip()
        clause = re.split(r"(?:[.!?;]\s+|\s+[—–]\s+|\n)", left)[-1]
        clause = clause[-150:].rstrip()
        tail = NAME_TAIL.search(clause)
        if tail:
            candidate = clean_name_candidate(tail.group(1))
            if candidate:
                return candidate, "nearest proper-name phrase before source address"
        # Historic copy often uses a simple Name, 123 Street construction.
        comma_tail = re.search(
            r"([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9&'’./ -]{1,90})\s*,\s*$",
            clause,
        )
        if comma_tail:
            candidate = clean_name_candidate(comma_tail.group(1))
            if candidate:
                return candidate, "source clause immediately before comma-address"
        # Upper-case leads remain common in the earliest columns.
        caps = re.findall(r"(?:^|[.!?;]\s+)([A-Z][A-Z0-9&'’ .\-/]{2,70})\s*$", left)
        if caps:
            candidate = clean_name_candidate(caps[-1].title())
            if candidate:
                return candidate, "source uppercase lead before address"
    called = CALLED_AFTER.search(text)
    if called:
        candidate = clean_name_candidate(called.group(1))
        if candidate:
            return candidate, "source called/named phrase"
    specific_title = base.title_name(title)
    if specific_title:
        return specific_title, "specific source headline"
    slug = base.slug_name(url)
    if slug:
        return slug, "source URL slug"
    return "", "no reliable venue-name association"


def maps_search(query: str, purpose: str):
    endpoint = "https://www.google.com/search?" + urllib.parse.urlencode(
        {"tbm": "map", "authuser": "0", "hl": "en", "gl": "us", "q": query}
    )
    _response, text, status = base.get(endpoint, purpose, 0.30, 22)
    return (base.parse_google(text) if status == 200 else []), endpoint


def best_address_match(address: str, places: list[dict[str, Any]]):
    for place in places[:12]:
        ok, why = base.addr_agree(address, place.get("address", ""))
        if ok:
            return place, why
    return None, "no exact building/street result"


def census_address_geocode(address: str):
    # Used only as an address/coordinate fallback for source-associated historical US venues.
    endpoint = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urllib.parse.urlencode(
        {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    )
    _response, text, status = base.get(endpoint, "census-address-geocode", 0.12, 20)
    if status != 200:
        return None
    try:
        payload = json.loads(text)
        matches = ((payload.get("result") or {}).get("addressMatches") or [])
        if not matches:
            return None
        first = matches[0]
        coords = first.get("coordinates") or {}
        matched = base.clean(first.get("matchedAddress") or "")
        lat = float(coords["y"])
        lng = float(coords["x"])
        if not matched or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        return {"address": matched, "lat": lat, "lng": lng}
    except Exception:
        return None


def improved_complete_address(address: str) -> str:
    value = base.clean(address)
    if not value:
        return ""
    if re.search(
        r"(?i)\b(?:United States|USA|U\.S\.|France|Italy|United Kingdom|Japan|Spain|"
        r"Germany|Canada|Mexico|Greece|Portugal|Austria|Belgium|Switzerland|Netherlands|"
        r"Denmark|Sweden|Norway|Australia|China|Hong Kong|South Korea|India|Brazil)\b",
        value,
    ):
        return value
    if re.search(
        r"(?i)\b(?:NY|NJ|CT|MA|PA|CA|IL|FL|TX|DC)\s+\d{5}(?:-\d{4})?\b|"
        r"\b(?:Brooklyn|Queens|Bronx|Manhattan|Staten Island|New York|Jersey City|Hoboken)\b",
        value,
    ):
        return value + ", United States"
    return value


def improved_google_lookup(name: str, address: str):
    query = f"{name}, {address}"
    places, request_url = maps_search(query, "google-maps-identity-verification")
    best = None
    best_score = -1.0
    reason = "no matching Google Maps identity/address result"
    for place in places[:10]:
        name_score = base.sim(name, place.get("name", ""))
        address_ok, address_reason = base.addr_agree(address, place.get("address", ""))
        score = name_score + (1.0 if address_ok else 0.0)
        if score > best_score:
            best = place
            best_score = score
            reason = f"name_similarity={name_score:.3f}; {address_reason}"
    if best and base.sim(name, best.get("name", "")) >= 0.58 and base.addr_agree(address, best.get("address", ""))[0]:
        return best, reason, request_url

    # Closed historical venues often no longer have a business entity in Maps. The source
    # article remains the identity evidence; verify the exact physical address separately.
    address_places, _address_request = maps_search(address, "google-maps-address-verification")
    address_place, address_reason = best_address_match(address, address_places)
    if address_place:
        mapped_address = improved_complete_address(address_place.get("address", ""))
        search_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(
            f"{name}, {mapped_address or address}"
        )
        return (
            {
                "name": name,
                "address": mapped_address or address_place.get("address", ""),
                "lat": address_place.get("lat"),
                "lng": address_place.get("lng"),
                "cid": "",
                "url": search_url,
                "website": "",
                "categories": [],
            },
            f"source-era identity plus address-level Google Maps verification; {address_reason}",
            request_url,
        )

    census = census_address_geocode(address)
    if census:
        mapped_address = improved_complete_address(census["address"])
        search_url = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(
            f"{name}, {mapped_address}"
        )
        return (
            {
                "name": name,
                "address": mapped_address,
                "lat": census["lat"],
                "lng": census["lng"],
                "cid": "",
                "url": search_url,
                "website": "",
                "categories": [],
            },
            "source-era identity plus U.S. Census address-coordinate verification",
            request_url,
        )
    return None, reason, request_url


base.discover = unified_discover
base.name_from = improved_name_from
base.google_lookup = improved_google_lookup
base.complete_address = improved_complete_address

if __name__ == "__main__":
    raise SystemExit(base.main())
