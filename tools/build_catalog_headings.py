"""Build the small offline filter index from authoritative summary cells, never from movie filenames."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'addons/script.module.bobbi.catalog/resources'
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.library_labels import ref, visible_name


def heading(value):
    if not isinstance(value, str) or re.search(r'\[/?(?:COLOR|B|I|CR|UPPERCASE|LOWERCASE)\b',value,re.I):
        return ''
    return visible_name(value.translate(str.maketrans('[]','【】')))


def build(database):
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        titles = {}
        for group,origin,name in db.execute("SELECT group_key,origin,text FROM entries WHERE origin LIKE '汇总!%'"):
            if re.fullmatch(r'汇总![A-Z]{1,2}[1-9]\d*',origin):
                titles.setdefault(group,set()).add(heading(name))
        groups = [g for g, in db.execute('SELECT DISTINCT group_key FROM shares ORDER BY group_key')]
    names = {g:next(iter(titles[g])) if len(titles.get(g,()))==1 else '' for g in groups}
    copies=Counter(n.casefold() for n in names.values() if n)
    result={}
    for group,name in names.items():
        key=ref('qqdocs',group)
        label=name or ('补充共享库 ' if group.startswith('supp-') else '腾讯文档源库 ') + key[:8].upper()+'（未返回名称）'
        if name and copies[name.casefold()]>1:
            label += ' · ' + key[:8].upper()
        result[key]=label
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    data=json.dumps(build(ASSETS/'catalog.sqlite3'),sort_keys=True,ensure_ascii=False,indent=2)+'\n'
    target=ASSETS/'collection-headings.json'
    if args.check:
        if target.read_bytes()!=data.encode('utf8'):raise SystemExit('Public catalogue heading index is stale')
    else:target.write_bytes(data.encode('utf8'))
