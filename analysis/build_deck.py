"""Build the HTX biosurveillance briefing deck on the MGI 2025 template.

Data: Basic.stat.xlsx (QC), analysis/species_all.tsv (taxonomy), analysis/amr.tsv (MEGARes),
analysis/vf.tsv (VFDB), assembly/*.amr_attribution.tsv + assembly/*.<db>.tsv (assembly cross-check).
Narrative is the conclusion set from docs/biothreat_assessment.md.

Typography/geometry follow HTX_biosurveillance_briefing_modifed.pptx (the user's hand-adjusted
reference): Arial throughout, MINIMUM body size 12 pt - see MIN_PT, which floors every run.

    python3 analysis/build_deck.py    ->  HTX_biosurveillance_briefing.pptx
"""
import csv, os, openpyxl
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
TPL = 'MGI PPT templates_2025_v1.pptx'
OUT = 'HTX_biosurveillance_briefing.pptx'
SAMPLES = ['WBM156', 'WBM174', 'WBM179', 'WBM185', 'WBM232']
MIN_PT = 12.0            # user requirement: nothing smaller than Arial 12
FONT = 'Arial'

BLUE = RGBColor(0x00, 0x53, 0x9B)
LIGHT = RGBColor(0xED, 0xF2, 0xF8)
INK = RGBColor(0x33, 0x33, 0x33)
RED = RGBColor(0xC0, 0x2A, 0x2A)
AMBER = RGBColor(0xB8, 0x6A, 0x00)
GREEN = RGBColor(0x1E, 0x7A, 0x3C)
GREY = RGBColor(0x77, 0x77, 0x77)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SITES = {
    'WBM156': 'Ferry terminal - arrival restroom, tap',
    'WBM174': 'Changi T3 - arrival, automated passport scanner',
    'WBM179': 'Changi T3 - departure, fingerprint reader',
    'WBM185': 'Changi T3 - departure, check-in kiosk touchscreen',
    'WBM232': 'Changi T4 - departure, trolley handles (rows 5-6)',
}

FLAGGED = {
    'WBM156': [
        ('Streptococcus pneumoniae', '70 reads / est. 1,800', 'Bracken inflation; oral commensal streptococci dominate the sample', 'amber'),
        ('Pseudomonas aeruginosa', '111 reads (0.76%)', 'Plausible tap/water biofilm; load is flat across all 5 sites', 'amber'),
        ('Neisseria meningitidis', '31 reads', 'N. subflava is 8.2% here - species assignment is not separable', 'grey'),
        ('Campylobacter concisus', '523 reads', 'Oral commensal Campylobacter, not the enteric pathogen', 'grey'),
    ],
    'WBM174': [
        ('Clostridium botulinum', '11 reads', 'REFUTED - 1 unique molecule, and zero bont toxin genes (see next slide)', 'grey'),
        ('Bacillus cereus group', '22 reads, 41% unique', 'Real, but zero pXO1 / pXO2 - not B. anthracis', 'amber'),
        ('Staphylococcus aureus', '1,444 reads (0.40%)', 'Present; blaZ + ermC detected, no mecA in this sample', 'amber'),
        ('Rickettsia felis', '101 reads', 'Flea-borne agent; not on the CDC list, low-confidence call', 'grey'),
    ],
    'WBM179': [
        ('Vibrio cholerae', '11 reads', 'REFUTED - 1 unique molecule; no ctxA/ctxB', 'grey'),
        ('Staphylococcus aureus', '1,699 reads (0.20%)', 'Present with blaZ; mecI but no mecA', 'amber'),
        ('Staphylococcus epidermidis', '65,238 reads (3.37%)', 'Skin flora - expected on a fingerprint reader', 'grey'),
        ('Streptococcus sanguinis', '41,427 reads (3.43%)', 'Oral flora transfer; 40 VFDB hits are commensal adhesins', 'grey'),
    ],
    'WBM185': [
        ('mecA - MEG_3778', '90.89% cov / 10.51x', 'Strongest AMR call in the batch at read level, but it did NOT assemble - host unresolved', 'red'),
        ('CTX-M ESBL - MEG_2430', '82.88% cov / 7.25x', 'Extended-spectrum beta-lactamase, with K. pneumoniae also present', 'red'),
        ('Staphylococcus aureus', '2,300 reads (0.42%)', 'Co-occurs with abundant CoNS (S. hominis 11.2%, S. haemolyticus 1.8%)', 'amber'),
        ('Bacillus cereus group', '43 reads, 42% unique', 'Real environmental B. cereus; zero anthrax plasmid markers', 'amber'),
    ],
    'WBM232': [
        ('Acinetobacter baumannii', '6,496 reads (4.72%), 27% unique', 'SITE-SPECIFIC ENRICHMENT: 2,507 rpm vs 58-417 rpm elsewhere (6-43x)', 'red'),
        ('CTX-M ESBL - MEG_2378', '60.56% cov / 11.69x', 'Acquired ESBL - the one genuinely acquired resistance gene here', 'red'),
        ('AdeJ and LpxA - MEG_692, MEG_3626', '53.72% / 5.38x  and  51.65% / 1.90x', 'Efflux pump and colistin target - PRESENCE ONLY, resistance not demonstrated', 'amber'),
        ('L. pneumophila / C. tetani / N. meningitidis', '25 / 28 / 13 reads', 'ALL REFUTED - 2 unique molecules, or GC far from the expected genome GC', 'grey'),
    ],
}

