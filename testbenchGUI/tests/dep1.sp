* Opamp netlist for contest (K. Yamamoto, 2024)
.param   psvoltage=3.0
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
M1 N001 N001 Vdd Vdd cmosp l=0.2u w=4.1u m=val1 ad='4.1u*0.6u' as='4.1u*0.6u' pd='4.1u+1.2u' ps='4.1u+1.2u'
R1 N001 N002 100MEG
M2 N002 N002 Vss Vss cmosn l=0.3u w=2.2u m=val2 ad='2.2u*0.6u' as='2.2u*0.6u' pd='2.2u+1.2u' ps='2.2u+1.2u'
* Diff1
M3 N003 N003 Vdd Vdd cmosp l=0.2u w=2u m=val3 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M4 N004 N003 Vdd Vdd cmosp l=0.2u w=2u m=val3 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M5 N003 inm N005 Vss cmosn l=0.3u w=2u m=val4 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M6 N004 inp N005 Vss cmosn l=0.3u w=2u m=val4 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M7 N005 N002 Vss Vss cmosn l=0.3u w=2.2u m=val5 ad='2.2u*0.6u' as='2.2u*0.6u' pd='2.2u+1.2u' ps='2.2u+1.2u'
* Diff2
M8 N006 N006 Vss Vss cmosn l=0.3u w=2u m=val6 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M9 N007 N006 Vss Vss cmosn l=0.3u w=2u m=val6 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M10 N006 inm N008 Vdd cmosp l=0.2u w=2u m=val7 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M11 N007 inp N008 Vdd cmosp l=0.2u w=2u m=val7 ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
M12 N008 N001 Vdd Vdd cmosp l=0.2u w=4.1u m=val8 ad='4.1u*0.6u' as='4.1u*0.6u' pd='4.1u+1.2u' ps='4.1u+1.2u'
* Output
M13 out N004 Vdd Vdd cmosp l=0.2u w=0.4u m=val9 ad='0.4u*0.6u' as='0.4u*0.6u' pd='0.4u+1.2u' ps='0.4u+1.2u'
M14 out N007 Vss Vss cmosn l=0.3u w=0.4u m=val10 ad='0.4u*0.6u' as='0.4u*0.6u' pd='0.4u+1.2u' ps='0.4u+1.2u'
.ends opamp