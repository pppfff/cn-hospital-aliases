"""Collect primary website evidence for the current top-1000 review targets.

This is an evidence collection pass, not an automatic alias approval. Robots
rules, TLS errors, access challenges and rate limits are respected. Only the
URLs already supplied in ROR metadata are visited, plus their robots.txt.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import csv
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from cn_hospital_aliases.normalizer import normalize_name

USER_AGENT = "HospitalNameResearch/0.3"
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/raw/official_sites"
_locks, _last_request = {}, {}
_guard = threading.Lock()


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.headings, self.title = [], [], []
        self.skip, self.in_title, self.in_heading = 0, False, False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2"}:
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2"}:
            self.in_heading = False

    def handle_data(self, data):
        if self.skip:
            return
        data = " ".join(data.split())
        if not data:
            return
        self.parts.append(data)
        if self.in_title:
            self.title.append(data)
        if self.in_heading:
            self.headings.append(data)


def _request(url):
    host = urlparse(url).netloc
    with _guard:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        delay = max(0.0, 2.0 - (time.monotonic() - _last_request.get(host, 0)))
        if delay:
            time.sleep(delay)
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=12) as response:
                return response.status, response.geturl(), response.headers, response.read(3_000_000)
        finally:
            _last_request[host] = time.monotonic()


def collect(url, cached_only=False):
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    path = CACHE / (digest + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = {"requested_url": url, "checked_at": datetime.now(timezone.utc).isoformat(), "status": "unreadable", "title": "", "headings": [], "text": "", "automatic_identity_approval": False}
    if cached_only:
        return {**result, "status": "not_checked", "checked_at": ""}
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Unsupported URL scheme")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = origin + "/robots.txt"
        try:
            status, _, _, body = _request(robots_url)
            if status != 200:
                raise ValueError(f"robots returned HTTP {status}")
            if re.search(br"<html|<!doctype|<script", body[:8192], re.I):
                raise ValueError("robots URL returned HTML instead of crawl rules")
            robots = RobotFileParser()
            robots.parse(body.decode("utf-8", errors="replace").splitlines())
            if not robots.can_fetch(USER_AGENT, url):
                result["status"] = "robots_disallowed"
                raise ValueError("robots.txt disallows this URL")
            crawl_delay = robots.crawl_delay(USER_AGENT) or robots.crawl_delay("*") or 0
            if crawl_delay > 2:
                if crawl_delay > 60:
                    raise ValueError("Long robots crawl delay; defer this website to manual review")
                time.sleep(crawl_delay)
        except HTTPError as error:
            if error.code not in {404, 410}:
                raise
        status, final_url, headers, body = _request(url)
        result.update(http_status=status, final_url=final_url, response_sha256=hashlib.sha256(body).hexdigest())
        if status != 200:
            raise ValueError(f"Website returned HTTP {status}")
        content_type = headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise ValueError("URL did not return an HTML website")
        encoding = headers.get_content_charset()
        if not encoding:
            match = re.search(br'charset\s*=\s*[\"\x27]?([\w-]+)', body[:8192], re.I)
            encoding = match.group(1).decode("ascii") if match else "utf-8"
        page = PageText()
        page.feed(body.decode(encoding, errors="replace"))
        text = " ".join(page.parts)
        title = " | ".join(page.title)
        if len(text) < 80 or re.search(r"just a moment|checking your browser|访问验证|人机验证|安全验证|域名出售|域名已到期", title, re.I):
            result["status"] = "challenge_or_noncontent"
            raise ValueError("No usable public institution text")
        result.update(status="readable", title=title[:1000], headings=page.headings[:30], text=text[:150_000])
    except Exception as error:
        result["error"] = str(error)[:400]
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-only", action="store_true", help="reconcile cached evidence to the current master without any network calls")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    with (ROOT / "data/master/top1000_review.csv").open(encoding="utf-8-sig", newline="") as handle:
        priorities = list(csv.DictReader(handle))
    with (ROOT / "data/master/top1000_candidates.csv").open(encoding="utf-8-sig", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    with sqlite3.connect(ROOT / "data/master/hospital_master.sqlite") as db:
        websites = dict(db.execute("SELECT hospital_id,website FROM institutions WHERE website!=''").fetchall())
        names = {}
        for key, name in db.execute("SELECT hospital_id,name FROM names"):
            names.setdefault(key, set()).add(name)
    targets = {row["hospital_id"] for row in priorities} | {row["candidate_hospital_id"] for row in candidates}
    urls = sorted({websites[key] for key in targets if websites.get(key)})
    print(f"Collecting {len(urls)} unique primary website URLs for top-1000 targets/candidates", flush=True)
    pages = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(collect, url, args.cached_only): url for url in urls}
        for n, future in enumerate(as_completed(futures), 1):
            pages[futures[future]] = future.result()
            if n % 25 == 0 or n == len(urls):
                print(f"Checked {n}/{len(urls)} websites", flush=True)
    result_rows = []
    for key in sorted(targets):
        if not websites.get(key):
            continue
        page = pages[websites[key]]
        normalized = normalize_name(page["text"])
        matched_names = [name for name in sorted(names.get(key, set())) if len(normalize_name(name)) >= 6 and normalize_name(name) in normalized]
        result_rows.append({"hospital_id": key, "website": websites[key], "status": page["status"], "title": page["title"], "matched_reference_names": " | ".join(matched_names), "checked_at": page["checked_at"], "automatic_identity_approval": False, "error": page.get("error", "")})
    output = ROOT / "data/master/official_website_checks.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]) if result_rows else ["hospital_id"])
        writer.writeheader()
        writer.writerows(result_rows)
    from collections import Counter
    summary = {"unique_urls": len(urls), "institution_targets": len(result_rows), "results": dict(Counter(page["status"] for page in pages.values())), "automatic_identity_approvals": 0}
    (ROOT / "data/master/official_website_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    checks = {row["hospital_id"]: row for row in result_rows}
    candidates_by_target = {}
    for row in candidates:
        candidates_by_target.setdefault(row["hospital_id"], set()).add(row["candidate_hospital_id"])
    progress = []
    for row in priorities:
        key = row["hospital_id"]
        direct = checks.get(key, {})
        candidate_checks = [checks[target] for target in candidates_by_target.get(key, []) if target in checks]
        progress.append({"priority_rank": row["priority_rank"], "hospital_id": key, "canonical_name": row["canonical_name"], "ranking_basis": row["ranking_basis"], "review_status": row["review_status"], "website_status": direct.get("status", "no_reference_website"), "website": direct.get("website", ""), "candidate_website_checks": sum(item["status"] != "not_checked" for item in candidate_checks), "readable_candidate_websites": sum(item["status"] == "readable" for item in candidate_checks), "fields_to_check": row["fields_to_check"], "automatic_identity_approval": False})
    with (ROOT / "data/master/top1000_audit_progress.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(progress[0]) if progress else ["hospital_id"])
        writer.writeheader()
        writer.writerows(progress)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
