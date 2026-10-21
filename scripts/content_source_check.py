"""FOOD-01 reproducible source check for food-description drafts.

fetch    Download every cited source into ignored data/processed/FOOD-01-sources/ (Wikipedia
         by the pinned oldid through the public API, other pages over HTTPS) and record
         SHA-256, HTTP status and fetch time. Text is untrusted data for human reviewers.
overlap  Compare each cited field with its fetched source text and fail when a draft repeats
         a long word sequence verbatim (copy risk). This is an aid for reviewers, not a review.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from food_content import CONTENT, FIELDS, load, validate

OUT = ROOT / 'data/processed/FOOD-01-sources'
AGENT = 'FoodLensSourceCheck/1.0 (student project; local verification)'
MAX_SHARED_WORDS = 8


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.skip += 1
        elif tag in ('p', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'div', 'tr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible(html):
    parser = Text()
    parser.feed(html)
    return re.sub(r'\n\s*\n+', '\n', ''.join(parser.parts))


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            time.sleep(int(exc.headers.get('Retry-After') or 20) + 5)


def fetch(document):
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for source in document['sources']:
        url = source['url']
        if source['source_kind'] == 'open_license_encyclopedia':
            parts = urllib.parse.urlsplit(url)
            oldid = urllib.parse.parse_qs(parts.query)['oldid'][0]
            api = f'https://{parts.netloc}/w/api.php?' + urllib.parse.urlencode(
                dict(action='parse', oldid=oldid, prop='text', format='json', formatversion=2))
            status, raw = get(api)
            text = visible(json.loads(raw)['parse']['text'])
            time.sleep(3)
        else:
            status, raw = get(url)
            text = visible(raw.decode('utf-8', 'replace'))
        (OUT / (source['source_key'] + '.txt')).write_text(text, encoding='utf-8')
        records.append(dict(source_key=source['source_key'], url=url, http_status=status, raw_sha256=hashlib.sha256(raw).hexdigest(),
                            text_chars=len(text), fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds')))
        print(f"{source['source_key']}: HTTP {status}, {len(text)} chars")
    report = dict(task='FOOD-01', content_sha256=hashlib.sha256(CONTENT.read_bytes()).hexdigest(), sources=records)
    (OUT.parent / 'FOOD-01-source-fetch.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return records


def words(text):
    text = unicodedata.normalize('NFC', text).lower()
    return re.findall(r'\w+', text)


def longest_shared(a, b):
    """Longest run of consecutive identical words between a draft field and source text."""
    best, previous = 0, {}
    for x in a:
        current = {}
        for j, y in enumerate(b):
            if x == y:
                current[j] = previous.get(j - 1, 0) + 1
                best = max(best, current[j])
        previous = current
    return best


def overlap(document):
    findings = []
    for entry in document['descriptions']:
        for ref in entry['sources']:
            path = OUT / (ref['source_key'] + '.txt')
            if not path.exists():
                raise FileNotFoundError('Run fetch first: ' + ref['source_key'])
            source_words = words(path.read_text(encoding='utf-8'))
            for field in ref['supports']:
                shared = longest_shared(words(entry[field]), source_words)
                if shared >= MAX_SHARED_WORDS:
                    findings.append(dict(slug=entry['slug'], field=field, source_key=ref['source_key'], shared_words=shared))
    report = dict(task='FOOD-01', threshold_words=MAX_SHARED_WORDS, checked_entries=len(document['descriptions']), findings=findings,
                  content_sha256=hashlib.sha256(CONTENT.read_bytes()).hexdigest(), status='passed' if not findings else 'failed')
    (OUT.parent / 'FOOD-01-overlap.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return findings


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['fetch', 'overlap'])
    args = parser.parse_args()
    document = load()
    validate(document)
    if args.command == 'fetch':
        fetch(document)
        return 0
    findings = overlap(document)
    for f in findings:
        print(f"{f['slug']}.{f['field']} shares {f['shared_words']} consecutive words with {f['source_key']}")
    print(f"Overlap check: {len(findings)} findings (threshold {MAX_SHARED_WORDS} words)")
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
