#!/usr/bin/env python3
"""Pull every post from the 7° andar Substack into data/posts.json.

Run by the deploy workflow before each build, so new episodes show up on the
site without anyone editing the repo. Uses only the standard library.
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

PUB = "https://7andar.substack.com"
YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=UC3nN6VoaDGo8v8WUihqoMLw"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (setimoandar.com site build)"}


def get(url, as_json=True):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read()
    return json.loads(body) if as_json else body


def list_slugs():
    """Archive API pages of 12; fall back to the sitemap for anything beyond."""
    slugs = []
    first = get(f"{PUB}/api/v1/archive?sort=new&limit=12")
    posts = first["posts"] if isinstance(first, dict) else first
    slugs += [p["slug"] for p in posts]
    try:
        xml = get(f"{PUB}/sitemap.xml", as_json=False).decode()
        for slug in re.findall(r"/p/([a-z0-9-]+)</loc>", xml):
            if slug not in slugs:
                slugs.append(slug)
    except Exception as e:  # sitemap is a nice-to-have
        print("sitemap failed:", e, file=sys.stderr)
    return slugs


def youtube_ids():
    """Map episode number -> YouTube video id from the channel RSS (latest 15)."""
    out = {}
    try:
        root = ET.fromstring(get(YT_FEED, as_json=False))
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        for e in root.findall("a:entry", ns):
            title = e.findtext("a:title", "", ns)
            vid = e.findtext("yt:videoId", "", ns)
            m = re.match(r"\D*(\d+)\s*\|", title)
            if m and vid:
                out[m.group(1)] = vid
    except Exception as e:
        print("youtube feed failed:", e, file=sys.stderr)
    return out


def main():
    keep = ("id", "slug", "title", "subtitle", "description", "type", "post_date",
            "podcast_url", "podcast_duration", "podcast_episode_image_url",
            "cover_image", "body_html", "canonical_url", "audience", "wordcount")
    posts = []
    for slug in list_slugs():
        p = get(f"{PUB}/api/v1/posts/{slug}")
        if p.get("audience") not in (None, "everyone"):
            continue
        posts.append({k: p.get(k) for k in keep})
    posts.sort(key=lambda p: p["post_date"], reverse=True)
    with open(os.path.join(ROOT, "data", "posts.json"), "w") as f:
        json.dump(posts, f, ensure_ascii=False, indent=1)

    # Fill in YouTube ids for new episodes without touching curated data.
    extra_path = os.path.join(ROOT, "data", "episodes-extra.json")
    extra = json.load(open(extra_path))
    for num, vid in youtube_ids().items():
        extra.setdefault(num, {}).setdefault("youtube", vid)
    with open(extra_path, "w") as f:
        json.dump(extra, f, ensure_ascii=False, indent=1)
    print(f"synced {len(posts)} posts")


if __name__ == "__main__":
    main()
