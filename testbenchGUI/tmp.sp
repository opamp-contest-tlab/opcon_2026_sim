.param psvoltage=1.6v
.subckt opamp inm inp out vdd vss
m1 fbm inm n004 vss cmosn l=2e-06 w=2e-05 m=20 as=1.2e-11 ps=4.12e-05 ad=1.2e-11 pd=4.12e-05
m2 fbp inp n004 vss cmosn l=2e-06 w=2e-05 m=20 as=1.2e-11 ps=4.12e-05 ad=1.2e-11 pd=4.12e-05
m3 n004 vbn vss vss cmosn l=2e-06 w=1e-05 as=6e-12 ps=2.12e-05 ad=6e-12 pd=2.12e-05
m4 vbn vbn vss vss cmosn l=1e-06 w=5e-06 as=3e-12 ps=1.12e-05 ad=3e-12 pd=1.12e-05
r1 vbp vbn r=1meg
m5 n002 n002 vdd vdd cmosp l=2e-06 w=2.2e-05 as=1.32e-11 ps=4.52e-05 ad=1.32e-11 pd=4.52e-05
m6 n001 n002 vdd vdd cmosp l=2e-06 w=2.2e-05 as=1.32e-11 ps=4.52e-05 ad=1.32e-11 pd=4.52e-05
m7 out n001 vdd vdd cmosp l=2e-06 w=0.00022 as=1.32e-10 ps=0.0004412 ad=1.32e-10 pd=0.0004412
m8 out n005 vss vss cmosn l=2e-06 w=0.0001 as=6e-11 ps=0.0002012 ad=6e-11 pd=0.0002012
m9 n001 inp fbp vss cmosn l=2e-06 w=2e-05 m=20 as=1.2e-11 ps=4.12e-05 ad=1.2e-11 pd=4.12e-05
m10 n002 inm fbm vss cmosn l=2e-06 w=2e-05 m=20 as=1.2e-11 ps=4.12e-05 ad=1.2e-11 pd=4.12e-05
m11 vbp vbp vdd vdd cmosp l=1e-06 w=2e-05 as=1.2e-11 ps=4.12e-05 ad=1.2e-11 pd=4.12e-05
m14 n005 n006 vss vss cmosn l=2e-06 w=1e-05 as=6e-12 ps=2.12e-05 ad=6e-12 pd=2.12e-05
m16 n003 vbp vdd vdd cmosp l=2e-06 w=2.2e-05 as=1.32e-11 ps=4.52e-05 ad=1.32e-11 pd=4.52e-05
m12 n006 n006 vss vss cmosn l=2e-06 w=1e-05 as=6e-12 ps=2.12e-05 ad=6e-12 pd=2.12e-05
c1 out fbp c=3p
c2 n005 fbm c=3p
m13 n006 n001 n003 vdd cmosp l=2e-06 w=2.2e-05 as=1.32e-11 ps=4.52e-05 ad=1.32e-11 pd=4.52e-05
m15 n005 n002 n003 vdd cmosp l=2e-06 w=2.2e-05 as=1.32e-11 ps=4.52e-05 ad=1.32e-11 pd=4.52e-05
.ends
