"""Spectrum of a capture at given frequencies: spec.py CAPTURE.npy F1 F2 ..."""
import numpy as np, sys
from scipy.signal import welch
x=np.load(sys.argv[1]); fs=50000
f,P=welch(x,fs,window='flattop',nperseg=2**16)   # bin 0.76 Hz; flattop for amplitude
df=f[1]
def lvl(f0):  # rms of a sinusoid near f0 from flattop PSD: sum power over +-5 bins
    i=np.argmin(abs(f-f0)); return np.sqrt(P[i-8:i+9].sum()*df/ (1.0) )  # approx
# rely on spectrum amplitude: use welch 'spectrum' scaling
f,Ps=welch(x,fs,window='flattop',nperseg=2**16,scaling='spectrum')
def amp(f0):
    i=np.argmin(abs(f-f0)); j=i-6+np.argmax(Ps[i-6:i+7]); return np.sqrt(Ps[j]), f[j]
for f0 in [float(a) for a in sys.argv[2:]]:
    v,fp=amp(f0); print(f"{f0:8.2f} Hz (pk @{fp:8.2f}): {v*1e3:8.4f} mVrms  {20*np.log10(v):7.1f} dBV")
# top peaks
idx=np.argsort(Ps)[::-1]; seen=[]
for i in idx:
    if all(abs(f[i]-s)>20 for s in seen): seen.append(f[i])
    if len(seen)>=12: break
print("top:", ", ".join(f"{s:.0f}:{20*np.log10(np.sqrt(Ps[np.argmin(abs(f-s))])):.1f}" for s in sorted(seen)))
