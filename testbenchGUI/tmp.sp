.param psvoltage=3
.subckt opamp inm inp out vdd vss
m37 out net18 vss vss cmosn l=200e-9 w=1.980e-6 m=1 as=1.188e-12 ps=5.16e-06 ad=1.188e-12 pd=5.16e-06
m36 net18 net5 net17 vss cmosn l=200e-9 w=3.5e-6 m=1 as=2.1e-12 ps=8.2e-06 ad=2.1e-12 pd=8.2e-06
m49 net17 net2 vss vss cmosn l=200e-9 w=3.5e-6 m=1 as=2.1e-12 ps=8.2e-06 ad=2.1e-12 pd=8.2e-06
m29 net20 net5 net19 vss cmosn l=200e-9 w=8.500e-7 m=1 as=5.1e-13 ps=2.9e-06 ad=5.1e-13 pd=2.9e-06
m50 net11 net6 vss vss cmosn l=4e-6 w=400e-9 m=1 as=2.4e-13 ps=2e-06 ad=2.4e-13 pd=2e-06
m43 net12 net6 vss vss cmosn l=4e-6 w=400e-9 m=1 as=2.4e-13 ps=2e-06 ad=2.4e-13 pd=2e-06
m39 net2 net2 vss vss cmosn l=200e-9 w=1e-6 m=1 as=6e-13 ps=3.2e-06 ad=6e-13 pd=3.2e-06
m11 net7 net7 net5 vss cmosn l=200e-9 w=2e-6 m=1 as=1.2e-12 ps=5.2e-06 ad=1.2e-12 pd=5.2e-06
m42 net10 net5 net12 vss cmosn l=200e-9 w=1e-6 m=1 as=6e-13 ps=3.2e-06 ad=6e-13 pd=3.2e-06
m15 net6 net5 net11 vss cmosn l=200e-9 w=1e-6 m=1 as=6e-13 ps=3.2e-06 ad=6e-13 pd=3.2e-06
m13 net5 net5 net2 vss cmosn l=200e-9 w=1e-6 m=1 as=6e-13 ps=3.2e-06 ad=6e-13 pd=3.2e-06
m47 net16 net5 net21 vss cmosn l=200e-9 w=8.500e-7 m=1 as=5.1e-13 ps=2.9e-06 ad=5.1e-13 pd=2.9e-06
m48 net21 net20 vss vss cmosn l=3e-6 w=3.500e-7 m=1 as=2.1e-13 ps=1.9e-06 ad=2.1e-13 pd=1.9e-06
m24 net19 net20 vss vss cmosn l=3e-6 w=3.500e-7 m=1 as=2.1e-13 ps=1.9e-06 ad=2.1e-13 pd=1.9e-06
m34 net18 net16 out out cmosp l=200e-9 w=1.120e-5 m=1 as=6.72e-12 ps=2.36e-05 ad=6.72e-12 pd=2.36e-05
m33 out net4 vdd vdd cmosp l=200e-9 w=1.590e-5 m=1 as=9.54e-12 ps=3.3e-05 ad=9.54e-12 pd=3.3e-05
m32 net14 net4 vdd vdd cmosp l=1e-6 w=15e-6 m=1 as=9e-12 ps=3.12e-05 ad=9e-12 pd=3.12e-05
m31 net13 net10 net14 net14 cmosp l=200e-9 w=3.000e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m44 net15 out net14 net14 cmosp l=200e-9 w=3.000e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m7 net4 net4 vdd vdd cmosp l=200e-9 w=3e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m41 net10 net5 net8 vdd cmosp l=200e-9 w=3e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m40 net8 inm net3 net3 cmosp l=600e-9 w=9e-6 m=1 as=5.4e-12 ps=1.92e-05 ad=5.4e-12 pd=1.92e-05
m17 net9 inp net3 net3 cmosp l=600e-9 w=9e-6 m=1 as=5.4e-12 ps=1.92e-05 ad=5.4e-12 pd=1.92e-05
m16 net3 net4 vdd vdd cmosp l=1e-6 w=15e-6 m=1 as=9e-12 ps=3.12e-05 ad=9e-12 pd=3.12e-05
m21 net6 net5 net9 vdd cmosp l=200e-9 w=3e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m38 net1 net1 net4 vdd cmosp l=200e-9 w=3e-6 m=1 as=1.8e-12 ps=7.2e-06 ad=1.8e-12 pd=7.2e-06
m45 net16 net5 net15 vdd cmosp l=200e-9 w=3.100e-6 m=1 as=1.86e-12 ps=7.4e-06 ad=1.86e-12 pd=7.4e-06
m46 net20 net5 net13 vdd cmosp l=200e-9 w=3.100e-6 m=1 as=1.86e-12 ps=7.4e-06 ad=1.86e-12 pd=7.4e-06
r0 net1 net7 r=330e3 m=1
r1 net22 net10 r=13e3
c0 vdd net22 c=300e-15
.ends opamp
