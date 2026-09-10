# Patreon Scraper API

<p align="center">
  <a href="https://www.scrapingbee.com/">
    <img src="REPLACE_WITH_SCREENSHOT_URL" alt="patreon-api" />
  </a>
</p>

[![checks](https://github.com/ScrapingBee/patreon-api/workflows/checks/badge.svg)](https://github.com/ScrapingBee/patreon-api/actions)
[![pypi](https://img.shields.io/pypi/v/patreon-scraper-api.svg)](https://pypi.org/project/patreon-scraper-api/)
[![python](https://img.shields.io/pypi/pyversions/patreon-scraper-api.svg)](https://pypi.org/project/patreon-scraper-api/)
[![npm](https://img.shields.io/npm/v/patreon-scraper-api.svg)](https://www.npmjs.com/package/patreon-scraper-api)
[![node](https://img.shields.io/node/v/patreon-scraper-api.svg)](https://www.npmjs.com/package/patreon-scraper-api)
[![license](https://img.shields.io/github/license/ScrapingBee/patreon-api.svg)](LICENSE)

Four ways to get data off a public Patreon creator page, and the honest failure mode of each. This is a [patreon scraper](https://www.scrapingbee.com/scrapers/patreon-api/) built on [ScrapingBee's web scraping API](https://www.scrapingbee.com/features/ai-web-scraping-api/), and it is organised as a route decision rather than a tutorial, because on Patreon the field you want decides which route you take.

Everything below was run against `https://www.patreon.com/kurzgesagt` on 2026-09-10. Where a route failed, that is recorded rather than quietly dropped.

## The scope wall, first

A Patreon page has two halves and only one of them is in scope here.

**In scope, public, no account required:** creator display name, campaign tagline, the public about text, avatar and banner image URLs, post titles that Patreon publishes openly, the entry tier price teaser, canonical URL, and the aggregate patron counts Patreon chooses to render.

**Out of scope, permanently:** patron only posts, attachment downloads, member lists, individual pledge amounts, direct messages, and anything else that only appears once you are signed in. Scraping under login credentials is prohibited by ScrapingBee's terms of service, so none of it is reachable through this API and none of it is demonstrated here.

That line is not a technical limit you can parameter your way past. It is the product boundary.

## Route table

| Route | Gets you | Credits | Fails when |
|---|---|---|---|
| 1. Meta tags via `extract_rules` | Name, tagline, description, canonical | 5 | Never observed to fail. Patreon renders these server side |
| 2. Structured data block | Full about text, avatar, thumbnail, alternate name | 5 | `extract_rules` cannot reach it, see below |
| 3. `ai_extract_rules` | Name, about, entry price teaser | 30 | Returns the teaser string, not a tier array |
| 4. Raw HTML plus payload parse | Every tier: title, price, post count | 5 | Patreon changes its bootstrap format |

Authentication for all four is a header: `Authorization: Bearer YOUR_API_KEY`. The `api_key` query parameter still answers, but the documentation marks it deprecated.

## Route 1: meta tags

The cheapest route, and the one that survives redesigns, because these tags exist for Facebook and Google rather than for the app.

```python
import os, requests, json

rules = {
    "creator":  {"selector": "h1", "output": "text"},
    "title":    "title",
    "og_title": {"selector": 'meta[property="og:title"]', "output": "@content"},
    "og_desc":  {"selector": 'meta[name="description"]',   "output": "@content"},
}

r = requests.get(
    "https://app.scrapingbee.com/api/v1/",
    headers={"Authorization": f"Bearer {os.environ['SCRAPINGBEE_API_KEY']}"},
    params={
        "url": "https://www.patreon.com/kurzgesagt",
        "extract_rules": json.dumps(rules),
        "mode": "auto",
    },
)
print(r.json())
```

Live response:

```json
{
  "creator": "Kurzgesagt – In a Nutshell",
  "title": "Kurzgesagt – In a Nutshell — Creating Science Animation Videos | Patreon",
  "og_title": "Kurzgesagt – In a Nutshell — Creating Science Animation Videos",
  "og_desc": "Get more from Kurzgesagt – In a Nutshell on Patreon. Creating Science Animation Videos. Support Kurzgesagt – In a Nutshell and get exclusive access to their work."
}
```

Note the `title` splits cleanly on the em dash into creator name and campaign tagline, which is how you get the tagline as its own field without a second selector.

Cost was 5 credits, read from the `spb-cost` response header. `mode=auto` walked the ladder and settled on the JavaScript rung. It is worth knowing that `spb-initial-status-code` came back as `308`, because Patreon redirects the bare path to its canonical form. That is a redirect, not a block.

## Route 2: the structured data block

Patreon publishes a `ProfilePage` object in an `application/ld+json` script tag. It holds the complete about text, which the meta description truncates, plus both image sizes.

**`extract_rules` cannot read it.** This was tested directly:

```json
{"jsonld": {"selector": "script[type=\"application/ld+json\"]", "output": "@text"}}
```

returned `null`. Script tag contents are not addressable through the extraction rule engine. So route 2 means fetching the page and parsing the block yourself:

```python
import json, re

html = requests.get(
    "https://app.scrapingbee.com/api/v1/",
    headers={"Authorization": f"Bearer {os.environ['SCRAPINGBEE_API_KEY']}"},
    params={"url": "https://www.patreon.com/kurzgesagt", "mode": "auto"},
).text

for block in re.findall(
    r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S
):
    obj = json.loads(block)
    if obj.get("@type") == "ProfilePage":
        person = obj["mainEntity"]
        print(person["name"], person["alternateName"], person["url"])
        print(person["image"]["contentUrl"])
        print(person["description"][:200])
```

The live page carried six such blocks. Block order is not stable, so match on `@type` rather than index. Three types appeared: `ProfilePage` (the creator), `BreadcrumbList`, and an `Organization` block describing Patreon itself, which you almost certainly want to skip.

## Route 3: AI extraction

Useful when you do not want to maintain a parser, and honest about what it gives back:

```bash
curl -G "https://app.scrapingbee.com/api/v1/" \
  -H "Authorization: Bearer $SCRAPINGBEE_API_KEY" \
  --data-urlencode "url=https://www.patreon.com/kurzgesagt" \
  --data-urlencode 'ai_extract_rules={"creator_name":"the creator display name","about":"the about text","membership_tiers":{"type":"list","description":"each tier with name and monthly price"}}' \
  -d render_js=true -d premium_proxy=true
```

`creator_name` and `about` came back complete and correct. `membership_tiers` came back as a single element list:

```json
["Access exclusive benefits starting at $3.14/month"]
```

That is the entry price teaser Patreon renders on the campaign page, not the tier breakdown. The full tier cards are mounted by a component that had not rendered at capture time, so the model described what was actually on the page. Cost was 30 credits: 25 for premium plus JavaScript, plus 5 for the AI query. Read more on [AI data extraction](https://www.scrapingbee.com/features/ai-web-scraping-api/).

If you only need the entry price, route 3 is a reasonable trade. If you need every tier, use route 4.

## Route 4: the bootstrap payload

Patreon ships its own application state into the page as double escaped JSON, and the complete tier list lives in there. This is the route that gets you everything route 3 could not.

The tier objects sit inside `"attributes"` blocks. Brace match them rather than regexing individual fields, then filter to the blocks that carry tier keys:

```python
import json, re

raw = html.encode("utf-8", "ignore").decode("unicode_escape", "ignore")

tiers = []
for match in re.finditer(r'"attributes":\{', raw):
    start, depth = match.end() - 1, 0
    for i in range(start, start + 8000):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                blob = raw[start:i + 1]
                if "declined_patron_count" in blob:
                    tiers.append(json.loads(blob))
                break

for t in sorted(tiers, key=lambda t: t["amount_cents"]):
    print(t["title"], t["amount_cents"] / 100, t["currency"], t["post_count"])
```

Live output, four tiers:

```
Free              0.0   USD   8 posts
Trainee Producer  3.14  USD   1 post
Producer          15.0  USD   62 posts
Senior Producer   42.0  USD   58 posts
```

That `3.14` is the same number route 3's AI extraction reported as the teaser string `Access exclusive benefits starting at $3.14/month`, which is a useful cross check that both routes are reading the same page correctly.

### The field that is not what it looks like

Every tier object carries these keys:

```
amount_cents  currency  title  description  url  image_url
is_free_tier  post_count  published  requires_shipping
declined_patron_count  patron_amount_cents  patron_currency
discord_role_ids  remaining  user_limit
```

**`declined_patron_count` is not the tier's patron count.** It counts declined payments. On the page tested it read 2, 31, 14 and 0 across the four tiers, which is nothing like a membership number for a creator of that size. There is no public per tier patron count in this payload, so if you need one, it is not available here and should not be inferred from this field.

`amount_cents` with `currency` is the tier price, and it is the pair to trust. `patron_amount_cents` and `patron_currency` also appear, reading `800` and `DKK` on the free tier, which does not correspond to the tier price, so pass those through raw rather than interpreting them.

`remaining` and `user_limit` were both null on every tier tested. They exist for limited availability tiers, so expect real values on creators who cap a tier.

### Brittleness

This reads a private application format that Patreon has no obligation to keep stable. Gate it behind a check that falls back to route 1 when nothing matches, rather than letting an empty list read as a creator with no tiers.

## Ready made packages

```bash
pip install patreon-scraper-api
npm install patreon-scraper-api
```

```python
from patreon_scraper_api import PatreonScraper

bee = PatreonScraper("YOUR_API_KEY")

bee.creator("kurzgesagt")      # route 1, 5 credits, name and tagline
bee.profile("kurzgesagt")      # route 2, full about text, 4,476 chars live
bee.tiers("kurzgesagt")        # route 4, all four tiers, route 1 fallback
bee.price_ladder("kurzgesagt") # tier titles with prices in major units
bee.entry_tier("kurzgesagt")   # cheapest paid tier, skips the free one
bee.entry_price("kurzgesagt")  # route 3, 30 credits, the teaser string
```

## Choosing a route

Pick by the field you need, not by preference:

- Just the name and tagline for a directory or a monitoring dashboard: route 1. It is 5 credits and it does not break.
- The full about copy, for search or embeddings: route 2.
- Entry price only, with no parser to own: route 3.
- Every tier, its price and its post count: route 4.

Combining routes 1 and 2 in one request is possible because they read the same fetched page. Ask for `extract_rules` and keep the HTML by adding nothing, or just fetch raw and run both parsers locally for a single 5 credit charge.

## Credit cost

Measured on live calls:

| Configuration | Credits |
|---|---|
| `mode=auto` on a creator page, settled at the JavaScript rung | 5 |
| `render_js=true` plus `premium_proxy=true` | 25 |
| The same plus `ai_extract_rules` | 30 |
| Validation error (bad parameter) | 0 |

Auto mode is worth defaulting to here, because it charges only for the configuration that worked. Note that `mode=auto` is incompatible with `render_js`, `premium_proxy` and `stealth_proxy`. Sending both returns HTTP 400 and bills nothing, which fails quietly if you are not reading status codes. Plan tiers are on the [pricing page](https://www.scrapingbee.com/pricing).

## Also worth reading

Rate of change on Patreon's front end is high, so build the fallbacks before you need them. ScrapingBee's own roundup of [Patreon scraping approaches](https://www.scrapingbee.com/blog/best-patreon-scrapers/) covers the tooling landscape, the [extraction rules reference](https://www.scrapingbee.com/documentation/data-extraction/) covers the selector syntax used in route 1, and [Patreon's Community Guidelines](https://www.patreon.com/policy/guidelines) and [Terms of Use](https://www.patreon.com/policy/legal) govern what you may do with creator data once you hold it.

## FAQ

**Is there an official Patreon API?**
Patreon publishes an OAuth API for creators to read their own campaign and member data. It is the right tool when you own the campaign or have the creator's consent. This project covers the public page surface instead, for cases where you do not have that access and are only reading what Patreon shows anonymously.

**Can I get a list of a creator's patrons?**
No. Member identities are not public, are not reachable without signing in, and are out of scope for the reasons in the scope section.

**Why is my tier list empty?**
Because `[data-tag="tier-title"]` returns an empty array on the live page. That selector was tested and does not match. Use route 4 for tier data.

**How many patrons does a creator have?**
Not available from the public page. The only count in the payload is `declined_patron_count`, which is declined payments rather than members, and reporting it as a patron count would be wrong. Post counts per tier are available and real.

**Which credit tier do I need for this?**
Route 1 at 5 credits per creator means 250,000 credits covers 50,000 creator checks. That is inside the entry paid plan.

## Credits

Built and maintained by [wordstotech](https://github.com/wordstotech-design). Powered by ScrapingBee.

## License

MIT. See [LICENSE](LICENSE).
