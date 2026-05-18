import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests


DEFAULT_NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
]

NEWS_ENABLED = str(os.environ.get("ENABLE_NEWS_SENTIMENT", "true")).lower() in {"1", "true", "yes", "on"}
NEWS_LOOKBACK_HOURS = int(os.environ.get("NEWS_LOOKBACK_HOURS", "36"))
NEWS_TIMEOUT_SECONDS = float(os.environ.get("NEWS_TIMEOUT_SECONDS", "8"))
NEWS_MAX_ITEMS = int(os.environ.get("NEWS_MAX_ITEMS", "50"))

ASSET_KEYWORDS = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum", "ether"),
    "SOL": ("sol", "solana"),
    "XRP": ("xrp", "ripple"),
    "BNB": ("bnb", "binance"),
    "ADA": ("ada", "cardano"),
    "DOGE": ("doge", "dogecoin"),
    "DOT": ("dot", "polkadot"),
    "MATIC": ("matic", "polygon"),
    "AVAX": ("avax", "avalanche"),
    "LINK": ("link", "chainlink"),
    "PEPE": ("pepe",),
    "SHIB": ("shib", "shiba inu"),
    "BONK": ("bonk",),
    "FLOKI": ("floki",),
    "LUNC": ("lunc", "terra luna classic"),
    "BTT": ("btt", "bittorrent"),
}

POSITIVE_KEYWORDS = (
    "approved", "approval", "etf inflow", "inflows", "partnership", "adoption",
    "launch", "upgrade", "integrates", "listing", "record high", "all-time high",
    "rally", "surge", "surges", "bullish", "breakout", "funding", "treasury",
    "accumulation", "buys", "buying", "institutional",
)

NEGATIVE_KEYWORDS = (
    "hack", "exploit", "lawsuit", "sues", "sec sues", "ban", "banned", "crackdown",
    "outflow", "outflows", "liquidation", "sell-off", "plunge", "plunges", "falls",
    "crash", "bearish", "fraud", "bankruptcy", "delist", "delisting", "halt",
    "investigation", "charged", "charges", "scam", "stolen", "attack",
)


def _configured_feeds():
    raw = os.environ.get("NEWS_FEEDS", "").strip()
    if not raw:
        return DEFAULT_NEWS_FEEDS
    feeds = []
    for idx, url in enumerate(raw.split(","), start=1):
        url = url.strip()
        if url:
            feeds.append((f"Feed {idx}", url))
    return feeds or DEFAULT_NEWS_FEEDS


def _strip_html(value):
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def _sentiment_score(text):
    low = text.lower()
    score = 0
    hits = []
    for word in POSITIVE_KEYWORDS:
        if word in low:
            score += 1
            hits.append(word)
    for word in NEGATIVE_KEYWORDS:
        if word in low:
            score -= 1
            hits.append(word)
    return max(-5, min(5, score)), hits[:5]


def _label(score):
    if score >= 3:
        return "POSITIVE"
    if score >= 1:
        return "MILD POSITIVE"
    if score <= -3:
        return "NEGATIVE"
    if score <= -1:
        return "MILD NEGATIVE"
    return "NEUTRAL"


def _symbols_for_text(text, symbols=None):
    low = text.lower()
    wanted = set(symbols or ASSET_KEYWORDS)
    matched = []
    for symbol, keywords in ASSET_KEYWORDS.items():
        if symbol not in wanted:
            continue
        if any(re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", low) for keyword in keywords):
            matched.append(symbol)
    return matched


def fetch_news_articles(symbols=None):
    if not NEWS_ENABLED:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 KriptoMania/1.0"}

    for source, url in _configured_feeds():
        try:
            resp = requests.get(url, timeout=NEWS_TIMEOUT_SECONDS, headers=headers)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            continue

        for item in root.findall(".//item"):
            title = _strip_html(item.findtext("title"))
            link = _strip_html(item.findtext("link"))
            summary = _strip_html(item.findtext("description"))
            published = _parse_date(item.findtext("pubDate"))
            if published and published < cutoff:
                continue
            text = f"{title} {summary}"
            score, keywords = _sentiment_score(text)
            matched = _symbols_for_text(text, symbols)
            articles.append({
                "source": source,
                "title": title,
                "link": link,
                "summary": summary[:240],
                "published": published.isoformat() if published else None,
                "score": score,
                "label": _label(score),
                "keywords": keywords,
                "symbols": matched,
            })

    articles.sort(key=lambda a: (a.get("published") or "", abs(a.get("score", 0))), reverse=True)
    return articles[:NEWS_MAX_ITEMS]


def build_news_profile(symbols=None):
    articles = fetch_news_articles(symbols=symbols)
    if not articles:
        return {
            "enabled": NEWS_ENABLED,
            "global_score": 0,
            "global_label": "NO DATA",
            "articles": [],
            "by_symbol": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    scored = [a for a in articles if a.get("score")]
    global_score = round(sum(a["score"] for a in scored) / max(1, len(scored)), 2)
    by_symbol = {}
    for article in articles:
        for symbol in article.get("symbols", []):
            stats = by_symbol.setdefault(symbol, {"score_sum": 0, "hits": 0, "headlines": []})
            stats["score_sum"] += article.get("score", 0)
            stats["hits"] += 1
            if len(stats["headlines"]) < 3:
                stats["headlines"].append({
                    "title": article.get("title"),
                    "source": article.get("source"),
                    "score": article.get("score", 0),
                    "label": article.get("label"),
                    "link": article.get("link"),
                })

    for stats in by_symbol.values():
        stats["score"] = round(stats["score_sum"] / max(1, stats["hits"]), 2)
        stats["label"] = _label(stats["score"])

    return {
        "enabled": NEWS_ENABLED,
        "global_score": global_score,
        "global_label": _label(global_score),
        "articles": articles[:12],
        "by_symbol": by_symbol,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def apply_news_adjustments(items, profile=None):
    profile = profile or build_news_profile(symbols=[i.get("symbol") for i in items if isinstance(i, dict)])
    by_symbol = profile.get("by_symbol", {})
    for item in items:
        symbol = item.get("symbol")
        stats = by_symbol.get(symbol)
        score = stats.get("score") if stats else profile.get("global_score", 0) * 0.35
        score = float(score or 0)
        if score >= 3:
            adjustment = 4
        elif score >= 1:
            adjustment = 2
        elif score <= -3:
            adjustment = -6
        elif score <= -1:
            adjustment = -3
        else:
            adjustment = 0

        headline = ""
        if stats and stats.get("headlines"):
            headline = stats["headlines"][0]["title"]
        item["news_score"] = round(score, 2)
        item["news_label"] = _label(score)
        item["news_adjustment"] = adjustment
        item["news_headline"] = headline

        if adjustment:
            item["score"] = int(max(0, min(100, int(item.get("score", 0)) + adjustment)))
            alloc_key = "allocation_pct" if "allocation_pct" in item else "alloc_pct" if "alloc_pct" in item else None
            if alloc_key and float(item.get(alloc_key, 0) or 0) > 0:
                item[alloc_key] = round(max(0, min(10, float(item[alloc_key]) * (1 + adjustment / 30))), 1)
        if adjustment <= -6 and str(item.get("action", "")).upper() in {"BELI KUAT", "CICIL BELI"}:
            item["action"] = "WATCH"
            item["emoji"] = "⚪"
            if "allocation_pct" in item:
                item["allocation_pct"] = 0
            if "alloc_pct" in item:
                item["alloc_pct"] = 0
    return items
