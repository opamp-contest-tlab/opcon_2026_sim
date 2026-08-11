

* settings ***************
.lib 'lib/settings.lib' settings2
**************************

* opamp ******************
.include 'tmp.sp'
**************************

* ac1 ********************
.title ac1
.lib 'lib/analyses_dep4.lib' ac1
**************************

* ac2 ********************
.alter ac2
.del lib 'lib/analyses_dep4.lib' ac1
.lib 'lib/analyses_dep4.lib' ac2
**************************

* dc1 ********************
.alter dc1
.del lib 'lib/analyses_dep4.lib' ac2
.lib 'lib/analyses_dep4.lib' dc1
**************************

* dc2 ********************
.alter dc2
.del lib 'lib/analyses_dep4.lib' dc1
.lib 'lib/analyses_dep4.lib' dc2
**************************

* tran1 ********************
.alter tran1
.del lib 'lib/analyses_dep4.lib' dc2
.lib 'lib/analyses_dep4.lib' tran1
**************************

* tran2 ********************
.alter tran2
.del lib 'lib/analyses_dep4.lib' tran1
.lib 'lib/analyses_dep4.lib' tran2
**************************
