import sys
import os
import re
import json
import unicodedata
from typing import Dict, List, Tuple, Optional

# MHTML parsing
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from datetime import datetime

TIER_NAMES = ["SS", "S", "A", "B", "C", "D"]


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize('NFKD', s)
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s\-\+\*'\(\)☆]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def load_html_from_mhtml(path: str) -> str:
    """Extract the HTML body from an MHTML (MIME) file. Fallback to raw read if needed."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        msg = BytesParser(policy=policy.default).parsebytes(data)
        # Find first text/html part
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type() or ""
                if ctype.startswith('text/html'):
                    try:
                        return part.get_content()
                    except Exception:
                        try:
                            return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        except Exception:
                            continue
        # Fallback: treat as plain HTML
        try:
            return data.decode('utf-8', errors='ignore')
        except Exception:
            return data.decode('latin-1', errors='ignore')
    except Exception as e:
        raise RuntimeError(f"Failed to read MHTML: {e}")


def extract_tier_sections(soup: BeautifulSoup) -> List[Tuple[str, object]]:
    """Return a list of (tier_name, header_tag) discovered in the document, in DOM order."""
    tier_headers: List[Tuple[str, object]] = []
    header_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    tier_regex = re.compile(r"^(ss|s|a|b|c|d)\s*tier\b", re.I)

    for tag in soup.find_all(header_tags):
        text = (tag.get_text() or '').strip()
        if not text:
            continue
        if tier_regex.search(text):
            # normalize to canonical tier label prefix
            m = re.search(r"(SS|S|A|B|C|D)", text, re.I)
            if not m:
                continue
            tier = m.group(1).upper()
            tier_headers.append((tier, tag))
    return tier_headers


def collect_text_candidates(node) -> List[str]:
    """Collect candidate skill names under a node using heuristics: list items, anchors, strong tags, and card titles."""
    names: List[str] = []

    # List items
    for li in node.find_all('li'):
        t = (li.get_text(" ") or '').strip()
        if t:
            names.append(t)

    # Anchor texts
    for a in node.find_all('a'):
        t = (a.get_text(" ") or '').strip()
        if t:
            names.append(t)

    # Headings/strongs inside the section
    for tag in node.find_all(['h4', 'h5', 'h6', 'strong', 'b', 'span']):
        t = (tag.get_text(" ") or '').strip()
        if t:
            names.append(t)

    # De-duplicate while preserving order
    seen = set()
    out: List[str] = []
    for n in names:
        nn = n.strip()
        if nn and nn not in seen:
            seen.add(nn)
            out.append(nn)
    return out


def is_plausible_skill_name(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    # Exclude generic headings and non-name phrases
    if re.search(r"\b(tier|overview|notes|summary|what|how|update|version)\b", normalize_text(t)):
        return False
    # Must contain letters, and not be overly long
    if not re.search(r"[A-Za-z]", t):
        return False
    if len(t) > 80:
        return False
    return True


def parse_tiers_from_html(html: str) -> Dict[str, List[str]]:
    soup = BeautifulSoup(html, 'html.parser')
    headers = extract_tier_sections(soup)
    tier_to_names: Dict[str, List[str]] = {t: [] for t in TIER_NAMES}

    if not headers:
        # Fallback: try to find sections by text chunks containing "SS Tier" etc.
        text = soup.get_text("\n")
        for i, tier in enumerate(TIER_NAMES):
            pat = re.compile(rf"{tier}\\s*Tier", re.I)
            m = pat.search(text)
            if not m:
                continue
            start = m.end()
            # end is next tier occurrence
            end = len(text)
            for j in range(i+1, len(TIER_NAMES)):
                m2 = re.search(rf"{TIER_NAMES[j]}\\s*Tier", text, re.I)
                if m2:
                    end = min(end, m2.start())
            block = text[start:end]
            # naive candidate extraction: lines with capitalization and not containing 'Tier'
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            cands = [l for l in lines if is_plausible_skill_name(l)]
            # Limit noise
            cands = cands[:500]
            seen = set()
            out = []
            for c in cands:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
            tier_to_names[tier] = out
        return tier_to_names

    # DOM-based section extraction
    for idx, (tier, tag) in enumerate(headers):
        # Determine the boundary: until next tier header or end
        end_node = headers[idx+1][1] if idx + 1 < len(headers) else None
        # Collect siblings until end_node
        section_nodes = []
        n = tag.next_sibling
        while n is not None and n is not end_node:
            section_nodes.append(n)
            n = n.next_sibling
        # Build a temporary container soup fragment
        container = BeautifulSoup("<div></div>", 'html.parser')
        holder = container.div
        for n in section_nodes:
            try:
                holder.append(n)
            except Exception:
                continue
        names = collect_text_candidates(holder)
        names = [x for x in names if is_plausible_skill_name(x)]
        tier_to_names[tier] = names

    return tier_to_names


def load_existing_json(json_path: str) -> List[Dict]:
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def build_index(existing: List[Dict]) -> Dict[str, Dict]:
    idx: Dict[str, Dict] = {}
    for item in existing or []:
        name = item.get('name')
        if not isinstance(name, str):
            continue
        idx[normalize_text(name)] = item
    return idx


def best_match(name: str, index: Dict[str, Dict], threshold: float = 0.88) -> Optional[Dict]:
    key = normalize_text(name)
    # Exact normalized match
    if key in index:
        return index[key]
    # Fuzzy
    best = None
    best_score = 0.0
    for k, item in index.items():
        score = similar(key, k)
        if score > best_score:
            best = item
            best_score = score
    if best and best_score >= threshold:
        return best
    return None


def merge_tiers_into_json(
    tier_map: Dict[str, List[str]],
    existing: List[Dict]
) -> Tuple[List[Dict], int, int]:
    index = build_index(existing)

    updated = 0
    added = 0

    # Keep a set of names we have assigned from MHTML for reporting
    assigned = set()

    for tier in TIER_NAMES:
        names = tier_map.get(tier, []) or []
        for raw_name in names:
            name = raw_name.strip()
            if not name:
                continue
            # Remove trailing annotations often used in articles (e.g., parentheticals) only if clearly not part of skill
            cleaned = re.sub(r"\s*\([^)]*\)$", "", name).strip()
            # Try to find a matching existing skill
            match = best_match(cleaned, index)
            if match is not None:
                prev_tier = match.get('tier')
                if prev_tier != tier:
                    match['tier'] = tier
                    updated += 1
                assigned.add(match.get('name'))
            else:
                # Add new minimal entry
                new_obj = {
                    'name': cleaned,
                    'tier': tier,
                    'skill_type': '',
                    'description': '',
                    'rarity': '',
                    'base_cost': ''
                }
                existing.append(new_obj)
                index[normalize_text(cleaned)] = new_obj
                added += 1
                assigned.add(cleaned)

    return existing, updated, added


def backup_file(path: str) -> Optional[str]:
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{path}.backup_{ts}"
        with open(path, 'r', encoding='utf-8') as src, open(backup_path, 'w', encoding='utf-8') as dst:
            dst.write(src.read())
        return backup_path
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/update_skills_from_mhtml.py <path-to-mhtml> [--json <json-path>]")
        sys.exit(1)

    mhtml_path = sys.argv[1]
    json_path = 'web/src/assets/umamusume_final_skills_fixed.json'

    if '--json' in sys.argv:
        try:
            json_path = sys.argv[sys.argv.index('--json') + 1]
        except Exception:
            print("--json flag provided but no path value found")
            sys.exit(1)

    if not os.path.isfile(mhtml_path):
        print(f"MHTML not found: {mhtml_path}")
        sys.exit(1)
    if not os.path.isfile(json_path):
        print(f"JSON not found: {json_path}")
        sys.exit(1)

    print(f"Reading MHTML: {mhtml_path}")
    html = load_html_from_mhtml(mhtml_path)
    print(f"Extracting tier sections...")
    tiers = parse_tiers_from_html(html)

    total_found = sum(len(v or []) for v in tiers.values())
    non_empty = {k: len(v or []) for k, v in tiers.items() if v}
    print(f"Found candidate names per tier: {non_empty} (total {total_found})")

    print(f"Loading existing skills JSON: {json_path}")
    existing = load_existing_json(json_path)

    print("Merging tiers into JSON...")
    merged, updated, added = merge_tiers_into_json(tiers, existing)

    # Backup existing file
    bkp = backup_file(json_path)
    if bkp:
        print(f"Backup saved: {bkp}")

    # Save merged file
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Done. Updated {updated} skills, added {added} new entries. Total skills: {len(merged)}")


if __name__ == '__main__':
    main()