ACTIONABLE = {
    'WBM156': ('NO ACTION', GREEN,
               'Profile is human oral/salivary flora plus water-associated organisms - exactly what a '
               'restroom tap should look like. No threat agent, no clinically meaningful AMR '
               '(13 resistance classes, all intrinsic/ribosomal).\n'
               'CAVEAT: 91.3% of reads were host; only 622k classified reads survived - ~5x less microbial '
               'data than WBM179. The short hit list is a sensitivity limit, not a clean tap.'),
    'WBM174': ('MONITOR', AMBER,
               'Skin-flora dominated (C. acnes 34.2%) - a heavily hand-touched surface behaving normally. '
               'S. aureus with blaZ + ermC is community-normal carriage, not a resistance event.\n'
               'ACTION: none beyond routine touchpoint cleaning. The botulism call is refuted on both the '
               'organism and the toxin gene, and should be closed out rather than escalated.'),
    'WBM179': ('MONITOR', AMBER,
               'Deepest classified dataset (3.1M reads) and still nothing threat-level. Oral + skin flora '
               'transfer from fingers; 21 AMR classes but no mecA, no ESBL.\n'
               'ACTION: none. The V. cholerae call is refuted at read level - close it out. This sample is '
               'the best negative-control-like baseline in the batch for comparison.'),
    'WBM185': ('INVESTIGATE', RED,
               'Highest AMR burden in the batch: 90 genes across 21 classes, including mecA at 90.9% '
               'breadth and CTX-M at 82.9%.\n'
               'ACTION 1: resolve the mecA host. S. aureus (2,300 reads) and coagulase-negative '
               'staphylococci (S. hominis 11.2%) are both abundant, and assembly did NOT recover mecA, so '
               '"MRSA" cannot be claimed from this data. Culture is now the only way to settle it.\n'
               'ACTION 2: enhanced disinfection audit of check-in kiosk touchscreens; re-swab with a '
               'culture arm to obtain isolates for AST.'),
    'WBM232': ('ESCALATE', RED,
               'The one operationally significant finding in the batch. A. baumannii at 4.72% with a '
               'depth-normalised load 6-43x above every other site - this passes the kitome test, i.e. it '
               'is real site enrichment, not reagent background. 268 A. baumannii virulence-factor hits.\n'
               'ACTION 1: re-swab T4 trolley handles WITH A CULTURE ARM. Metagenomics cannot give you an '
               'antibiogram; you need an isolate for AST.\n'
               'ACTION 2: treat the CTX-M / LpxA / AdeJ combination as a hypothesis to test by culture, '
               'not as a confirmed XDR organism - the next slide explains why.\n'
               'ACTION 3: trolley-handle disinfection frequency review at T4 departure rows 5-6.'),
}

CAT_A = [
    ('Bacillus anthracis', 'NEGATIVE',
     'B. cereus group present (WBM174 22 rds, WBM185 43 rds, both >40% unique, correct GC). '
     'Excluded at PLASMID level: zero pXO1 (pagA/lef/cya/atxA), zero pXO2 (capA-E). '
     'Only VFDB hits are chromosomal isdC and GBAA_RS23245, shared across the whole B. cereus group.'),
    ('Clostridium botulinum', 'NEGATIVE',
     'WBM174: 11 reads that collapse to ONE unique sequence - an amplification artifact, not an organism. '
     'No botulinum neurotoxin (bont) gene in any sample.'),
    ('Yersinia pestis', 'NEGATIVE',
     'No Yersinia of any species in any sample. The ybtT/irp2 hits are yersiniabactin siderophore genes '
     'carried by K. pneumoniae and E. coli - a shared iron-uptake island, not plague.'),
    ('Francisella tularensis', 'NEGATIVE', 'Absent, and no Francisella congeners detected.'),
    ('Variola / Orthopoxvirus', 'NEGATIVE',
     'Meaningful negative - these are dsDNA viruses and WOULD have been sequenced by this DNA library.'),
    ('Viral haemorrhagic fevers\n(Ebola, Marburg, Lassa, Junin)', 'NOT ASSESSABLE',
     'All are RNA viruses. There is NO RNA library in this batch, so they are structurally undetectable. '
     'This is a missing test, not a negative result.'),
]

CAT_BC = [
    ('B', 'Brucella spp.', '"Brucella anthropi" in all 5 samples (14-1,824 rds)',
     'NOT BRUCELLOSIS - this is Ochrobactrum anthropi, renamed into Brucella in 2020. Ubiquitous reagent '
     'contaminant. It carries a false "Human Infection: Y" flag in every sample.'),
    ('B', 'Vibrio cholerae', 'WBM179, 11 reads', 'REFUTED - 1 unique molecule, no cholera toxin genes.'),
    ('B', 'Clostridium perfringens', 'WBM174 84, WBM185 248, WBM232 29 rds',
     'Present at trace level. Ubiquitous soil/gut anaerobe; no epsilon-toxin (etx) gene detected.'),
    ('B', 'Escherichia coli', '62-118 real reads (est. up to 12,076)',
     'Trace, and the Bracken estimate is inflated ~100x. No O157:H7 markers (stx1/stx2/eae) detected.'),
    ('B', 'Salmonella / Shigella / Coxiella /\nBurkholderia mallei / pseudomallei / C. psittaci', 'ABSENT',
     'No reads assigned to any of these in any sample.'),
    ('B', 'Rickettsia felis / massiliae', 'WBM174 101, WBM185 151/53 rds',
     'Low-confidence trace calls; R. prowazekii (the listed agent) is absent.'),
    ('C', 'Mycobacterium tuberculosis (MDR-TB)', 'ABSENT',
     'No M. tuberculosis complex reads. The Mycobacterium present (M. avium, M. grossiae, M. paragordonae, '
     'M. intracellulare) are environmental NTM, typical of building water systems.'),
    ('C', 'Nipah, Hantavirus, TBE, Yellow fever', 'NOT ASSESSABLE',
     'All RNA viruses - no RNA library. Same structural blind spot as the Category A VHFs.'),
]


# --- helpers ---------------------------------------------------------------
def _style(run, size, bold, color):
    run.font.size = Pt(max(size, MIN_PT))
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT


