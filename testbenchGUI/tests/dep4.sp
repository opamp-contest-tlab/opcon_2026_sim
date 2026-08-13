* Opamp netlist for contest (K. Yamamoto, 2024)
.param   psvoltage=5.0
.subckt opamp inm inp out vdd vss
* Parameters by K. Yamamoto
.PARAM
+ val1=23
+ val2=14
+ val3=3
+ val4=2
+ val5=60
+ val6=3
+ val7=2
+ val8=60
+ val9=15
+ val10=15
* Bias
M1 N001 N001 Vdd Vdd bsim3v3p l=1.2u w=12u m=val1 
R1 N001 N002 100MEG
M2 N002 N002 Vss Vss bsim3v3n l=1.2u w=12u m=val2 
* Diff1
M3 N003 N003 Vdd Vdd bsim3v3p l=1.2u w=12u m=val3 
M4 N004 N003 Vdd Vdd bsim3v3p l=1.2u w=12u m=val3 
M5 N003 inm N005 Vss bsim3v3n l=1.2u w=12u m=val4 
M6 N004 inp N005 Vss bsim3v3n l=1.2u w=12u m=val4 
M7 N005 N002 Vss Vss bsim3v3n l=1.2u w=12u m=val5 
* Diff2
M8 N006 N006 Vss Vss bsim3v3n l=1.2u w=12u m=val6 
M9 N007 N006 Vss Vss bsim3v3n l=1.2u w=12u m=val6 
M10 N006 inm N008 Vdd bsim3v3p l=1.2u w=12u m=val7 
M11 N007 inp N008 Vdd bsim3v3p l=1.2u w=12u m=val7 
M12 N008 N001 Vdd Vdd bsim3v3p l=1.2u w=12u m=val8 
* Output
M13 out N004 Vdd Vdd bsim3v3p l=1.2u w=12u m=val9 
M14 out N007 Vss Vss bsim3v3n l=1.2u w=12u m=val10 
.ends opamp