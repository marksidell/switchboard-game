"""Step levels from sweep.npy + freqs.npy in DIR: response.py DIR"""
import numpy as np
import sys; S=sys.argv[1].rstrip("/")+"/"
x=np.load(S+"sweep.npy"); x=x-x.mean(); fs=50000; fr=np.load(S+"freqs.npy")
L=int(0.25*fs); w=np.hanning(L); n=np.arange(L)
def g(fq,a):
    s=x[a:a+L]; return abs(np.sum(s*w*np.exp(-2j*np.pi*fq*n/fs)))*2/w.sum()/np.sqrt(2)
def score(on): return sum(g(fr[k],on+int((k*0.5+0.08)*fs)) for k in range(0,60,3))
cands=np.arange(int(0.5*fs),int(3*fs),250)
on=cands[np.argmax([score(c) for c in cands])]
cands=np.arange(on-300,on+300,10); on=cands[np.argmax([score(c) for c in cands])]
res=np.array([g(fq,on+int((k*0.5+0.08)*fs)) for k,fq in enumerate(fr)])
# noise at same freq in the silence after the sweep (pilots, hum): 40.5 s onwards
end=on+int((len(fr)*0.5+0.5)*fs)
noise=np.array([g(fq,end) for fq in fr])
db=20*np.log10(res); nd=20*np.log10(noise)
k1=np.argmin(abs(fr-1000)); ref=db[k1]
print(f"onset {on/fs:.3f}s; 1 kHz at receiver {res[k1]*1e3:.2f} mVrms ({ref:.1f} dBV) for -20 dBFS pk")
for fq,d,nn in zip(fr,db,nd):
    print(f"{fq:7.1f} {d:7.1f} dBV {d-ref:+6.1f} dB   (silence {nn:6.1f})")
np.save(S+"resp.npy",np.vstack([fr,db,nd]))
