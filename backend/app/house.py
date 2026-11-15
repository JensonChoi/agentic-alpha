"""Bounded House PTR acquisition and conservative, deterministic text-PDF parsing.

Source text is data only. Unrecognized layouts and amendments require review.
No filing date is promoted to historical public availability.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

from defusedxml import ElementTree
import httpx
import pdfplumber

from .disclosures import Disclosure, load_snapshot, register_snapshot
from .providers import DisclosureArtifactProvider

BASE = 'https://disclosures-clerk.house.gov'
PORTAL = BASE + '/FinancialDisclosure/ViewReport'
MAPPING = 'https://clerk.house.gov/members/P000197'
OWNER_EVIDENCE = 'https://ethics.house.gov/wp-content/uploads/2023/12/FINAL-2021-FD-Instructions_1.pdf'
ASSET_EVIDENCE = 'https://fd.house.gov/reference/asset-type-codes.aspx'
PARSER = 'house-ptr-layout/3'
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
MAX_DOCUMENTS = 500
OWNERS = {'SP': 'spouse', 'DC': 'dependent', 'JT': 'joint', '': 'unknown'}


def checksum(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def identifier(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise ValueError('Invalid immutable identifier')
    return value


def official_url(value: str) -> str:
    url = httpx.URL(value)
    if url.scheme != 'https' or url.host != 'disclosures-clerk.house.gov' or url.port not in (None, 443):
        raise ValueError('Require an official House disclosure source URL')
    return value


def read_bounded(path: Path) -> bytes:
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Source exceeds byte limit')
    return raw


def parse_index(raw: bytes, year: int, member_id: str) -> tuple[list[dict], int]:
    if member_id != 'P000197':
        raise ValueError('Only the evidenced Nancy Pelosi / P000197 mapping is supported')
    if len(raw) > MAX_BYTES:
        raise ValueError('Index exceeds byte limit')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 10 or sum(i.file_size for i in entries) > MAX_BYTES:
            raise ValueError('Index archive expansion limit')
        names = [i.filename for i in entries]
        if len(names) != len(set(names)) or any('/' in n or '\\' in n or n.startswith('.') for n in names):
            raise ValueError('Unsafe or duplicate index archive paths')
        expected = f'{year}FD.xml'
        if expected not in names:
            raise ValueError('Missing annual XML index')
        xml = archive.read(expected)  # Never extract archive paths to disk.
    root = ElementTree.fromstring(xml)
    if root.tag != 'FinancialDisclosure' or not len(root):
        raise ValueError('Unexpected or empty House index')
    found, seen = [], {}
    for element in root:
        row = {c.tag: (c.text or '').strip() for c in element}
        if element.tag != 'Member' or not {'First', 'Last', 'StateDst', 'FilingType', 'FilingDate', 'Year', 'DocID'} <= row.keys():
            raise ValueError('Incomplete House index schema')
        if (row['First'], row['Last']) != ('Nancy', 'Pelosi'):
            continue
        if not re.fullmatch(r'CA\d{2}', row['StateDst']) or row['Year'] != str(year):
            raise ValueError('Unresolved member identity/year')
        if not row['DocID'].isdigit():
            raise ValueError('Invalid document identity')
        if row['DocID'] in seen:
            if row != seen[row['DocID']]:
                raise ValueError('Conflicting index document identity')
            continue
        seen[row['DocID']] = dict(row)
        row['filing_date'] = datetime.strptime(row['FilingDate'], '%m/%d/%Y').date().isoformat()
        found.append(row)
    return found, len(root)


def _fields(page, table, row) -> tuple[list[str], str]:
    """Use header column geometry: House merges body cells across all columns."""
    bbox = row.bbox
    original = page.crop(bbox).extract_text() or ''
    columns = table.rows[0].cells
    if len(columns) != 8 or any(c is None for c in columns):
        raise ValueError('Unrecognized transaction columns')
    # The asset code terminates the main asset description before full-width notes.
    asset_box = (columns[2][0], bbox[1], columns[2][2], bbox[3])
    words = page.crop(asset_box).extract_words()
    codes = [w for w in words if re.fullmatch(r'\[[A-Z0-9]{2}\]', w['text'])]
    if len(codes) != 1:
        raise ValueError('Missing/ambiguous asset code or continuation row')
    status_words = [w for w in page.crop(bbox).extract_words() if re.fullmatch(r'F(?:iling|\x00+)', w['text'], re.I)]
    bottom = min((w['top'] for w in status_words), default=codes[0]['bottom'] + 2)
    values = []
    for c in columns:
        values.append(' '.join((page.crop((c[0], bbox[1], c[2], min(bottom, bbox[3]))).extract_text() or '').split()))
    return values, original



def amount_bounds(amount: str) -> tuple[float, float, str]:
    money = r'\$(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?'
    if re.fullmatch(money, amount):
        value = float(Decimal(amount[1:].replace(',', '')))
        return value, value, 'exact'
    match = re.fullmatch(f'({money})\\s*-\\s*({money})', amount)
    if not match:
        raise ValueError('Unresolved amount range or exact dollar value')
    low, high = (float(Decimal(v[1:].replace(',', ''))) for v in match.groups())
    if high < low:
        raise ValueError('Invalid value range')
    return low, high, 'range'


def _preceding_fragment(pdf, number: int, table, row_no: int, values: list[str]):
    """Join only complementary columns on adjacent pages, never economic similarity.

    A borderless final row can escape pdfplumber's table detection. Its next-page
    continuation must be the first body row and cannot repeat owner/action/dates.
    """
    if number < 2 or row_no != 1 or any(values[i] for i in (0, 1, 3, 4, 5, 7)):
        return None
    if not re.fullmatch(r'\$[\d,]+(?:\.\d{2})?', values[6]):
        return None
    previous = pdf.pages[number - 2]
    tables = [t for t in previous.find_tables() if t.extract() and
              [str(v or '').replace('\n', ' ') for v in t.extract()[0]][:5] ==
              ['ID', 'Owner', 'Asset', 'Transaction Type', 'Date']]
    if not tables:
        return None
    prior = tables[-1]
    columns = prior.rows[0].cells
    if len(columns) != 8 or any(c is None for c in columns):
        return None
    if any(abs(a[0]-b[0]) > 2 or abs(a[2]-b[2]) > 2 for a,b in zip(columns, table.rows[0].cells)):
        return None
    words = [w for w in previous.extract_words() if w['top'] >= prior.bbox[3]]
    if not words or max(w['bottom'] for w in words)-min(w['top'] for w in words) > 50:
        return None
    bbox = (prior.bbox[0], min(w['top'] for w in words)-1, prior.bbox[2], max(w['bottom'] for w in words)+1)
    prefix = [' '.join((previous.crop((c[0],bbox[1],c[2],bbox[3])).extract_text() or '').split()) for c in columns]
    if prefix[0] or prefix[7] or prefix[1] not in OWNERS or prefix[3] not in ('P','S','S (partial)','S (full)','E'):
        return None
    if not all(re.fullmatch(r'\d{2}/\d{2}/\d{4}', prefix[i]) for i in (4,5)):
        return None
    if not prefix[2] or re.search(r'\[[A-Z0-9]{2}\]|\([A-Z][A-Z0-9.-]*\)', prefix[2]) or not re.fullmatch(r'\$[\d,]+(?:\.\d{2})?\s*-',prefix[6]):
        return None
    merged = [a+' '+b if a and b else a or b for a,b in zip(prefix,values)]
    fragment = dict(page=number-1, table=len(tables), bbox=list(bbox), cells=prefix,
                    original_text=previous.crop(bbox).extract_text() or '')
    return merged, fragment

def parse_pdf(raw: bytes, document: dict, max_pages: int = MAX_PAGES) -> dict:
    if len(raw) > MAX_BYTES or not raw.startswith(b'%PDF-'):
        raise ValueError('Invalid PDF signature or byte limit')
    records, quarantines, pages = [], [], []
    last_locator = None
    coverage = {}
    recognized_pages = set()
    docid = document['document_id']
    doc_hash = checksum(raw)
    with pdfplumber.open(BytesIO(raw)) as pdf:
        if len(pdf.pages) > max_pages:
            raise ValueError('PDF page limit')
        texts = [p.extract_text() or '' for p in pdf.pages]
        combined = '\n'.join(texts)
        if f'Filing ID #{docid}' not in combined or not re.search(r'Name:\s*Hon\. Nancy Pelosi\b', combined):
            return dict(records=[], quarantines=[dict(document_id=docid, reason='Unresolved document/member identity or scanned PDF')], pages=texts)
        for number, (page, text) in enumerate(zip(pdf.pages, texts), 1):
            pages.append(dict(page=number, text=text))
            if not text.strip():
                quarantines.append(dict(document_id=docid, page=number, reason='Scanned/image-only page; OCR unsupported'))
                continue
            recognized = False
            for table_no, table in enumerate(page.find_tables(), 1):
                extracted = table.extract()
                if not extracted or [str(v or '').replace('\n', ' ') for v in extracted[0]][:5] != ['ID', 'Owner', 'Asset', 'Transaction Type', 'Date']:
                    continue
                recognized = True
                recognized_pages.add(number)
                coverage.setdefault(number, []).append(table.bbox)
                from types import SimpleNamespace
                body = list(enumerate(table.rows[1:], 1))
                groups = []
                for row_no, row in body:
                    raw_text = page.crop(row.bbox).extract_text() or ''
                    cells = extracted[row_no]
                    if row_no == 1 and all(not c for c in cells[:7]) and cells[7] == '$200?':
                        continue  # Repeated header split by a page break.
                    if re.match(r'(?:F(?:iling|\x00+) S(?:tatus|\x00+):|D(?:escription|\x00+):)', raw_text, re.I):
                        if groups:
                            prior_no, prior = groups[-1]
                            groups[-1] = (prior_no, SimpleNamespace(bbox=(prior.bbox[0], prior.bbox[1], prior.bbox[2], row.bbox[3])))
                        elif records and records[-1]['source_id'] == last_locator:
                            # Explicit description continuation after a repeated header.
                            previous = records[-1]
                            previous['original'].setdefault('continuations', []).append(dict(page=number, bbox=list(row.bbox), original_text=raw_text))
                            previous['original']['original_text'] += '\n' + raw_text
                            if re.search(r'\b(option|options|exercis\w*|gift\w*|merger|exchange|contribution|donor-advised)\b', raw_text, re.I):
                                previous['action'] = 'UNSUPPORTED'
                        else:
                            quarantines.append(dict(document_id=docid, page=number, reason='Orphan continuation requires review', original_text=raw_text))
                        continue
                    groups.append((row_no, row))
                for row_no, row in groups:
                    locator = f'house:{docid}:p{number}:t{table_no}:r{row_no}'
                    last_locator = locator
                    evidence = dict(document_id=docid, file_sha256=doc_hash, page=number, table=table_no, row=row_no, bbox=list(row.bbox), retrieved_at=document['retrieved_at'], parser_version=PARSER, original_text=page.crop(row.bbox).extract_text() or '')
                    try:
                        values, original = _fields(page, table, row)
                        joined = _preceding_fragment(pdf, number, table, row_no, values)
                        if joined:
                            values, fragment = joined
                            evidence['continuations'] = [dict(page=number, table=table_no, row=row_no, bbox=list(row.bbox), original_text=original)]
                            evidence.update(page=fragment['page'], table=fragment['table'], row='tail', bbox=fragment['bbox'], preceding_fragment=fragment)
                            original = fragment['original_text'] + '\n' + original
                            evidence['original_text'] = original
                            locator = f"house:{docid}:p{fragment['page']}:t{fragment['table']}:tail"
                            last_locator = locator
                        _, owner, asset, action, traded, notified, amount, _ = values
                        if owner not in OWNERS:
                            raise ValueError('Unknown owner code')
                        code = re.search(r'\[([A-Z0-9]{2})\]', asset).group(1)
                        ticker = re.findall(r'\(([A-Z][A-Z0-9.\-]{0,9})\)', asset)
                        security = {'ST': 'stock', 'EF': 'etf'}.get(code, 'unsupported')
                        if len(ticker) != 1 and security != 'unsupported':
                            raise ValueError('Missing or ambiguous explicit ticker')
                        low, high, amount_kind = amount_bounds(amount)
                        if (re.search(r'\bamend\w*\b', combined.split('ID Owner Asset', 1)[0], re.I) or re.search(r'\b(amend\w*|correct\w*)\b', original, re.I)) or ': New' not in original:
                            raise ValueError('Amendment/status requires evidenced row linkage')
                        normalized_action = {'P': 'BUY', 'S': 'SELL', 'S (partial)': 'SELL', 'S (full)': 'SELL', 'E': 'UNSUPPORTED'}.get(action)
                        if normalized_action is None:
                            raise ValueError('Unrecognized transaction type')
                        # An exercise, gift, or merger is not an ordinary stock purchase/sale.
                        if re.search(r'\b(option|options|exercis\w*|gift\w*|merger|exchange|contribution|donor-advised)\b', original, re.I):
                            normalized_action = 'UNSUPPORTED'
                        evidence.update(cells=values, amount_kind=amount_kind, asset_code=code, notification_date=notified, sale_description=action, diagnostics=['Availability unverified; explicit source ticker only; no symbol remapping'])
                        record = Disclosure(source_id=locator, revision=doc_hash, member_id='P000197', owner=OWNERS[owner], ticker=ticker[0] if len(ticker)==1 else '', security_type=security, action=normalized_action, transaction_date=datetime.strptime(traded, '%m/%d/%Y').date(), filing_date=document['filing_date'], source_url=document['source_url'], ingested_at=document.get('ingested_at', document['retrieved_at']), value_low=low, value_high=high, original_value_range=amount, original=evidence)
                        records.append(record.model_dump(mode='json'))
                        if joined:
                            coverage.setdefault(fragment['page'], []).append(fragment['bbox'])
                    except (ValueError, AttributeError) as exc:
                        quarantines.append(dict(source_id=locator, reason=str(exc), original=evidence))
        # Defer coverage reconciliation until adjacent-page joins have succeeded.
        for number, (page, text) in enumerate(zip(pdf.pages, texts), 1):
            if not text.strip():
                continue
            covered = coverage.get(number, [])
            outside = [w for w in page.extract_words() if re.fullmatch(r'\d{2}/\d{2}/\d{4}', w['text']) and not any(b[1] <= w['top'] <= b[3] for b in covered)]
            if (number not in recognized_pages and not re.search(r'Digitally Signed:|I CERTIFY', text)) or len(outside) > (1 if 'Digitally Signed:' in text else 0):
                quarantines.append(dict(document_id=docid, page=number, reason='Unrecognized page/transaction layout; review entire page', original_text=text))
    if not records and not quarantines:
        quarantines.append(dict(document_id=docid, reason='No recognized transaction rows'))
    return dict(records=records, quarantines=quarantines, pages=pages)


@dataclass
class HouseProvider:
    timeout: float = 20
    interval: float = 1
    client: httpx.Client | None = None

    def fetch(self, url: str) -> bytes:
        official_url(url)
        if not 1 <= self.timeout <= 60 or not 0.1 <= self.interval <= 10:
            raise ValueError('Network bounds: timeout 1..60s, interval 0.1..10s')
        client = self.client or httpx.Client(timeout=self.timeout, follow_redirects=False)
        try:
            for attempt in range(3):
                time.sleep(self.interval)
                try:
                    with client.stream('GET', url, timeout=self.timeout) as response:
                        response.raise_for_status()
                        content_type = response.headers.get('content-type', '').split(';')[0]
                        if url.endswith('.pdf') and content_type not in ('application/pdf', 'application/octet-stream'):
                            raise ValueError('Unexpected PDF content type')
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_BYTES:
                                raise ValueError('Download byte limit')
                        return bytes(raw)
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    response = getattr(exc, 'response', None)
                    status = response.status_code if response is not None else None
                    if status is not None and status != 429 and status < 500 or attempt == 2:
                        raise
                    delay = 2 ** attempt
                    if response is not None and response.headers.get('Retry-After'):
                        value = response.headers['Retry-After']
                        try:
                            delay = float(value)
                        except ValueError:
                            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                        if delay > 60:
                            raise ValueError('Source throttled beyond bounded retry window') from exc
                    time.sleep(max(0, delay))
        finally:
            if self.client is None:
                client.close()
        raise AssertionError('unreachable')

    def acquire(self, member_id: str, start: date, end: date, staging: Path) -> dict:
        if end < start or end.year - start.year > 9:
            raise ValueError('Invalid scope: maximum ten index years')
        portal = self.fetch(PORTAL)
        (staging / 'portal.html').write_bytes(portal)
        bundle = dict(indexes=[], documents=[], discovery='annual indexes retrieved; historical completeness unknown')
        for year in range(start.year, end.year + 1):
            route = f'/public_disc/financial-pdfs/{year}FD.zip'
            if route.encode() not in portal:
                raise ValueError(f'Official portal does not list requested index year {year}')
            raw = self.fetch(BASE + route)
            path = staging / f'{year}FD.zip'; path.write_bytes(raw)
            rows, _ = parse_index(raw, year, member_id)
            bundle['indexes'].append(dict(path=str(path), source_url=BASE + route, year=year))
            (staging / f'{year}.discovery.json').write_text(json.dumps(dict(year=year, member_rows=rows, expected_documents=[r['DocID'] for r in rows if r['FilingType']=='P']), indent=2))
            for row in rows:
                if row['FilingType'] != 'P':
                    continue
                if len(bundle['documents']) >= MAX_DOCUMENTS:
                    raise ValueError('Document count limit')
                docid = row['DocID']; url = f'{BASE}/public_disc/ptr-pdfs/{year}/{docid}.pdf'
                raw = self.fetch(url)
                path = staging / f'{docid}.pdf'; path.write_bytes(raw)
                bundle['documents'].append(dict(path=str(path), source_url=url, document_id=docid, year=year))
        return bundle


def ingest(identifier_value: str, member_id: str, start: date, end: date, artifact_dir: str, provenance: str, bundle: dict | None = None, provider: DisclosureArtifactProvider | None = None) -> dict:
    """Reserve a new directory, stage all bytes/review output, then register once.

    Failure directories remain inspectable but cannot be reused or registered.
    Local imports must provide official indexes and every selected PTR in them.
    """
    identifier(identifier_value)
    if not provenance.strip() or end < start or end.year - start.year > 9:
        raise ValueError('Require provenance and bounded date scope')
    root = Path(artifact_dir).resolve() / identifier_value
    root.mkdir(parents=True, exist_ok=False)
    artifacts, records, quarantines, documents, indexes = [], [], [], [], []
    retrieved = datetime.now(timezone.utc).isoformat()
    def preserve(path, raw, url):
        path.write_bytes(raw)
        artifacts.append(dict(path=str(path), sha256=checksum(raw), bytes=len(raw), source_url=url, retrieved_at=retrieved))
    try:
        online = bundle is None
        if online:
            bundle = (provider or HouseProvider()).acquire(member_id, start, end, root)
            preserve(root / 'portal.html', read_bounded(root / 'portal.html'), PORTAL)
        if len(bundle['documents']) > MAX_DOCUMENTS:
            raise ValueError('Document count limit')
        years, expected = set(), {}
        for index in bundle['indexes']:
            year = int(index['year'])
            if year in years or year not in range(start.year, end.year + 1):
                raise ValueError('Duplicate/out-of-scope index year')
            years.add(year)
            raw = read_bounded(Path(index['path']))
            url = official_url(index['source_url'])
            preserve(root / f'{year}FD.zip', raw, url)
            rows, total = parse_index(raw, year, member_id)
            indexes.append(dict(year=year, total_rows=total, member_rows=rows, sha256=checksum(raw)))
            for row in rows:
                if row['FilingType'] == 'P':
                    if row['DocID'] in expected:
                        raise ValueError('Conflicting cross-index document identity')
                    expected[row['DocID']] = row
        if years != set(range(start.year, end.year + 1)):
            raise ValueError('Incomplete index years')
        supplied = [d['document_id'] for d in bundle['documents']]
        if len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
            raise ValueError('Incomplete acquisition or duplicate/unindexed documents')
        for item in bundle['documents']:
            docid = item['document_id']; row = expected[docid]
            url = official_url(item['source_url'])
            if url != f'{BASE}/public_disc/ptr-pdfs/{row["Year"]}/{docid}.pdf':
                raise ValueError('Document URL/index mismatch')
            raw = read_bounded(Path(item['path']))
            if not raw.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF signature; acquisition incomplete')
            path = root / f'{docid}.pdf'; preserve(path, raw, url)
            document = dict(document_id=docid, filing_date=row['filing_date'], source_url=url, retrieved_at=retrieved)
            # Isolate parser CPU/memory and enforce a wall-clock bound on untrusted PDFs.
            try:
                process = subprocess.run([sys.executable, '-m', 'app.house', str(path), json.dumps(document)], capture_output=True, text=True, timeout=45)
            except subprocess.TimeoutExpired:
                process = subprocess.CompletedProcess([], 1, '', 'Parser wall-clock limit exceeded')
            if process.returncode:
                parsed = dict(records=[], quarantines=[dict(document_id=docid, reason='PDF parser failed/resource limit', diagnostic=process.stderr[-2000:])], pages=[])
            else:
                parsed = json.loads(process.stdout)
            from sqlalchemy import select
            from . import data
            from .db import DisclosureSnapshot
            with data.Session() as db:
                previous = db.scalars(select(DisclosureSnapshot)).all()
                changed = any(d['document_id']==docid and d['sha256']!=checksum(raw) for snapshot in previous for d in snapshot.manifest.get('documents', []))
            if changed:
                parsed['quarantines'].extend(dict(source_id=d['source_id'], original=d['original'], reason='Changed source bytes: row identity/revision requires review') for d in parsed['records'])
                parsed['records'] = []
            records.extend(parsed['records']); quarantines.extend(parsed['quarantines'])
            documents.append({**document, 'sha256': checksum(raw), 'rows': len(parsed['records']), 'quarantines': len(parsed['quarantines'])})
            preserve(root / f'{docid}.extraction.json', json.dumps(parsed, indent=2).encode(), url)
        metadata = dict(provider='house', provenance=provenance, retrieved_at=retrieved, parser_version=PARSER, library_version=pdfplumber.__version__, member_id=member_id, requested_start=str(start), requested_end=str(end), mapping_evidence=MAPPING, owner_evidence=OWNER_EVIDENCE, asset_evidence=ASSET_EVIDENCE, indexes=indexes, documents=documents, artifacts=artifacts, quarantines=quarantines, quality=dict(discovery='partial' if not online else 'unknown', historical_revisions='unknown', parsing='partial' if quarantines else 'complete for supplied documents', verified_availability='unverified'), counts=dict(documents=len(documents), parsed_rows=len(records), quarantines=len(quarantines), unverified=len(records), unsupported=sum(d['security_type']=='unsupported' or d['action']=='UNSUPPORTED' for d in records)), warnings=['No historical publication evidence; filing/notification/signature dates are not publication dates', 'Annual index observation is not exhaustive historical coverage; revisions and documents outside queried years unknown', 'Local copies do not establish exhaustive discovery' if not online else 'All current indexed PTRs acquired, including post-end filings for audit', 'Unrecognized/scanned layouts and amendments require review; no OCR or inferred tickers'])
        review = dict(metadata=metadata, records=records)
        preserve(root / 'review.json', json.dumps(review, indent=2).encode(), PORTAL)
        manifest = register_snapshot(identifier_value, records, metadata)
        (root / 'registered.json').write_text(json.dumps(manifest, indent=2))
        return manifest
    except Exception as exc:
        (root / 'failure.json').write_text(json.dumps(dict(error=str(exc), registered=False, artifacts=artifacts), indent=2))
        raise


def correct_snapshot(source: str, target: str, corrections: list[dict], provenance: str) -> dict:
    """Evidence-backed corrections; originals and previous immutable snapshot survive."""
    records, manifest = load_snapshot(source)
    by_id = {d['source_id']: d for d in records}
    quarantined = {q['source_id']: q for q in manifest.get('quarantines', []) if q.get('source_id')}
    seen = set()
    for correction in corrections:
        key = correction['source_id']
        if key in seen or key not in by_id and key not in quarantined:
            raise ValueError('Duplicate/unknown correction identity')
        seen.add(key)
        if not correction.get('reviewer') or not correction.get('evidence'):
            raise ValueError('Correction requires reviewer and source evidence')
        before = by_id.get(key)
        changes = correction['changes']
        if {'source_id', 'revision', 'original'} & changes.keys():
            raise ValueError('Correction cannot replace source identity or original extraction')
        if changes.get('availability_quality', 'unverified') != 'unverified':
            if correction.get('publication_basis') not in ('documented_publication', 'synthetic_fixture'):
                raise ValueError('Filing/retrieval/notification dates are not historical publication evidence')
            if not changes.get('publication_evidence'):
                raise ValueError('Publication provenance required')
        candidate = {**(before or {}), **changes, 'source_id': key, 'revision': target, 'original': dict(extraction=(before or quarantined[key]).get('original'), previous_record=before, correction=correction, parent_snapshot=source)}
        if candidate.get('amends'):
            if not correction.get('amendment_evidence') or candidate['amends'] not in by_id or candidate['amends'] == key or by_id[candidate['amends']].get('amends'):
                raise ValueError('Amendment requires evidence and a known original identity')
        by_id[key] = Disclosure(**candidate).model_dump(mode='json')
    metadata = {k: v for k, v in manifest.items() if k not in ('sha256', 'schema_version', 'count', 'records_sha256', 'members', 'owners', 'availability', 'observed_coverage')}
    metadata.update(parent_snapshot=source, parent_sha256=manifest['sha256'], provenance=provenance, corrections=corrections)
    metadata['quarantines'] = [q for q in manifest.get('quarantines', []) if q.get('source_id') not in seen]
    metadata['counts'] = {**metadata.get('counts', {}), 'quarantines': len(metadata['quarantines']), 'parsed_rows': len(by_id), 'unverified': sum(d['availability_quality']=='unverified' for d in by_id.values())}
    metadata['quality'] = {**metadata.get('quality', {}), 'verified_availability': 'operator-reviewed; see row evidence'}
    return register_snapshot(target, list(by_id.values()), metadata)


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform != 'darwin':
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    print(json.dumps(parse_pdf(read_bounded(Path(sys.argv[1])), json.loads(sys.argv[2]))))
