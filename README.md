# channel-activity

Check when YouTube channels last uploaded, using only public data.

Give it a list of channel handles or channel IDs. For each one it resolves the
channel ID from the public channel page, reads YouTube's public RSS feed, and
reports the most recent upload date.

No API key. No login. No scraping of anything that isn't public — the feed at
`/feeds/videos.xml` is the same one any feed reader uses. Python 3, standard
library only, no dependencies.

## Use

```bash
python3 channel_activity.py @SomeChannel @AnotherChannel
python3 channel_activity.py --file examples/handles.txt > out.csv
```

CSV goes to stdout, a summary to stderr, so you can redirect one without losing
the other:

```
input,channel_id,channel_title,last_upload,days_since,feed_entries,note
@CryptidHollow,UCaZ7cY6umnKDmZMdWLhGqnQ,Cryptid Hollow,2026-09-06,2,15,
@HistoryHacksShorts,UCvZeMY-woUfza36l9tVEFLg,HistoryHacksShorts,2026-04-04,157,9,
@somechannelwithnovideos,UCXk...,SecretZone,,,0,no public uploads in feed
```

```
Resolved 3 of 3 channels.
  uploaded within 7 days      1 / 3  ( 33%)
  uploaded within 30 days     1 / 3  ( 33%)
  silent over 90 days         1 / 3  ( 33%)
  median days since upload  157
```

`--delay` sets the pause between channels (default 1 second). Please leave it
at something polite if you are checking more than a handful.

## The gotcha worth knowing

YouTube's feed carries **one channel-level `<published>`** — the date the channel
was created — in addition to one date per video. If you count every `<published>`
in the document you will report one video too many for every channel, and for a
channel with no uploads at all you will report its creation date as an upload.

Read `<published>` only from inside `<entry>` elements. This script does. We got
it wrong the first time, which is why it is called out here.

## Limits

The feed returns at most **15** recent videos. So `feed_entries` is a floor, not
a total: 15 means "at least 15", anything less is the channel's whole history.
That cap is useful — it splits channels into "published fewer than 15 ever" and
"published more" for free — but it is an artefact of the feed, not a meaningful
threshold in itself.

Deleted, private and members-only videos do not appear. A channel can be active
in ways this does not see (community posts, livestreams that were not kept).
"Last upload" means "most recent public video in the feed", nothing more.

## Why this exists

It produced the numbers in
[We checked 115 faceless YouTube channels — 47% had stopped posting](https://plotclip.com/resources/faceless-channels-that-stopped-posting),
and it is published so anyone can check that work or run it on their own list.

Built by [PlotClip](https://plotclip.com).

## Licence

MIT — see [LICENSE](LICENSE).
