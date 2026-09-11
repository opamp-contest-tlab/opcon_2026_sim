.param psvoltage=1.2v
.subckt opamp inm inp out vdd vss
c000 net021 out c=0.3p
mn1 net016 net016 vss vss cmosn l=1.1e-05 w=9.17e-06 m=1 as=5.502e-12 ps=1.954e-05 ad=5.502e-12 pd=1.954e-05
mn2 net004 net016 vss vss cmosn l=1.1e-05 w=9.17e-06 m=1 as=5.502e-12 ps=1.954e-05 ad=5.502e-12 pd=1.954e-05
mn3 out net004 vss vss cmosn l=1.1e-05 w=9.17e-06 m=1 as=5.502e-12 ps=1.954e-05 ad=5.502e-12 pd=1.954e-05
mp1 net027 net027 vdd vdd cmosp l=1.1e-05 w=2.75e-05 m=1 as=1.65e-11 ps=5.62e-05 ad=1.65e-11 pd=5.62e-05
mp2 net003 net027 vdd vdd cmosp l=1.1e-05 w=2.75e-05 m=2 as=1.65e-11 ps=5.62e-05 ad=1.65e-11 pd=5.62e-05
mp3 out net027 vdd vdd cmosp l=1.1e-05 w=2.75e-05 m=1 as=1.65e-11 ps=5.62e-05 ad=1.65e-11 pd=5.62e-05
mp4 net016 inm net003 net003 cmosp l=1.1e-05 w=2.75e-05 m=1 as=1.65e-11 ps=5.62e-05 ad=1.65e-11 pd=5.62e-05
r0 net027 vss r=145k
mp5 net004 inp net003 net003 cmosp l=1.1e-05 w=2.75e-05 m=1 as=1.65e-11 ps=5.62e-05 ad=1.65e-11 pd=5.62e-05
r002 net004 net021 r=160k
.ends
