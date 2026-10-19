; main.handleQrCodeStatus
0075dcf0  ldr x16,[x28, #0x10]
0075dcf4  sub x17,sp,#0x170
0075dcf8  cmp x17,x16
0075dcfc  b.ls 0x0075e1e4
0075dd00  sub x20,sp,#0x1f0
0075dd04  stp x29,x30,[x20, #-0x8]
0075dd08  mov sp,x20
0075dd0c  sub x29,sp,#0x8
0075dd10  str x2,[sp, #0x208]
0075dd14  str x1,[sp, #0x200]
0075dd18  str x0,[sp, #0x1f8]
0075dd1c  ldr x2,[x0, #0x18]
0075dd20  mov x0,x1
0075dd24  blr x2
0075dd28  str x0,[sp, #0x70]
0075dd2c  nop
0075dd30  adrp x0,0x9e8000
0075dd34  add x0,x0,#0xea
0075dd38  orr x1,xzr,#0xc
0075dd3c  bl 0x00209720
0075dd40  str x0,[sp, #0x80]
0075dd44  str x1,[sp, #0x48]
0075dd48  adrp x0,0x8b0000
0075dd4c  add x0,x0,#0x5c0
0075dd50  bl 0x0002dd40
0075dd54  str x0,[sp, #0x78]
0075dd58  adrp x1,0x9f0000
0075dd5c  add x1,x1,#0xb73
0075dd60  orr x2,xzr,#0x10
0075dd64  stp x1,x2,[x0]
0075dd68  adrp x0,0x969000
0075dd6c  add x0,x0,#0x220
0075dd70  ldr x1,[sp, #0x70]
0075dd74  ldr x2,[sp, #0x80]
0075dd78  ldr x3,[sp, #0x48]
0075dd7c  bl 0x00021200
0075dd80  orr x1,xzr,#0x1
0075dd84  stp x1,x1,[x0, #0x8]
0075dd88  adrp x27,0x147a000
0075dd8c  ldr w1,[x27, #0x910]
0075dd90  cbnz w1,0x0075dd9c
0075dd94  ldr x2,[sp, #0x78]
0075dd98  b 0x0075ddac
0075dd9c  ldr x1,[x0]
0075dda0  bl 0x000959d0
0075dda4  ldr x2,[sp, #0x78]
0075dda8  stp x2,x1,[x25]
0075ddac  str x2,[x0]
0075ddb0  ldr x1,[sp, #0x208]
0075ddb4  ldr x0,[x1, #0x10]
0075ddb8  bl 0x001a0640
0075ddbc  mov x1,x0
0075ddc0  adrp x2,0x9d9000
0075ddc4  add x2,x2,#0xf87
0075ddc8  orr x3,xzr,#0x8
0075ddcc  adrp x0,0x973000
0075ddd0  add x0,x0,#0x360
0075ddd4  bl 0x00020d00
0075ddd8  ldp x1,x2,[x0]
0075dddc  cbnz x2,0x0075ddec
0075dde0  mov x3,xzr
0075dde4  mov x2,xzr
0075dde8  b 0x0075ddf0
0075ddec  ldp x2,x3,[x1]
0075ddf0  mov x0,x2
0075ddf4  mov x1,x3
0075ddf8  bl 0x0075b1c0
0075ddfc  str x0,[sp, #0x68]
0075de00  str x1,[sp, #0x40]
0075de04  ldr x2,[sp, #0x208]
0075de08  ldr x0,[x2, #0x10]
0075de0c  bl 0x001a0640
0075de10  mov x1,x0
0075de14  adrp x2,0x9d2000
0075de18  add x2,x2,#0x10d
0075de1c  orr x3,xzr,#0x3
0075de20  adrp x0,0x973000
0075de24  add x0,x0,#0x360
0075de28  bl 0x00020d00
0075de2c  ldp x2,x3,[x0]
0075de30  cbnz x3,0x0075de40
0075de34  mov x4,xzr
0075de38  mov x5,xzr
0075de3c  b 0x0075de44
0075de40  ldp x4,x5,[x2]
0075de44  str x5,[sp, #0x30]
0075de48  str x4,[sp, #0x50]
0075de4c  adrp x27,0x144e000
0075de50  ldr x1,[x27, #0x530]
0075de54  adrp x0,0x8ed000
0075de58  add x0,x0,#0xb60
0075de5c  ldr x2,[sp, #0x68]
0075de60  ldr x3,[sp, #0x40]
0075de64  bl 0x00020f70
0075de68  ldp x4,x0,[x0]
0075de6c  tbz w1,#0x0,0x0075dfd0
0075de70  ldr x2,[sp, #0x30]
0075de74  cmp x2,#0x6
0075de78  b.ne 0x0075df14
0075de7c  ldr x1,[sp, #0x50]
0075de80  ldr w3,[x1]
0075de84  mov x5,#0x616d
0075de88  movk x5,#0x756e, LSL #16
0075de8c  cmp w3,w5
0075de90  b.ne 0x0075df18
0075de94  ldrh w3,[x1, #0x4]
0075de98  mov x5,#0x6c61
0075de9c  cmp w3,w5
0075dea0  b.ne 0x0075df18
0075dea4  adrp x27,0x144e000
0075dea8  ldr x0,[x27, #0x510]
0075deac  cbnz x0,0x0075debc
0075deb0  mov x1,xzr
0075deb4  mov x0,xzr
0075deb8  b 0x0075dec8
0075debc  ldr x1,[sp, #0x68]
0075dec0  ldr x2,[sp, #0x40]
0075dec4  bl 0x005bb260
0075dec8  cbz x1,0x0075def0
0075decc  ldr x2,[sp, #0x1f8]
0075ded0  cbz x2,0x0075e110
0075ded4  ldr x3,[x2, #0x8]
0075ded8  adrp x4,0x1432000
0075dedc  add x4,x4,#0x320
0075dee0  ldar x5,[x4]
0075dee4  ldr w2,[x2, #0x10]
0075dee8  ldr x6,[x5]
0075deec  b 0x0075e194
0075def0  ldr x0,[sp, #0x1f8]
0075def4  cbz x0,0x0075e088
0075def8  ldr x1,[x0, #0x8]
0075defc  adrp x3,0x1432000
0075df00  add x3,x3,#0x340
0075df04  ldar x4,[x3]
0075df08  ldr w5,[x0, #0x10]
0075df0c  ldr x6,[x4]
0075df10  b 0x0075e0d8
0075df14  ldr x1,[sp, #0x50]
0075df18  ldr x3,[x4, #0x30]
0075df1c  blr x3
0075df20  cbnz x1,0x0075dfa0
0075df24  str x0,[sp, #0x60]
0075df28  ldp x5,x6,[x0]
0075df2c  cmp x6,#0x9
0075df30  b.ne 0x0075df7c
0075df34  ldr x6,[x5]
0075df38  mov x7,#0x6f63
0075df3c  movk x7,#0x666e, LSL #16
0075df40  movk x7,#0x7269, LSL #32
0075df44  movk x7,#0x656d, LSL #48
0075df48  cmp x6,x7
0075df4c  b.ne 0x0075df7c
0075df50  ldrb w5,[x5, #0x8]
0075df54  cmp w5,#0x64
0075df58  b.ne 0x0075df7c
0075df5c  ldp x3,x4,[x0, #0x10]
0075df60  cbz x4,0x0075df7c
0075df64  adrp x27,0x144e000
0075df68  ldr x0,[x27, #0x510]
0075df6c  ldr x1,[sp, #0x68]
0075df70  ldr x2,[sp, #0x40]
0075df74  bl 0x005baf30
0075df78  ldr x0,[sp, #0x60]
0075df7c  ldr x1,[sp, #0x1f8]
0075df80  cbz x1,0x0075dff8
0075df84  ldr x3,[x1, #0x8]
0075df88  adrp x4,0x1432000
0075df8c  add x4,x4,#0x360
0075df90  ldar x5,[x4]
0075df94  ldr w6,[x1, #0x10]
0075df98  ldr x7,[x5]
0075df9c  b 0x0075e044
0075dfa0  ldr x1,[x1, #0x18]
0075dfa4  mov x0,x2
0075dfa8  blr x1
0075dfac  mov x2,x0
0075dfb0  mov x3,x1
0075dfb4  mov x4,#0x1f4
0075dfb8  ldr x0,[sp, #0x1f8]
0075dfbc  ldr x1,[sp, #0x200]
0075dfc0  bl 0x0075b720
0075dfc4  ldp x29,x30,[sp, #-0x8]
0075dfc8  add sp,sp,#0x1f0
0075dfcc  ret
0075dfd0  ldr x0,[sp, #0x1f8]
0075dfd4  ldr x1,[sp, #0x200]
0075dfd8  adrp x2,0x9f0000
0075dfdc  add x2,x2,#0xba3
0075dfe0  orr x3,xzr,#0x10
0075dfe4  mov x4,#0x190
0075dfe8  bl 0x0075b720
0075dfec  ldp x29,x30,[sp, #-0x8]
0075dff0  add sp,sp,#0x1f0
0075dff4  ret
0075dff8  add x3,sp,#0x88
0075dffc  stp xzr,xzr,[x3]
0075e000  stp xzr,xzr,[x3, #0x10]
0075e004  stp xzr,xzr,[x3, #0x20]
0075e008  stp xzr,xzr,[x3, #0x30]
0075e00c  stp xzr,xzr,[x3, #0x40]
0075e010  stp xzr,xzr,[x3, #0x50]
0075e014  ldr x4,[sp, #0x200]
0075e018  stp x1,x4,[sp, #0x88]
0075e01c  orr x4,xzr,#0x1
0075e020  strb w4,[sp, #0xa8]
0075e024  adrp x1,0x885000
0075e028  add x1,x1,#0x5a0
0075e02c  mov x2,x0
0075e030  mov x0,x3
0075e034  bl 0x00134da0
0075e038  ldp x29,x30,[sp, #-0x8]
0075e03c  add sp,sp,#0x1f0
0075e040  ret
0075e044  and x8,x6,x7
0075e048  lsl x8,x8,#0x4
0075e04c  add x8,x8,#0x8
0075e050  ldr x9,[x5, x8#0x0]
0075e054  add x8,x5,x8
0075e058  cmp x9,x3
0075e05c  b.eq 0x0075e080
0075e060  add x6,x6,#0x1
0075e064  cbnz x9,0x0075e044
0075e068  mov x0,x4
0075e06c  mov x1,x3
0075e070  bl 0x0002a110
0075e074  mov x1,x0
0075e078  ldr x0,[sp, #0x60]
0075e07c  b 0x0075dff8
0075e080  ldr x1,[x8, #0x8]
0075e084  b 0x0075dff8
0075e088  add x3,sp,#0xe8
0075e08c  stp xzr,xzr,[x3]
0075e090  stp xzr,xzr,[x3, #0x10]
0075e094  stp xzr,xzr,[x3, #0x20]
0075e098  stp xzr,xzr,[x3, #0x30]
0075e09c  stp xzr,xzr,[x3, #0x40]
0075e0a0  stp xzr,xzr,[x3, #0x50]
0075e0a4  ldr x4,[sp, #0x200]
0075e0a8  stp x0,x4,[sp, #0xe8]
0075e0ac  orr x4,xzr,#0x1
0075e0b0  strb w4,[sp, #0x108]
0075e0b4  mov x0,x3
0075e0b8  adrp x1,0x95a000
0075e0bc  add x1,x1,#0xde0
0075e0c0  adrp x2,0xc19000
0075e0c4  add x2,x2,#0x840
0075e0c8  bl 0x00134da0
0075e0cc  ldp x29,x30,[sp, #-0x8]
0075e0d0  add sp,sp,#0x1f0
0075e0d4  ret
0075e0d8  and x7,x5,x6
0075e0dc  lsl x7,x7,#0x4
0075e0e0  add x7,x7,#0x8
0075e0e4  ldr x8,[x4, x7#0x0]
0075e0e8  add x7,x4,x7
0075e0ec  cmp x8,x1
0075e0f0  b.eq 0x0075e108
0075e0f4  add x5,x5,#0x1
0075e0f8  cbnz x8,0x0075e0d8
0075e0fc  mov x0,x3
0075e100  bl 0x0002a110
0075e104  b 0x0075e088
0075e108  ldr x0,[x7, #0x8]
0075e10c  b 0x0075e088
0075e110  add x3,sp,#0x148
0075e114  stp xzr,xzr,[x3]
0075e118  stp xzr,xzr,[x3, #0x10]
0075e11c  stp xzr,xzr,[x3, #0x20]
0075e120  stp xzr,xzr,[x3, #0x30]
0075e124  stp xzr,xzr,[x3, #0x40]
0075e128  stp xzr,xzr,[x3, #0x50]
0075e12c  ldr x3,[sp, #0x200]
0075e130  stp x2,x3,[sp, #0x148]
0075e134  orr x2,xzr,#0x1
0075e138  strb w2,[sp, #0x168]
0075e13c  add x2,sp,#0x1a8
0075e140  stp xzr,xzr,[x2]
0075e144  stp xzr,xzr,[x2, #0x10]
0075e148  stp xzr,xzr,[x2, #0x20]
0075e14c  stp xzr,xzr,[x2, #0x30]
0075e150  adrp x3,0x9dd000
0075e154  add x3,x3,#0xd
0075e158  mov x4,#0x9
0075e15c  stp x3,x4,[sp, #0x1a8]
0075e160  stp x0,x1,[sp, #0x1b8]
0075e164  adrp x0,0x95a000
0075e168  add x0,x0,#0xde0
0075e16c  mov x1,x2
0075e170  bl 0x00029ed0
0075e174  adrp x1,0x95a000
0075e178  add x1,x1,#0xde0
0075e17c  mov x2,x0
0075e180  add x0,sp,#0x148
0075e184  bl 0x00134da0
0075e188  ldp x29,x30,[sp, #-0x8]
0075e18c  add sp,sp,#0x1f0
0075e190  ret
0075e194  and x7,x2,x6
0075e198  lsl x7,x7,#0x4
0075e19c  add x7,x7,#0x8
0075e1a0  ldr x8,[x5, x7#0x0]
0075e1a4  add x7,x5,x7
0075e1a8  cmp x8,x3
0075e1ac  b.eq 0x0075e1dc
0075e1b0  add x2,x2,#0x1
0075e1b4  cbnz x8,0x0075e194
0075e1b8  str x1,[sp, #0x38]
0075e1bc  str x0,[sp, #0x58]
0075e1c0  mov x0,x4
0075e1c4  mov x1,x3
0075e1c8  bl 0x0002a110
0075e1cc  ldr x1,[sp, #0x38]
0075e1d0  mov x2,x0
0075e1d4  ldr x0,[sp, #0x58]
0075e1d8  b 0x0075e110
0075e1dc  ldr x2,[x7, #0x8]
0075e1e0  b 0x0075e110
0075e1e4  stp x0,x1,[sp, #0x8]
0075e1e8  str x2,[sp, #0x18]
0075e1ec  mov x3,x30
0075e1f0  bl 0x00093ad0
0075e1f4  ldp x0,x1,[sp, #0x8]
0075e1f8  ldr x2,[sp, #0x18]
0075e1fc  b 0x0075dcf0
