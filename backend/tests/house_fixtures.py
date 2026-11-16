"""Tiny synthetic vector PDFs; no real financial data or network in CI."""
from io import BytesIO
from pathlib import Path
import zipfile


def pdf(rows=None, docid='900001', pages=1, scanned=False, split_notes=False, continuation=False, split_transaction=False, conflicting_continuation=False, split_header=False, delayed_status=False, complete_tail=False):
    rows = rows if rows is not None else [dict(owner='SP', ticker='AAPL', action='P')]
    objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    page_ids = []
    for page_number in range(pages):
        ops = []
        def text(x, y, value):
            value = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            ops.append(f'BT /F1 8 Tf {x} {y} Td ({value}) Tj ET')
        if not scanned:
            text(30, 760, 'SYNTHETIC TEST - NOT A REAL DISCLOSURE')
            text(30, 745, 'Filing ID #' + docid)
            text(30, 730, 'Name: Hon. Nancy Pelosi')
            xs = [20, 45, 80, 290, 355, 420, 490, 570, 610]
            top, header_bottom = 700, 670
            bottom = header_bottom - 60 * len(rows)
            for x in xs:
                ops.append(f'{x} {top} m {x} {header_bottom} l S')
            for y in [top, header_bottom] + [header_bottom - 60*(i+1) for i in range(len(rows))]:
                ops.append(f'20 {y} m 610 {y} l S')
            ops += [f'20 {header_bottom} m 20 {bottom} l S', f'610 {header_bottom} m 610 {bottom} l S']
            for x, value in zip(xs, ['ID', 'Owner', 'Asset', 'Transaction Type', 'Date', 'Notification Date', 'Amount', 'Cap.']):
                text(x+2, 685, value)
            if split_header and page_number:
                ops.append('20 682 m 610 682 l S')
                # Replace the header text with two geometrically separate rows.
                ops = [op for op in ops if not (' 685 Td ' in op)]
                for x,value in zip(xs,['ID','Owner','Asset','Transaction','Date','Notification','Amount','Cap.']): text(x+2,690,value)
                for x,value in zip(xs,['','','','Type','','Date','','Gains > $200?']): text(x+2,674,value)
                ops = [op.replace('/F1 8 Tf','/F1 5 Tf') if 'Gains > $200?' in op else op for op in ops]
            for i, row in enumerate(rows):
                y = 655 - 60*i
                if delayed_status and page_number and i==0:
                    text(82,y,'Filing Status: New')
                    text(82,y-12,'Description: Sold 1,000 shares.')
                    continue
                if split_transaction and page_number and i==0:
                    text(82,y,'Stock (TEST) [ST]')
                    text(492,y,'$100,000')
                    if conflicting_continuation: text(47,y,'SP')
                    text(82,y-24,'Filing Status: New')
                    text(82,y-36,'Description: Exercised 50 call options.')
                    continue
                if continuation and page_number and i==0:
                    text(82, y, 'Description: Gift of shares continued from preceding page')
                    continue
                if split_notes:
                    ops.append(f'20 {y-16} m 610 {y-16} l S')
                asset = row.get('asset', 'Synthetic wrapped company')
                ticker = row.get('ticker', 'AAPL')
                values = ['', row.get('owner', ''), asset, row.get('action', 'P'), row.get('date','03/01/2024'), '03/02/2024', row.get('amount_first','$1,001 -'), '']
                for x, value in zip(xs, values): text(x+2, y, value)
                text(82, y-10, (f'({ticker}) ' if ticker else '') + '['+row.get('code','ST')+']')
                text(492, y-10, row.get('amount_last','$15,000'))
                if delayed_status and page_number==0 and i==len(rows)-1: continue
                text(82, y-24, 'Filing Status: '+row.get('status','New'))
                text(82, y-36, row.get('note','SYNTHETIC row'))
            if complete_tail:
                for x,value in zip(xs,['','SP','Tail company (TEST) [ST]','P','03/01/2024','03/02/2024','$1,001 - $15,000','']): text(x+2,bottom-15,value)
                text(82,bottom-30,'Filing Status: New')
                text(82,bottom-42,'Description: Ordinary purchase.')
            elif split_transaction and page_number==0:
                for x,value in zip(xs,['','SP','Synthetic split company','P','03/01/2024','03/02/2024','$50,001 -','']): text(x+2,bottom-15,value)
            else:
                text(30, bottom-15, 'I CERTIFY these statements are true, complete, and correct.')
                text(30, bottom-25, 'Digitally Signed: Hon. Nancy Pelosi , 04/01/2024')
        stream = '\n'.join(ops).encode()
        page_id, content_id = len(objects)+1, len(objects)+2
        page_ids.append(page_id)
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 640 800] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(str(i)+" 0 R" for i in page_ids)}] /Count {pages} >>'.encode()
    raw = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for i, obj in enumerate(objects,1):
        offsets.append(len(raw)); raw.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref = len(raw)
    raw.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: raw.extend(f'{offset:010d} 00000 n \n'.encode())
    raw.extend(f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(raw)


def index(docid='900001', year=2024, first='Nancy', last='Pelosi'):
    raw = BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
        z.writestr(f'{year}FD.xml', f'<FinancialDisclosure><Member><First>{first}</First><Last>{last}</Last><StateDst>CA11</StateDst><Year>{year}</Year><FilingType>P</FilingType><FilingDate>4/1/{year}</FilingDate><DocID>{docid}</DocID></Member></FinancialDisclosure>')
    return raw.getvalue()


def bundle(root: Path, **kwargs):
    root.mkdir(parents=True, exist_ok=True)
    (root/'index.zip').write_bytes(index())
    (root/'source.pdf').write_bytes(pdf(**kwargs))
    return dict(indexes=[dict(path=str(root/'index.zip'),source_url='https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2024FD.zip',year=2024)],documents=[dict(path=str(root/'source.pdf'),source_url='https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2024/900001.pdf',year=2024,document_id='900001')])
