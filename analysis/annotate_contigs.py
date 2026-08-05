"""Annotate assembled contigs with AMR / plasmid genes and attribute each to a host organism.

The PFI report calls AMR genes straight off reads, so a gene like mecA or CTX-M is never linked
to the organism carrying it -- in a sample with abundant S. aureus AND abundant coagulase-
negative staphylococci, "mecA present" does not tell you whose it is. This script closes that
gap in two steps:

  1. abricate vs megares (same DB the PFI report used, so results are comparable) plus card,
     resfinder, ncbi, and plasmidfinder -> which genes sit on which contig, with coordinates.
  2. For every AMR-carrying contig, map the per-taxon read sets already extracted under
     ExtractRead_DNA/Species/<Taxon>/ onto it. Whichever taxon's reads cover the contig is the
     organism carrying the gene. This needs no external taxonomy DB -- the classifier already
     did the taxon assignment, we are only re-using it.

Contig coverage and GC come from the megahit header (multi=... is k-mer depth).

Run from the repo root, after the assemblies exist:
    python3 analysis/annotate_contigs.py WBM232 WBM185
"""
import os, re, subprocess, sys, glob, collections, csv

ENV = os.path.expanduser('~/miniconda3/envs/pathogeniq/bin')
DBS = ['megares', 'card', 'resfinder', 'ncbi', 'plasmidfinder']
# Genes we specifically need attributed; others are reported but not read-mapped.
FOCUS = re.compile(r'(mec[AIR]|CTX|bla|OXA|TEM|SHV|van[AB]|mcr|LPXA|ICR)', re.I)
THREADS = '32'


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True,
                          env={**os.environ, 'PATH': ENV + ':' + os.environ['PATH']}, **kw)


def abricate(contigs, sample, outdir):
    """Run abricate across all DBs; return rows as dicts."""
    rows = []
    for db in DBS:
        out = f'{outdir}/{sample}.{db}.tsv'
        r = sh(f'abricate --db {db} --threads {THREADS} --quiet {contigs} > {out}')
        if r.returncode != 0:
            print(f'  ! abricate {db} failed: {r.stderr.strip()[:200]}')
            continue
        with open(out) as fh:
            for row in csv.DictReader(fh, delimiter='\t'):
                row['DB'] = db
                rows.append(row)
    return rows


def contig_stats(path):
    """seq id -> (length, kmer_coverage, gc%) from megahit headers."""
    stats = {}
    sid = None
    seq = []
    with open(path) as fh:
        for line in fh:
            if line.startswith('>'):
                if sid:
                    stats[sid] = _finish(hdr, seq)
                hdr = line[1:].strip()
                sid = hdr.split()[0]
                seq = []
            else:
                seq.append(line.strip())
        if sid:
            stats[sid] = _finish(hdr, seq)
    return stats


def _finish(hdr, seq):
    s = ''.join(seq)
    m = re.search(r'multi=([\d.]+)', hdr)
    gc = (s.count('G') + s.count('C')) / len(s) * 100 if s else 0
    return dict(len=len(s), cov=float(m.group(1)) if m else 0.0, gc=round(gc, 1))


def attribute(sample, contigs, target_ids, outdir):
    """Map each taxon's extracted reads onto the AMR contigs; report who covers what."""
    sub = f'{outdir}/{sample}.amr_contigs.fa'
    keep, out = False, []
    with open(contigs) as fh:
        for line in fh:
            if line.startswith('>'):
                keep = line[1:].split()[0] in target_ids
            if keep:
                out.append(line)
    open(sub, 'w').write(''.join(out))
    sh(f'bwa-mem2 index {sub} 2>/dev/null')

    taxa = sorted(glob.glob(f'{sample}/ExtractRead_DNA/Species/*/'))
    hits = collections.defaultdict(lambda: collections.Counter())
    for i, d in enumerate(taxa):
        name = os.path.basename(d.rstrip('/'))
        r1, r2 = f'{d}{name}_1.fq.gz', f'{d}{name}_2.fq.gz'
        if not (os.path.exists(r1) and os.path.exists(r2)):
            continue
        # -a off, primary alignments only, MAPQ>=20 to avoid repeat-driven cross-mapping
        r = sh(f'bwa-mem2 mem -t {THREADS} {sub} {r1} {r2} 2>/dev/null '
               f'| samtools view -F 0x900 -q 20 - | cut -f3 | sort | uniq -c')
        for line in r.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                hits[parts[1]][name] += int(parts[0])
        if (i + 1) % 100 == 0:
            print(f'    ...{i+1}/{len(taxa)} taxa mapped')
    return hits


def main(samples):
    outdir = 'assembly'
    for sample in samples:
        contigs = f'{outdir}/{sample}.contigs.fa'
        if not os.path.exists(contigs):
            print(f'{sample}: no assembly at {contigs} -- skipping')
            continue
        print(f'=== {sample}')
        stats = contig_stats(contigs)
        print(f'  contigs={len(stats)}  total={sum(s["len"] for s in stats.values())/1e6:.1f} Mb'
              f'  max={max(s["len"] for s in stats.values())/1e3:.0f} kb')

        rows = abricate(contigs, sample, outdir)
        print(f'  abricate hits: {len(rows)} across {len(DBS)} DBs')

        focus = [r for r in rows if FOCUS.search(r.get('GENE', ''))]
        target = {r['SEQUENCE'] for r in focus}
        print(f'  focus genes: {len(focus)} on {len(target)} contigs')
        if not target:
            continue

        hits = attribute(sample, contigs, target, outdir)

        with open(f'{outdir}/{sample}.amr_attribution.tsv', 'w', newline='') as fh:
            w = csv.writer(fh, delimiter='\t')
            w.writerow(['contig', 'len', 'kmer_cov', 'gc', 'db', 'gene', 'product',
                        'pct_cov', 'pct_id', 'top_taxa'])
            for r in sorted(focus, key=lambda x: -stats[x['SEQUENCE']]['len']):
                c = r['SEQUENCE']; s = stats[c]
                top = '; '.join(f'{t}:{n}' for t, n in hits[c].most_common(5)) or 'NO_TAXON_READS'
                w.writerow([c, s['len'], s['cov'], s['gc'], r['DB'], r['GENE'],
                            r.get('PRODUCT', '')[:60], r.get('%COVERAGE', ''),
                            r.get('%IDENTITY', ''), top])
        print(f'  -> {outdir}/{sample}.amr_attribution.tsv')


if __name__ == '__main__':
    main(sys.argv[1:] or ['WBM232', 'WBM185'])
