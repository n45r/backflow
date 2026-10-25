"""Walk the remote TAR headers with HTTP Range requests; print offset, size, name.

Usage: python -I scripts/tar_index.py <url> <total_size>
"""
import subprocess
import sys

url, total = sys.argv[1], int(sys.argv[2])


def rng(a, b):
    return subprocess.run(["curl", "-sL", "-r", f"{a}-{b}", url], capture_output=True, check=True).stdout


off = 0
while off + 512 <= total:
    h = rng(off, off + 511)
    if len(h) != 512 or h == b"\0" * 512:
        break
    name = h[0:100].rstrip(b"\0").decode()
    prefix = h[345:500].rstrip(b"\0").decode()
    size = int(h[124:136].rstrip(b"\0 ").decode() or "0", 8)
    print(f"{off + 512}\t{size}\t{(prefix + '/' if prefix else '') + name}", flush=True)
    off += 512 + ((size + 511) // 512) * 512
