"""-20 dBFS pk stepped sines, 1/12 oct 100 Hz-10 kHz, 0.4 s on 0.1 s off, 1 s lead: mksweep.py OUT.wav FREQS.npy"""
import numpy as np, sys
from scipy.io import wavfile
fs=48000; A=10**(-20/20)
f=np.round(100*2**(np.arange(0,int(np.log2(100)*12)+1)/12),1)  # 1/12 oct 100 Hz..10 kHz
on,gap,ramp=0.4,0.1,0.01
seg=[np.zeros(int(1.0*fs))]
for fr in f:
    t=np.arange(int(on*fs))/fs; x=A*np.sin(2*np.pi*fr*t)
    r=int(ramp*fs); w=np.ones_like(x); w[:r]=np.linspace(0,1,r); w[-r:]=np.linspace(1,0,r)
    seg+= [x*w, np.zeros(int(gap*fs))]
y=np.concatenate(seg).astype(np.float32)
wavfile.write(sys.argv[1], fs, y); np.save(sys.argv[2], f); print(len(f), len(y)/fs)
