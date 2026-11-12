"""AD3 scope ch1 record mode: ad3rec.py SECONDS OUT.npy [RANGE_V]"""
import ctypes as C, sys, time, numpy as np
d=C.cdll.LoadLibrary("libdwf.so")
secs=float(sys.argv[1]); out=sys.argv[2]; rng=float(sys.argv[3]) if len(sys.argv)>3 else 5.0
fs=50000.0; N=int(secs*fs)
h=C.c_int()
if not d.FDwfDeviceOpen(C.c_int(-1),C.byref(h)) or h.value==0:
    e=C.create_string_buffer(512); d.FDwfGetLastErrorMsg(e); sys.exit("open failed: "+e.value.decode())
try:
    d.FDwfAnalogInChannelEnableSet(h,C.c_int(0),C.c_int(1))
    d.FDwfAnalogInChannelRangeSet(h,C.c_int(0),C.c_double(rng))
    d.FDwfAnalogInChannelOffsetSet(h,C.c_int(0),C.c_double(0))
    d.FDwfAnalogInAcquisitionModeSet(h,C.c_int(3))   # acqmodeRecord
    d.FDwfAnalogInFrequencySet(h,C.c_double(fs))
    d.FDwfAnalogInRecordLengthSet(h,C.c_double(secs))
    d.FDwfAnalogInConfigure(h,C.c_int(0),C.c_int(0)); time.sleep(0.5)
    d.FDwfAnalogInConfigure(h,C.c_int(0),C.c_int(1))
    buf=np.zeros(N); got=0; lost=0; corr=0
    st=C.c_byte(); a=C.c_int(); l=C.c_int(); c=C.c_int()
    while got<N:
        d.FDwfAnalogInStatus(h,C.c_int(1),C.byref(st))
        d.FDwfAnalogInStatusRecord(h,C.byref(a),C.byref(l),C.byref(c))
        lost+=l.value; corr+=c.value
        n=min(a.value,N-got)
        if n:
            tmp=(C.c_double*n)(); d.FDwfAnalogInStatusData(h,C.c_int(0),tmp,C.c_int(n))
            buf[got:got+n]=tmp; got+=n
        elif st.value==2: break
        else: time.sleep(0.01)
    np.save(out,buf[:got]); print(f"samples {got} lost {lost} corrupt {corr} rms {np.sqrt(np.mean(buf[:got]**2))*1e3:.2f} mVrms")
finally:
    d.FDwfDeviceClose(h)
