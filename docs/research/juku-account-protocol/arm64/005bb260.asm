; mv-daemon/provider.(*TokenStore).Get
005bb260  ldr x16,[x28, #0x10]
005bb264  cmp sp,x16
005bb268  b.ls 0x005bb390
005bb26c  str x30,[sp, #-0x60]!
005bb270  stur x29,[sp, #-0x8]
005bb274  sub x29,sp,#0x8
005bb278  str x1,[sp, #0x70]
005bb27c  str xzr,[sp, #0x50]
005bb280  strb wzr,[sp, #0x2f]
005bb284  stp xzr,xzr,[sp, #0x30]
005bb288  ldrsb x27,[x0]
005bb28c  nop
005bb290  adrp x27,0x1479000
005bb294  ldrb w4,[x27, #0xc55]
005bb298  tbz w4,#0x0,0x005bb2b4
005bb29c  orr x4,xzr,#0x1
005bb2a0  mov w27,wzr
005bb2a4  casal w27,w4,[x0]
005bb2a8  cmp w27,wzr
005bb2ac  cset x5,eq
005bb2b0  b 0x005bb2d0
005bb2b4  orr x4,xzr,#0x1
005bb2b8  ldaxr w27,[x0]
005bb2bc  cmp w27,wzr
005bb2c0  b.ne 0x005bb2cc
005bb2c4  stlxr w27,w4,[x0]
005bb2c8  cbnz x27,0x005bb2b8
005bb2cc  cset x5,eq
005bb2d0  tbnz w5,#0x0,0x005bb2f0
005bb2d4  str x0,[sp, #0x68]
005bb2d8  str x2,[sp, #0x78]
005bb2dc  str x1,[sp, #0x70]
005bb2e0  bl 0x0009c680
005bb2e4  ldr x0,[sp, #0x68]
005bb2e8  ldr x1,[sp, #0x70]
005bb2ec  ldr x2,[sp, #0x78]
005bb2f0  adrp x4,0x5bb000
005bb2f4  add x4,x4,#0x3b0
005bb2f8  stp x4,x0,[sp, #0x40]
005bb2fc  add x4,sp,#0x40
005bb300  str x4,[sp, #0x50]
005bb304  orr x4,xzr,#0x1
005bb308  strb w4,[sp, #0x2f]
005bb30c  ldr x4,[x0, #0x18]
005bb310  cbz x4,0x005bb354
005bb314  adrp x0,0x8ec000
005bb318  add x0,x0,#0xae0
005bb31c  mov x3,x2
005bb320  mov x2,x1
005bb324  mov x1,x4
005bb328  bl 0x00020d00
005bb32c  ldp x4,x5,[x0]
005bb330  stp x4,x5,[sp, #0x30]
005bb334  strb wzr,[sp, #0x2f]
005bb338  ldr x26,[sp, #0x50]
005bb33c  ldr x4,[x26]
005bb340  blr x4
005bb344  ldp x0,x1,[sp, #0x30]
005bb348  ldur x29,[sp, #-0x8]
005bb34c  ldr x30,[sp], #0x60
005bb350  ret
005bb354  stp xzr,xzr,[sp, #0x30]
005bb358  strb wzr,[sp, #0x2f]
005bb35c  ldr x26,[sp, #0x50]
005bb360  ldr x0,[x26]
005bb364  blr x0
005bb368  ldp x0,x1,[sp, #0x30]
005bb36c  ldur x29,[sp, #-0x8]
005bb370  ldr x30,[sp], #0x60
005bb374  ret
005bb390  stp x0,x1,[sp, #0x8]
005bb394  str x2,[sp, #0x18]
005bb398  mov x3,x30
005bb39c  bl 0x00093ad0
005bb3a0  ldp x0,x1,[sp, #0x8]
005bb3a4  ldr x2,[sp, #0x18]
005bb3a8  b 0x005bb260
