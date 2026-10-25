"""Summarise the basement gauge (32_s6_h_us_maxbotix.txt): first sustained >5 mm, peak, recession.

Usage: python -I scripts/gauge_events.py <path-to-txt> [threshold_mm] [sustain_s]
"""
import sys
from collections import OrderedDict
from datetime import datetime

path = sys.argv[1]
thr = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
sustain = int(sys.argv[3]) if len(sys.argv) > 3 else 30

# Several samples per second: take the per-second median.
per_sec = OrderedDict()
with open(path) as f:
    next(f)
    for line in f:
        line = line.strip()
        if not line:
            continue
        ts, v = line.split(";")
        per_sec.setdefault(ts, []).append(float(v))

secs = []
for ts, vals in per_sec.items():
    vals.sort()
    secs.append((datetime.strptime(ts, "%d/%m/%Y %H:%M:%S"), vals[len(vals) // 2]))

print(f"samples={sum(len(v) for v in per_sec.values())} seconds={len(secs)} "
      f"span={secs[0][0]:%H:%M:%S}-{secs[-1][0]:%H:%M:%S}")


def first_sustained(series, cond):
    for i in range(len(series)):
        win = series[i:i + sustain]
        if len(win) == sustain and all(cond(v) for _, v in win):
            return series[i][0]
    return None


onset = first_sustained(secs, lambda v: v > thr)
peak_t, peak_v = max(secs, key=lambda x: x[1])
after = [s for s in secs if s[0] > peak_t]
recede = first_sustained(after, lambda v: v <= thr) if after else None
first_any = next((t for t, v in secs if v > 0), None)
print(f"first nonzero: {first_any:%H:%M:%S}" if first_any else "first nonzero: none")
print(f"onset (>{thr} mm for {sustain}s): {onset:%H:%M:%S}" if onset else "onset: none")
print(f"peak: {peak_v:.1f} mm at {peak_t:%H:%M:%S}")
plateau = [t for t, v in secs if v >= peak_v - 2]
print(f"within 2 mm of peak: {plateau[0]:%H:%M:%S}-{plateau[-1]:%H:%M:%S}")
print(f"recede (<= {thr} mm for {sustain}s after peak): {recede:%H:%M:%S}" if recede else "recede: not within record")
# coarse profile every 60 s
for t, v in secs[::60]:
    print(f"  {t:%H:%M:%S} {v:6.1f}")
