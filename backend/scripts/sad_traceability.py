"""Extract exact SAD identifiers for source traceability; no inferred acceptance."""
from collections import Counter
import argparse
from pathlib import Path
import hashlib
import json
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / 'documents/greencity-project/SAD_GREENCITY.docx'


def requirements():
    with ZipFile(DOCUMENT) as archive: root = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    found = {}
    for row in root.findall('.//w:tr', ns):
        cells = [' '.join(t.text or '' for t in cell.findall('.//w:t', ns)).strip() for cell in row.findall('w:tc', ns)]
        if len(cells) < 2: continue
        identifier = re.match(r'^(FR-[A-Z]+\d+|BR-[A-Z]+\d+|NFR-[A-Z]*\d+)(?=\s|$)',cells[0])
        if identifier: found.setdefault(identifier[0], {'id':identifier[0], 'requirement':cells[1], 'details':cells[2:]})
    return list(found.values())


def build_matrix(rows):
    directory = ROOT / 'documents/greencity-project'
    mapping = json.loads((directory / 'SAD_IMPLEMENTATION_MAP.json').read_text(encoding='utf-8'))
    groups = mapping['groups']
    fr_counts = Counter(re.fullmatch(r'FR-([A-Z]+)\d+',r['id'])[1] for r in rows if r['id'].startswith('FR-'))
    if set(fr_counts) != set(groups) or any(len(groups[k]['features']) != count for k,count in fr_counts.items()):
        raise ValueError('FR mapping is missing or has a different requirement count; review the SAD map')
    referenced = {p for v in groups.values() for p in v['files']} | {p for v in mapping['nfr'].values() for p in v['files']}
    missing = [p for p in referenced if not (ROOT / p).is_file()]
    if missing: raise ValueError('Missing source evidence: ' + ', '.join(sorted(missing)))
    records = []
    for r in rows:
        match = re.fullmatch(r'(FR|BR)-([A-Z]+)(\d+)',r['id'])
        if match:
            kind, group, number = match.groups()
            spec = groups[group]
            note = spec['features'][int(number)-1] if kind=='FR' else 'Quy tắc được đối chiếu ở các đường xử lý của miền ' + spec['label'] + '; nội dung kiểm soát: ' + ' '.join(r['details'])
            record = {**r, 'group':group, 'status':'CODE_MAPPED', 'implementation':note, 'files':spec['files']}
        else:
            spec = mapping['nfr'][r['id']]
            record = {**r,'group':'NFR','status':spec['status'],'implementation':spec['note'],'files':spec['files']}
        records.append(record)
    summary = {'fr_mapped':sum(r['id'].startswith('FR-') for r in records),
        'br_mapped':sum(r['id'].startswith('BR-') for r in records),
        'nfr_code_mapped':sum(r['id'].startswith('NFR-') and r['status']=='CODE_MAPPED' for r in records),
        'nfr_design_targets':sum(r['status']=='DESIGN_TARGET_NOT_MEASURED' for r in records)}
    result = {'source':DOCUMENT.name,'source_sha256':hashlib.sha256(DOCUMENT.read_bytes()).hexdigest(),
        'meaning':'Ánh xạ mã nguồn và căn cứ kiểm tra; không suy ra nghiệm thu thực tế từ số lượng mã yêu cầu.',
        'summary':summary,'requirements':records,
        'source_files_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(referenced)}}
    (directory / 'SAD_FULL_TRACEABILITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def escape(value): return str(value).replace('|','\\|').replace('\n',' ')
    def links(paths): return ', '.join(f'[{Path(p).name}]({(ROOT/p).as_posix()})' for p in paths)
    lines = ['# GreenCity — Đối chiếu đầy đủ SAD với mã nguồn', '',
        f'Nguồn: [{DOCUMENT.name}]({DOCUMENT.as_posix()}). SHA-256: `{result["source_sha256"]}`.', '',
        f'Có {summary["fr_mapped"]} FR, {summary["br_mapped"]} BR và 10 NFR. Tất cả FR/BR có ánh xạ; 8 NFR có cơ chế mã nguồn, 2 NFR giữ mục tiêu thiết kế cần đo theo tải/thời gian nghiệm thu.', '',
        '**Cách đọc:** `CODE_MAPPED` là có đường xử lý và file nguồn được đối chiếu. Đây là 100% mã yêu cầu được lập bảng, không phải tuyên bố mọi nhánh đã được nghiệm thu bằng kiểm thử thực tế. Test tự động và database được ghi riêng trong SAD_FULL_IMPLEMENTATION.md. Chính sách và kênh ngoài dùng cấu hình đã chọn.', '',
        'Các dòng FR nêu điểm thực hiện cụ thể; các dòng BR giữ nguyên mô tả/quy tắc SAD và dẫn tới miền thực thi. JSON kèm SHA-256 từng file giúp phát hiện bảng đối chiếu đã cũ sau khi sửa mã.', '']
    for key,spec in groups.items():
        lines += [f'## {key} — {spec["label"]}', '', 'Mã và kiểm tra: '+links(spec['files'])+'.', '',
            '| Mã | Yêu cầu SAD | Điểm thực hiện trong mã |','| --- | --- | --- |']
        lines += [f'| {r["id"]} | {escape(r["requirement"])} | {escape(r["implementation"])} |' for r in records if r['group']==key and r['id'].startswith('FR-')]
        lines += ['', '| Mã BR | Tên quy tắc | Nội dung SAD được đối chiếu |','| --- | --- | --- |']
        lines += [f'| {r["id"]} | {escape(r["requirement"])} | {escape(" ".join(r["details"]))} |' for r in records if r['group']==key and r['id'].startswith('BR-')]
        lines += ['']
    lines += ['## NFR — Yêu cầu phi chức năng','','| Mã | Yêu cầu | Cơ chế và giới hạn | Căn cứ |','| --- | --- | --- | --- |']
    lines += [f'| {r["id"]} | {escape(r["requirement"])} | {escape(r["implementation"])} | {links(r["files"])} |' for r in records if r['group']=='NFR']
    (directory / 'SAD_FULL_TRACEABILITY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--matrix',action='store_true');args=parser.parse_args()
    rows = requirements()
    if args.matrix:
        build_matrix(rows)
        return
    path = ROOT / 'backend/.local/sad-requirements.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'source':'SAD_GREENCITY.docx','sha256':hashlib.sha256(DOCUMENT.read_bytes()).hexdigest(),'requirements':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(Counter(re.match(r'([A-Z]+-[A-Z]*)',r['id'])[1] for r in rows)),ensure_ascii=False))


if __name__ == '__main__': main()
