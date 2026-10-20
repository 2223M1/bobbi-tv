; main.handleQrCode
0075be80  ldr x16,[x28, #0x10]
0075be84  sub x17,sp,#0xd0
0075be88  cmp x17,x16
0075be8c  b.ls 0x0075c324
0075be90  sub x20,sp,#0x150
0075be94  stp x29,x30,[x20, #-0x8]
0075be98  mov sp,x20
0075be9c  sub x29,sp,#0x8
0075bea0  str x2,[sp, #0x168]
0075bea4  str x1,[sp, #0x160]
0075bea8  str x0,[sp, #0x158]
0075beac  ldr x2,[x0, #0x18]
0075beb0  mov x0,x1
0075beb4  blr x2
0075beb8  str x0,[sp, #0x70]
0075bebc  nop
0075bec0  adrp x0,0x9e8000
0075bec4  add x0,x0,#0xea
0075bec8  orr x1,xzr,#0xc
0075becc  bl 0x00209720
0075bed0  str x0,[sp, #0x140]
0075bed4  str x1,[sp, #0x50]
0075bed8  adrp x0,0x8b0000
0075bedc  add x0,x0,#0x5c0
0075bee0  bl 0x0002dd40
0075bee4  str x0,[sp, #0x138]
0075bee8  adrp x1,0x9f0000
0075beec  add x1,x1,#0xb73
0075bef0  orr x2,xzr,#0x10
0075bef4  stp x1,x2,[x0]
0075bef8  adrp x0,0x969000
0075befc  add x0,x0,#0x220
0075bf00  ldr x1,[sp, #0x70]
0075bf04  ldr x2,[sp, #0x140]
0075bf08  ldr x3,[sp, #0x50]
0075bf0c  bl 0x00021200
0075bf10  orr x1,xzr,#0x1
0075bf14  stp x1,x1,[x0, #0x8]
0075bf18  adrp x27,0x147a000
0075bf1c  ldr w1,[x27, #0x910]
0075bf20  cbnz w1,0x0075bf2c
0075bf24  ldr x2,[sp, #0x138]
0075bf28  b 0x0075bf3c
0075bf2c  ldr x1,[x0]
0075bf30  bl 0x000959d0
0075bf34  ldr x2,[sp, #0x138]
0075bf38  stp x2,x1,[x25]
0075bf3c  str x2,[x0]
0075bf40  ldr x1,[sp, #0x168]
0075bf44  ldr x0,[x1, #0x10]
0075bf48  bl 0x001a0640
0075bf4c  mov x1,x0
0075bf50  adrp x2,0x9d9000
0075bf54  add x2,x2,#0xf87
0075bf58  orr x3,xzr,#0x8
0075bf5c  adrp x0,0x973000
0075bf60  add x0,x0,#0x360
0075bf64  bl 0x00020d00
0075bf68  ldp x1,x2,[x0]
0075bf6c  cbnz x2,0x0075bf7c
0075bf70  mov x3,xzr
0075bf74  mov x2,xzr
0075bf78  b 0x0075bf80
0075bf7c  ldp x2,x3,[x1]
0075bf80  mov x0,x2
0075bf84  mov x1,x3
0075bf88  bl 0x0075b1c0
0075bf8c  str x0,[sp, #0x60]
0075bf90  str x1,[sp, #0x30]
0075bf94  adrp x27,0x144e000
0075bf98  ldr x2,[x27, #0x530]
0075bf9c  mov x3,x1
0075bfa0  mov x1,x2
0075bfa4  mov x2,x0
0075bfa8  adrp x0,0x8ed000
0075bfac  add x0,x0,#0xb60
0075bfb0  bl 0x00020f70
0075bfb4  ldp x2,x0,[x0]
0075bfb8  tbz w1,#0x0,0x0075c26c
0075bfbc  ldr x1,[sp, #0x30]
0075bfc0  cmp x1,#0x8
0075bfc4  b.ne 0x0075c0d8
0075bfc8  ldr x3,[sp, #0x60]
0075bfcc  ldr x4,[x3]
0075bfd0  mov x5,#0x4c43
0075bfd4  movk x5,#0x554f, LSL #16
0075bfd8  movk x5,#0x3144, LSL #32
0075bfdc  movk x5,#0x3531, LSL #48
0075bfe0  cmp x4,x5
0075bfe4  b.ne 0x0075c0d8
0075bfe8  str x0,[sp, #0x68]
0075bfec  str x2,[sp, #0x38]
0075bff0  ldr x1,[sp, #0x168]
0075bff4  ldr x0,[x1, #0x10]
0075bff8  bl 0x001a0640
0075bffc  mov x1,x0
0075c000  adrp x2,0x9e4000
0075c004  add x2,x2,#0x344
0075c008  mov x3,#0xb
0075c00c  adrp x0,0x973000
0075c010  add x0,x0,#0x360
0075c014  bl 0x00020d00
0075c018  ldp x1,x2,[x0]
0075c01c  cbnz x2,0x0075c02c
0075c020  mov x4,xzr
0075c024  mov x3,xzr
0075c028  b 0x0075c030
0075c02c  ldp x3,x4,[x1]
0075c030  cbnz x4,0x0075c04c
0075c034  adrp x27,0x144e000
0075c038  ldr x0,[x27, #0x548]
0075c03c  cbz x0,0x0075c04c
0075c040  bl 0x00774cc0
0075c044  mov x4,x1
0075c048  mov x3,x0
0075c04c  ldr x5,[sp, #0x38]
0075c050  adrp x6,0xc1c000
0075c054  add x6,x6,#0x630
0075c058  cmp x5,x6
0075c05c  b.ne 0x0075c068
0075c060  ldr x0,[sp, #0x68]
0075c064  b 0x0075c06c
0075c068  mov x0,xzr
0075c06c  b.ne 0x0075c0c8
0075c070  str x4,[sp, #0x48]
0075c074  str x3,[sp, #0x80]
0075c078  mov x1,x3
0075c07c  mov x2,x4
0075c080  bl 0x00538530
0075c084  cbnz x1,0x0075c0e0
0075c088  ldr x3,[sp, #0x48]
0075c08c  cbz x3,0x0075c0e0
0075c090  adrp x27,0x144e000
0075c094  ldr x4,[x27, #0x548]
0075c098  cbz x4,0x0075c0e0
0075c09c  str x1,[sp, #0x40]
0075c0a0  str x2,[sp, #0x78]
0075c0a4  str x0,[sp, #0x58]
0075c0a8  mov x0,x4
0075c0ac  ldr x1,[sp, #0x80]
0075c0b0  mov x2,x3
0075c0b4  bl 0x00774ec0
0075c0b8  ldr x0,[sp, #0x58]
0075c0bc  ldr x1,[sp, #0x40]
0075c0c0  ldr x2,[sp, #0x78]
0075c0c4  b 0x0075c0e0
0075c0c8  ldr x1,[x5, #0x48]
0075c0cc  ldr x0,[sp, #0x68]
0075c0d0  blr x1
0075c0d4  b 0x0075c0e0
0075c0d8  ldr x1,[x2, #0x48]
0075c0dc  blr x1
0075c0e0  cbnz x1,0x0075c23c
0075c0e4  str x0,[sp, #0x58]
0075c0e8  ldp x4,x1,[x0, #0x10]
0075c0ec  cbz x1,0x0075c218
0075c0f0  str x1,[sp, #0x50]
0075c0f4  nop
0075c0f8  cmp x1,#0xa
0075c0fc  b.lt 0x0075c12c
0075c100  str x4,[sp, #0x140]
0075c104  mov x0,x4
0075c108  adrp x1,0x9e1000
0075c10c  add x1,x1,#0x7b3
0075c110  mov x2,#0xa
0075c114  bl 0x00012aa0
0075c118  tbz w0,#0x0,0x0075c124
0075c11c  ldr x0,[sp, #0x58]
0075c120  b 0x0075c218
0075c124  ldr x1,[sp, #0x50]
0075c128  ldr x4,[sp, #0x140]
0075c12c  mov x0,x4
0075c130  orr x2,xzr,#0x1
0075c134  mov x3,#0x12c
0075c138  bl 0x005592f0
0075c13c  cbnz x3,0x0075c19c
0075c140  adrp x27,0x144e000
0075c144  ldr x4,[x27, #0x890]
0075c148  mov x3,x2
0075c14c  mov x2,x1
0075c150  mov x1,x0
0075c154  mov x0,x4
0075c158  bl 0x001229a0
0075c15c  mov x2,#0x16
0075c160  mov x3,x0
0075c164  mov x4,x1
0075c168  mov x0,xzr
0075c16c  adrp x1,0x9fa000
0075c170  add x1,x1,#0xfac
0075c174  bl 0x00076780
0075c178  ldr x4,[sp, #0x58]
0075c17c  str x1,[x4, #0x18]
0075c180  adrp x27,0x147a000
0075c184  ldr w5,[x27, #0x910]
0075c188  cbz w5,0x0075c198
0075c18c  ldr x2,[x4, #0x10]
0075c190  bl 0x000959d0
0075c194  stp x0,x2,[x25]
0075c198  str x0,[x4, #0x10]
0075c19c  add x2,sp,#0xe8
0075c1a0  stp xzr,xzr,[x2]
0075c1a4  stp xzr,xzr,[x2, #0x10]
0075c1a8  ldr x0,[sp, #0x60]
0075c1ac  ldr x1,[sp, #0x30]
0075c1b0  bl 0x0008bd90
0075c1b4  adrp x2,0x8a6000
0075c1b8  add x2,x2,#0x880
0075c1bc  stp x2,x0,[sp, #0xe8]
0075c1c0  ldr x0,[sp, #0x50]
0075c1c4  bl 0x0008bd10
0075c1c8  adrp x2,0x8a6000
0075c1cc  add x2,x2,#0xac0
0075c1d0  stp x2,x0,[sp, #0xf8]
0075c1d4  adrp x2,0x75c000
0075c1d8  add x2,x2,#0x340
0075c1dc  str x2,[sp, #0x108]
0075c1e0  adrp x2,0xa20000
0075c1e4  add x2,x2,#0xcd3
0075c1e8  mov x3,#0x36
0075c1ec  stp x2,x3,[sp, #0x110]
0075c1f0  orr x2,xzr,#0x2
0075c1f4  str x2,[sp, #0x130]
0075c1f8  add x3,sp,#0xe8
0075c1fc  stp x3,x2,[sp, #0x120]
0075c200  adrp x27,0x144e000
0075c204  ldr x0,[x27, #0x5a8]
0075c208  mov x1,xzr
0075c20c  add x3,sp,#0x108
0075c210  bl 0x0013e8e0
0075c214  ldr x0,[sp, #0x58]
0075c218  ldr x1,[sp, #0x158]
0075c21c  cbz x1,0x0075c294
0075c220  ldr x3,[x1, #0x8]
0075c224  adrp x4,0x1432000
0075c228  add x4,x4,#0x260
0075c22c  ldar x5,[x4]
0075c230  ldr w6,[x1, #0x10]
0075c234  ldr x7,[x5]
0075c238  b 0x0075c2e0
0075c23c  ldr x1,[x1, #0x18]
0075c240  mov x0,x2
0075c244  blr x1
0075c248  mov x2,x0
0075c24c  mov x3,x1
0075c250  mov x4,#0x1f4
0075c254  ldr x0,[sp, #0x158]
0075c258  ldr x1,[sp, #0x160]
0075c25c  bl 0x0075b720
0075c260  ldp x29,x30,[sp, #-0x8]
0075c264  add sp,sp,#0x150
0075c268  ret
0075c26c  ldr x0,[sp, #0x158]
0075c270  ldr x1,[sp, #0x160]
0075c274  adrp x2,0x9f0000
0075c278  add x2,x2,#0xba3
0075c27c  orr x3,xzr,#0x10
0075c280  mov x4,#0x190
0075c284  bl 0x0075b720
0075c288  ldp x29,x30,[sp, #-0x8]
0075c28c  add sp,sp,#0x150
0075c290  ret
0075c294  add x3,sp,#0x88
0075c298  stp xzr,xzr,[x3]
0075c29c  stp xzr,xzr,[x3, #0x10]
0075c2a0  stp xzr,xzr,[x3, #0x20]
0075c2a4  stp xzr,xzr,[x3, #0x30]
0075c2a8  stp xzr,xzr,[x3, #0x40]
0075c2ac  stp xzr,xzr,[x3, #0x50]
0075c2b0  ldr x4,[sp, #0x160]
0075c2b4  stp x1,x4,[sp, #0x88]
0075c2b8  orr x4,xzr,#0x1
0075c2bc  strb w4,[sp, #0xa8]
0075c2c0  adrp x1,0x885000
0075c2c4  add x1,x1,#0x660
0075c2c8  mov x2,x0
0075c2cc  mov x0,x3
0075c2d0  bl 0x00134da0
0075c2d4  ldp x29,x30,[sp, #-0x8]
0075c2d8  add sp,sp,#0x150
0075c2dc  ret
0075c2e0  and x8,x6,x7
0075c2e4  lsl x8,x8,#0x4
0075c2e8  add x8,x8,#0x8
0075c2ec  ldr x9,[x5, x8#0x0]
0075c2f0  add x8,x5,x8
0075c2f4  cmp x9,x3
0075c2f8  b.eq 0x0075c31c
0075c2fc  add x6,x6,#0x1
0075c300  cbnz x9,0x0075c2e0
0075c304  mov x0,x4
0075c308  mov x1,x3
0075c30c  bl 0x0002a110
0075c310  mov x1,x0
0075c314  ldr x0,[sp, #0x58]
0075c318  b 0x0075c294
0075c31c  ldr x1,[x8, #0x8]
0075c320  b 0x0075c294
0075c324  stp x0,x1,[sp, #0x8]
0075c328  str x2,[sp, #0x18]
0075c32c  mov x3,x30
0075c330  bl 0x00093ad0
0075c334  ldp x0,x1,[sp, #0x8]
0075c338  ldr x2,[sp, #0x18]
0075c33c  b 0x0075be80
