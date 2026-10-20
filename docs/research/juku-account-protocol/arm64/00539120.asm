; mv-daemon/provider.(*Cloud115Provider).PollQrLogin
00539120  ldr x16,[x28, #0x10]
00539124  sub x17,sp,#0x6b0
00539128  cmp x17,x16
0053912c  b.ls 0x0053a6fc
00539130  sub x20,sp,#0x730
00539134  stp x29,x30,[x20, #-0x8]
00539138  mov sp,x20
0053913c  sub x29,sp,#0x8
00539140  str x1,[sp, #0x740]
00539144  str xzr,[sp, #0x1d0]
00539148  stp xzr,xzr,[sp, #0x1a8]
0053914c  nop
00539150  mov x0,x1
00539154  mov x1,x2
00539158  adrp x2,0xc0a000
0053915c  add x2,x2,#0x630
00539160  orr x3,xzr,#0x1
00539164  mov x4,xzr
00539168  mov x5,#-0x1
0053916c  bl 0x000b6600
00539170  cmp x1,#0x4
00539174  b.lt 0x005394a8
00539178  ldp x3,x4,[x0]
0053917c  str x4,[sp, #0x80]
00539180  str x3,[sp, #0x1e8]
00539184  ldp x5,x6,[x0, #0x10]
00539188  str x6,[sp, #0xa8]
0053918c  str x5,[sp, #0x210]
00539190  ldp x7,x8,[x0, #0x20]
00539194  str x8,[sp, #0x88]
00539198  str x7,[sp, #0x1f0]
0053919c  ldp x9,x10,[x0, #0x30]
005391a0  str x10,[sp, #0x68]
005391a4  str x9,[sp, #0x1d8]
005391a8  cmp x1,#0x5
005391ac  b.lt 0x005391c8
005391b0  ldp x11,x12,[x0, #0x40]
005391b4  cbnz x12,0x005391d4
005391b8  adrp x11,0x9d2000
005391bc  add x11,x11,#0x1df
005391c0  orr x12,xzr,#0x3
005391c4  b 0x005391d4
005391c8  adrp x11,0x9d2000
005391cc  add x11,x11,#0x1df
005391d0  orr x12,xzr,#0x3
005391d4  str x12,[sp, #0x100]
005391d8  str x11,[sp, #0x290]
005391dc  adrp x0,0xc18000
005391e0  add x0,x0,#0xa8
005391e4  adrp x1,0x1479000
005391e8  add x1,x1,#0xc40
005391ec  mov x2,#0xac00
005391f0  movk x2,#0xfc23, LSL #16
005391f4  movk x2,#0x6, LSL #32
005391f8  bl 0x00143200
005391fc  str x0,[sp, #0xd0]
00539200  str x1,[sp, #0x268]
00539204  str x2,[sp, #0x190]
00539208  add x0,sp,#0x178
0053920c  bl 0x000563c0
00539210  add x1,sp,#0x6a8
00539214  stp xzr,xzr,[x1]
00539218  stp xzr,xzr,[x1, #0x10]
0053921c  stp xzr,xzr,[x1, #0x20]
00539220  stp xzr,xzr,[x1, #0x30]
00539224  stp xzr,xzr,[x1, #0x40]
00539228  stp xzr,xzr,[x1, #0x50]
0053922c  stp xzr,xzr,[x1, #0x60]
00539230  adrp x27,0x142c000
00539234  add x27,x27,#0x210
00539238  ldp x4,x5,[x27]
0053923c  add x27,sp,#0x6a8
00539240  stp x4,x5,[x27]
00539244  adrp x4,0x9f2000
00539248  add x4,x4,#0x9c2
0053924c  mov x5,#0x11
00539250  add x27,sp,#0x6b8
00539254  stp x4,x5,[x27]
00539258  ldr x4,[sp, #0x1e8]
0053925c  ldr x5,[sp, #0x80]
00539260  add x27,sp,#0x6c8
00539264  stp x4,x5,[x27]
00539268  adrp x4,0x9d5000
0053926c  add x4,x4,#0xc73
00539270  orr x5,xzr,#0x6
00539274  add x27,sp,#0x6d8
00539278  stp x4,x5,[x27]
0053927c  ldr x4,[sp, #0x210]
00539280  ldr x6,[sp, #0xa8]
00539284  add x27,sp,#0x6e8
00539288  stp x4,x6,[x27]
0053928c  adrp x4,0x9d5000
00539290  add x4,x4,#0xc79
00539294  add x27,sp,#0x6f8
00539298  stp x4,x5,[x27]
0053929c  ldr x4,[sp, #0x1f0]
005392a0  ldr x5,[sp, #0x88]
005392a4  add x27,sp,#0x708
005392a8  stp x4,x5,[x27]
005392ac  mov x0,xzr
005392b0  orr x2,xzr,#0x7
005392b4  mov x3,x2
005392b8  bl 0x000765a0
005392bc  adrp x2,0x9d2000
005392c0  add x2,x2,#0x101
005392c4  orr x3,xzr,#0x3
005392c8  mov x4,x0
005392cc  mov x5,x1
005392d0  mov x6,xzr
005392d4  mov x7,xzr
005392d8  ldr x0,[sp, #0xd0]
005392dc  ldr x1,[sp, #0x268]
005392e0  bl 0x00269cd0
005392e4  cbnz x1,0x00539488
005392e8  str x0,[sp, #0x230]
005392ec  ldr x2,[x0, #0x38]
005392f0  str x2,[sp, #0x258]
005392f4  nop
005392f8  adrp x0,0x9e1000
005392fc  add x0,x0,#0x73b
00539300  mov x1,#0xa
00539304  bl 0x00209720
00539308  str x0,[sp, #0x2b0]
0053930c  str x1,[sp, #0x110]
00539310  adrp x0,0x8b0000
00539314  add x0,x0,#0x5c0
00539318  bl 0x0002dd40
0053931c  str x0,[sp, #0x2a8]
00539320  adrp x2,0x9e8000
00539324  add x2,x2,#0x5e2
00539328  orr x3,xzr,#0xc
0053932c  stp x2,x3,[x0]
00539330  adrp x0,0x969000
00539334  add x0,x0,#0x220
00539338  ldr x1,[sp, #0x258]
0053933c  ldr x2,[sp, #0x2b0]
00539340  ldr x3,[sp, #0x110]
00539344  bl 0x00021200
00539348  orr x2,xzr,#0x1
0053934c  stp x2,x2,[x0, #0x8]
00539350  adrp x27,0x147a000
00539354  ldr w2,[x27, #0x910]
00539358  cbnz w2,0x00539364
0053935c  ldr x3,[sp, #0x2a8]
00539360  b 0x00539374
00539364  ldr x2,[x0]
00539368  bl 0x000959d0
0053936c  ldr x3,[sp, #0x2a8]
00539370  stp x3,x2,[x25]
00539374  str x3,[x0]
00539378  adrp x27,0x142b000
0053937c  ldr x0,[x27, #0x120]
00539380  ldr x1,[sp, #0x230]
00539384  bl 0x00232f70
00539388  cbnz x1,0x005393f8
0053938c  str x0,[sp, #0x1c8]
00539390  ldp x1,x2,[x0, #0x40]
00539394  ldrsb x27,[x1]
00539398  adrp x3,0x53a000
0053939c  add x3,x3,#0x880
005393a0  str x3,[sp, #0x5f0]
005393a4  str x1,[sp, #0x5f8]
005393a8  str x2,[sp, #0x600]
005393ac  add x1,sp,#0x5f0
005393b0  str x1,[sp, #0x160]
005393b4  add x0,sp,#0x148
005393b8  bl 0x000563c0
005393bc  adrp x0,0x8e5000
005393c0  add x0,x0,#0xc80
005393c4  bl 0x0002dd40
005393c8  str x0,[sp, #0x718]
005393cc  ldr x1,[sp, #0x1c8]
005393d0  ldp x1,x2,[x1, #0x40]
005393d4  str x2,[sp, #0x238]
005393d8  cbz x1,0x00539504
005393dc  ldr x3,[x1, #0x8]
005393e0  adrp x4,0x1434000
005393e4  add x4,x4,#0xa60
005393e8  ldar x5,[x4]
005393ec  ldr w6,[x1, #0x10]
005393f0  ldr x7,[x5]
005393f4  b 0x0053a6bc
005393f8  str x2,[sp, #0x260]
005393fc  str x1,[sp, #0xc8]
00539400  ldr x1,[sp, #0xd0]
00539404  ldr x1,[x1, #0x28]
00539408  ldr x0,[sp, #0x268]
0053940c  blr x1
00539410  adrp x27,0x142d000
00539414  add x27,x27,#0x1f0
00539418  ldp x2,x3,[x27]
0053941c  bl 0x0009ba10
00539420  tbz w0,#0x0,0x00539460
00539424  adrp x0,0x95a000
00539428  add x0,x0,#0xde0
0053942c  bl 0x0002dd40
00539430  adrp x1,0x9d7000
00539434  add x1,x1,#0x3b7
00539438  orr x2,xzr,#0x7
0053943c  stp x1,x2,[x0]
00539440  str x0,[sp, #0x1d0]
00539444  stp xzr,xzr,[sp, #0x1a8]
00539448  bl 0x000568e0
0053944c  ldp x1,x2,[sp, #0x1a8]
00539450  ldr x0,[sp, #0x1d0]
00539454  ldp x29,x30,[sp, #-0x8]
00539458  add sp,sp,#0x730
0053945c  ret
00539460  str xzr,[sp, #0x1d0]
00539464  ldr x0,[sp, #0xc8]
00539468  ldr x1,[sp, #0x260]
0053946c  stp x0,x1,[sp, #0x1a8]
00539470  bl 0x000568e0
00539474  ldp x1,x2,[sp, #0x1a8]
00539478  ldr x0,[sp, #0x1d0]
0053947c  ldp x29,x30,[sp, #-0x8]
00539480  add sp,sp,#0x730
00539484  ret
00539488  str xzr,[sp, #0x1d0]
0053948c  stp x1,x2,[sp, #0x1a8]
00539490  bl 0x000568e0
00539494  ldp x1,x2,[sp, #0x1a8]
00539498  ldr x0,[sp, #0x1d0]
0053949c  ldp x29,x30,[sp, #-0x8]
005394a0  add sp,sp,#0x730
005394a4  ret
005394a8  adrp x0,0x8f8000
005394ac  add x0,x0,#0x5a0
005394b0  bl 0x0002dd40
005394b4  adrp x1,0x9f0000
005394b8  add x1,x1,#0xd63
005394bc  orr x2,xzr,#0x10
005394c0  stp x1,x2,[x0]
005394c4  str xzr,[sp, #0x1d0]
005394c8  adrp x1,0xc11000
005394cc  add x1,x1,#0xa38
005394d0  stp x1,x0,[sp, #0x1a8]
005394d4  bl 0x000568e0
005394d8  ldp x1,x2,[sp, #0x1a8]
005394dc  ldr x0,[sp, #0x1d0]
005394e0  ldp x29,x30,[sp, #-0x8]
005394e4  add sp,sp,#0x730
005394e8  ret
00539504  str x1,[sp, #0x2b0]
00539508  adrp x0,0x991000
0053950c  add x0,x0,#0xb80
00539510  bl 0x0002dd40
00539514  ldr x1,[sp, #0x2b0]
00539518  str x1,[x0]
0053951c  adrp x27,0x147a000
00539520  ldr w1,[x27, #0x910]
00539524  cbnz w1,0x00539530
00539528  ldr x3,[sp, #0x238]
0053952c  b 0x0053953c
00539530  bl 0x000959c0
00539534  ldr x3,[sp, #0x238]
00539538  str x3,[x25]
0053953c  str x3,[x0, #0x8]
00539540  adrp x1,0x898000
00539544  add x1,x1,#0x5e0
00539548  ldr x2,[sp, #0x718]
0053954c  bl 0x00134740
00539550  cbnz x0,0x00539bc0
00539554  ldr x1,[sp, #0x718]
00539558  ldr x1,[x1]
0053955c  cmp x1,#0x1
00539560  b.ne 0x00539574
00539564  orr x1,xzr,#0x7
00539568  adrp x0,0x9d7000
0053956c  add x0,x0,#0x6ea
00539570  b 0x005395ac
00539574  cmp x1,#0x2
00539578  b.ne 0x0053958c
0053957c  mov x1,#0x9
00539580  adrp x0,0x9dd000
00539584  add x0,x0,#0xd
00539588  b 0x005395ac
0053958c  cmn x1,#0x1
00539590  b.ne 0x005395a0
00539594  adrp x0,0x9d7000
00539598  add x0,x0,#0x6f1
0053959c  b 0x005395a8
005395a0  adrp x0,0x9d7000
005395a4  add x0,x0,#0x3b7
005395a8  orr x1,xzr,#0x7
005395ac  str x1,[sp, #0xa0]
005395b0  str x0,[sp, #0x208]
005395b4  adrp x0,0x95a000
005395b8  add x0,x0,#0xde0
005395bc  bl 0x0002dd40
005395c0  ldr x1,[sp, #0xa0]
005395c4  str x1,[x0, #0x8]
005395c8  adrp x27,0x147a000
005395cc  ldr w2,[x27, #0x910]
005395d0  cbnz w2,0x005395dc
005395d4  ldr x2,[sp, #0x208]
005395d8  b 0x005395e8
005395dc  bl 0x000959c0
005395e0  ldr x2,[sp, #0x208]
005395e4  str x2,[x25]
005395e8  str x2,[x0]
005395ec  cmp x1,#0x9
005395f0  b.ne 0x00539be0
005395f4  ldr x3,[x2]
005395f8  mov x4,#0x6f63
005395fc  movk x4,#0x666e, LSL #16
00539600  movk x4,#0x7269, LSL #32
00539604  movk x4,#0x656d, LSL #48
00539608  cmp x3,x4
0053960c  b.ne 0x00539be0
00539610  ldrb w2,[x2, #0x8]
00539614  cmp w2,#0x64
00539618  b.ne 0x00539be0
0053961c  str x0,[sp, #0x220]
00539620  add x27,sp,#0x698
00539624  stp xzr,xzr,[x27]
00539628  ldr x0,[sp, #0x290]
0053962c  ldr x1,[sp, #0x100]
00539630  bl 0x0008bd90
00539634  adrp x2,0x8a6000
00539638  add x2,x2,#0x880
0053963c  add x27,sp,#0x698
00539640  stp x2,x0,[x27]
00539644  adrp x0,0xa21000
00539648  add x0,x0,#0xf6e
0053964c  mov x1,#0x37
00539650  add x2,sp,#0x698
00539654  orr x3,xzr,#0x1
00539658  mov x4,x3
0053965c  bl 0x001042e0
00539660  str x0,[sp, #0x280]
00539664  str x1,[sp, #0xe8]
00539668  add x2,sp,#0x5c0
0053966c  stp xzr,xzr,[x2]
00539670  stp xzr,xzr,[x2, #0x10]
00539674  stp xzr,xzr,[x2, #0x20]
00539678  add x2,sp,#0x478
0053967c  mov x3,#0x5
00539680  stp xzr,xzr,[x2], #0x10
00539684  stp xzr,xzr,[x2], #0x10
00539688  stp xzr,xzr,[x2], #0x10
0053968c  stp xzr,xzr,[x2], #0x10
00539690  sub x3,x3,#0x1
00539694  cbnz x3,0x00539680
00539698  str xzr,[x2]
0053969c  orr x2,xzr,#-0x7f7f7f7f7f7f7f80
005396a0  str x2,[sp, #0x478]
005396a4  add x2,sp,#0x478
005396a8  str x2,[sp, #0x5d0]
005396ac  bl 0x0008ef50
005396b0  str x0,[sp, #0x5c8]
005396b4  nop
005396b8  adrp x0,0x8b0000
005396bc  add x0,x0,#0x5c0
005396c0  bl 0x0002dd40
005396c4  ldr x2,[sp, #0x80]
005396c8  str x2,[x0, #0x8]
005396cc  adrp x27,0x147a000
005396d0  ldr w2,[x27, #0x910]
005396d4  cbnz w2,0x005396e0
005396d8  ldr x4,[sp, #0x1e8]
005396dc  b 0x005396ec
005396e0  bl 0x000959c0
005396e4  ldr x4,[sp, #0x1e8]
005396e8  str x4,[x25]
005396ec  str x0,[sp, #0x2a8]
005396f0  str x4,[x0]
005396f4  adrp x0,0x973000
005396f8  add x0,x0,#0x360
005396fc  add x1,sp,#0x5c0
00539700  adrp x2,0x9d7000
00539704  add x2,x2,#0x722
00539708  orr x3,xzr,#0x7
0053970c  bl 0x00021200
00539710  orr x4,xzr,#0x1
00539714  stp x4,x4,[x0, #0x8]
00539718  adrp x27,0x147a000
0053971c  ldr w4,[x27, #0x910]
00539720  cbnz w4,0x0053972c
00539724  ldr x2,[sp, #0x2a8]
00539728  b 0x0053973c
0053972c  ldr x1,[x0]
00539730  bl 0x000959d0
00539734  ldr x2,[sp, #0x2a8]
00539738  stp x2,x1,[x25]
0053973c  str x2,[x0]
00539740  nop
00539744  adrp x0,0x8b0000
00539748  add x0,x0,#0x5c0
0053974c  bl 0x0002dd40
00539750  ldr x1,[sp, #0x100]
00539754  str x1,[x0, #0x8]
00539758  adrp x27,0x147a000
0053975c  ldr w2,[x27, #0x910]
00539760  cbnz w2,0x0053976c
00539764  ldr x4,[sp, #0x290]
00539768  b 0x00539778
0053976c  bl 0x000959c0
00539770  ldr x4,[sp, #0x290]
00539774  str x4,[x25]
00539778  str x0,[sp, #0x2a8]
0053977c  str x4,[x0]
00539780  adrp x0,0x973000
00539784  add x0,x0,#0x360
00539788  add x1,sp,#0x5c0
0053978c  adrp x2,0x9d2000
00539790  add x2,x2,#0x233
00539794  orr x3,xzr,#0x3
00539798  bl 0x00021200
0053979c  orr x4,xzr,#0x1
005397a0  stp x4,x4,[x0, #0x8]
005397a4  adrp x27,0x147a000
005397a8  ldr w4,[x27, #0x910]
005397ac  cbnz w4,0x005397b8
005397b0  ldr x2,[sp, #0x2a8]
005397b4  b 0x005397c8
005397b8  ldr x1,[x0]
005397bc  bl 0x000959d0
005397c0  ldr x2,[sp, #0x2a8]
005397c4  stp x2,x1,[x25]
005397c8  str x2,[x0]
005397cc  ldr x1,[sp, #0x100]
005397d0  cmp x1,#0x3
005397d4  b.ne 0x00539910
005397d8  ldr x2,[sp, #0x290]
005397dc  ldrh w3,[x2]
005397e0  mov x4,#0x6577
005397e4  cmp w3,w4
005397e8  b.ne 0x00539914
005397ec  ldrb w3,[x2, #0x2]
005397f0  cmp w3,#0x62
005397f4  b.ne 0x00539914
005397f8  nop
005397fc  adrp x0,0x8b0000
00539800  add x0,x0,#0x5c0
00539804  bl 0x0002dd40
00539808  ldr x1,[sp, #0xa8]
0053980c  str x1,[x0, #0x8]
00539810  adrp x27,0x147a000
00539814  ldr w1,[x27, #0x910]
00539818  cbnz w1,0x00539824
0053981c  ldr x4,[sp, #0x210]
00539820  b 0x00539830
00539824  bl 0x000959c0
00539828  ldr x4,[sp, #0x210]
0053982c  str x4,[x25]
00539830  str x0,[sp, #0x2a8]
00539834  str x4,[x0]
00539838  adrp x0,0x973000
0053983c  add x0,x0,#0x360
00539840  add x1,sp,#0x5c0
00539844  adrp x2,0x9d2000
00539848  add x2,x2,#0xc50
0053984c  orr x3,xzr,#0x4
00539850  bl 0x00021200
00539854  orr x4,xzr,#0x1
00539858  stp x4,x4,[x0, #0x8]
0053985c  adrp x27,0x147a000
00539860  ldr w4,[x27, #0x910]
00539864  cbnz w4,0x00539870
00539868  ldr x2,[sp, #0x2a8]
0053986c  b 0x00539880
00539870  ldr x1,[x0]
00539874  bl 0x000959d0
00539878  ldr x2,[sp, #0x2a8]
0053987c  stp x2,x1,[x25]
00539880  str x2,[x0]
00539884  adrp x0,0x8b0000
00539888  add x0,x0,#0x5c0
0053988c  bl 0x0002dd40
00539890  ldr x1,[sp, #0x88]
00539894  str x1,[x0, #0x8]
00539898  adrp x27,0x147a000
0053989c  ldr w1,[x27, #0x910]
005398a0  cbnz w1,0x005398ac
005398a4  ldr x4,[sp, #0x1f0]
005398a8  b 0x005398b8
005398ac  bl 0x000959c0
005398b0  ldr x4,[sp, #0x1f0]
005398b4  str x4,[x25]
005398b8  str x0,[sp, #0x2a8]
005398bc  str x4,[x0]
005398c0  adrp x0,0x973000
005398c4  add x0,x0,#0x360
005398c8  add x1,sp,#0x5c0
005398cc  adrp x2,0x9d2000
005398d0  add x2,x2,#0xc28
005398d4  orr x3,xzr,#0x4
005398d8  bl 0x00021200
005398dc  orr x4,xzr,#0x1
005398e0  stp x4,x4,[x0, #0x8]
005398e4  adrp x27,0x147a000
005398e8  ldr w4,[x27, #0x910]
005398ec  cbnz w4,0x005398f8
005398f0  ldr x2,[sp, #0x2a8]
005398f4  b 0x00539908
005398f8  ldr x1,[x0]
005398fc  bl 0x000959d0
00539900  ldr x2,[sp, #0x2a8]
00539904  stp x2,x1,[x25]
00539908  str x2,[x0]
0053990c  b 0x00539914
00539910  ldr x2,[sp, #0x290]
00539914  add x0,sp,#0x5c0
00539918  bl 0x0019f7f0
0053991c  str x1,[sp, #0xb0]
00539920  str x0,[sp, #0x218]
00539924  adrp x0,0x940000
00539928  add x0,x0,#0xbe0
0053992c  bl 0x0002dd40
00539930  ldr x1,[sp, #0xb0]
00539934  str x1,[x0, #0x8]
00539938  adrp x27,0x147a000
0053993c  ldr w1,[x27, #0x910]
00539940  cbnz w1,0x0053994c
00539944  ldr x8,[sp, #0x218]
00539948  b 0x00539958
0053994c  bl 0x000959c0
00539950  ldr x8,[sp, #0x218]
00539954  str x8,[x25]
00539958  str x8,[x0]
0053995c  mov x8,#-0x1
00539960  stp xzr,x8,[x0, #0x10]
00539964  adrp x1,0x1479000
00539968  add x1,x1,#0xc40
0053996c  adrp x2,0x9d2000
00539970  add x2,x2,#0xad8
00539974  orr x3,xzr,#0x4
00539978  ldr x4,[sp, #0x280]
0053997c  ldr x5,[sp, #0xe8]
00539980  adrp x6,0xc11000
00539984  add x6,x6,#0x958
00539988  mov x7,x0
0053998c  adrp x0,0xc18000
00539990  add x0,x0,#0xa8
00539994  bl 0x00269cd0
00539998  cbnz x1,0x00539ba0
0053999c  str x0,[sp, #0x228]
005399a0  ldr x2,[x0, #0x38]
005399a4  str x2,[sp, #0x250]
005399a8  nop
005399ac  adrp x0,0x9e8000
005399b0  add x0,x0,#0xea
005399b4  orr x1,xzr,#0xc
005399b8  bl 0x00209720
005399bc  str x0,[sp, #0x2b0]
005399c0  str x1,[sp, #0x110]
005399c4  adrp x0,0x8b0000
005399c8  add x0,x0,#0x5c0
005399cc  bl 0x0002dd40
005399d0  str x0,[sp, #0x2a8]
005399d4  adrp x2,0xa09000
005399d8  add x2,x2,#0xc3a
005399dc  mov x3,#0x21
005399e0  stp x2,x3,[x0]
005399e4  adrp x0,0x969000
005399e8  add x0,x0,#0x220
005399ec  ldr x1,[sp, #0x250]
005399f0  ldr x2,[sp, #0x2b0]
005399f4  ldr x3,[sp, #0x110]
005399f8  bl 0x00021200
005399fc  orr x2,xzr,#0x1
00539a00  stp x2,x2,[x0, #0x8]
00539a04  adrp x27,0x147a000
00539a08  ldr w2,[x27, #0x910]
00539a0c  cbnz w2,0x00539a18
00539a10  ldr x2,[sp, #0x2a8]
00539a14  b 0x00539a28
00539a18  ldr x1,[x0]
00539a1c  bl 0x000959d0
00539a20  ldr x2,[sp, #0x2a8]
00539a24  stp x2,x1,[x25]
00539a28  str x2,[x0]
00539a2c  add x0,sp,#0x448
00539a30  stp xzr,xzr,[x0]
00539a34  stp xzr,xzr,[x0, #0x10]
00539a38  stp xzr,xzr,[x0, #0x20]
00539a3c  add x0,sp,#0x340
00539a40  orr x1,xzr,#0x4
00539a44  stp xzr,xzr,[x0], #0x10
00539a48  stp xzr,xzr,[x0], #0x10
00539a4c  stp xzr,xzr,[x0], #0x10
00539a50  stp xzr,xzr,[x0], #0x10
00539a54  sub x1,x1,#0x1
00539a58  cbnz x1,0x00539a44
00539a5c  str xzr,[x0]
00539a60  orr x0,xzr,#-0x7f7f7f7f7f7f7f80
00539a64  str x0,[sp, #0x340]
00539a68  add x0,sp,#0x340
00539a6c  str x0,[sp, #0x458]
00539a70  bl 0x0008ef50
00539a74  str x0,[sp, #0x450]
00539a78  adrp x0,0x8ec000
00539a7c  add x0,x0,#0xae0
00539a80  add x1,sp,#0x448
00539a84  adrp x2,0x9d5000
00539a88  add x2,x2,#0xbdd
00539a8c  orr x3,xzr,#0x6
00539a90  bl 0x00021200
00539a94  mov x1,#0x12
00539a98  str x1,[x0, #0x8]
00539a9c  adrp x27,0x147a000
00539aa0  ldr w1,[x27, #0x910]
00539aa4  cbz w1,0x00539ab4
00539aa8  ldr x4,[x0]
00539aac  bl 0x000959c0
00539ab0  str x4,[x25]
00539ab4  adrp x4,0x9f4000
00539ab8  add x4,x4,#0xeb0
00539abc  str x4,[x0]
00539ac0  adrp x0,0x8ec000
00539ac4  add x0,x0,#0xae0
00539ac8  add x1,sp,#0x448
00539acc  adrp x2,0x9d7000
00539ad0  add x2,x2,#0x3cc
00539ad4  orr x3,xzr,#0x7
00539ad8  bl 0x00021200
00539adc  mov x4,#0x13
00539ae0  str x4,[x0, #0x8]
00539ae4  adrp x27,0x147a000
00539ae8  ldr w4,[x27, #0x910]
00539aec  cbz w4,0x00539afc
00539af0  ldr x4,[x0]
00539af4  bl 0x000959c0
00539af8  str x4,[x25]
00539afc  adrp x4,0x9f6000
00539b00  add x4,x4,#0x896
00539b04  str x4,[x0]
00539b08  ldr x0,[sp, #0x290]
00539b0c  ldr x1,[sp, #0x100]
00539b10  ldr x2,[sp, #0x1d8]
00539b14  ldr x3,[sp, #0x68]
00539b18  bl 0x00538200
00539b1c  str x1,[sp, #0x110]
00539b20  str x0,[sp, #0x2b0]
00539b24  adrp x0,0x8ec000
00539b28  add x0,x0,#0xae0
00539b2c  add x1,sp,#0x448
00539b30  adrp x2,0x9e1000
00539b34  add x2,x2,#0x73b
00539b38  mov x3,#0xa
00539b3c  bl 0x00021200
00539b40  ldr x4,[sp, #0x110]
00539b44  str x4,[x0, #0x8]
00539b48  adrp x27,0x147a000
00539b4c  ldr w4,[x27, #0x910]
00539b50  cbnz w4,0x00539b5c
00539b54  ldr x4,[sp, #0x2b0]
00539b58  b 0x00539b6c
00539b5c  ldr x3,[x0]
00539b60  bl 0x000959d0
00539b64  ldr x4,[sp, #0x2b0]
00539b68  stp x4,x3,[x25]
00539b6c  str x4,[x0]
00539b70  add x2,sp,#0x638
00539b74  stp xzr,xzr,[x2]
00539b78  stp xzr,xzr,[x2, #0x10]
00539b7c  stp xzr,xzr,[x2, #0x20]
00539b80  stp xzr,xzr,[x2, #0x30]
00539b84  stp xzr,xzr,[x2, #0x40]
00539b88  stp xzr,xzr,[x2, #0x50]
00539b8c  adrp x0,0x8ec000
00539b90  add x0,x0,#0xae0
00539b94  add x1,sp,#0x448
00539b98  bl 0x0002e450
00539b9c  b 0x00539c0c
00539ba0  str xzr,[sp, #0x1d0]
00539ba4  stp x1,x2,[sp, #0x1a8]
00539ba8  bl 0x000568e0
00539bac  ldp x1,x2,[sp, #0x1a8]
00539bb0  ldr x0,[sp, #0x1d0]
00539bb4  ldp x29,x30,[sp, #-0x8]
00539bb8  add sp,sp,#0x730
00539bbc  ret
00539bc0  str xzr,[sp, #0x1d0]
00539bc4  stp x0,x1,[sp, #0x1a8]
00539bc8  bl 0x000568e0
00539bcc  ldp x1,x2,[sp, #0x1a8]
00539bd0  ldr x0,[sp, #0x1d0]
00539bd4  ldp x29,x30,[sp, #-0x8]
00539bd8  add sp,sp,#0x730
00539bdc  ret
00539be0  str x0,[sp, #0x1d0]
00539be4  stp xzr,xzr,[sp, #0x1a8]
00539be8  bl 0x000568e0
00539bec  ldp x1,x2,[sp, #0x1a8]
00539bf0  ldr x0,[sp, #0x1d0]
00539bf4  ldp x29,x30,[sp, #-0x8]
00539bf8  add sp,sp,#0x730
00539bfc  ret
00539c00  str x2,[x0]
00539c04  add x0,sp,#0x638
00539c08  bl 0x0002e4c0
00539c0c  ldr x2,[sp, #0x638]
00539c10  cbz x2,0x00539cc8
00539c14  ldp x0,x1,[x2]
00539c18  ldr x2,[sp, #0x640]
00539c1c  ldp x2,x3,[x2]
00539c20  str x3,[sp, #0x78]
00539c24  str x2,[sp, #0x1e0]
00539c28  ldr x2,[sp, #0x228]
00539c2c  ldr x2,[x2, #0x38]
00539c30  str x2,[sp, #0x2a0]
00539c34  nop
00539c38  bl 0x00209720
00539c3c  str x0,[sp, #0x2b0]
00539c40  str x1,[sp, #0x110]
00539c44  adrp x0,0x8b0000
00539c48  add x0,x0,#0x5c0
00539c4c  bl 0x0002dd40
00539c50  ldr x2,[sp, #0x78]
00539c54  str x2,[x0, #0x8]
00539c58  adrp x27,0x147a000
00539c5c  ldr w2,[x27, #0x910]
00539c60  cbnz w2,0x00539c6c
00539c64  ldr x4,[sp, #0x1e0]
00539c68  b 0x00539c78
00539c6c  bl 0x000959c0
00539c70  ldr x4,[sp, #0x1e0]
00539c74  str x4,[x25]
00539c78  str x0,[sp, #0x2a8]
00539c7c  str x4,[x0]
00539c80  adrp x0,0x969000
00539c84  add x0,x0,#0x220
00539c88  ldr x1,[sp, #0x2a0]
00539c8c  ldr x2,[sp, #0x2b0]
00539c90  ldr x3,[sp, #0x110]
00539c94  bl 0x00021200
00539c98  orr x4,xzr,#0x1
00539c9c  stp x4,x4,[x0, #0x8]
00539ca0  adrp x27,0x147a000
00539ca4  ldr w4,[x27, #0x910]
00539ca8  cbnz w4,0x00539cb4
00539cac  ldr x2,[sp, #0x2a8]
00539cb0  b 0x00539c00
00539cb4  ldr x1,[x0]
00539cb8  bl 0x000959d0
00539cbc  ldr x2,[sp, #0x2a8]
00539cc0  stp x2,x1,[x25]
00539cc4  b 0x00539c00
00539cc8  adrp x27,0x142b000
00539ccc  ldr x0,[x27, #0x120]
00539cd0  ldr x1,[sp, #0x228]
00539cd4  bl 0x00232f70
00539cd8  cbnz x1,0x00539d34
00539cdc  str x0,[sp, #0x1c0]
00539ce0  ldp x1,x2,[x0, #0x40]
00539ce4  ldrsb x27,[x1]
00539ce8  adrp x3,0x53a000
00539cec  add x3,x3,#0x840
00539cf0  str x3,[sp, #0x328]
00539cf4  str x1,[sp, #0x330]
00539cf8  str x2,[sp, #0x338]
00539cfc  add x1,sp,#0x328
00539d00  str x1,[sp, #0x130]
00539d04  add x0,sp,#0x118
00539d08  bl 0x000563c0
00539d0c  ldr x2,[sp, #0x1c0]
00539d10  ldp x3,x1,[x2, #0x40]
00539d14  cbz x3,0x00539d54
00539d18  ldr x4,[x3, #0x8]
00539d1c  adrp x0,0x1434000
00539d20  add x0,x0,#0xa80
00539d24  ldar x5,[x0]
00539d28  ldr w3,[x3, #0x10]
00539d2c  ldr x6,[x5]
00539d30  b 0x0053a678
00539d34  str xzr,[sp, #0x1d0]
00539d38  stp x1,x2,[sp, #0x1a8]
00539d3c  bl 0x000568e0
00539d40  ldp x1,x2,[sp, #0x1a8]
00539d44  ldr x0,[sp, #0x1d0]
00539d48  ldp x29,x30,[sp, #-0x8]
00539d4c  add sp,sp,#0x730
00539d50  ret
00539d54  mov x0,x3
00539d58  bl 0x000a27d0
00539d5c  cbnz x3,0x00539ec0
00539d60  str x2,[sp, #0xf8]
00539d64  str x1,[sp, #0xf0]
00539d68  str x0,[sp, #0x288]
00539d6c  adrp x0,0x952000
00539d70  add x0,x0,#0x180
00539d74  bl 0x0002dd40
00539d78  str x0,[sp, #0x720]
00539d7c  ldr x1,[sp, #0xf0]
00539d80  ldr x2,[sp, #0xf8]
00539d84  adrp x3,0x899000
00539d88  add x3,x3,#0xf20
00539d8c  mov x4,x0
00539d90  ldr x0,[sp, #0x288]
00539d94  bl 0x00123de0
00539d98  cbz x0,0x00539e24
00539d9c  add x3,sp,#0x308
00539da0  stp xzr,xzr,[x3]
00539da4  stp xzr,xzr,[x3, #0x10]
00539da8  cbz x0,0x00539db0
00539dac  ldr x0,[x0, #0x8]
00539db0  add x27,sp,#0x308
00539db4  stp x0,x1,[x27]
00539db8  mov x0,xzr
00539dbc  ldr x1,[sp, #0x288]
00539dc0  ldr x2,[sp, #0xf0]
00539dc4  bl 0x00076cd0
00539dc8  bl 0x0008bd90
00539dcc  adrp x3,0x8a6000
00539dd0  add x3,x3,#0x880
00539dd4  add x27,sp,#0x318
00539dd8  stp x3,x0,[x27]
00539ddc  adrp x3,0x53a000
00539de0  add x3,x3,#0x7e0
00539de4  str x3,[sp, #0x608]
00539de8  adrp x3,0xa29000
00539dec  add x3,x3,#0x44c
00539df0  mov x4,#0x42
00539df4  add x27,sp,#0x610
00539df8  stp x3,x4,[x27]
00539dfc  orr x2,xzr,#0x2
00539e00  str x2,[sp, #0x630]
00539e04  add x3,sp,#0x308
00539e08  add x27,sp,#0x620
00539e0c  stp x3,x2,[x27]
00539e10  adrp x27,0x144e000
00539e14  ldr x0,[x27, #0x5a8]
00539e18  mov x1,xzr
00539e1c  add x3,sp,#0x608
00539e20  bl 0x0013e8e0
00539e24  ldr x2,[sp, #0x720]
00539e28  ldr x3,[x2, #0x20]
00539e2c  cbz x3,0x00539e9c
00539e30  add x27,sp,#0x2f8
00539e34  stp xzr,xzr,[x27]
00539e38  ldp x0,x1,[x2, #0x18]
00539e3c  bl 0x0008bd90
00539e40  adrp x2,0x8a6000
00539e44  add x2,x2,#0x880
00539e48  add x27,sp,#0x2f8
00539e4c  stp x2,x0,[x27]
00539e50  adrp x2,0x53a000
00539e54  add x2,x2,#0x780
00539e58  str x2,[sp, #0x608]
00539e5c  adrp x2,0xa1f000
00539e60  add x2,x2,#0x6a5
00539e64  mov x3,#0x34
00539e68  add x27,sp,#0x610
00539e6c  stp x2,x3,[x27]
00539e70  orr x2,xzr,#0x1
00539e74  str x2,[sp, #0x630]
00539e78  add x3,sp,#0x2f8
00539e7c  add x27,sp,#0x620
00539e80  stp x3,x2,[x27]
00539e84  adrp x27,0x144e000
00539e88  ldr x0,[x27, #0x5a8]
00539e8c  mov x1,xzr
00539e90  orr x2,xzr,#0x2
00539e94  add x3,sp,#0x608
00539e98  bl 0x0013e8e0
00539e9c  bl 0x0008c430
00539ea0  str x0,[sp, #0x278]
00539ea4  ldr x0,[sp, #0x1c0]
00539ea8  ldr x0,[x0, #0x38]
00539eac  bl 0x00235810
00539eb0  str x0,[sp, #0x1b8]
00539eb4  str x1,[sp, #0x60]
00539eb8  mov x2,xzr
00539ebc  b 0x00539ee4
00539ec0  str xzr,[sp, #0x1d0]
00539ec4  stp x3,x4,[sp, #0x1a8]
00539ec8  bl 0x000568e0
00539ecc  ldp x1,x2,[sp, #0x1a8]
00539ed0  ldr x0,[sp, #0x1d0]
00539ed4  ldp x29,x30,[sp, #-0x8]
00539ed8  add sp,sp,#0x730
00539edc  ret
00539ee0  add x2,x2,#0x1
00539ee4  cmp x1,x2
00539ee8  b.le 0x00539f60
00539eec  ldr x4,[x0, x2, LSL #0x3]
00539ef0  ldp x5,x3,[x4]
00539ef4  cbz x3,0x00539ee0
00539ef8  ldp x4,x6,[x4, #0x10]
00539efc  cbz x6,0x00539ee0
00539f00  str x6,[sp, #0x110]
00539f04  str x4,[sp, #0x2b0]
00539f08  str x2,[sp, #0x108]
00539f0c  adrp x0,0x8ec000
00539f10  add x0,x0,#0xae0
00539f14  ldr x1,[sp, #0x278]
00539f18  mov x2,x5
00539f1c  bl 0x00021200
00539f20  ldr x4,[sp, #0x110]
00539f24  str x4,[x0, #0x8]
00539f28  adrp x27,0x147a000
00539f2c  ldr w4,[x27, #0x910]
00539f30  cbnz w4,0x00539f3c
00539f34  ldr x5,[sp, #0x2b0]
00539f38  b 0x00539f4c
00539f3c  ldr x4,[x0]
00539f40  bl 0x000959d0
00539f44  ldr x5,[sp, #0x2b0]
00539f48  stp x5,x4,[x25]
00539f4c  str x5,[x0]
00539f50  ldr x0,[sp, #0x1b8]
00539f54  ldr x1,[sp, #0x60]
00539f58  ldr x2,[sp, #0x108]
00539f5c  b 0x00539ee0
00539f60  ldr x4,[sp, #0x720]
00539f64  ldr x1,[x4, #0x28]
00539f68  cbz x1,0x0053a2d8
00539f6c  adrp x0,0x8ec000
00539f70  add x0,x0,#0xbe0
00539f74  adrp x2,0x9d5000
00539f78  add x2,x2,#0x991
00539f7c  orr x3,xzr,#0x6
00539f80  bl 0x00020d00
00539f84  ldp x4,x5,[x0]
00539f88  adrp x0,0x8ec000
00539f8c  add x0,x0,#0xbe0
00539f90  cmp x4,x0
00539f94  b.eq 0x00539f9c
00539f98  mov x5,xzr
00539f9c  b.ne 0x0053a128
00539fa0  add x2,sp,#0x638
00539fa4  stp xzr,xzr,[x2]
00539fa8  stp xzr,xzr,[x2, #0x10]
00539fac  stp xzr,xzr,[x2, #0x20]
00539fb0  stp xzr,xzr,[x2, #0x30]
00539fb4  stp xzr,xzr,[x2, #0x40]
00539fb8  stp xzr,xzr,[x2, #0x50]
00539fbc  mov x1,x5
00539fc0  bl 0x0002e450
00539fc4  b 0x00539fd0
00539fc8  add x0,sp,#0x638
00539fcc  bl 0x0002e4c0
00539fd0  ldr x4,[sp, #0x638]
00539fd4  cbz x4,0x0053a120
00539fd8  ldp x2,x3,[x4]
00539fdc  ldr x4,[sp, #0x640]
00539fe0  ldp x4,x5,[x4]
00539fe4  adrp x6,0x8a6000
00539fe8  add x6,x6,#0x880
00539fec  cmp x4,x6
00539ff0  b.ne 0x00539ffc
00539ff4  ldp x7,x8,[x5]
00539ff8  b 0x0053a004
00539ffc  mov x8,xzr
0053a000  mov x7,xzr
0053a004  b.ne 0x0053a058
0053a008  cbz x8,0x0053a058
0053a00c  str x8,[sp, #0x98]
0053a010  str x7,[sp, #0x200]
0053a014  adrp x0,0x8ec000
0053a018  add x0,x0,#0xae0
0053a01c  ldr x1,[sp, #0x278]
0053a020  bl 0x00021200
0053a024  ldr x4,[sp, #0x98]
0053a028  str x4,[x0, #0x8]
0053a02c  adrp x27,0x147a000
0053a030  ldr w4,[x27, #0x910]
0053a034  cbnz w4,0x0053a040
0053a038  ldr x2,[sp, #0x200]
0053a03c  b 0x0053a050
0053a040  ldr x1,[x0]
0053a044  bl 0x000959d0
0053a048  ldr x2,[sp, #0x200]
0053a04c  stp x2,x1,[x25]
0053a050  str x2,[x0]
0053a054  b 0x00539fc8
0053a058  adrp x1,0x8a6000
0053a05c  add x1,x1,#0xc40
0053a060  cmp x4,x1
0053a064  b.ne 0x0053a070
0053a068  ldr d0,[x5]
0053a06c  b 0x0053a074
0053a070  fmov d0,xzr
0053a074  b.ne 0x00539fc8
0053a078  str x3,[sp, #0xc0]
0053a07c  str x2,[sp, #0x248]
0053a080  add x27,sp,#0x698
0053a084  stp xzr,xzr,[x27]
0053a088  fmov x0,d0
0053a08c  bl 0x0008bd10
0053a090  adrp x1,0x8a6000
0053a094  add x1,x1,#0xc40
0053a098  add x27,sp,#0x698
0053a09c  stp x1,x0,[x27]
0053a0a0  adrp x0,0x9d2000
0053a0a4  add x0,x0,#0xc0c
0053a0a8  orr x1,xzr,#0x4
0053a0ac  add x2,sp,#0x698
0053a0b0  orr x3,xzr,#0x1
0053a0b4  mov x4,x3
0053a0b8  bl 0x001042e0
0053a0bc  str x1,[sp, #0x110]
0053a0c0  str x0,[sp, #0x2b0]
0053a0c4  adrp x0,0x8ec000
0053a0c8  add x0,x0,#0xae0
0053a0cc  ldr x1,[sp, #0x278]
0053a0d0  ldr x2,[sp, #0x248]
0053a0d4  ldr x3,[sp, #0xc0]
0053a0d8  bl 0x00021200
0053a0dc  ldr x1,[sp, #0x110]
0053a0e0  str x1,[x0, #0x8]
0053a0e4  adrp x27,0x147a000
0053a0e8  ldr w1,[x27, #0x910]
0053a0ec  cbnz w1,0x0053a0f8
0053a0f0  ldr x2,[sp, #0x2b0]
0053a0f4  b 0x0053a108
0053a0f8  ldr x1,[x0]
0053a0fc  bl 0x000959d0
0053a100  ldr x2,[sp, #0x2b0]
0053a104  stp x2,x1,[x25]
0053a108  str x2,[x0]
0053a10c  adrp x1,0x8a6000
0053a110  add x1,x1,#0xc40
0053a114  adrp x6,0x8a6000
0053a118  add x6,x6,#0x880
0053a11c  b 0x00539fc8
0053a120  adrp x0,0x8ec000
0053a124  add x0,x0,#0xbe0
0053a128  ldr x3,[sp, #0x720]
0053a12c  ldr x1,[x3, #0x28]
0053a130  add x2,sp,#0x638
0053a134  stp xzr,xzr,[x2]
0053a138  stp xzr,xzr,[x2, #0x10]
0053a13c  stp xzr,xzr,[x2, #0x20]
0053a140  stp xzr,xzr,[x2, #0x30]
0053a144  stp xzr,xzr,[x2, #0x40]
0053a148  stp xzr,xzr,[x2, #0x50]
0053a14c  bl 0x0002e450
0053a150  b 0x0053a15c
0053a154  add x0,sp,#0x638
0053a158  bl 0x0002e4c0
0053a15c  ldr x4,[sp, #0x638]
0053a160  cbz x4,0x0053a2d8
0053a164  ldp x2,x3,[x4]
0053a168  ldr x4,[sp, #0x640]
0053a16c  ldp x4,x5,[x4]
0053a170  cmp x3,#0x6
0053a174  b.ne 0x0053a19c
0053a178  ldr w6,[x2]
0053a17c  mov x7,#0x6f63
0053a180  movk x7,#0x6b6f, LSL #16
0053a184  cmp w6,w7
0053a188  b.ne 0x0053a19c
0053a18c  ldrh w6,[x2, #0x4]
0053a190  mov x7,#0x6569
0053a194  cmp w6,w7
0053a198  b.eq 0x0053a154
0053a19c  adrp x6,0x8a6000
0053a1a0  add x6,x6,#0x880
0053a1a4  cmp x4,x6
0053a1a8  b.ne 0x0053a1b4
0053a1ac  ldp x7,x8,[x5]
0053a1b0  b 0x0053a1bc
0053a1b4  mov x8,xzr
0053a1b8  mov x7,xzr
0053a1bc  b.ne 0x0053a210
0053a1c0  cbz x8,0x0053a210
0053a1c4  str x7,[sp, #0x1f8]
0053a1c8  str x8,[sp, #0x90]
0053a1cc  adrp x0,0x8ec000
0053a1d0  add x0,x0,#0xae0
0053a1d4  ldr x1,[sp, #0x278]
0053a1d8  bl 0x00021200
0053a1dc  ldr x4,[sp, #0x90]
0053a1e0  str x4,[x0, #0x8]
0053a1e4  adrp x27,0x147a000
0053a1e8  ldr w4,[x27, #0x910]
0053a1ec  cbnz w4,0x0053a1f8
0053a1f0  ldr x2,[sp, #0x1f8]
0053a1f4  b 0x0053a208
0053a1f8  ldr x1,[x0]
0053a1fc  bl 0x000959d0
0053a200  ldr x2,[sp, #0x1f8]
0053a204  stp x2,x1,[x25]
0053a208  str x2,[x0]
0053a20c  b 0x0053a154
0053a210  adrp x1,0x8a6000
0053a214  add x1,x1,#0xc40
0053a218  cmp x4,x1
0053a21c  b.ne 0x0053a228
0053a220  ldr d0,[x5]
0053a224  b 0x0053a22c
0053a228  fmov d0,xzr
0053a22c  b.ne 0x0053a154
0053a230  str x3,[sp, #0xb8]
0053a234  str x2,[sp, #0x240]
0053a238  add x27,sp,#0x698
0053a23c  stp xzr,xzr,[x27]
0053a240  fmov x0,d0
0053a244  bl 0x0008bd10
0053a248  adrp x1,0x8a6000
0053a24c  add x1,x1,#0xc40
0053a250  add x27,sp,#0x698
0053a254  stp x1,x0,[x27]
0053a258  adrp x0,0x9d2000
0053a25c  add x0,x0,#0xc0c
0053a260  orr x1,xzr,#0x4
0053a264  add x2,sp,#0x698
0053a268  orr x3,xzr,#0x1
0053a26c  mov x4,x3
0053a270  bl 0x001042e0
0053a274  str x1,[sp, #0x110]
0053a278  str x0,[sp, #0x2b0]
0053a27c  adrp x0,0x8ec000
0053a280  add x0,x0,#0xae0
0053a284  ldr x1,[sp, #0x278]
0053a288  ldr x2,[sp, #0x240]
0053a28c  ldr x3,[sp, #0xb8]
0053a290  bl 0x00021200
0053a294  ldr x1,[sp, #0x110]
0053a298  str x1,[x0, #0x8]
0053a29c  adrp x27,0x147a000
0053a2a0  ldr w1,[x27, #0x910]
0053a2a4  cbnz w1,0x0053a2b0
0053a2a8  ldr x2,[sp, #0x2b0]
0053a2ac  b 0x0053a2c0
0053a2b0  ldr x1,[x0]
0053a2b4  bl 0x000959d0
0053a2b8  ldr x2,[sp, #0x2b0]
0053a2bc  stp x2,x1,[x25]
0053a2c0  str x2,[x0]
0053a2c4  adrp x1,0x8a6000
0053a2c8  add x1,x1,#0xc40
0053a2cc  adrp x6,0x8a6000
0053a2d0  add x6,x6,#0x880
0053a2d4  b 0x0053a154
0053a2d8  add x2,sp,#0x638
0053a2dc  stp xzr,xzr,[x2]
0053a2e0  stp xzr,xzr,[x2, #0x10]
0053a2e4  stp xzr,xzr,[x2, #0x20]
0053a2e8  stp xzr,xzr,[x2, #0x30]
0053a2ec  stp xzr,xzr,[x2, #0x40]
0053a2f0  stp xzr,xzr,[x2, #0x50]
0053a2f4  adrp x0,0x8ec000
0053a2f8  add x0,x0,#0xae0
0053a2fc  ldr x1,[sp, #0x278]
0053a300  bl 0x0002e450
0053a304  b 0x0053a310
0053a308  add x0,sp,#0x638
0053a30c  bl 0x0002e4c0
0053a310  ldr x3,[sp, #0x638]
0053a314  cbz x3,0x0053a3e4
0053a318  str x3,[sp, #0x298]
0053a31c  ldp x0,x1,[x3]
0053a320  ldr x2,[sp, #0x640]
0053a324  ldr x2,[x2, #0x8]
0053a328  str x2,[sp, #0x70]
0053a32c  bl 0x000b79b0
0053a330  cmp x1,#0x3
0053a334  b.ne 0x0053a37c
0053a338  ldrh w3,[x0]
0053a33c  mov x4,#0x4955
0053a340  cmp w3,w4
0053a344  b.ne 0x0053a35c
0053a348  ldrb w4,[x0, #0x2]
0053a34c  cmp w4,#0x44
0053a350  b.eq 0x0053a3d8
0053a354  cmp x1,#0x3
0053a358  b 0x0053a360
0053a35c  cmp x1,#0x3
0053a360  b.ne 0x0053a37c
0053a364  mov x4,#0x4943
0053a368  cmp w3,w4
0053a36c  b.ne 0x0053a37c
0053a370  ldrb w3,[x0, #0x2]
0053a374  cmp w3,#0x44
0053a378  b.eq 0x0053a3d8
0053a37c  cmp x1,#0x4
0053a380  b.ne 0x0053a398
0053a384  ldr w3,[x0]
0053a388  mov x4,#0x4553
0053a38c  movk x4,#0x4449, LSL #16
0053a390  cmp w3,w4
0053a394  b.eq 0x0053a3d8
0053a398  cmp x1,#0xb
0053a39c  b.ne 0x0053a308
0053a3a0  ldr x3,[x0]
0053a3a4  mov x4,#0x3131
0053a3a8  movk x4,#0x5f35, LSL #16
0053a3ac  movk x4,#0x5355, LSL #32
0053a3b0  movk x4,#0x5245, LSL #48
0053a3b4  cmp x3,x4
0053a3b8  b.ne 0x0053a308
0053a3bc  ldrh w3,[x0, #0x8]
0053a3c0  mov x4,#0x495f
0053a3c4  cmp w3,w4
0053a3c8  b.ne 0x0053a308
0053a3cc  ldrb w3,[x0, #0xa]
0053a3d0  cmp w3,#0x44
0053a3d4  b.ne 0x0053a308
0053a3d8  ldr x0,[sp, #0x70]
0053a3dc  cbz x0,0x0053a308
0053a3e0  ldr x3,[sp, #0x298]
0053a3e4  cbz x3,0x0053a428
0053a3e8  add x2,sp,#0x638
0053a3ec  stp xzr,xzr,[x2]
0053a3f0  stp xzr,xzr,[x2, #0x10]
0053a3f4  stp xzr,xzr,[x2, #0x20]
0053a3f8  stp xzr,xzr,[x2, #0x30]
0053a3fc  stp xzr,xzr,[x2, #0x40]
0053a400  stp xzr,xzr,[x2, #0x50]
0053a404  adrp x0,0x8ec000
0053a408  add x0,x0,#0xae0
0053a40c  ldr x1,[sp, #0x278]
0053a410  bl 0x0002e450
0053a414  mov x0,xzr
0053a418  mov x1,xzr
0053a41c  mov x2,xzr
0053a420  mov x3,xzr
0053a424  b 0x0053a53c
0053a428  add x3,sp,#0x2d8
0053a42c  stp xzr,xzr,[x3]
0053a430  stp xzr,xzr,[x3, #0x10]
0053a434  adrp x3,0x8ec000
0053a438  add x3,x3,#0xae0
0053a43c  ldr x4,[sp, #0x278]
0053a440  add x27,sp,#0x2d8
0053a444  stp x3,x4,[x27]
0053a448  mov x0,xzr
0053a44c  ldr x1,[sp, #0x288]
0053a450  ldr x2,[sp, #0xf0]
0053a454  bl 0x00076cd0
0053a458  bl 0x0008bd90
0053a45c  adrp x3,0x8a6000
0053a460  add x3,x3,#0x880
0053a464  add x27,sp,#0x2e8
0053a468  stp x3,x0,[x27]
0053a46c  adrp x3,0x53a000
0053a470  add x3,x3,#0x720
0053a474  str x3,[sp, #0x608]
0053a478  adrp x3,0xa37000
0053a47c  add x3,x3,#0x791
0053a480  mov x4,#0x66
0053a484  add x27,sp,#0x610
0053a488  stp x3,x4,[x27]
0053a48c  orr x2,xzr,#0x2
0053a490  str x2,[sp, #0x630]
0053a494  add x3,sp,#0x2d8
0053a498  add x27,sp,#0x620
0053a49c  stp x3,x2,[x27]
0053a4a0  adrp x27,0x144e000
0053a4a4  ldr x0,[x27, #0x5a8]
0053a4a8  mov x1,xzr
0053a4ac  add x3,sp,#0x608
0053a4b0  bl 0x0013e8e0
0053a4b4  adrp x0,0xa2e000
0053a4b8  add x0,x0,#0xfe8
0053a4bc  mov x1,#0x4d
0053a4c0  mov x2,xzr
0053a4c4  mov x3,xzr
0053a4c8  mov x4,xzr
0053a4cc  bl 0x00101840
0053a4d0  cbnz x0,0x0053a500
0053a4d4  nop
0053a4d8  adrp x0,0x8f8000
0053a4dc  add x0,x0,#0x5a0
0053a4e0  bl 0x0002dd40
0053a4e4  adrp x1,0xa2e000
0053a4e8  add x1,x1,#0xfe8
0053a4ec  mov x2,#0x4d
0053a4f0  stp x1,x2,[x0]
0053a4f4  mov x1,x0
0053a4f8  adrp x0,0xc11000
0053a4fc  add x0,x0,#0xa38
0053a500  str xzr,[sp, #0x1d0]
0053a504  stp x0,x1,[sp, #0x1a8]
0053a508  bl 0x000568e0
0053a50c  ldp x1,x2,[sp, #0x1a8]
0053a510  ldr x0,[sp, #0x1d0]
0053a514  ldp x29,x30,[sp, #-0x8]
0053a518  add sp,sp,#0x730
0053a51c  ret
0053a520  str x0,[x5]
0053a524  add x0,sp,#0x638
0053a528  bl 0x0002e4c0
0053a52c  ldrb w0,[sp, #0x5f]
0053a530  ldr x1,[sp, #0xe0]
0053a534  ldr x2,[sp, #0xd8]
0053a538  ldr x3,[sp, #0x270]
0053a53c  ldr x7,[sp, #0x638]
0053a540  cbz x7,0x0053a62c
0053a544  str x1,[sp, #0xe0]
0053a548  str x2,[sp, #0xd8]
0053a54c  str x3,[sp, #0x270]
0053a550  strb w0,[sp, #0x5f]
0053a554  ldp x1,x2,[x7]
0053a558  ldr x7,[sp, #0x640]
0053a55c  ldp x5,x6,[x7]
0053a560  mov x0,xzr
0053a564  adrp x3,0xc0a000
0053a568  add x3,x3,#0x5f8
0053a56c  orr x4,xzr,#0x1
0053a570  bl 0x000767f0
0053a574  ldr x7,[sp, #0xd8]
0053a578  add x8,x7,#0x1
0053a57c  ldr x2,[sp, #0xe0]
0053a580  cmp x2,x8
0053a584  b.cc 0x0053a594
0053a588  ldr x3,[sp, #0x270]
0053a58c  ldrb w4,[sp, #0x5f]
0053a590  b 0x0053a5f4
0053a594  str x1,[sp, #0x110]
0053a598  str x0,[sp, #0x2b0]
0053a59c  cmp x8,#0x2
0053a5a0  b.gt 0x0053a5c8
0053a5a4  ldrb w3,[sp, #0x5f]
0053a5a8  tbnz w3,#0x0,0x0053a5c8
0053a5ac  cbnz x7,0x0053a5c8
0053a5b0  add x3,sp,#0x2b8
0053a5b4  stp xzr,xzr,[x3]
0053a5b8  stp xzr,xzr,[x3, #0x10]
0053a5bc  orr x2,xzr,#0x2
0053a5c0  orr x4,xzr,#0x1
0053a5c4  b 0x0053a5f4
0053a5c8  ldr x0,[sp, #0x270]
0053a5cc  mov x1,x8
0053a5d0  orr x3,xzr,#0x1
0053a5d4  adrp x4,0x8a6000
0053a5d8  add x4,x4,#0x880
0053a5dc  bl 0x00090b80
0053a5e0  mov x8,x1
0053a5e4  mov x3,x0
0053a5e8  ldrb w4,[sp, #0x5f]
0053a5ec  ldr x0,[sp, #0x2b0]
0053a5f0  ldr x1,[sp, #0x110]
0053a5f4  str x3,[sp, #0x270]
0053a5f8  str x8,[sp, #0xd8]
0053a5fc  str x2,[sp, #0xe0]
0053a600  strb w4,[sp, #0x5f]
0053a604  sub x5,x8,#0x1
0053a608  add x5,x3,x5, LSL #0x4
0053a60c  str x1,[x5, #0x8]
0053a610  adrp x27,0x147a000
0053a614  ldr w1,[x27, #0x910]
0053a618  cbz w1,0x0053a520
0053a61c  ldr x1,[x5]
0053a620  bl 0x000959d0
0053a624  stp x0,x1,[x25]
0053a628  b 0x0053a520
0053a62c  mov x0,x3
0053a630  adrp x3,0x9d1000
0053a634  add x3,x3,#0xc5a
0053a638  orr x4,xzr,#0x2
0053a63c  mov x5,x1
0053a640  mov x1,x2
0053a644  mov x2,x5
0053a648  bl 0x000b6ce0
0053a64c  ldr x5,[sp, #0x220]
0053a650  str x1,[x5, #0x18]
0053a654  adrp x27,0x147a000
0053a658  ldr w6,[x27, #0x910]
0053a65c  cbz w6,0x0053a66c
0053a660  ldr x1,[x5, #0x10]
0053a664  bl 0x000959d0
0053a668  stp x0,x1,[x25]
0053a66c  str x0,[x5, #0x10]
0053a670  mov x0,x5
0053a674  b 0x00539be0
0053a678  and x7,x3,x6
0053a67c  lsl x7,x7,#0x4
0053a680  add x7,x7,#0x8
0053a684  ldr x8,[x5, x7#0x0]
0053a688  add x7,x5,x7
0053a68c  cmp x8,x4
0053a690  b.eq 0x0053a6b4
0053a694  add x3,x3,#0x1
0053a698  cbnz x8,0x0053a678
0053a69c  str x1,[sp, #0x2b0]
0053a6a0  mov x1,x4
0053a6a4  bl 0x0002a110
0053a6a8  ldr x1,[sp, #0x2b0]
0053a6ac  mov x3,x0
0053a6b0  b 0x00539d54
0053a6b4  ldr x3,[x7, #0x8]
0053a6b8  b 0x00539d54
0053a6bc  and x8,x6,x7
0053a6c0  lsl x8,x8,#0x4
0053a6c4  add x8,x8,#0x8
0053a6c8  ldr x9,[x5, x8#0x0]
0053a6cc  add x8,x5,x8
0053a6d0  cmp x9,x3
0053a6d4  b.eq 0x0053a6f4
0053a6d8  add x6,x6,#0x1
0053a6dc  cbnz x9,0x0053a6bc
0053a6e0  mov x0,x4
0053a6e4  mov x1,x3
0053a6e8  bl 0x0002a110
0053a6ec  mov x1,x0
0053a6f0  b 0x00539504
0053a6f4  ldr x1,[x8, #0x8]
0053a6f8  b 0x00539504
0053a6fc  stp x0,x1,[sp, #0x8]
0053a700  str x2,[sp, #0x18]
0053a704  mov x3,x30
0053a708  bl 0x00093ad0
0053a70c  ldp x0,x1,[sp, #0x8]
0053a710  ldr x2,[sp, #0x18]
0053a714  b 0x00539120
