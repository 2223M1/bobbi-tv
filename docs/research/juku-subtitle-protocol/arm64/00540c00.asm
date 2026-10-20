; mv-daemon/provider.(*Cloud115Provider).resolve115Subtitles
00540c00  ldr x16,[x28, #0x10]
00540c04  sub x17,sp,#0x2b0
00540c08  cmp x17,x16
00540c0c  b.ls 0x005413e0
00540c10  sub x20,sp,#0x330
00540c14  stp x29,x30,[x20, #-0x8]
00540c18  mov sp,x20
00540c1c  sub x29,sp,#0x8
00540c20  str x5,[sp, #0x360]
00540c24  str x4,[sp, #0x358]
00540c28  str x3,[sp, #0x350]
00540c2c  str x13,[sp, #0x3a0]
00540c30  str x12,[sp, #0x398]
00540c34  str x10,[sp, #0x388]
00540c38  str x9,[sp, #0x380]
00540c3c  str x6,[sp, #0x368]
00540c40  str x2,[sp, #0x348]
00540c44  str x1,[sp, #0x340]
00540c48  str x8,[sp, #0x378]
00540c4c  str x7,[sp, #0x370]
00540c50  add x0,sp,#0x2b0
00540c54  stp xzr,xzr,[x0]
00540c58  stp xzr,xzr,[x0, #0x10]
00540c5c  stp xzr,xzr,[x0, #0x20]
00540c60  add x0,sp,#0x1e8
00540c64  orr x1,xzr,#0x3
00540c68  stp xzr,xzr,[x0], #0x10
00540c6c  stp xzr,xzr,[x0], #0x10
00540c70  stp xzr,xzr,[x0], #0x10
00540c74  stp xzr,xzr,[x0], #0x10
00540c78  sub x1,x1,#0x1
00540c7c  cbnz x1,0x00540c68
00540c80  str xzr,[x0]
00540c84  orr x0,xzr,#-0x7f7f7f7f7f7f7f80
00540c88  str x0,[sp, #0x1e8]
00540c8c  add x0,sp,#0x1e8
00540c90  str x0,[sp, #0x2c0]
00540c94  bl 0x0008ef50
00540c98  str x0,[sp, #0x2b8]
00540c9c  ldr x0,[sp, #0x380]
00540ca0  ldr x1,[sp, #0x388]
00540ca4  mov x2,xzr
00540ca8  mov x3,xzr
00540cac  mov x4,xzr
00540cb0  mov x5,xzr
00540cb4  b 0x00540cc0
00540cb8  add x0,x0,#0x20
00540cbc  add x2,x2,#0x1
00540cc0  str x3,[sp, #0x90]
00540cc4  str x4,[sp, #0x88]
00540cc8  str x5,[sp, #0x110]
00540ccc  cmp x1,x2
00540cd0  b.le 0x00540ebc
00540cd4  str x2,[sp, #0x108]
00540cd8  str x0,[sp, #0x320]
00540cdc  ldp x8,x9,[x0, #0x10]
00540ce0  str x9,[sp, #0x100]
00540ce4  str x8,[sp, #0x318]
00540ce8  ldp x10,x11,[x0]
00540cec  str x11,[sp, #0xf8]
00540cf0  str x10,[sp, #0x310]
00540cf4  cbnz x11,0x00540d00
00540cf8  orr x6,xzr,#0x1
00540cfc  b 0x00540d48
00540d00  adrp x0,0x8ec000
00540d04  add x0,x0,#0xb60
00540d08  add x1,sp,#0x2b0
00540d0c  mov x2,x10
00540d10  mov x3,x11
00540d14  bl 0x00020d00
00540d18  ldrb w4,[x0]
00540d1c  ldr x0,[sp, #0x320]
00540d20  ldr x1,[sp, #0x388]
00540d24  ldr x2,[sp, #0x108]
00540d28  ldr x3,[sp, #0x90]
00540d2c  ldr x5,[sp, #0x110]
00540d30  ldr x8,[sp, #0x318]
00540d34  ldr x9,[sp, #0x100]
00540d38  ldr x10,[sp, #0x310]
00540d3c  ldr x11,[sp, #0xf8]
00540d40  mov x6,x4
00540d44  ldr x4,[sp, #0x88]
00540d48  tbnz w6,#0x0,0x00540cb8
00540d4c  adrp x0,0x8ec000
00540d50  add x0,x0,#0xb60
00540d54  add x1,sp,#0x2b0
00540d58  mov x2,x10
00540d5c  mov x3,x11
00540d60  bl 0x00021200
00540d64  orr x4,xzr,#0x1
00540d68  strb w4,[x0]
00540d6c  ldr x0,[sp, #0x340]
00540d70  ldr x1,[sp, #0x348]
00540d74  ldr x2,[sp, #0x350]
00540d78  ldr x3,[sp, #0x358]
00540d7c  ldr x4,[sp, #0x310]
00540d80  ldr x5,[sp, #0xf8]
00540d84  ldr x6,[sp, #0x398]
00540d88  ldr x7,[sp, #0x3a0]
00540d8c  bl 0x0053fca0
00540d90  cbnz x4,0x00540d98
00540d94  cbnz x1,0x00540dc8
00540d98  ldr x0,[sp, #0x340]
00540d9c  ldr x1,[sp, #0x348]
00540da0  ldr x2,[sp, #0x350]
00540da4  ldr x3,[sp, #0x358]
00540da8  ldr x4,[sp, #0x310]
00540dac  ldr x5,[sp, #0xf8]
00540db0  ldr x6,[sp, #0x398]
00540db4  ldr x7,[sp, #0x3a0]
00540db8  mov x8,xzr
00540dbc  mov x9,xzr
00540dc0  mov x10,xzr
00540dc4  bl 0x0053eee0
00540dc8  cbz x1,0x00540e94
00540dcc  ldr x8,[sp, #0x88]
00540dd0  add x8,x8,#0x1
00540dd4  ldr x9,[sp, #0x100]
00540dd8  cmp x9,#0x0
00540ddc  csel x9,x3,x9,eq
00540de0  ldr x10,[sp, #0x318]
00540de4  csel x10,x2,x10,eq
00540de8  str x10,[sp, #0x120]
00540dec  stp x9,x0,[sp, #0x128]
00540df0  mov x7,#0x64
00540df4  stp x1,x7,[sp, #0x138]
00540df8  ldr x2,[sp, #0x90]
00540dfc  cmp x2,x8
00540e00  b.cc 0x00540e10
00540e04  mov x1,x8
00540e08  ldr x0,[sp, #0x110]
00540e0c  b 0x00540e28
00540e10  ldr x0,[sp, #0x110]
00540e14  mov x1,x8
00540e18  orr x3,xzr,#0x1
00540e1c  adrp x4,0x940000
00540e20  add x4,x4,#0xfa0
00540e24  bl 0x00090b80
00540e28  lsl x8,x1,#0x3
00540e2c  add x8,x8,x8, LSL #0x2
00540e30  sub x8,x8,#0x28
00540e34  add x8,x0,x8
00540e38  adrp x27,0x147a000
00540e3c  ldr w9,[x27, #0x910]
00540e40  cbz w9,0x00540e78
00540e44  str x0,[sp, #0x308]
00540e48  str x1,[sp, #0xf0]
00540e4c  str x2,[sp, #0xe8]
00540e50  str x8,[sp, #0x300]
00540e54  adrp x0,0x940000
00540e58  add x0,x0,#0xfa0
00540e5c  mov x1,x8
00540e60  add x2,sp,#0x120
00540e64  bl 0x0002e530
00540e68  ldr x0,[sp, #0x308]
00540e6c  ldr x1,[sp, #0xf0]
00540e70  ldr x2,[sp, #0xe8]
00540e74  ldr x8,[sp, #0x300]
00540e78  ldp x9,x10,[sp, #0x120]
00540e7c  ldp x11,x12,[sp, #0x130]
00540e80  ldr x13,[sp, #0x140]
00540e84  stp x9,x10,[x8]
00540e88  stp x11,x12,[x8, #0x10]
00540e8c  str x13,[x8, #0x20]
00540e90  b 0x00540ea0
00540e94  ldr x2,[sp, #0x90]
00540e98  ldr x1,[sp, #0x88]
00540e9c  ldr x0,[sp, #0x110]
00540ea0  mov x3,x2
00540ea4  mov x4,x1
00540ea8  mov x5,x0
00540eac  ldr x0,[sp, #0x320]
00540eb0  ldr x1,[sp, #0x388]
00540eb4  ldr x2,[sp, #0x108]
00540eb8  b 0x00540cb8
00540ebc  cbnz x4,0x00540f64
00540ec0  ldr x0,[sp, #0x368]
00540ec4  cbz x0,0x00540f64
00540ec8  cmp x0,#0x1
00540ecc  b.eq 0x00540ed8
00540ed0  ldr x8,[sp, #0x360]
00540ed4  b 0x00540ee8
00540ed8  ldr x8,[sp, #0x360]
00540edc  ldrb w9,[x8]
00540ee0  cmp w9,#0x30
00540ee4  b.eq 0x00540f64
00540ee8  ldr x1,[sp, #0x348]
00540eec  ldr x2,[sp, #0x350]
00540ef0  ldr x3,[sp, #0x358]
00540ef4  mov x4,x8
00540ef8  mov x5,x0
00540efc  orr x6,xzr,#0x1
00540f00  mov x7,#0x64
00540f04  ldr x0,[sp, #0x340]
00540f08  bl 0x0053bf80
00540f0c  cbnz x1,0x00540f54
00540f10  cbz x0,0x00540f44
00540f14  ldp x9,x10,[x0]
00540f18  cbz x10,0x00540f34
00540f1c  str x10,[sp, #0x108]
00540f20  mov x0,xzr
00540f24  mov x1,xzr
00540f28  mov x2,xzr
00540f2c  mov x3,xzr
00540f30  b 0x00540f94
00540f34  ldr x0,[sp, #0x90]
00540f38  ldr x1,[sp, #0x88]
00540f3c  ldr x2,[sp, #0x110]
00540f40  b 0x00540f7c
00540f44  ldr x0,[sp, #0x90]
00540f48  ldr x1,[sp, #0x88]
00540f4c  ldr x2,[sp, #0x110]
00540f50  b 0x00540f7c
00540f54  ldr x0,[sp, #0x90]
00540f58  ldr x1,[sp, #0x88]
00540f5c  ldr x2,[sp, #0x110]
00540f60  b 0x00540f7c
00540f64  mov x0,x5
00540f68  mov x1,x4
00540f6c  mov x2,x3
00540f70  ldp x29,x30,[sp, #-0x8]
00540f74  add sp,sp,#0x330
00540f78  ret
00540f7c  mov x3,x0
00540f80  mov x4,x1
00540f84  mov x5,x2
00540f88  b 0x00540f64
00540f8c  add x9,x9,#0x70
00540f90  add x0,x0,#0x1
00540f94  str x1,[sp, #0xb0]
00540f98  str x2,[sp, #0xa8]
00540f9c  str x3,[sp, #0x190]
00540fa0  cmp x0,x10
00540fa4  b.ge 0x00541188
00540fa8  add x11,sp,#0x120
00540fac  ldp q16,q17,[x9]
00540fb0  stp q16,q17,[x11]
00540fb4  ldp q16,q17,[x9, #0x20]
00540fb8  stp q16,q17,[x11, #0x20]
00540fbc  ldp q16,q17,[x9, #0x40]
00540fc0  stp q16,q17,[x11, #0x40]
00540fc4  ldr q16,[x9, #0x60]
00540fc8  str q16,[x11, #0x60]
00540fcc  ldrb w11,[sp, #0x140]
00540fd0  tbnz w11,#0x0,0x00540f8c
00540fd4  str x0,[sp, #0x100]
00540fd8  str x9,[sp, #0x320]
00540fdc  ldp x0,x1,[sp, #0x130]
00540fe0  bl 0x002bb9a0
00540fe4  cbnz x1,0x00541004
00540fe8  ldr x0,[sp, #0x100]
00540fec  ldr x9,[sp, #0x320]
00540ff0  ldr x10,[sp, #0x108]
00540ff4  ldr x1,[sp, #0xb0]
00540ff8  ldr x2,[sp, #0xa8]
00540ffc  ldr x3,[sp, #0x190]
00541000  b 0x00540f8c
00541004  ldp x0,x1,[sp, #0x120]
00541008  bl 0x0055a8f0
0054100c  cbnz x1,0x00541020
00541010  ldr x2,[sp, #0xb0]
00541014  ldr x1,[sp, #0xa8]
00541018  ldr x0,[sp, #0x190]
0054101c  b 0x00541168
00541020  str x1,[sp, #0x98]
00541024  str x0,[sp, #0x118]
00541028  mov x2,x0
0054102c  mov x3,x1
00541030  adrp x0,0x8ec000
00541034  add x0,x0,#0xb60
00541038  add x1,sp,#0x2b0
0054103c  bl 0x00020d00
00541040  ldrb w4,[x0]
00541044  tbz w4,#0x0,0x00541058
00541048  ldr x2,[sp, #0xb0]
0054104c  ldr x1,[sp, #0xa8]
00541050  ldr x0,[sp, #0x190]
00541054  b 0x00541168
00541058  add x9,sp,#0x198
0054105c  stp xzr,xzr,[x9]
00541060  stp xzr,xzr,[x9, #0x10]
00541064  stp xzr,xzr,[x9, #0x20]
00541068  stp xzr,xzr,[x9, #0x30]
0054106c  stp xzr,xzr,[x9, #0x40]
00541070  ldr x9,[sp, #0x118]
00541074  ldr x10,[sp, #0x98]
00541078  stp x9,x10,[sp, #0x198]
0054107c  ldr x9,[sp, #0xa8]
00541080  add x9,x9,#0x1
00541084  str x9,[sp, #0xf8]
00541088  ldp x9,x10,[sp, #0x130]
0054108c  stp x9,x10,[sp, #0x1a8]
00541090  mov x0,xzr
00541094  adrp x1,0x9dd000
00541098  add x1,x1,#0x4e7
0054109c  mov x2,#0x9
005410a0  ldr x3,[sp, #0x340]
005410a4  ldr x4,[sp, #0x348]
005410a8  adrp x5,0xc0a000
005410ac  add x5,x5,#0x628
005410b0  orr x6,xzr,#0x1
005410b4  ldr x7,[sp, #0x360]
005410b8  ldr x8,[sp, #0x368]
005410bc  bl 0x00076870
005410c0  stp x0,x1,[sp, #0x1b8]
005410c4  ldr x9,[sp, #0x118]
005410c8  ldr x10,[sp, #0x98]
005410cc  stp x9,x10,[sp, #0x1c8]
005410d0  ldr x2,[sp, #0xb0]
005410d4  ldr x1,[sp, #0xf8]
005410d8  cmp x2,x1
005410dc  b.cc 0x005410e8
005410e0  ldr x0,[sp, #0x190]
005410e4  b 0x005410fc
005410e8  ldr x0,[sp, #0x190]
005410ec  orr x3,xzr,#0x1
005410f0  adrp x4,0x96d000
005410f4  add x4,x4,#0x7a0
005410f8  bl 0x00090b80
005410fc  lsl x9,x1,#0x4
00541100  add x9,x9,x9, LSL #0x2
00541104  sub x9,x9,#0x50
00541108  add x9,x0,x9
0054110c  adrp x27,0x147a000
00541110  ldr w10,[x27, #0x910]
00541114  cbz w10,0x0054114c
00541118  str x0,[sp, #0x2f8]
0054111c  str x1,[sp, #0xe0]
00541120  str x2,[sp, #0xd8]
00541124  str x9,[sp, #0x2f0]
00541128  adrp x0,0x96d000
0054112c  add x0,x0,#0x7a0
00541130  mov x1,x9
00541134  add x2,sp,#0x198
00541138  bl 0x0002e530
0054113c  ldr x0,[sp, #0x2f8]
00541140  ldr x1,[sp, #0xe0]
00541144  ldr x2,[sp, #0xd8]
00541148  ldr x9,[sp, #0x2f0]
0054114c  add x10,sp,#0x198
00541150  ldp q16,q17,[x10]
00541154  stp q16,q17,[x9]
00541158  ldp q16,q17,[x10, #0x20]
0054115c  stp q16,q17,[x9, #0x20]
00541160  ldr q16,[x10, #0x40]
00541164  str q16,[x9, #0x40]
00541168  ldr x9,[sp, #0x320]
0054116c  ldr x10,[sp, #0x108]
00541170  mov x3,x0
00541174  ldr x0,[sp, #0x100]
00541178  mov x4,x1
0054117c  mov x1,x2
00541180  mov x2,x4
00541184  b 0x00540f8c
00541188  cbz x2,0x005411f4
0054118c  add x0,sp,#0x68
00541190  adrp x1,0x9dd000
00541194  add x1,x1,#0x4e7
00541198  mov x2,#0x9
0054119c  ldr x3,[sp, #0x340]
005411a0  ldr x4,[sp, #0x348]
005411a4  adrp x5,0xc0a000
005411a8  add x5,x5,#0x628
005411ac  orr x6,xzr,#0x1
005411b0  ldr x7,[sp, #0x360]
005411b4  ldr x8,[sp, #0x368]
005411b8  bl 0x00076870
005411bc  mov x2,x0
005411c0  mov x3,x1
005411c4  ldr x4,[sp, #0x190]
005411c8  ldr x5,[sp, #0xa8]
005411cc  ldr x6,[sp, #0xb0]
005411d0  ldr x0,[sp, #0x370]
005411d4  ldr x1,[sp, #0x378]
005411d8  bl 0x00559760
005411dc  str x1,[sp, #0xa0]
005411e0  mov x2,xzr
005411e4  ldr x3,[sp, #0x90]
005411e8  ldr x4,[sp, #0x110]
005411ec  ldr x5,[sp, #0x88]
005411f0  b 0x00541238
005411f4  ldr x0,[sp, #0x88]
005411f8  ldr x1,[sp, #0x90]
005411fc  ldr x2,[sp, #0x110]
00541200  mov x3,x0
00541204  mov x0,x1
00541208  mov x1,x3
0054120c  b 0x00540f7c
00541210  ldr x6,[sp, #0x320]
00541214  add x6,x6,#0x28
00541218  ldr x7,[sp, #0x108]
0054121c  add x7,x7,#0x1
00541220  mov x3,x2
00541224  mov x4,x0
00541228  mov x5,x1
0054122c  ldr x1,[sp, #0xa0]
00541230  mov x2,x7
00541234  mov x0,x6
00541238  cmp x1,x2
0054123c  b.le 0x005413d0
00541240  str x3,[sp, #0xd0]
00541244  str x2,[sp, #0x108]
00541248  str x5,[sp, #0xc8]
0054124c  str x4,[sp, #0x2e8]
00541250  str x0,[sp, #0x320]
00541254  ldp x4,x5,[x0]
00541258  ldp x6,x7,[x0, #0x10]
0054125c  ldr x8,[x0, #0x20]
00541260  stp x4,x5,[sp, #0x120]
00541264  stp x6,x7,[sp, #0x130]
00541268  str x8,[sp, #0x140]
0054126c  ldp x2,x3,[sp, #0x130]
00541270  adrp x0,0x8ec000
00541274  add x0,x0,#0xb60
00541278  add x1,sp,#0x2b0
0054127c  bl 0x00020d00
00541280  ldrb w4,[x0]
00541284  tbz w4,#0x0,0x00541298
00541288  ldr x2,[sp, #0xd0]
0054128c  ldr x1,[sp, #0xc8]
00541290  ldr x0,[sp, #0x2e8]
00541294  b 0x00541210
00541298  ldp x2,x3,[sp, #0x130]
0054129c  adrp x0,0x8ec000
005412a0  add x0,x0,#0xb60
005412a4  add x1,sp,#0x2b0
005412a8  bl 0x00021200
005412ac  orr x4,xzr,#0x1
005412b0  strb w4,[x0]
005412b4  ldp x4,x5,[sp, #0x130]
005412b8  ldr x0,[sp, #0x340]
005412bc  ldr x1,[sp, #0x348]
005412c0  ldr x2,[sp, #0x350]
005412c4  ldr x3,[sp, #0x358]
005412c8  ldr x6,[sp, #0x398]
005412cc  ldr x7,[sp, #0x3a0]
005412d0  bl 0x0053fca0
005412d4  cbnz x4,0x005412dc
005412d8  cbnz x1,0x00541308
005412dc  ldp x4,x5,[sp, #0x130]
005412e0  ldr x0,[sp, #0x340]
005412e4  ldr x1,[sp, #0x348]
005412e8  ldr x2,[sp, #0x350]
005412ec  ldr x3,[sp, #0x358]
005412f0  ldr x6,[sp, #0x398]
005412f4  ldr x7,[sp, #0x3a0]
005412f8  mov x8,xzr
005412fc  mov x9,xzr
00541300  mov x10,xzr
00541304  bl 0x0053eee0
00541308  cbz x1,0x005413c0
0054130c  cbnz x3,0x00541314
00541310  ldp x2,x3,[sp, #0x120]
00541314  str x2,[sp, #0x120]
00541318  stp x3,x0,[sp, #0x128]
0054131c  mov x5,#0x64
00541320  stp x1,x5,[sp, #0x138]
00541324  ldr x5,[sp, #0xc8]
00541328  add x1,x5,#0x1
0054132c  ldr x2,[sp, #0xd0]
00541330  cmp x2,x1
00541334  b.cc 0x00541340
00541338  ldr x0,[sp, #0x2e8]
0054133c  b 0x00541354
00541340  ldr x0,[sp, #0x2e8]
00541344  orr x3,xzr,#0x1
00541348  adrp x4,0x940000
0054134c  add x4,x4,#0xfa0
00541350  bl 0x00090b80
00541354  lsl x4,x1,#0x3
00541358  add x4,x4,x4, LSL #0x2
0054135c  sub x4,x4,#0x28
00541360  add x4,x0,x4
00541364  adrp x27,0x147a000
00541368  ldr w5,[x27, #0x910]
0054136c  cbz w5,0x005413a4
00541370  str x0,[sp, #0x2e0]
00541374  str x1,[sp, #0xc0]
00541378  str x2,[sp, #0xb8]
0054137c  str x4,[sp, #0x308]
00541380  adrp x0,0x940000
00541384  add x0,x0,#0xfa0
00541388  mov x1,x4
0054138c  add x2,sp,#0x120
00541390  bl 0x0002e530
00541394  ldr x0,[sp, #0x2e0]
00541398  ldr x1,[sp, #0xc0]
0054139c  ldr x2,[sp, #0xb8]
005413a0  ldr x4,[sp, #0x308]
005413a4  ldp x6,x7,[sp, #0x120]
005413a8  ldp x8,x9,[sp, #0x130]
005413ac  ldr x10,[sp, #0x140]
005413b0  stp x6,x7,[x4]
005413b4  stp x8,x9,[x4, #0x10]
005413b8  str x10,[x4, #0x20]
005413bc  b 0x00541210
005413c0  ldr x1,[sp, #0xc8]
005413c4  ldr x2,[sp, #0xd0]
005413c8  ldr x0,[sp, #0x2e8]
005413cc  b 0x00541210
005413d0  mov x0,x5
005413d4  mov x1,x3
005413d8  mov x2,x4
005413dc  b 0x00541200
005413e0  stp x0,x1,[sp, #0x8]
005413e4  stp x2,x3,[sp, #0x18]
005413e8  stp x4,x5,[sp, #0x28]
005413ec  stp x6,x7,[sp, #0x38]
005413f0  stp x8,x9,[sp, #0x48]
005413f4  stp x10,x11,[sp, #0x58]
005413f8  stp x12,x13,[sp, #0x68]
005413fc  mov x3,x30
00541400  bl 0x00093ad0
00541404  ldp x0,x1,[sp, #0x8]
00541408  ldp x2,x3,[sp, #0x18]
0054140c  ldp x4,x5,[sp, #0x28]
00541410  ldp x6,x7,[sp, #0x38]
00541414  ldp x8,x9,[sp, #0x48]
00541418  ldp x10,x11,[sp, #0x58]
0054141c  ldp x12,x13,[sp, #0x68]
00541420  b 0x00540c00
