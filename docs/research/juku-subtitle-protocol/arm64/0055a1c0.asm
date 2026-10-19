; mv-daemon/provider.ExtractSubFidsFromUrl
0055a1c0  ldr x16,[x28, #0x10]
0055a1c4  sub x17,sp,#0x180
0055a1c8  cmp x17,x16
0055a1cc  b.ls 0x0055a528
0055a1d0  sub x20,sp,#0x200
0055a1d4  stp x29,x30,[x20, #-0x8]
0055a1d8  mov sp,x20
0055a1dc  sub x29,sp,#0x8
0055a1e0  str x0,[sp, #0x208]
0055a1e4  cbz x1,0x0055a2a0
0055a1e8  str x1,[sp, #0x210]
0055a1ec  str x0,[sp, #0x208]
0055a1f0  adrp x0,0xa1e000
0055a1f4  add x0,x0,#0xaa4
0055a1f8  mov x1,#0x33
0055a1fc  bl 0x002ae050
0055a200  ldr x1,[sp, #0x208]
0055a204  ldr x2,[sp, #0x210]
0055a208  mov x3,#-0x1
0055a20c  bl 0x002b05b0
0055a210  cbz x1,0x0055a288
0055a214  str x1,[sp, #0x80]
0055a218  str x0,[sp, #0xc0]
0055a21c  add x0,sp,#0x1c8
0055a220  stp xzr,xzr,[x0]
0055a224  stp xzr,xzr,[x0, #0x10]
0055a228  stp xzr,xzr,[x0, #0x20]
0055a22c  add x0,sp,#0x100
0055a230  orr x1,xzr,#0x3
0055a234  stp xzr,xzr,[x0], #0x10
0055a238  stp xzr,xzr,[x0], #0x10
0055a23c  stp xzr,xzr,[x0], #0x10
0055a240  stp xzr,xzr,[x0], #0x10
0055a244  sub x1,x1,#0x1
0055a248  cbnz x1,0x0055a234
0055a24c  str xzr,[x0]
0055a250  orr x0,xzr,#-0x7f7f7f7f7f7f7f80
0055a254  str x0,[sp, #0x100]
0055a258  add x0,sp,#0x100
0055a25c  str x0,[sp, #0x1d8]
0055a260  bl 0x0008ef50
0055a264  str x0,[sp, #0x1d0]
0055a268  ldr x0,[sp, #0xc0]
0055a26c  ldr x1,[sp, #0x80]
0055a270  mov x2,xzr
0055a274  mov x3,xzr
0055a278  mov x4,xzr
0055a27c  mov x5,xzr
0055a280  mov x6,xzr
0055a284  b 0x0055a2c0
0055a288  mov x0,xzr
0055a28c  mov x1,xzr
0055a290  mov x2,xzr
0055a294  ldp x29,x30,[sp, #-0x8]
0055a298  add sp,sp,#0x200
0055a29c  ret
0055a2a0  mov x0,xzr
0055a2a4  mov x1,xzr
0055a2a8  mov x2,xzr
0055a2ac  ldp x29,x30,[sp, #-0x8]
0055a2b0  add sp,sp,#0x200
0055a2b4  ret
0055a2b8  add x0,x0,#0x18
0055a2bc  add x2,x2,#0x1
0055a2c0  cmp x1,x2
0055a2c4  b.le 0x0055a4d8
0055a2c8  ldp x7,x8,[x0]
0055a2cc  cmp x8,#0x2
0055a2d0  b.lt 0x0055a2b8
0055a2d4  str x2,[sp, #0xa0]
0055a2d8  str x0,[sp, #0xd8]
0055a2dc  strb w3,[sp, #0x57]
0055a2e0  str x6,[sp, #0x70]
0055a2e4  str x5,[sp, #0x68]
0055a2e8  str x4,[sp, #0xb0]
0055a2ec  ldp x0,x1,[x7, #0x10]
0055a2f0  str x1,[sp, #0x60]
0055a2f4  str x0,[sp, #0xa8]
0055a2f8  orr x2,xzr,#0x2
0055a2fc  bl 0x0019c730
0055a300  cmp x2,#0x0
0055a304  cset x3,ne
0055a308  eor x3,x3,#0x1
0055a30c  tst w3,#0x1
0055a310  ldr x3,[sp, #0x60]
0055a314  csel x1,x1,x3,ne
0055a318  ldr x3,[sp, #0xa8]
0055a31c  csel x0,x0,x3,ne
0055a320  adrp x2,0xc0a000
0055a324  add x2,x2,#0x5f0
0055a328  orr x3,xzr,#0x1
0055a32c  mov x4,xzr
0055a330  mov x5,#-0x1
0055a334  bl 0x000b6600
0055a338  str x1,[sp, #0x58]
0055a33c  mov x2,xzr
0055a340  ldrb w3,[sp, #0x57]
0055a344  ldr x4,[sp, #0x70]
0055a348  ldr x5,[sp, #0x68]
0055a34c  ldr x6,[sp, #0xb0]
0055a350  b 0x0055a37c
0055a354  ldr x7,[sp, #0xc8]
0055a358  add x7,x7,#0x10
0055a35c  ldr x8,[sp, #0x98]
0055a360  add x8,x8,#0x1
0055a364  mov x3,x0
0055a368  mov x0,x7
0055a36c  mov x4,x2
0055a370  mov x5,x1
0055a374  ldr x1,[sp, #0x58]
0055a378  mov x2,x8
0055a37c  cmp x1,x2
0055a380  b.le 0x0055a4bc
0055a384  str x2,[sp, #0x98]
0055a388  strb w3,[sp, #0x56]
0055a38c  str x4,[sp, #0x90]
0055a390  str x5,[sp, #0x88]
0055a394  str x6,[sp, #0xd0]
0055a398  str x0,[sp, #0xc8]
0055a39c  ldp x0,x1,[x0]
0055a3a0  bl 0x000b89d0
0055a3a4  str x0,[sp, #0xb8]
0055a3a8  str x1,[sp, #0x78]
0055a3ac  cbnz x1,0x0055a3b8
0055a3b0  mov x4,xzr
0055a3b4  b 0x0055a3e0
0055a3b8  mov x2,x0
0055a3bc  mov x3,x1
0055a3c0  adrp x0,0x8ec000
0055a3c4  add x0,x0,#0xb60
0055a3c8  add x1,sp,#0x1c8
0055a3cc  bl 0x00020d00
0055a3d0  ldrb w4,[x0]
0055a3d4  eor x4,x4,#0x1
0055a3d8  ldr x0,[sp, #0xb8]
0055a3dc  ldr x1,[sp, #0x78]
0055a3e0  tbnz w4,#0x0,0x0055a3f8
0055a3e4  ldr x1,[sp, #0x88]
0055a3e8  ldr x2,[sp, #0x90]
0055a3ec  ldrb w0,[sp, #0x56]
0055a3f0  ldr x6,[sp, #0xd0]
0055a3f4  b 0x0055a354
0055a3f8  mov x2,x0
0055a3fc  mov x3,x1
0055a400  adrp x0,0x8ec000
0055a404  add x0,x0,#0xb60
0055a408  add x1,sp,#0x1c8
0055a40c  bl 0x00021200
0055a410  orr x4,xzr,#0x1
0055a414  strb w4,[x0]
0055a418  ldr x4,[sp, #0x88]
0055a41c  add x1,x4,#0x1
0055a420  ldr x2,[sp, #0x90]
0055a424  cmp x2,x1
0055a428  b.cc 0x0055a438
0055a42c  ldr x6,[sp, #0xd0]
0055a430  ldrb w0,[sp, #0x56]
0055a434  b 0x0055a480
0055a438  cmp x1,#0x2
0055a43c  b.gt 0x0055a464
0055a440  ldrb w0,[sp, #0x56]
0055a444  tbnz w0,#0x0,0x0055a464
0055a448  cbnz x4,0x0055a464
0055a44c  add x6,sp,#0xe0
0055a450  stp xzr,xzr,[x6]
0055a454  stp xzr,xzr,[x6, #0x10]
0055a458  orr x2,xzr,#0x2
0055a45c  orr x0,xzr,#0x1
0055a460  b 0x0055a480
0055a464  ldr x0,[sp, #0xd0]
0055a468  orr x3,xzr,#0x1
0055a46c  adrp x4,0x8a6000
0055a470  add x4,x4,#0x880
0055a474  bl 0x00090b80
0055a478  mov x6,x0
0055a47c  ldrb w0,[sp, #0x56]
0055a480  sub x3,x1,#0x1
0055a484  add x3,x6,x3, LSL #0x4
0055a488  ldr x4,[sp, #0x78]
0055a48c  str x4,[x3, #0x8]
0055a490  adrp x27,0x147a000
0055a494  ldr w4,[x27, #0x910]
0055a498  cbnz w4,0x0055a4a4
0055a49c  ldr x5,[sp, #0xb8]
0055a4a0  b 0x0055a4b4
0055a4a4  ldr x4,[x3]
0055a4a8  bl 0x000959d0
0055a4ac  ldr x5,[sp, #0xb8]
0055a4b0  stp x5,x4,[x25]
0055a4b4  str x5,[x3]
0055a4b8  b 0x0055a354
0055a4bc  ldr x0,[sp, #0xd8]
0055a4c0  ldr x1,[sp, #0x80]
0055a4c4  ldr x2,[sp, #0xa0]
0055a4c8  mov x7,x6
0055a4cc  mov x6,x4
0055a4d0  mov x4,x7
0055a4d4  b 0x0055a2b8
0055a4d8  add x3,sp,#0x200
0055a4dc  mov x7,sp
0055a4e0  sub x3,x3,x7
0055a4e4  mov x1,x4
0055a4e8  sub x4,x4,x7
0055a4ec  cmp x4,x3
0055a4f0  b.cs 0x0055a510
0055a4f4  adrp x0,0x8a6000
0055a4f8  add x0,x0,#0x880
0055a4fc  mov x2,x5
0055a500  bl 0x00073140
0055a504  mov x5,x1
0055a508  mov x6,x2
0055a50c  mov x1,x0
0055a510  mov x0,x1
0055a514  mov x1,x5
0055a518  mov x2,x6
0055a51c  ldp x29,x30,[sp, #-0x8]
0055a520  add sp,sp,#0x200
0055a524  ret
0055a528  stp x0,x1,[sp, #0x8]
0055a52c  mov x3,x30
0055a530  bl 0x00093ad0
0055a534  ldp x0,x1,[sp, #0x8]
0055a538  b 0x0055a1c0