def txbox(slide, l, t, w, h, text, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
          space_after=4, line=1.0):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.03)
    tf.margin_top = tf.margin_bottom = 0
    for i, ln in enumerate(text.split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line
        r = p.add_run(); r.text = ln
        _style(r, size, bold, color)
    return tb


def title(slide, text, sub=None, w=12.4, size=26):
    txbox(slide, 0.5, 0.28, w, 0.55, text, size=size, bold=True, color=BLUE)
    if sub:
        txbox(slide, 0.5, 0.88, 12.4, 0.3, sub, size=12, color=GREY)
    ln = slide.shapes.add_shape(1, Inches(0.5), Inches(1.22), Inches(12.33), Inches(0.028))
    ln.fill.solid(); ln.fill.fore_color.rgb = BLUE
    ln.line.fill.background(); ln.shadow.inherit = False


def table(slide, l, t, w, rows, widths, sizes=(12, 12), header_h=0.34, row_h=0.30,
          colors=None, bolds=None):
    nr, nc = len(rows), len(rows[0])
    h = header_h + row_h * (nr - 1)
    gt = slide.shapes.add_table(nr, nc, Inches(l), Inches(t), Inches(w), Inches(h)).table
    gt.rows[0].height = Inches(header_h)
    for i in range(1, nr):
        gt.rows[i].height = Inches(row_h)
    tot = sum(widths)
    for c, ww in enumerate(widths):
        gt.columns[c].width = Inches(w * ww / tot)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = gt.cell(r, c)
            cell.text = str(val)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BLUE if r == 0 else (LIGHT if r % 2 == 0 else WHITE)
            numeric = str(val).replace('.', '').replace('%', '').replace(',', '').replace('x', '')
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.RIGHT if (c > 0 and r > 0 and numeric.isdigit()) else PP_ALIGN.LEFT
                for run in p.runs:
                    _style(run, sizes[0] if r == 0 else sizes[1],
                           (r == 0) or (bolds or {}).get((r, c), False),
                           WHITE if r == 0 else (colors or {}).get((r, c), INK))
    return gt


def chip(slide, l, t, w, h, text, rgb, size=13):
    s = slide.shapes.add_shape(5, Inches(l), Inches(t), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb
    s.line.fill.background(); s.shadow.inherit = False
    s.text_frame.word_wrap = True
    p = s.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    _style(r, size, True, WHITE)
    return s


def panel(slide, l, t, h, rgb=BLUE):
    """Thin left rule used to group a block of text."""
    s = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(0.07), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb
    s.line.fill.background(); s.shadow.inherit = False
    return s


# --- data loading ----------------------------------------------------------
def qc():
    return {s: {k: v for k, v in openpyxl.load_workbook(f'{s}/Basic.stat.xlsx').active
                .iter_rows(values_only=True)} for s in SAMPLES}


def species():
    rows = [x for x in csv.DictReader(open('analysis/species_all.tsv'), delimiter='\t')
            if x['level'] == 'speciesData']
    return {s: sorted([x for x in rows if x['sample'] == s], key=lambda x: -float(x['ab']))
            for s in SAMPLES}


def amr_counts():
    a = list(csv.DictReader(open('analysis/amr.tsv'), delimiter='\t'))
    return {s: (len([x for x in a if x['sample'] == s]),
                len({x['Class'] for x in a if x['sample'] == s})) for s in SAMPLES}


def vf_counts():
    v = list(csv.DictReader(open('analysis/vf.tsv'), delimiter='\t'))
    return {s: len([x for x in v if x['sample'] == s]) for s in SAMPLES}


# --- slides ----------------------------------------------------------------
def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[3])


def s_cover(prs):
    cov = prs.slides[0]
    for sh in cov.shapes:
        if sh.name == '副标题 2':
            sh.text_frame.text = 'Biosurveillance of Singapore Transport Hubs'
            for p in sh.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(30); r.font.bold = True; r.font.name = FONT
        if sh.name == '文本框 6':
            sh.text_frame.text = 'DNA shotgun metagenomics  |  5 surface swabs  |  2026.07.31'
            for p in sh.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(12); r.font.name = FONT
    txbox(cov, 0.82, 4.55, 7.6, 1.1,
          'Threat-agent screen, CDC Category A/B/C assessment, and AMR profile\n'
          'Kraken2 / Bracken taxonomy - MEGARes AMR - VFDB virulence',
          size=13, color=GREY, line=1.15)


def s_method(prs):
    s = blank(prs)
    title(s, 'The assay, and what it can and cannot see')
    txbox(s, 0.5, 1.45, 6.0, 0.3, 'METHOD', size=13, bold=True, color=BLUE)
    txbox(s, 0.5, 1.8, 6.0, 3.9,
          'DNA-only shotgun metagenomics, 150 bp paired-end\n'
          'Host depletion, then Kraken2 classification with Bracken abundance re-estimation\n'
          'AMR called against MEGARes; virulence factors against VFDB\n'
          'Reports generated by PFI software v5.1.2 / database v5.1.1\n\n'
          'Verification performed for this briefing:\n'
          '3,678 of 3,698 extracted FASTQs match their reported read counts exactly (the 20 '
          'differences are name normalisation only). Resistance and virulence tables match the '
          'HTML reports row for row.',
          size=14, line=1.25, space_after=6)
    txbox(s, 6.9, 1.45, 6.0, 0.3, 'THREE THINGS THAT WILL MISLEAD YOU', size=13, bold=True, color=RED)
    txbox(s, 6.9, 1.8, 6.0, 3.9,
          '1. Judge on Real Read, not Abundance. Abundance and Estimate Read are Bracken '
          'redistributions and can be wildly inflated - S. agalactiae in WBM174 has 29 species-specific '
          'reads but an estimate of 8,301.\n\n'
          '2. A read count is not a molecule count. These libraries are low-biomass and heavily '
          'amplified: only 27-36% of reads are unique. Several trace calls collapse to a single unique '
          'sequence.\n\n'
          '3. The "Human Infection: Y" flag is unreliable at the edges - it fires on renamed '
          'environmental organisms.',
          size=14, line=1.25, space_after=6)
    txbox(s, 0.5, 5.85, 12.4, 1.2,
          'Discriminators applied throughout: (a) unique-read fraction vs the library baseline; '
          '(b) observed GC vs expected genome GC; (c) depth-normalised load (reads per million '
          'classified) across all five sites - a real site finding is enriched in one sample, a reagent '
          'contaminant is flat everywhere; (d) for B. anthracis, presence of the pXO1/pXO2 plasmid '
          'markers rather than chromosomal genes shared across the B. cereus group.',
          size=12, color=GREY, line=1.2)


def s_qc(prs, Q):
    s = blank(prs)
    title(s, 'Initial QC - all five samples', 'Basic.stat.xlsx, DNA libraries, 150 bp PE')
    rows = [['Sample', 'Site', 'Raw reads', 'GC', 'Q30', 'Low-qual', 'Host', 'Clean', 'Unclass.', 'Classified']]
    colors, bolds = {}, {}
    for i, sm in enumerate(SAMPLES, start=1):
        q = Q[sm]
        pct = lambda k: q[k].split(' ')[1].strip('()')
        rows.append([sm, SITES[sm].split(' - ')[0], f"{q['Raw_Read']:,}", q['Raw_GC'], q['Raw_Q30'],
                     pct('Lowquality_Read'), pct('Host_Read'), pct('Clean_Read'),
                     pct('Unclassified_Read'), f"{int(q['Classified_Read'].split(' ')[0]):,}"])
        colors[(i, 0)] = BLUE
    colors[(1, 6)] = colors[(1, 9)] = RED
    bolds[(1, 6)] = bolds[(1, 9)] = True
    table(s, 0.5, 1.5, 12.33, rows, [1.1, 2.74, 1.42, 0.82, 0.88, 1.1, 0.99, 0.99, 1.04, 1.26],
          sizes=(12, 14), row_h=0.38, colors=colors, bolds=bolds)
    txbox(s, 0.5, 3.9, 12.4, 0.3, 'READ THIS TABLE FROM RIGHT TO LEFT', size=13, bold=True, color=BLUE)
    txbox(s, 0.5, 4.25, 12.4, 2.55,
          'Base quality is uniformly excellent - Q30 98.0-98.5%, low-quality reads under 1.5% in every '
          'sample. Quality is not the limiting factor here; BIOMASS is.\n\n'
          'The number that determines sensitivity is the last column, classified reads. WBM156 lost '
          '91.3% of its reads to host depletion and ended with 622,642 classified reads - roughly 5x '
          'less microbial data than WBM179. Its shorter hit list is a detection-limit artifact, not '
          'evidence of a cleaner tap.\n\n'
          'Unclassified fractions of 72-90% are normal for environmental swabs against a clinical '
          'database. We probed the unclassified bin of all five samples directly (GC spectrum plus '
          'over-represented 25-mers) and found no dominant unknown organism - top k-mers sit at '
          '0.01-0.02% after removing a poly-G artifact and Illumina adapter read-through.',
          size=14, line=1.25, space_after=7)


def s_caveats(prs):
    s = blank(prs)
    title(s, 'QC caveats that change how you read the results')
    items = [
        ('No negative control', AMBER, 1.5,
         'No blank extraction control was included in this batch. Trace calls below ~100 reads cannot be '
         'formally separated from reagent background. We compensated with a cross-sample kitome analysis '
         '(216 core taxa shared by all 5 samples; 50 known contaminant genera; 46 with abundance-vs-depth '
         'correlation rho <= -0.6, e.g. P. putida at rho = -1.00) - but a blank would have been better.'),
        ('Heavy amplification', AMBER, 1.15,
         'Unique-read fraction is only 27-36% and is flat across read-count bins. Any taxon far below its '
         "sample's baseline is amplified single molecules, not an organism. This is the test that refuted "
         'C. botulinum, V. cholerae and L. pneumophila.'),
        ('Sequencing artifacts', GREY, 1.15,
         'Both R2 files carry a poly-G 25-mer spike (~0.14% of reads) - standard 2-colour-chemistry '
         'no-signal. WBM156 shows Illumina adapter read-through at 0.26% of reads (WBM179 at 0.02%), '
         'indicating short inserts from degraded or low-input DNA. Trim before any assembly or k-mer work.'),
        ('AMR genes are called off reads', RED, 1.5,
         'The PFI pipeline reports resistance genes without linking them to an organism, and MEGARes '
         'holds many near-identical alleles of the same gene, so ONE true gene lights up SEVERAL MEG_ '
         'accessions. Both effects are unpacked on the WBM185 and WBM232 evidence slides. This is the '
         'single biggest interpretive trap in the standard report.'),
    ]
    y = 1.5
    for head, rgb, h, body in items:
        panel(s, 0.5, y, h, rgb)
        txbox(s, 0.72, y, 2.6, 0.3, head, size=13.5, bold=True, color=rgb)
        txbox(s, 3.3, y - 0.02, 9.5, h, body, size=14, line=1.2)
        y += h + 0.14


def s_topspecies(prs, SP):
    s = blank(prs)
    title(s, 'Top species by abundance - side by side',
          'Bracken abundance %; species-specific ("real") reads in brackets')
    rows = [['#'] + SAMPLES]
    for i in range(6):
        rows.append([str(i + 1)] + [f"{SP[sm][i]['name']}\n{SP[sm][i]['ab']}%  "
                                    f"({int(SP[sm][i]['real']):,} rds)" for sm in SAMPLES])
    table(s, 0.5, 1.5, 12.33, rows, [0.35, 2.4, 2.4, 2.4, 2.4, 2.4], sizes=(12, 12), row_h=0.62)
    txbox(s, 0.5, 5.65, 12.4, 1.1,
          'Cutibacterium acnes - skin sebaceous flora - tops four of five samples and reaches 57.4% in '
          'WBM232. These are hand-touched surfaces, so a human skin signature dominating is the expected '
          'baseline, not a finding. WBM185 is the exception: Staphylococcus and Kocuria displace C. acnes, '
          'and WBM232 is the only sample where a recognised nosocomial pathogen (A. baumannii) reaches '
          'the top three.', size=12, color=GREY, line=1.2)


def s_sample(prs, sm, Q, SP, AM, VF):
    s = blank(prs)
    verdict, vcolor, action = ACTIONABLE[sm]
    title(s, f'{sm}  -  {SITES[sm]}', w=10.1, size=22)
    chip(s, 10.88, 0.3, 1.95, 0.45, verdict, vcolor)
    q = Q[sm]
    txbox(s, 0.5, 1.4, 12.35, 0.2,
          f"{q['Raw_Read']:,} raw reads   |   host {q['Host_Read'].split(' ')[1].strip('()')}   |   "
          f"{int(q['Classified_Read'].split(' ')[0]):,} classified   |   {len(SP[sm])} species   |   "
          f"{AM[sm][0]} AMR genes / {AM[sm][1]} classes   |   {VF[sm]} VF hits",
          size=12, color=BLUE, bold=True)

    txbox(s, 0.5, 1.82, 5.9, 0.28, 'TOP SPECIES BY ABUNDANCE', size=12.5, bold=True, color=BLUE)
    rows = [['Species', 'Ab %', 'Real', 'Est.']]
    for x in SP[sm][:8]:
        rows.append([x['name'], x['ab'], f"{int(x['real']):,}", f"{int(x['est']):,}"])
    table(s, 0.5, 2.15, 5.9, rows, [3.33, 0.75, 0.86, 0.97], sizes=(12, 12), row_h=0.27)

    txbox(s, 6.7, 1.82, 6.13, 0.28, 'FLAGGABLE SPECIES / SIGNALS', size=12.5, bold=True, color=RED)
    cmap = {'red': RED, 'amber': AMBER, 'grey': GREY}
    y = 2.15
    for name, ev, note, lvl in FLAGGED[sm]:
        rgb = cmap[lvl]
        dot = s.shapes.add_shape(9, Inches(6.72), Inches(y + 0.05), Inches(0.11), Inches(0.11))
        dot.fill.solid(); dot.fill.fore_color.rgb = rgb
        dot.line.fill.background(); dot.shadow.inherit = False
        txbox(s, 6.95, y - 0.03, 5.88, 0.24, f'{name}   -   {ev}', size=13, bold=True, color=rgb)
        txbox(s, 6.95, y + 0.24, 5.88, 0.42, note, size=12, color=INK, line=1.1)
        y += 0.72

    txbox(s, 0.5, 4.95, 12.33, 0.28, f'WHAT IS ACTIONABLE  -  {verdict}',
          size=12.5, bold=True, color=vcolor)
    txbox(s, 0.5, 5.28, 12.33, 1.7, action, size=13, line=1.18, space_after=3)


def s_botulism(prs):
    s = blank(prs)
    title(s, 'WBM174 - botulism, and why the bont gene is the actual test',
          'Why 11 reads of Clostridium botulinum is not a botulism finding')
    txbox(s, 0.5, 1.42, 6.05, 0.28, 'WHAT MAKES BOTULISM A CATEGORY A AGENT', size=13, bold=True, color=BLUE)
    panel(s, 0.5, 1.75, 2.15, BLUE)
    txbox(s, 0.72, 1.75, 5.83, 2.15,
          'The threat is not the bacterium, it is the protein. Botulinum neurotoxin (BoNT) is the most '
          'potent toxin known - lethal dose in the low nanograms per kilogram. It blocks acetylcholine '
          'release at the neuromuscular junction, causing descending flaccid paralysis and respiratory '
          'failure.\n\n'
          'It is a Category A agent because it can be disseminated in food or as an aerosol, and because '
          'even a small cluster consumes ICU beds, ventilators and antitoxin stocks.',
          size=13, line=1.2, space_after=6)
    txbox(s, 6.78, 1.42, 6.05, 0.28, 'WHY THE ORGANISM ALONE MEANS NOTHING', size=13, bold=True, color=BLUE)
    panel(s, 6.78, 1.75, 2.15, BLUE)
    txbox(s, 7.0, 1.75, 5.83, 2.15,
          'C. botulinum is a spore-forming anaerobe living in soil and dust worldwide, so traces on an '
          'environmental surface are unremarkable.\n\n'
          'Toxin production comes from the bont gene cluster (types A-G; A, B, E, F cause human disease), '
          'which is MOBILE - chromosome, plasmid or prophage depending on strain. Non-toxigenic '
          'C. botulinum exists, and toxigenic C. butyricum and C. baratii exist. Species identity '
          'therefore does not imply toxin.',
          size=13, line=1.2, space_after=6)

    txbox(s, 0.5, 4.4, 12.33, 0.28, 'WHAT THE WBM174 DATA ACTUALLY SHOWS', size=13, bold=True, color=GREEN)
    rows = [['Test', 'Result', 'Interpretation'],
            ['Species-specific reads', '11', 'Below any credible detection threshold to begin with'],
            ['Unique molecules after dedup', '1', 'All 11 reads are copies of ONE fragment - an '
             'amplification artifact, not an organism'],
            ['bont toxin gene (VFDB)', '0 reads', 'Zero in WBM174 and zero in all four other samples'],
            ['Other Clostridium virulence hits', 'C. perfringens only',
             'fbpA, tadA, nagH/nagI adhesins in WBM185 - no neurotoxin of any kind anywhere in the batch']]
    colors = {(i, 1): GREEN for i in range(1, 5)}
    table(s, 0.5, 4.72, 12.33, rows, [2.9, 2.0, 7.43], sizes=(12, 12), row_h=0.42, colors=colors,
          bolds={(i, 1): True for i in range(1, 5)})
    txbox(s, 0.5, 6.85, 12.4, 0.5,
          'VERDICT: negative on the organism AND on the toxin gene - and botulism (foodborne, wound, '
          'infant-intestinal or aerosol) has no dry-surface transmission route anyway. Close the call out.',
          size=12.5, bold=True, color=GREEN, line=1.15)


def s_wbm185_evidence(prs):
    s = blank(prs)
    title(s, 'WBM185 - how mecA and CTX-M are actually called',
          'Reading the MEGARes rows in the HTML report: why MEG_3778 and MEG_2430, and not the others')
    txbox(s, 0.5, 1.38, 12.33, 0.28,
          'THE MEGARes HIERARCHY:   Type  >  Class  >  Mechanism  >  GROUP  >  MEG_ accession',
          size=13, bold=True, color=BLUE)
    txbox(s, 0.5, 1.7, 12.33, 0.5,
          'A MEG_ number is not a gene - it is ONE REFERENCE ALLELE of a gene, and MEGARes stores many '
          'near-identical alleles per gene. The rows below are NOT three mecA genes and two CTX-M genes: '
          'they are one mecA read pool and one CTX-M read pool, split across alleles.',
          size=13, line=1.18)
    rows = [['Group', 'Accession', 'Coverage', 'Depth', 'Reading'],
            ['MECA', 'MEG_3778', '90.89%', '10.51x', 'BEST ALLELE - highest breadth AND highest depth. This is the representative call.'],
            ['MECA', 'MEG_3780', '59.77%', '2.83x', 'Partial cross-mapping of the same read pool onto a homologous allele'],
            ['MECA', 'MEG_3770', '58.52%', '6.68x', 'Same - not an additional mecA gene'],
            ['MECI', 'MEG_3803', '65.50%', '5.66x', 'mecI is the REPRESSOR of the mec operon - co-occurrence supports a genuine SCCmec element (mecR1 not detected)'],
            ['CTX', 'MEG_2430', '82.88%', '7.25x', 'BEST ALLELE of the blaCTX-M family - the representative ESBL call'],
            ['CTX', 'MEG_2435', '54.14%', '2.71x', 'Partial cross-mapping onto a second CTX-M allele'],
            ['BLAZ', 'MEG_1330 / 1331', '70.65% / 64.73%', '8.17x / 4.24x', 'Staphylococcal penicillinase - ordinary carriage, and the one gene that DID assemble']]
    colors = {(1, 0): RED, (1, 4): RED, (5, 0): RED, (5, 4): RED}
    bolds = {(1, 0): True, (1, 4): True, (5, 0): True, (5, 4): True}
    table(s, 0.5, 2.32, 12.33, rows, [0.85, 1.7, 1.4, 1.2, 7.18], sizes=(12, 12), row_h=0.42,
          colors=colors, bolds=bolds)
    txbox(s, 0.5, 5.68, 6.05, 0.28, 'WHY 90.89% COVERAGE IS THE STRONG PART', size=13, bold=True, color=GREEN)
    txbox(s, 0.5, 6.0, 6.05, 1.1,
          'Breadth, not depth, separates a real gene from a conserved fragment. 90.89% of the ~2 kb mecA '
          'reference carries read support at 10.5x depth - a near-complete gene, and the reason mecA is '
          'the strongest AMR call in the batch AT READ LEVEL.',
          size=13, line=1.15)
    txbox(s, 6.78, 5.68, 6.05, 0.28, 'WHY IT STILL IS NOT "MRSA"', size=13, bold=True, color=RED)
    txbox(s, 6.78, 6.0, 6.05, 1.1,
          'Read-level calling carries no linkage, so mecA is tied to no organism - and S. aureus '
          '(2,300 rds) and coagulase-negative staphylococci (S. hominis 11.2%) are both abundant. We '
          'assembled the sample to close that gap. It did not close - see next slide.',
          size=13, line=1.15)


def s_assembly(prs):
    s = blank(prs)
    title(s, 'The assembly cross-check - and what it could not confirm',
          'megahit on host-depleted reads; abricate vs megares, card, resfinder, ncbi and plasmidfinder')
    rows = [['Sample', 'Contigs', 'Total', 'N50', 'AMR genes recovered on contigs', 'mecA / CTX-M?'],
            ['WBM185', '57,627', '54.9 Mb', '849 bp',
             "blaZ + blaR1 + blaI penicillinase operon (97-99% id, full length, GC 25.3%), msrA, mphC, "
             "lnuA, fusB, aph(3')-Ia, ant(4')-Ia, ermX, qacA/C/J/R  +  12 staphylococcal plasmid replicons",
             'NO - neither, in any of the 5 databases'],
            ['WBM232', '10,837', '15.9 Mb', '26,611 bp',
             "blaI, ermX, ant(3'')-IIa, mgrA  -  and no plasmid replicons at all",
             'NO - no CTX-M, no lpxA, no adeJ']]
    colors = {(1, 5): RED, (2, 5): RED, (1, 0): BLUE, (2, 0): BLUE}
    table(s, 0.5, 1.5, 12.33, rows, [0.95, 0.9, 0.85, 0.95, 5.85, 2.83], sizes=(12, 12), row_h=1.0,
          colors=colors, bolds={(1, 5): True, (2, 5): True})
    txbox(s, 0.5, 3.75, 12.33, 0.28, 'WHY THIS IS INFORMATIVE RATHER THAN A FAILED RUN',
          size=13, bold=True, color=BLUE)
    txbox(s, 0.5, 4.05, 12.33, 3.0,
          "WBM185's N50 of 849 bp is what an even, diverse community with no dominant organism looks like; "
          'WBM232 assembles far better because C. acnes at 57.4% gives deep uniform coverage.\n\n'
          'The assembly demonstrably works: the staphylococcal penicillinase operon came out full length at '
          '97-99% identity on a 22x contig of GC 25.3%, on staphylococcal plasmid replicons (rep7a/pSTE1, '
          'rep10/pNE131, repUS46, rep21/pWBG754). blaZ IS therefore attributable.\n\n'
          'mecA and CTX-M did not assemble at all - likeliest because their read pools split across '
          'divergent alleles from several staphylococcal species, so no consensus is reached, exactly as '
          'the multi-allele MEGARes pattern predicts. Mapping the per-taxon read sets onto the assembled '
          'AMR contigs returns ZERO reads at MAPQ >= 20 for every taxon, against 62 per 2M pairs from the '
          'unfiltered clean reads: the classifier never assigned these mobile elements to a species.\n\n'
          'CONCLUSION: gene presence is well supported at read level; HOST ATTRIBUTION IS NOT RESOLVABLE '
          'FROM THIS DATASET. Culture with AST is the only way to tell MRSA from methicillin-resistant '
          'skin staphylococci.',
          size=13, line=1.13, space_after=3)


def s_wbm232_evidence(prs):
    s = blank(prs)
    title(s, 'WBM232 - CTX-M with LpxA and AdeJ, and what XDR means',
          'Why partial coverage on the A. baumannii genome limits what can be claimed')
    rows = [['Determinant', 'Cov / Depth', 'What it is', 'What it does NOT prove'],
            ['CTX-M\nMEG_2378', '60.56%\n11.69x',
             'Acquired class A extended-spectrum beta-lactamase; destroys 3rd-generation cephalosporins. '
             'The only genuinely ACQUIRED resistance gene of the three.',
             'That it sits on the A. baumannii genome rather than on the K. pneumoniae also present '
             '(311 reads)'],
            ['AdeJ\nMEG_692', '53.72%\n5.38x',
             'Inner-membrane transporter of the AdeIJK RND efflux pump. CHROMOSOMAL AND INTRINSIC to '
             'essentially every A. baumannii; resistance comes from OVEREXPRESSION, usually via an adeN '
             'repressor mutation. The whole family is here - AdeH 88.6%/19.8x, AdeN 85.8%/8.9x, AdeG, '
             'AdeI, AdeL, AdeT1/T2.',
             'Anything about resistance - DNA cannot measure expression. It is better evidence that '
             'A. baumannii is genuinely present than that it is resistant.'],
            ['LpxA\nMEG_3626', '51.65%\n1.90x',
             'First enzyme of lipid A biosynthesis. Loss-of-function in lpxA/lpxC/lpxD abolishes LPS, and '
             'since colistin binds lipid A, an LPS-null A. baumannii is fully colistin-resistant. MEGARes '
             'files it as "colistin-resistant MUTANT".',
             'That the resistance mutation is there. lpxA is a core essential gene in every '
             'Gram-negative - presence is the default state. At 1.90x no variant can be called.']]
    colors = {(1, 0): RED, (2, 0): AMBER, (3, 0): AMBER}
    table(s, 0.5, 1.38, 12.33, rows, [1.5, 1.15, 5.85, 3.83], sizes=(12, 12), row_h=1.12,
          colors=colors, bolds={(i, 0): True for i in (1, 2, 3)})
    txbox(s, 0.5, 5.32, 6.05, 0.28, 'WHY LOW COVERAGE IS THE PROBLEM', size=13, bold=True, color=RED)
    txbox(s, 0.5, 5.64, 6.05, 1.45,
          '6,496 A. baumannii reads x 150 bp is ~0.97 Mb over a ~3.9 Mb genome - only ~0.25x '
          'genome-average. At 2-5x on one gene you cannot call the point mutations that lpxA/gyrA/parC '
          'resistance depends on, you cannot tell chromosome from plasmid from another organism because '
          'reads carry no linkage, and a sequencing error looks like a real SNP.',
          size=13, line=1.15)
    txbox(s, 6.78, 5.32, 6.05, 0.28, 'XDR - THE DEFINITION AND THE STAKES', size=13, bold=True, color=RED)
    txbox(s, 6.78, 5.64, 6.05, 1.45,
          'Magiorakos 2012 (ECDC/CDC): MDR = non-susceptible in >=3 drug categories; XDR = non-susceptible '
          "in ALL BUT <=2; PDR = all. IF one isolate had all of this - CTX-M off cephalosporins, aac(6') "
          'off aminoglycosides, AdeIJK off tetracyclines/tigecycline/fluoroquinolones, lpxA off colistin - '
          'that is XDR with the last-line drug gone. A hypothesis to culture, not a confirmed organism.',
          size=13, line=1.15)


def s_cat_a(prs):
    s = blank(prs)
    title(s, 'CDC Category A agents - are any actually present?',
          'The answer is no. Here is the evidence for each.')
    rows = [['Agent', 'Verdict', 'Evidence']]
    colors, bolds = {}, {}
    for i, (ag, vd, ev) in enumerate(CAT_A, start=1):
        rows.append([ag, vd, ev])
        colors[(i, 1)] = AMBER if vd == 'NOT ASSESSABLE' else GREEN
        bolds[(i, 1)] = True
    table(s, 0.5, 1.5, 12.33, rows, [2.31, 1.3, 8.72], sizes=(12, 12), row_h=0.72,
          colors=colors, bolds=bolds)
    txbox(s, 0.5, 6.3, 12.4, 0.7,
          'The anthrax exclusion is the important one: B. cereus group IS genuinely present in WBM174 and '
          'WBM185 at good unique-read fractions and correct GC. It is excluded as B. anthracis because '
          'both virulence plasmids are entirely absent - and the one capA hit in the data belongs to the '
          'S. aureus capsule operon, not the pXO2 capsule.', size=12, color=GREY, line=1.2)


def s_cat_bc(prs):
    s = blank(prs)
    title(s, 'CDC Category B and C agents')
    rows = [['Cat', 'Agent', 'Observed', 'Assessment']]
    colors = {}
    for i, (cat, ag, obs, note) in enumerate(CAT_BC, start=1):
        rows.append([cat, ag, obs, note])
        colors[(i, 0)] = BLUE
    table(s, 0.5, 1.36, 12.33, rows, [0.4, 2.98, 2.59, 6.36], sizes=(12, 12), row_h=0.6, colors=colors)
    txbox(s, 0.5, 6.63, 12.4, 0.6,
          'Nothing in Category B or C constitutes a public-health event. The single most important line '
          'is the first one: the Brucella flag in all five samples is a taxonomy artifact, and it is the '
          'kind of thing that triggers an unnecessary escalation if taken at face value.',
          size=12, color=GREY, line=1.2)


def s_amr(prs, AM):
    s = blank(prs)
    title(s, 'Antimicrobial resistance - where the real signal is',
          'MEGARes gene hits; coverage is breadth of the reference gene, depth is mean per-base coverage')
    KEY = {
        'WBM156': '- none of concern (13 classes, all intrinsic ribosomal / efflux)',
        'WBM174': 'blaZ 11.71x, ermC 10.17x  - community-normal S. aureus carriage',
        'WBM179': 'blaZ 6.04x, mecI 1.62x  - mecI regulator WITHOUT mecA; not MRSA',
        'WBM185': "mecA 90.9% / 10.51x,  CTX-M 82.9% / 7.25x,  aac(6') 79.8% / 7.42x,  blaZ 70.7% / 8.17x",
        'WBM232': "CTX-M 60.6% / 11.69x,  aac(6') 63.7% / 14.08x,  AdeH 88.6% / 19.8x,  AdeJ 53.7% / 5.38x,  LpxA 51.7% / 1.90x",
    }
    rows = [['Sample', 'AMR genes', 'Classes', 'Key beta-lactam / high-risk determinants']]
    colors, bolds = {}, {}
    for i, sm in enumerate(SAMPLES, start=1):
        rows.append([sm, AM[sm][0], AM[sm][1], KEY[sm]])
        colors[(i, 0)] = BLUE
        if sm in ('WBM185', 'WBM232'):
            colors[(i, 3)] = RED; bolds[(i, 3)] = True
    table(s, 0.5, 1.5, 12.33, rows, [1.1, 1.1, 0.9, 9.22], sizes=(12, 12), row_h=0.42,
          colors=colors, bolds=bolds)
    txbox(s, 0.5, 4.22, 12.4, 0.28, 'THE LIMITATION THAT MATTERS', size=13, bold=True, color=RED)
    txbox(s, 0.5, 4.57, 12.4, 2.3,
          'The PFI pipeline calls AMR genes straight off reads, so a gene is never linked to the organism '
          'carrying it. "mecA present" in a sample containing both S. aureus (2,300 reads) AND abundant '
          'coagulase-negative staphylococci (S. hominis 11.2%, S. haemolyticus 1.8%, S. epidermidis 4.1%) '
          'does not tell you whose mecA it is - and methicillin-resistant S. epidermidis is an ordinary '
          'skin organism, whereas MRSA on a check-in kiosk is a different conversation.\n\n'
          'We assembled both flagged samples with megahit to close this gap. blaZ was successfully placed '
          'on a staphylococcal plasmid; mecA, CTX-M, lpxA and adeJ did not assemble at all, so their host '
          'organism remains genuinely unresolved. Culture with AST is the way to settle it.',
          size=13, line=1.22, space_after=8)


def s_recs(prs):
    s = blank(prs)
    title(s, 'Recommendations')
    recs = [
        ('1', 'Re-swab WBM232 (T4 trolley handles) with a culture arm', RED,
         'Metagenomics cannot produce an antibiogram, and at 0.25x genome coverage it cannot call the '
         'lpxA / gyrA point mutations either. An A. baumannii isolate is needed for AST.'),
        ('2', 'Do not use the word "MRSA" for WBM185 on current evidence', RED,
         'Read-level mecA is strong (90.9% breadth) but assembly could not recover it, so it cannot be '
         'attributed to S. aureus rather than to the abundant coagulase-negative staphylococci.'),
        ('3', 'Add an RNA library to the protocol', AMBER,
         'Four of six Category A agents and every respiratory virus of surveillance interest are RNA '
         'viruses. The current assay cannot see them at all. This is the single largest gap.'),
        ('4', 'Include a blank extraction control in every batch', AMBER,
         'Without one, no trace call below ~100 reads can be formally cleared. This would have settled '
         'the botulism and cholera calls in minutes instead of days.'),
        ('5', 'Report Real Read and gene breadth alongside Abundance', GREY,
         'Bracken redistribution inflated several trace organisms by 30-100x, and collapsing the multiple '
         'MEG_ alleles of one gene into a single best-allele row would stop the double-counting.'),
    ]
    y = 1.5
    for n, head, rgb, body in recs:
        c = s.shapes.add_shape(9, Inches(0.5), Inches(y + 0.02), Inches(0.34), Inches(0.34))
        c.fill.solid(); c.fill.fore_color.rgb = rgb
        c.line.fill.background(); c.shadow.inherit = False
        p = c.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = n
        _style(r, 13, True, WHITE)
        txbox(s, 1.0, y, 5.6, 0.5, head, size=13, bold=True, color=rgb, line=1.05)
        txbox(s, 6.75, y, 6.08, 0.9, body, size=12, line=1.18)
        y += 1.0


def build():
    prs = Presentation(TPL)
    Q, SP, AM, VF = qc(), species(), amr_counts(), vf_counts()

    s_cover(prs)
    s_method(prs)
    s_qc(prs, Q)
    s_caveats(prs)
    s_topspecies(prs, SP)
    for sm in SAMPLES:
        s_sample(prs, sm, Q, SP, AM, VF)
        if sm == 'WBM174':
            s_botulism(prs)
        elif sm == 'WBM185':
            s_wbm185_evidence(prs)
            s_assembly(prs)
        elif sm == 'WBM232':
            s_wbm232_evidence(prs)
    s_cat_a(prs)
    s_cat_bc(prs)
    s_amr(prs, AM)
    s_recs(prs)

    # template slides: 0=cover, 1=empty placeholder, 2="Thank you"; ours start at 3.
    lst = prs.slides._sldIdLst
    ids = list(lst)
    lst.remove(ids[1])
    lst.remove(ids[2])
    lst.append(ids[2])

    prs.save(OUT)
    print(f'{OUT}: {len(list(lst))} slides')


if __name__ == '__main__':
    build()
