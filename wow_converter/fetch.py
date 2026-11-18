"""Glen's WoW Tools - fetcher. Copies byte ranges out of WoW's data files (read-only).
Reads requests.txt lines:  archive_number offset size output_name
Writes to the 'out' folder next to this script and logs to fetch_log.txt."""
import os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
data_dir = r'C:\Games\World of Warcraft\Data\data'
outdir = os.path.join(here, 'out'); os.makedirs(outdir, exist_ok=True)
log = open(os.path.join(here, 'fetch_log.txt'), 'w', encoding='utf-8')
def p(*a):
    print(*a); print(*a, file=log); log.flush()
t0 = time.time(); n = 0; bad = 0
for line in open(os.path.join(here, 'requests.txt'), encoding='utf-8'):
    parts = line.split()
    if len(parts) != 4 or line.startswith('#'): continue
    arch, off, size, name = int(parts[0]), int(parts[1]), int(parts[2]), parts[3]
    try:
        with open(os.path.join(data_dir, 'data.%03d' % arch), 'rb') as f:
            f.seek(off); buf = f.read(size)
        with open(os.path.join(outdir, name), 'wb') as g:
            g.write(buf)
        n += 1
        p('ok', name, len(buf))
    except Exception as e:
        bad += 1; p('FAILED', name, repr(e))
p('DONE %d ok, %d failed, %.1fs' % (n, bad, time.time() - t0))
log.close()
