"""Resolve a manga series online and build a chapter -> volume mapping.

Sources, in order of preference:
  1. MangaDex  /manga/{id}/aggregate  - real per-chapter volume assignments.
  2. AniList   GraphQL                - total volume + chapter counts only, so
     the mapping is derived by splitting chapters evenly across volumes. This
     is an approximation and is flagged as such.

When several series share (almost) the same name, candidates are ranked by
title similarity *and* how closely their chapter count matches the number of
chapters actually downloaded.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from mangabinder import REPO_URL, __version__
from mangabinder.paths import cache_dir

USER_AGENT = f"mangabinder/{__version__} (+{REPO_URL})"
MANGADEX_API = "https://api.mangadex.org"
ANILIST_API = "https://graphql.anilist.co"
CACHE_FILE = os.path.join(cache_dir(), "volume_cache.json")

# A MangaDex aggregate is only trusted if at least this fraction of its
# chapters carry a real volume number (uploaders often leave them blank).
MIN_VOLUME_COVERAGE = 0.7


# --------------------------------------------------------------------------
# name parsing
# --------------------------------------------------------------------------

_CHAPTER_PATTERNS = [
    re.compile(r"chapter[\s._-]*([0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(r"(?:^|[\s._-])ch?[\s._-]?([0-9]+(?:\.[0-9]+)?)(?:$|[\s._-])", re.I),
    re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*$"),
]


def parse_chapter_number(name):
    """Pull a chapter number out of a folder/file name, or None."""
    stem = os.path.splitext(os.path.basename(str(name).rstrip("/\\")))[0]
    for pattern in _CHAPTER_PATTERNS:
        match = pattern.search(stem)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def format_chapter_number(num):
    """1.0 -> '1', 10.5 -> '10.5' (matches how sources key chapters)."""
    return str(int(num)) if float(num).is_integer() else str(num)


def guess_series_title(names):
    """Guess a series title from chapter folder names.

    'monster-chapter-1' -> 'Monster'
    """
    stems = []
    for name in names:
        stem = os.path.splitext(os.path.basename(str(name).rstrip("/\\")))[0]
        # Drop the chapter marker and everything after it.
        cut = re.split(r"[\s._-]*chapter[\s._-]*[0-9]", stem, flags=re.I)[0]
        if cut == stem:
            cut = re.sub(r"[\s._-]+[0-9]+(?:\.[0-9]+)?$", "", stem)
        cut = cut.strip(" ._-")
        if cut:
            stems.append(cut)
    if not stems:
        return ""
    # Most common stem wins; ties broken by the longest.
    counts = {}
    for stem in stems:
        counts[stem.lower()] = counts.get(stem.lower(), 0) + 1
    best = max(counts, key=lambda k: (counts[k], len(k)))
    return re.sub(r"[._-]+", " ", best).strip().title()


def normalize_title(title):
    title = str(title or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return " ".join(title.split())


# --------------------------------------------------------------------------
# http helpers (stdlib only, so there is nothing extra to install)
# --------------------------------------------------------------------------

def _request(url, data=None, timeout=20, retries=2):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url} ({last_error})")


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    source: str          # 'mangadex' | 'anilist'
    series_id: str
    title: str
    alt_titles: list = field(default_factory=list)
    last_chapter: float = None
    volume_count: int = None
    year: int = None
    score: float = 0.0
    tier: int = 0        # 2 = exact name match, 1 = close, 0 = loose
    reason: str = ""

    def label(self):
        bits = [f"{self.title} [{self.source}]"]
        if self.year:
            bits.append(f"({self.year})")
        if self.last_chapter is not None:
            bits.append(f"{format_chapter_number(self.last_chapter)} ch")
        if self.volume_count:
            bits.append(f"{self.volume_count} vol")
        return " ".join(bits)


def _to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def search_mangadex(title, limit=10):
    url = f"{MANGADEX_API}/manga?" + urllib.parse.urlencode(
        {"title": title, "limit": limit, "order[relevance]": "desc"}
    )
    try:
        payload = _request(url)
    except RuntimeError:
        return []
    candidates = []
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        titles = attrs.get("title", {}) or {}
        main = titles.get("en") or next(iter(titles.values()), "")
        alts = []
        for alt in attrs.get("altTitles", []) or []:
            alts.extend(str(v) for v in alt.values())
        candidates.append(Candidate(
            source="mangadex",
            series_id=item.get("id", ""),
            title=main,
            alt_titles=alts,
            last_chapter=_to_float(attrs.get("lastChapter")),
            volume_count=_to_int(attrs.get("lastVolume")),
            year=_to_int(attrs.get("year")),
        ))
    return candidates


ANILIST_QUERY = """
query ($search: String) {
  Page(perPage: 10) {
    media(search: $search, type: MANGA) {
      id
      title { romaji english native }
      synonyms
      volumes
      chapters
      startDate { year }
    }
  }
}
"""


def search_anilist(title):
    try:
        payload = _request(ANILIST_API, data={"query": ANILIST_QUERY,
                                              "variables": {"search": title}})
    except RuntimeError:
        return []
    candidates = []
    for media in (payload.get("data", {}).get("Page", {}) or {}).get("media", []) or []:
        titles = media.get("title", {}) or {}
        main = titles.get("english") or titles.get("romaji") or titles.get("native") or ""
        alts = [t for t in titles.values() if t]
        alts.extend(media.get("synonyms") or [])
        candidates.append(Candidate(
            source="anilist",
            series_id=str(media.get("id", "")),
            title=main,
            alt_titles=alts,
            last_chapter=_to_float(media.get("chapters")),
            volume_count=_to_int(media.get("volumes")),
            year=_to_int((media.get("startDate") or {}).get("year")),
        ))
    return candidates


def score_candidate(cand, query_title, local_chapters):
    """Blend title similarity with how well the chapter count matches.

    The chapter count is what separates two series with near-identical names.
    It is treated as a *lower bound*: a partial download of a long series is
    normal, but a series that ends before our highest chapter cannot be the
    one we have on disk.
    """
    local_chapters = sorted(local_chapters or [])
    local_count = len(local_chapters)
    local_max = local_chapters[-1] if local_chapters else 0

    query_norm = normalize_title(query_title)
    names = [cand.title] + list(cand.alt_titles)
    title_sim = max(
        (SequenceMatcher(None, query_norm, normalize_title(n)).ratio() for n in names if n),
        default=0.0,
    )

    if local_count and cand.last_chapter:
        tolerance = max(3.0, local_count * 0.05)
        if cand.last_chapter + tolerance < local_max:
            # Series is too short to contain the chapters we already have.
            count_score = 0.05
            note = (f"only {format_chapter_number(cand.last_chapter)} chapters, "
                    f"but we have chapter {format_chapter_number(local_max)}")
        elif abs(cand.last_chapter - local_count) <= tolerance:
            count_score = 1.0
            note = f"chapter count matches ({format_chapter_number(cand.last_chapter)} vs {local_count} local)"
        else:
            # Plausible partial download; mild preference for a closer count.
            excess = cand.last_chapter - local_count
            count_score = max(0.45, 0.9 - excess / max(cand.last_chapter, 1.0) * 0.5)
            note = (f"partial download? {format_chapter_number(cand.last_chapter)} "
                    f"chapters published vs {local_count} local")
        score = 0.55 * title_sim + 0.45 * count_score
    else:
        score = title_sim * 0.75  # unknown count -> less trustworthy
        note = "no chapter count published"

    # A series with no volume information cannot drive a volume merge.
    if not cand.volume_count:
        score *= 0.85
        note += "; no volume count"

    # The name decides *which* series; the chapter count only breaks ties
    # between series with (nearly) the same name. Without this tiering a
    # coincidental chapter-count match on an unrelated title can outrank an
    # exact name match.
    if title_sim >= 0.95:
        cand.tier = 2
    elif title_sim >= 0.8:
        cand.tier = 1
    else:
        cand.tier = 0

    cand.score = round(score, 4)
    cand.reason = f"title {title_sim:.0%}; {note}"
    return cand.score


def resolve_series(title, local_chapters=None, verbose=True):
    """Search every source and return (best, ranked_candidates)."""
    candidates = search_mangadex(title) + search_anilist(title)
    if not candidates:
        return None, []
    for cand in candidates:
        score_candidate(cand, title, local_chapters)
    # Name tier first, then the score; MangaDex breaks a true tie because only
    # it can supply a real per-chapter map.
    ranked = sorted(candidates,
                    key=lambda c: (c.tier, c.score, c.source == "mangadex"),
                    reverse=True)
    if verbose:
        print(f"[+] Search '{title}' ({len(local_chapters or [])} local chapters) -> {len(ranked)} candidates")
        for cand in ranked[:5]:
            print(f"      {cand.score:.3f}  {cand.label()}  -- {cand.reason}")
    return ranked[0], ranked


# --------------------------------------------------------------------------
# volume maps
# --------------------------------------------------------------------------

def _drop_non_monotonic(mapping, verbose=True):
    """Remove chapters whose volume breaks the chapter->volume ordering.

    Volume numbers must never decrease as chapter numbers increase, but
    community metadata sometimes mis-tags a chapter (e.g. chapter 232 landing
    in volume 1). Keeping the longest non-decreasing run drops exactly those
    outliers; they are re-placed afterwards by the gap-filling step.
    """
    items = sorted(((float(k), v) for k, v in mapping.items()), key=lambda kv: kv[0])
    if len(items) < 3:
        return mapping

    # Longest non-decreasing subsequence over volume numbers (O(n^2) is fine
    # here - a series has at most a few thousand chapters).
    best_len = [1] * len(items)
    prev = [-1] * len(items)
    for i in range(1, len(items)):
        for j in range(i):
            if items[j][1] <= items[i][1] and best_len[j] + 1 > best_len[i]:
                best_len[i] = best_len[j] + 1
                prev[i] = j
    end = max(range(len(items)), key=lambda i: best_len[i])
    keep = set()
    while end != -1:
        keep.add(end)
        end = prev[end]

    cleaned = {format_chapter_number(items[i][0]): items[i][1] for i in sorted(keep)}
    dropped = len(items) - len(cleaned)
    if dropped and verbose:
        bad = [format_chapter_number(items[i][0]) for i in range(len(items)) if i not in keep]
        print(f"    [!] Ignoring {dropped} out-of-order volume tag(s) from the source: "
              f"{', '.join(bad[:8])}{'...' if dropped > 8 else ''}")
    return cleaned


def mangadex_volume_map(series_id, verbose=True):
    """chapter-number-string -> volume int, or None if unusable."""
    url = f"{MANGADEX_API}/manga/{series_id}/aggregate"
    try:
        payload = _request(url)
    except RuntimeError as exc:
        if verbose:
            print(f"    [!] MangaDex aggregate failed: {exc}")
        return None

    # The same chapter number can appear under several volumes when upload
    # groups disagree, so collect every claim and let the number of uploads
    # behind each one decide. A tie goes to the earliest volume.
    claims, unassigned = {}, 0
    for vol_key, vol in (payload.get("volumes") or {}).items():
        chapters = vol.get("chapters") or {}
        volume_no = _to_int(vol_key)
        if volume_no is None:          # literal "none"
            unassigned += len(chapters)
            continue
        for chap, meta in chapters.items():
            weight = _to_int((meta or {}).get("count")) or 1
            claims.setdefault(str(chap), {})
            claims[str(chap)][volume_no] = claims[str(chap)].get(volume_no, 0) + weight

    mapping, contested = {}, 0
    for chap, votes in claims.items():
        if len(votes) > 1:
            contested += 1
        mapping[chap] = min(votes, key=lambda v: (-votes[v], v))
    if contested and verbose:
        print(f"    [~] {contested} chapter(s) were tagged with conflicting volumes; "
              f"used the most-uploaded volume for each.")

    total = len(mapping) + unassigned
    if not mapping or total == 0:
        if verbose:
            print("    [!] MangaDex has no volume assignments for this series.")
        return None
    coverage = len(mapping) / total
    if coverage < MIN_VOLUME_COVERAGE:
        if verbose:
            print(f"    [!] MangaDex volume coverage only {coverage:.0%} - ignoring.")
        return None
    mapping = _drop_non_monotonic(mapping, verbose=verbose)
    if verbose:
        print(f"    [+] MangaDex volume data: {len(mapping)} chapters across "
              f"{len(set(mapping.values()))} volumes ({coverage:.0%} coverage)")
    return mapping


def even_split_map(chapter_numbers, volume_count):
    """Spread chapters across volumes as evenly as possible (approximate)."""
    chapters = sorted(chapter_numbers)
    if not chapters or not volume_count or volume_count < 1:
        return {}
    volume_count = min(volume_count, len(chapters))
    base, remainder = divmod(len(chapters), volume_count)
    mapping, index = {}, 0
    for vol in range(1, volume_count + 1):
        size = base + (1 if vol <= remainder else 0)
        for chap in chapters[index:index + size]:
            mapping[format_chapter_number(chap)] = vol
        index += size
    return mapping


def build_volume_map(candidate, chapter_numbers, verbose=True):
    """Return (mapping, info) where mapping is {chapter-str: volume-int}.

    Chapters the source does not know about (extras such as 10.5) inherit the
    volume of the nearest preceding known chapter.
    """
    info = {"source": None, "approximate": False, "series": candidate.label() if candidate else ""}
    mapping = None

    if candidate and candidate.source == "mangadex":
        mapping = mangadex_volume_map(candidate.series_id, verbose=verbose)
        if mapping:
            info["source"] = "mangadex-aggregate"

    if not mapping and candidate and candidate.volume_count:
        # Split across the series' *published* chapter range, not just what is
        # on disk - otherwise a partial download squeezes every downloaded
        # chapter into the first volumes.
        local_max = max(chapter_numbers) if chapter_numbers else 0
        total = candidate.last_chapter or local_max
        if total and total >= local_max:
            split_range = [float(n) for n in range(1, int(total) + 1)]
            # Keep any local half-chapters (10.5 etc) in the split.
            split_range = sorted(set(split_range) | set(chapter_numbers))
        else:
            split_range = sorted(chapter_numbers)
        mapping = even_split_map(split_range, candidate.volume_count)
        info["source"] = f"{candidate.source}-even-split"
        info["approximate"] = True
        if verbose:
            print(f"    [~] No per-chapter volume data; splitting {len(split_range)} "
                  f"chapters evenly across {candidate.volume_count} volumes (APPROXIMATE).")

    if not mapping:
        return {}, info

    # Fill gaps for local chapters the source did not list.
    known = sorted((float(k), v) for k, v in mapping.items() if _to_float(k) is not None)
    filled, missing = {}, 0
    for chap in sorted(chapter_numbers):
        key = format_chapter_number(chap)
        if key in mapping:
            filled[key] = mapping[key]
            continue
        prior = [vol for num, vol in known if num <= chap]
        if prior:
            filled[key] = prior[-1]
        elif known:
            filled[key] = known[0][1]
        else:
            missing += 1
    if missing and verbose:
        print(f"    [!] {missing} chapters could not be placed in a volume.")
    info["mapped"] = len(filled)
    info["volumes"] = len(set(filled.values()))
    return filled, info


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
    except OSError as exc:
        print(f"[!] Could not write cache: {exc}")


def get_volume_map(title, chapter_numbers, series_id=None, source=None,
                   use_cache=True, verbose=True):
    """Full pipeline: resolve the series, then build the chapter->volume map.

    Returns (mapping, info). `info` carries the resolved series label, the data
    source, and whether the mapping is approximate.
    """
    cache_key = f"{normalize_title(title)}|{len(chapter_numbers)}|{series_id or ''}"
    cache = _load_cache() if use_cache else {}
    if use_cache and cache_key in cache:
        entry = cache[cache_key]
        if verbose:
            print(f"[+] Using cached volume map for '{title}' ({entry['info'].get('series', '')})")
        return entry["mapping"], entry["info"]

    if series_id:
        candidate = Candidate(source=source or "mangadex", series_id=series_id, title=title)
        # Pull real metadata so an even-split fallback still knows the volume count.
        if candidate.source == "anilist":
            for found in search_anilist(title):
                if found.series_id == series_id:
                    candidate = found
                    break
    else:
        candidate, _ = resolve_series(title, chapter_numbers, verbose=verbose)

    if not candidate:
        if verbose:
            print(f"[!] No series found online for '{title}'.")
        return {}, {"source": None, "approximate": False, "series": ""}

    mapping, info = build_volume_map(candidate, chapter_numbers, verbose=verbose)
    if mapping and use_cache:
        cache[cache_key] = {"mapping": mapping, "info": info}
        _save_cache(cache)
    return mapping, info
