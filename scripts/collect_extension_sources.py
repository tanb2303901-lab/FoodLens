"""Collect versioned public source assets for ML-05. Never training-ready labels.

Only writes the new ignored extension directory. Original VietFood and its seven
CSVs are never touched. Commons results are candidates requiring semantic/bbox
review; downloaded metadata or filenames are not ground-truth annotations.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/food-extension-v2'
META = OUT / 'source-metadata'
UA = 'FoodLens-Academic-Dataset-Preparation/1.0 (local academic research)'
QUERIES = {
    'grilled_chicken_breast': ['"grilled chicken breast" -"Healthy Choice"', '"roasted chicken breast"', '"chicken breast" grilled -"Healthy Choice"',
        '"pechuga" "plancha"', '"pechuga" "parrilla"', '"Hähnchenbrust" gegrillt',
        '"blanc de poulet" grillé', '"peito de frango" grelhado', '"petto di pollo" griglia',
        'intitle:"chicken breast"', 'intitle:"Hähnchenbrust"'],
    'grilled_salmon': ['"grilled salmon"', '"baked salmon"'],
    'soft_drink': ['"soft drink" bottle', '"Coca-Cola" can', '"Pepsi" glass', '"soda drink"'],
    'sweet_potato': ['"sweet potato" cooked', '"sweet potato" boiled',
        'intitle:"sweet potato" -intitle:leaves -intitle:flower -intitle:plant',
        '"khoai lang"', '"baked sweet potato"', '"roasted sweet potato"'],
    'coffee': ['"Vietnamese coffee"', '"iced coffee"'],
}


def validate_image(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.width * image.height > 20_000_000 or image.width > 8192 or image.height > 8192:
            raise ValueError('Source image exceeds safe decode limits')
        image.load()  # JPEG verify() alone does not detect truncated pixel data.


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def fetch(url, path, expected=None, expected_size=None):
    if path.exists():
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Cached source checksum mismatch: ' + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    if url.endswith('.parquet') and 'huggingface.co/' in url:
        url += '?download=true'
    for attempt in range(32):
        offset = temp.stat().st_size if temp.exists() else 0
        headers = {'User-Agent': UA}
        if offset:
            headers['Range'] = 'bytes=' + str(offset) + '-'
        try:
            with urlopen(Request(url, headers=headers), timeout=35) as response:
                resumed = offset and response.status == 206
                if resumed and not response.headers.get('Content-Range', '').startswith('bytes ' + str(offset) + '-'):
                    raise ValueError('Invalid source resume offset')
                content_range = response.headers.get('Content-Range', '')
                total = expected_size
                if '/' in content_range and content_range.rsplit('/', 1)[1].isdigit():
                    total = int(content_range.rsplit('/', 1)[1])
                elif not resumed and response.headers.get('Content-Length', '').isdigit():
                    total = total or int(response.headers['Content-Length'])
                with temp.open('ab' if resumed else 'wb') as target:
                    while block := response.read(1024 * 1024):
                        target.write(block)
            if total and temp.stat().st_size < total:
                # Some source/CDN responses terminate without IncompleteRead, or
                # serve a bounded range. EOF is not proof the asset is complete.
                continue
            if total and temp.stat().st_size != total:
                raise ValueError('Source byte length mismatch')
            break
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 31:
                raise
            time.sleep(min(2 ** attempt, 10))
        except (TimeoutError, URLError, OSError):
            if attempt == 31:
                raise
            time.sleep(min(2 ** attempt, 10))
    else:
        raise RuntimeError('Source download remains incomplete')
    digest = hashlib.sha256()
    with temp.open('rb') as downloaded:
        while block := downloaded.read(1024 * 1024):
            digest.update(block)
    if expected and digest.hexdigest() != expected:
        raise ValueError('Downloaded source checksum mismatch: ' + path.name)
    temp.replace(path)


def foodseg():
    tree = json.loads((META / 'hf-foodseg-tree.json').read_text())
    tasks = []
    for item in tree:
        if item.get('path', '').endswith('.parquet'):
            url = 'https://huggingface.co/datasets/EduardoPacheco/FoodSeg103/resolve/main/' + item['path']
            tasks.append((url, OUT / 'sources/foodseg103' / Path(item['path']).name, item['lfs']['oid'], item['size']))
    fetch('https://huggingface.co/datasets/EduardoPacheco/FoodSeg103/resolve/main/id2label.json', META / 'foodseg103-id2label.json')
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, *task): task[1].name for task in tasks}
        for future in as_completed(futures):
            name = futures[future]
            future.result()
            print('FoodSeg source verified: ' + name, flush=True)
    write_json(OUT / 'foodseg-source-download.json', {
        'status': 'downloaded_not_reviewed', 'source': 'FoodSeg103', 'upstream': 'https://github.com/LARC-CMU-SMU/FoodSeg103-Benchmark-v1',
        'mirror': 'EduardoPacheco/FoodSeg103', 'files_verified': len(tasks),
        'scope': 'original segmentation sources; not automatically FoodLens labels',
        'created_at': datetime.now(timezone.utc).isoformat()})


def commons():
    candidates = {}
    for slug, queries in QUERIES.items():
        for query in queries:
            params = dict(action='query', format='json', generator='search', gsrnamespace=6,
                          gsrsearch=query, gsrlimit=100, prop='imageinfo', iiprop='url|extmetadata', iiurlwidth=960)
            url = 'https://commons.wikimedia.org/w/api.php?' + urlencode(params)
            key = hashlib.sha256(query.encode()).hexdigest()[:12]
            path = META / ('commons-' + slug + '-' + key + '.json')
            try:
                fetch(url, path)
                data = json.loads(path.read_text(encoding='utf-8'))
                for page in data.get('query', {}).get('pages', {}).values():
                    if not page.get('imageinfo'):
                        continue
                    info = page['imageinfo'][0]
                    ext = info.get('extmetadata', {})
                    license_name = ext.get('LicenseShortName', {}).get('value', '')
                    description = ext.get('ImageDescription', {}).get('value', '')
                    if not (license_name.startswith('CC ') or license_name in ('CC0', 'Public domain')):
                        continue
                    text = page['title'] + ' ' + description
                    if re.search(r'AI.generated|midjourney|stable.diffusion|dall.e|synthetic image', text, re.I):
                        continue
                    image_url = info.get('thumburl', info.get('url', ''))
                    host = urlsplit(image_url).hostname or ''
                    if not host.endswith('.wikimedia.org') or urlsplit(image_url).scheme != 'https':
                        continue
                    if not re.search(r'\.(?:jpg|jpeg|png)(?:/|$)', image_url, re.I):
                        continue
                    source_id = str(page['pageid'])
                    record = candidates.setdefault((slug, source_id), {
                        'candidate_class': slug, 'source': 'wikimedia_commons', 'source_id': source_id,
                        'title': page['title'], 'description': description,
                        'page_url': info.get('descriptionurl'), 'original_url': info.get('url'),
                        'download_url': image_url, 'license': license_name,
                        'license_url': ext.get('LicenseUrl', {}).get('value'),
                        'artist': ext.get('Artist', {}).get('value'),
                        'datetime_original': ext.get('DateTimeOriginal', {}).get('value'),
                        'queries': [], 'annotation_status': 'candidate_only_not_ground_truth'})
                    record['queries'].append(query)
                print('Commons source candidates: ' + slug + ' ' + str(sum(k[0] == slug for k in candidates)), flush=True)
            except Exception as exc:
                print('Commons metadata unavailable: ' + slug + ' ' + type(exc).__name__, flush=True)
            time.sleep(.3)
    records = list(candidates.values())
    def image(record):
        path = OUT / 'sources/commons' / record['candidate_class'] / (record['source_id'] + '.jpg')
        try:
            fetch(record['download_url'], path)
            validate_image(path)
            record.update(local_path=str(path.relative_to(OUT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), download_status='downloaded')
        except Exception as exc:
            record.update(download_status='failed', failure_kind=type(exc).__name__)
        return record
    completed = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(image, records):
            completed.append(record)
            if len(completed) % 25 == 0:
                write_json(OUT / 'commons-candidates.json', completed)
                print('Commons downloaded candidates: ' + str(sum(r['download_status'] == 'downloaded' for r in completed)), flush=True)
    write_json(OUT / 'commons-candidates.json', completed)
    print('Commons harvest completed; all files still need semantic/box review.', flush=True)


def retry_commons():
    manifest = OUT / 'commons-candidates.json'
    records = json.loads(manifest.read_text(encoding='utf-8'))
    failed = [r for r in records if r.get('download_status') != 'downloaded']
    def recover(record):
        path = OUT / 'sources/commons' / record['candidate_class'] / (record['source_id'] + '.jpg')
        try:
            fetch(record['download_url'], path)
            validate_image(path)
            record['previous_download_failure'] = record.pop('failure_kind', None)
            record.update(local_path=str(path.relative_to(OUT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), download_status='downloaded')
        except Exception as exc:
            record.update(download_status='failed', failure_kind=type(exc).__name__)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:
        for count, _ in enumerate(pool.map(recover, failed), 1):
            if count % 20 == 0:
                write_json(manifest, records)
                print('Commons recovered assets checked: ' + str(count), flush=True)
    write_json(manifest, records)
    print('Commons retry complete; candidates still require review.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', choices=['foodseg', 'commons', 'commons-retry'])
    args = parser.parse_args()
    {'foodseg': foodseg, 'commons': commons, 'commons-retry': retry_commons}[args.source]()
