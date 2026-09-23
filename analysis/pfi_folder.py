"""Build a PFI globalData object from a result FOLDER instead of the HTML report.

    from pfi_folder import is_pfi_folder, load_folder
    g = load_folder('WBM156')          # same dict triage.load_report returns

WHY. The engine's input contract is the HTML report, and that stays the default: it is the page the
microbiologist is already sent, so every verdict is checkable against the same document. But the PFI
result folder ships XLSX siblings of the exact three tables the engine reads, and reading those
instead removes a dependency on PFI's HTML template surviving a version upgrade - the report is a
Vue single-page app and `globalData` is an implementation detail of it, while the spreadsheets are
the deliverable. Verified identical on all five HTX swabs, row for row:

    species  373/929/693/967/737     resistance  33/80/72/90/66     virulence  252/468/414/657/654

WHICH FILE FEEDS WHICH BLOCK. Basic.stat.xlsx and Classify.stat.xlsx disagree - for WBM156 the first
says Classified_Read 622,642 and the second says 604,556, because they count at different stages.
`basicSummary.readsQc` in the HTML is Basic.stat verbatim, "(91.28%)" suffixes included, and that is
the block gate_integrity balances. Taking the wrong one silently fails the integrity gate on every
sample, so this module mirrors Basic.stat and leaves the parallel numbers alone.

NOT COVERED. `actionAssemble` and `actionFastqPathReview` are HTML-only links into the PFI web app.
No gate reads them. `showRNA` is false for a DNA folder, which is what makes the RNA agents report
NOT_TESTED - the same as every DNA-only HTML report delivered so far.

ponytail: stdlib xlsx reader, ~40 lines, no pandas. The engine is meant to run wherever the report
does; adding a numeric stack to read four spreadsheets would cost more than it buys.
"""
import os
import re
import zipfile
from xml.etree import ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

# Each block the engine reads, and the sheet it comes from.
SPECIES = 'Classify.DNA.Species.xlsx'
AMR = 'Resistance.DNA.xlsx'
VF = 'Virulence.DNA.xlsx'
QC = 'Basic.stat.xlsx'
REQUIRED = (SPECIES, QC)          # AMR and VF may legitimately be empty; these two may not


def _col(ref):
    """'BC7' -> 54. Cells carry their address, and a blank cell is simply absent from the row."""
    n = 0
    for ch in re.match(r'[A-Z]*', ref or '').group(0):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def sheet_rows(path):
    """Every row of the first worksheet, as a list of strings. Blank trailing cells are dropped."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')):
                shared.append(''.join(t.text or '' for t in si.iter(NS + 't')))
        names = sorted(n for n in z.namelist()
                       if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
        if not names:
            raise ValueError(f'{path}: no worksheet')
        root = ET.fromstring(z.read(names[0]))
    out = []
    for row in root.iter(NS + 'row'):
        cells = {}
        for c in row.iter(NS + 'c'):
            t, v = c.get('t'), c.find(NS + 'v')
            if t == 'inlineStr':
                val = ''.join(x.text or '' for x in c.iter(NS + 't'))
            elif v is None:
                val = ''
            elif t == 's':
                val = shared[int(v.text)]
            else:
                val = v.text or ''
            cells[_col(c.get('r'))] = val
        out.append([cells.get(i, '') for i in range(max(cells) + 1)] if cells else [])
    return out


def table(path):
    """A header-row sheet as a list of dicts, matching the HTML table shape exactly."""
    rows = sheet_rows(path)
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    return [{k: (r[i] if i < len(r) else '') for i, k in enumerate(head) if k}
            for r in rows[1:] if any(str(c).strip() for c in r)]


def keyed(path):
    """A two-column key/value sheet (Basic.stat, Classify.stat) as one dict."""
    return {r[0].strip(): (r[1] if len(r) > 1 else '')
            for r in sheet_rows(path) if r and r[0].strip()}


def is_pfi_folder(path):
    """True when this directory holds a PFI result set this module can read."""
    return os.path.isdir(path) and all(
        os.path.exists(os.path.join(path, f)) for f in REQUIRED)


def load_folder(path):
    """Assemble the globalData dict the gate cascade expects, from the folder's spreadsheets."""
    if not is_pfi_folder(path):
        missing = [f for f in REQUIRED if not os.path.exists(os.path.join(path, f))]
        raise ValueError(f'{path}: not a PFI result folder (missing {", ".join(missing)})')

    def opt(name):
        p = os.path.join(path, name)
        return table(p) if os.path.exists(p) else []

    qc = keyed(os.path.join(path, QC))
    qc.setdefault('Sample', os.path.basename(os.path.normpath(path)))
    return {
        'basicSummary': {'readsQc': {'data': [qc]}},
        'indentification_DNA': {'speciesData': {'data': table(os.path.join(path, SPECIES))}},
        'drugResistance': {'DNA': {'data': opt(AMR)}},
        'virulence': {'DNA': {'data': opt(VF)}},
        # A DNA result folder carries no RNA tables, which is what puts the RNA agents in
        # NOT_TESTED rather than letting them fall through to NO_ACTION.
        'showRNA': False,
    }


def _selftest():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, 'WBM156')
    if not is_pfi_folder(d):
        print('pfi_folder selftest SKIPPED - no WBM156 result folder here')
        return
    g = load_folder(d)
    sp = g['indentification_DNA']['speciesData']['data']
    assert len(sp) == 373, len(sp)
    assert sp[0]['Taxid'] and sp[0]['Scientific Name'] and sp[0]['Real Read']
    q = g['basicSummary']['readsQc']['data'][0]
    # The integrity gate balances THIS block. Basic.stat must be the source, not Classify.stat.
    num = lambda s: int(str(s).split(' ')[0].replace(',', ''))
    assert num(q['Unclassified_Read']) + num(q['Classified_Read']) == num(q['Clean_Read'])
    assert num(q['Classified_Read']) == 622642, q['Classified_Read']
    assert len(g['drugResistance']['DNA']['data']) == 33
    assert len(g['virulence']['DNA']['data']) == 252
    assert g['virulence']['DNA']['data'][0]['Virulence Factor']
    assert not is_pfi_folder(os.path.join(root, 'analysis'))
    print('pfi_folder selftest OK')


if __name__ == '__main__':
    _selftest()
