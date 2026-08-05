"""Verify every delivered FASTQ decompresses cleanly end to end.

File size and `gzip -t` are both unreliable here: one WBM232 file was byte-identical in size
before and after re-copy but corrupt mid-stream, and `gzip -t` exited 0 on corrupt files while
printing an error. Full decompression is the only check that caught both failures.

Run from the repo root:  python3 analysis/check_fastq_integrity.py
"""
import zlib, os, glob
from concurrent.futures import ProcessPoolExecutor


def check(path):
    size = os.path.getsize(path)
    d = zlib.decompressobj(31); ok = 0; out = 0; err = None
    with open(path, 'rb') as fh:
        while True:
            buf = fh.read(1 << 20)
            if not buf:
                break
            try:
                out += len(d.decompress(buf)); ok += len(buf)
                if d.eof:
                    rest = d.unused_data; d = zlib.decompressobj(31)
                    if rest:
                        out += len(d.decompress(rest))
            except Exception as e:
                err = str(e); break
    return path, size, ok / size * 100, out, err


if __name__ == '__main__':
    files = sorted(glob.glob('WBM*/*.fq.gz'))
    bad = 0
    with ProcessPoolExecutor(8) as ex:
        for path, size, pct, out, err in ex.map(check, files):
            flag = 'OK  ' if err is None else 'FAIL'
            if err:
                bad += 1
            print(f"{flag} {path:38s} {size/1e6:7.1f}MB  readable={pct:5.1f}%  "
                  f"out={out/1e9:5.2f}GB" + (f"  {err}" if err else ''))
    print(f"\n{len(files)-bad}/{len(files)} files intact")
