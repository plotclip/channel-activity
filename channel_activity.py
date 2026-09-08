#!/usr/bin/env python3
"""Check when YouTube channels last uploaded, using only public data.

Give it a list of channel handles or channel IDs. For each one it resolves the
channel ID from the public channel page, reads YouTube's public RSS feed, and
reports the most recent upload date.

No API key, no login, no scraping of anything that isn't public. The RSS feed
at /feeds/videos.xml is the same one any feed reader uses.

    python3 channel_activity.py @SomeChannel @AnotherChannel
    python3 channel_activity.py --file handles.txt > out.csv

Output is CSV on stdout; a summary goes to stderr so you can redirect one
without losing the other.

Written to make the numbers in this article reproducible:
https://plotclip.com/resources/faceless-channels-that-stopped-posting
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

CHANNEL_URL = "https://www.youtube.com/@{}"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# YouTube's feed returns at most 15 recent videos. A channel whose feed is full
# has published AT LEAST that many; a shorter feed is the channel's whole history.
FEED_CAP = 15

ID_RE = re.compile(r"^UC[\w-]{22}$")
EXTERNAL_ID_RE = re.compile(r'"externalId":"(UC[\w-]{22})"')
# The feed carries ONE channel-level <published> (when the channel was created) in
# addition to one per <entry>. Counting them all overstates the video count by one,
# and on a channel with no videos it would report the creation date as an upload.
# So parse entries first and only read <published> from inside them.
ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
PUBLISHED_RE = re.compile(r"<published>([^<]+)</published>")
TITLE_RE = re.compile(r"<title>([^<]*)</title>")


def _get(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def resolve_channel_id(handle: str, timeout: float) -> str | None:
    """Handle -> channel ID. Returns None if the channel page has no ID in it,
    which in practice means the handle does not exist."""
    handle = handle.lstrip("@")
    try:
        page = _get(CHANNEL_URL.format(handle), timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    m = EXTERNAL_ID_RE.search(page)
    return m.group(1) if m else None


def read_feed(channel_id: str, timeout: float) -> tuple[str, list[dt.date]]:
    """Channel ID -> (channel title, upload dates newest last)."""
    xml = _get(FEED_URL.format(channel_id), timeout)
    titles = TITLE_RE.findall(xml)
    dates = []
    for entry in ENTRY_RE.findall(xml):
        m = PUBLISHED_RE.search(entry)
        if m:
            dates.append(dt.date.fromisoformat(m.group(1)[:10]))
    # The feed's first <title> is the channel; the rest are videos.
    return (titles[0].strip() if titles else ""), sorted(dates)


def check(target: str, today: dt.date, timeout: float) -> dict:
    row = {"input": target, "channel_id": "", "channel_title": "",
           "last_upload": "", "days_since": "", "feed_entries": "", "note": ""}
    target = target.strip()
    if not target or target.startswith("#"):
        return {}
    try:
        cid = target if ID_RE.match(target) else resolve_channel_id(target, timeout)
        if not cid:
            row["note"] = "channel not found"
            return row
        row["channel_id"] = cid
        title, dates = read_feed(cid, timeout)
        row["channel_title"] = title
        row["feed_entries"] = len(dates)
        if dates:
            row["last_upload"] = dates[-1].isoformat()
            row["days_since"] = (today - dates[-1]).days
        else:
            row["note"] = "no public uploads in feed"
    except Exception as e:                      # network, decoding, malformed feed
        row["note"] = f"{type(e).__name__}: {e}"
    return row


def summarise(rows: list[dict], out) -> None:
    ok = [r for r in rows if r.get("days_since") != "" and r.get("days_since") is not None]
    if not ok:
        print("No channels resolved.", file=out)
        return
    n = len(ok)
    days = [r["days_since"] for r in ok]

    def share(pred) -> str:
        k = sum(1 for d in days if pred(d))
        return f"{k:>4} / {n}  ({round(100 * k / n):>3}%)"

    print(f"\nResolved {n} of {len(rows)} channels.", file=out)
    print(f"  uploaded within 7 days   {share(lambda d: d <= 7)}", file=out)
    print(f"  uploaded within 30 days  {share(lambda d: d <= 30)}", file=out)
    print(f"  silent over 90 days      {share(lambda d: d > 90)}", file=out)
    print(f"  silent over a year       {share(lambda d: d > 365)}", file=out)
    print(f"  median days since upload {int(statistics.median(days))}", file=out)

    # The feed cap gives a free split: a short feed is the channel's whole history.
    small = [r for r in ok if r["feed_entries"] < FEED_CAP]
    big = [r for r in ok if r["feed_entries"] >= FEED_CAP]
    for label, group in ((f"under {FEED_CAP} uploads ever", small),
                         (f"{FEED_CAP}+ uploads", big)):
        if not group:
            continue
        d = [r["days_since"] for r in group]
        active = sum(1 for x in d if x <= 30)
        print(f"  {label:<22} n={len(group):>4} | still posting {round(100*active/len(d)):>3}%"
              f" | median silence {int(statistics.median(d)):>4} days", file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("channels", nargs="*", help="handles (@name) or channel IDs (UC...)")
    ap.add_argument("--file", "-f", help="file with one handle or channel ID per line; "
                                         "blank lines and lines starting with # are skipped")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds between channels (default 1.0; be polite)")
    ap.add_argument("--timeout", type=float, default=20.0, help="per-request timeout")
    args = ap.parse_args()

    targets = list(args.channels)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            targets += [ln.strip() for ln in fh]
    targets = [t for t in targets if t and not t.startswith("#")]
    if not targets:
        ap.error("give at least one channel, or --file")

    today = dt.date.today()
    writer = csv.DictWriter(sys.stdout, fieldnames=["input", "channel_id", "channel_title",
                                                    "last_upload", "days_since",
                                                    "feed_entries", "note"])
    writer.writeheader()
    rows = []
    for i, t in enumerate(targets):
        row = check(t, today, args.timeout)
        if not row:
            continue
        rows.append(row)
        writer.writerow(row)
        sys.stdout.flush()
        print(f"[{i+1}/{len(targets)}] {t}", file=sys.stderr)
        if i + 1 < len(targets):
            time.sleep(args.delay)

    summarise(rows, sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
