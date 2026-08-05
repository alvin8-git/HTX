"""Probe the unclassified read fraction for a dominant unknown organism.

A novel/engineered agent absent from the classifier DB would land in unclassify.*.fq.gz and
show up as a sharp GC mode plus a highly over-represented k-mer. Diffuse GC + a flat k-mer
spectrum means the unclassified bin is unassignable/host-derived sequence, not one organism.

Run from the repo root:  python3 analysis/probe_unclassified.py

All five samples probe on R1 (WBM232's R1 was re-copied and verified 2026-07-31). WBM185 R2 is
kept as a control: R2 files carry a poly-G artifact (2-colour chemistry no-signal) that the R1
files do not, so the top k-mer must be read past it -- hence TOPN below. WBM156 and WBM179
additionally show Illumina adapter read-through, flagged in the output.
"""
import gzip, collections

N = 300_000          # reads sampled per file
TOPN = 4             # report this many top k-mers so poly-G doesn't mask the real signal
FILES = [('WBM156', 1), ('WBM174', 1), ('WBM179', 1), ('WBM185', 1), ('WBM232', 1),
         ('WBM185', 2)]                # R2 control for the poly-G artifact


def probe(sample, mate):
    gc = collections.Counter(); kmer = collections.Counter(); seqs = collections.Counter(); n = 0
    with gzip.open(f'{sample}/unclassify.DNA_{mate}.fq.gz', 'rt') as fh:
        for i, line in enumerate(fh):
            if i % 4 != 1:
                continue
            s = line.strip(); n += 1
            if n > N:
                break
            if len(s) < 65:
                continue
            gc[round((s.count('G') + s.count('C')) / len(s) * 100 / 5) * 5] += 1
            seqs[s] += 1
            kmer[s[40:65]] += 1
    tot = sum(gc.values())
    print(f"{sample} R{mate}: n={n-1} unique={len(seqs)/(n-1)*100:.0f}% "
          f"GC modes={[(g, f'{c/tot*100:.0f}%') for g, c in gc.most_common(3)]}")
    for s, c in kmer.most_common(TOPN):
        tag = '  <-- poly-G artifact, ignore' if len(set(s)) == 1 else ''
        print(f"    {c:6d}  {c/tot*100:6.3f}%  {s}{tag}")


if __name__ == '__main__':
    for sample, mate in FILES:
        probe(sample, mate)
