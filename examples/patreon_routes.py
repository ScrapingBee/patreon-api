"""Four routes to public Patreon creator data, in cost order.

Verified against https://www.patreon.com/kurzgesagt on 2026-09-10.
Public creator pages only. Nothing here signs in.
Set SCRAPINGBEE_API_KEY in your environment before running.
"""

import json
import os
import re

import requests

BASE = "https://app.scrapingbee.com/api/v1/"
HEADERS = {"Authorization": f"Bearer {os.environ['SCRAPINGBEE_API_KEY']}"}


def _fetch(url, **params):
    r = requests.get(BASE, headers=HEADERS, params={"url": url, **params}, timeout=120)
    r.raise_for_status()
    return r


def creator(slug):
    """Route 1: meta tags. 5 credits. The durable route."""
    rules = {
        "creator": {"selector": "h1", "output": "text"},
        "title": "title",
        "og_title": {"selector": 'meta[property="og:title"]', "output": "@content"},
        "og_desc": {"selector": 'meta[name="description"]', "output": "@content"},
    }
    data = _fetch(
        f"https://www.patreon.com/{slug}",
        extract_rules=json.dumps(rules),
        mode="auto",
    ).json()
    # Patreon joins creator name and campaign tagline with an em dash.
    if data.get("title") and "—" in data["title"]:
        name, _, tagline = data["title"].partition("—")
        data["campaign_tagline"] = tagline.split("|")[0].strip()
    return data


def profile(slug):
    """Route 2: the application/ld+json ProfilePage block. 5 credits.

    extract_rules cannot reach script tag contents, so this parses the
    fetched HTML instead. Match on @type, never on block index.
    """
    html = _fetch(f"https://www.patreon.com/{slug}", mode="auto").text
    for block in re.findall(
        r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S
    ):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("@type") == "ProfilePage":
            person = obj["mainEntity"]
            return {
                "name": person.get("name"),
                "alternate_name": person.get("alternateName"),
                "url": person.get("url"),
                "about": person.get("description"),
                "image": (person.get("image") or {}).get("contentUrl"),
                "thumbnail": (person.get("image") or {}).get("thumbnailUrl"),
            }
    return None


def entry_price(slug):
    """Route 3: ai_extract_rules. 30 credits.

    Returns the entry price teaser Patreon renders, not a tier array.
    """
    rules = {
        "creator_name": "the creator display name",
        "about": "the about text",
        "membership_tiers": {
            "type": "list",
            "description": "each tier with name and monthly price",
        },
    }
    return _fetch(
        f"https://www.patreon.com/{slug}",
        ai_extract_rules=json.dumps(rules),
        render_js="true",
        premium_proxy="true",
    ).json()


def tiers(slug):
    """Route 4: the bootstrap payload. 5 credits, brittle by design.

    Tier objects sit inside "attributes" blocks. Brace match them rather
    than regexing individual fields.

    Note: declined_patron_count counts DECLINED PAYMENTS, not the tier's
    patron count. There is no public per tier patron count here, so it is
    passed through unchanged rather than relabelled.

    Falls back to route 1 when Patreon changes the payload format.
    """
    html = _fetch(f"https://www.patreon.com/{slug}", mode="auto").text
    raw = html.encode("utf-8", "ignore").decode("unicode_escape", "ignore")

    found = []
    for match in re.finditer(r'"attributes":\{', raw):
        start, depth = match.end() - 1, 0
        for i in range(start, min(start + 8000, len(raw))):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    blob = raw[start:i + 1]
                    if "declined_patron_count" in blob:
                        try:
                            found.append(json.loads(blob))
                        except json.JSONDecodeError:
                            pass
                    break

    if not found:
        return {"tiers": [], "matched": False, "fallback": creator(slug)}

    found.sort(key=lambda t: t.get("amount_cents") or 0)
    return {"tiers": found, "matched": True, "count": len(found)}


if __name__ == "__main__":
    slug = "kurzgesagt"
    print("route 1:", creator(slug))
    print("route 2:", profile(slug))
    result = tiers(slug)
    print(f"route 4: {result['matched']}, {len(result['tiers'])} tiers")
    for t in result["tiers"]:
        price = (t.get("amount_cents") or 0) / 100
        print(f"   {t['title']:<18} {price:>7.2f} {t['currency']}  {t['post_count']} posts")
