#!/usr/bin/env python3
"""Fill the `taxid` field on every threat_list / clinical_watchlist entry.

    python3 analysis/resolve_taxids.py            # report what is missing
    python3 analysis/resolve_taxids.py --write    # resolve and write triage_rules.json

Resolution order: PFI_DB/list.<Kingdom>.xls (offline, and the same namespace the classifier
uses) -> NCBI E-utilities. Every NCBI hit is verified by fetching the record back and checking
that the rule-file name appears as the scientific name or as one of its synonyms; an
unverifiable hit is reported and NOT written. Names are cheap to get wrong, taxids are not
supposed to be, so nothing here guesses.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, 'analysis', 'triage_rules.json')
LISTS = os.path.join(ROOT, 'PFI_DB')
EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
KINGDOMS = ('Bacteria', 'Fungi', 'Metazoa', 'Protozoa', 'Viruses')


def local_map():
    """name -> (taxid, kingdom) from the kingdom-split lists. TSV despite the .xls extension."""
    out = {}
    for k in KINGDOMS:
        path = os.path.join(LISTS, f'list.{k}.xls')
        if not os.path.exists(path):
            continue
        for line in open(path, encoding='utf-8', errors='replace'):
            parts = line.rstrip('\r\n').split('\t')
            if len(parts) >= 2 and parts[1].strip() and parts[0].strip().isdigit():
                out.setdefault(parts[1].strip(), (parts[0].strip(), k))
    return out


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def ncbi(name):
    """(taxid, scientific_name, rank) or None. Verified: the query must be the record's own
    name or one of its synonyms, otherwise a fuzzy hit would silently enter the rule file."""
    q = urllib.parse.quote(name)
    hits = json.loads(_get(f'{EUTILS}esearch.fcgi?db=taxonomy&term={q}&retmode=json'))
    ids = hits.get('esearchresult', {}).get('idlist', [])
    if len(ids) != 1:
        return None
    time.sleep(0.4)
    xml = _get(f'{EUTILS}efetch.fcgi?db=taxonomy&id={ids[0]}&retmode=xml')
    sci = (re.search(r'<ScientificName>([^<]+)</ScientificName>', xml) or [None, ''])[1]
    rank = (re.search(r'<Rank>([^<]+)</Rank>', xml) or [None, ''])[1]
    known = {sci.lower()} | {m.lower() for m in
                             re.findall(r'<(?:Synonym|EquivalentName)>([^<]+)</', xml)}
    return (ids[0], sci, rank) if name.lower() in known else None


def main(write):
    rules = json.load(open(RULES_PATH), object_pairs_hook=OrderedDict)
    local = local_map()
    changed = unresolved = 0
    for section in ('threat_list', 'clinical_watchlist'):
        for name, entry in rules[section].items():
            if name == '_comment' or not isinstance(entry, dict) or entry.get('taxid'):
                continue
            src = None
            if name in local:
                taxid, src = local[name][0], f'PFI_DB/list.{local[name][1]}.xls'
            else:
                time.sleep(0.4)
                got = ncbi(name)
                if not got:
                    print(f'  UNRESOLVED  {name}')
                    unresolved += 1
                    continue
                taxid, src = got[0], f'NCBI ({got[1]}, rank {got[2]})'
            entry['taxid'] = taxid
            changed += 1
            print(f'  {taxid:>10}  {name:48} {src}')
    print(f'\n{changed} resolved, {unresolved} unresolved')
    if write and changed:
        open(RULES_PATH, 'w').write(json.dumps(rules, indent=2, ensure_ascii=False))
        print(f'wrote {os.path.relpath(RULES_PATH, ROOT)}')
    elif changed:
        print('dry run - pass --write to save')


if __name__ == '__main__':
    main('--write' in sys.argv)
