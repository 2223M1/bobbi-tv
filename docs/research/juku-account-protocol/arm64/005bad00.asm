; mv-daemon/provider.(*TokenStore).load
005bad00  ldr x16,[x28, #0x10]
005bad04  sub x17,sp,#0x20
005bad08  cmp x17,x16
005bad0c  b.ls 0x005bae90
005bad10  str x30,[sp, #-0xa0]!
005bad14  stur x29,[sp, #-0x8]
005bad18  sub x29,sp,#0x8
005bad1c  str xzr,[sp, #0x90]
005bad20  strb wzr,[sp, #0x37]
005bad24  ldrsb x27,[x0]
005bad28  nop
005bad2c  adrp x27,0x1479000
005bad30  ldrb w2,[x27, #0xc55]
005bad34  tbz w2,#0x0,0x005bad50
005bad38  orr x2,xzr,#0x1
005bad3c  mov w27,wzr
005bad40  casal w27,w2,[x0]
005bad44  cmp w27,wzr
005bad48  cset x3,eq
005bad4c  b 0x005bad6c
005bad50  orr x2,xzr,#0x1
005bad54  ldaxr w27,[x0]
005bad58  cmp w27,wzr
005bad5c  b.ne 0x005bad68
005bad60  stlxr w27,w2,[x0]
005bad64  cbnz x27,0x005bad54
005bad68  cset x3,eq
005bad6c  str x0,[sp, #0xa8]
005bad70  tbnz w3,#0x0,0x005bad7c
005bad74  bl 0x0009c680
005bad78  ldr x0,[sp, #0xa8]
005bad7c  adrp x2,0x5ba000
005bad80  add x2,x2,#0xeb0
005bad84  stp x2,x0,[sp, #0x80]
005bad88  add x2,sp,#0x80
005bad8c  str x2,[sp, #0x90]
005bad90  orr x2,xzr,#0x1
005bad94  strb w2,[sp, #0x37]
005bad98  ldp x0,x1,[x0, #0x8]
005bad9c  bl 0x000dd1c0
005bada0  cbnz x3,0x005bae64
005bada4  str x2,[sp, #0x60]
005bada8  str x1,[sp, #0x58]
005badac  str x0,[sp, #0x70]
005badb0  mov x2,x1
005badb4  mov x1,x0
005badb8  add x0,sp,#0x38
005badbc  bl 0x00076cd0
005badc0  bl 0x000b89d0
005badc4  nop
005badc8  cmp x1,#0x3
005badcc  b.lt 0x005badec
005badd0  str x0,[sp, #0x78]
005badd4  str x1,[sp, #0x68]
005badd8  adrp x1,0x9d2000
005baddc  add x1,x1,#0x125
005bade0  orr x2,xzr,#0x3
005bade4  bl 0x00012aa0
005bade8  tbnz w0,#0x0,0x005badfc
005badec  ldr x2,[sp, #0x60]
005badf0  ldr x1,[sp, #0x58]
005badf4  ldr x0,[sp, #0x70]
005badf8  b 0x005bae34
005badfc  bl 0x004f1a40
005bae00  mov x3,x1
005bae04  mov x4,x2
005bae08  ldr x1,[sp, #0x68]
005bae0c  mov x2,x0
005bae10  ldr x0,[sp, #0x78]
005bae14  bl 0x004f16a0
005bae18  cmp x3,#0x0
005bae1c  ldr x3,[sp, #0x60]
005bae20  csel x2,x3,x2,ne
005bae24  ldr x3,[sp, #0x58]
005bae28  csel x1,x3,x1,ne
005bae2c  ldr x3,[sp, #0x70]
005bae30  csel x0,x3,x0,ne
005bae34  ldr x5,[sp, #0xa8]
005bae38  add x4,x5,#0x18
005bae3c  adrp x3,0x892000
005bae40  add x3,x3,#0xe60
005bae44  bl 0x00123de0
005bae48  strb wzr,[sp, #0x37]
005bae4c  ldr x26,[sp, #0x90]
005bae50  ldr x5,[x26]
005bae54  blr x5
005bae58  ldur x29,[sp, #-0x8]
005bae5c  ldr x30,[sp], #0xa0
005bae60  ret
005bae64  strb wzr,[sp, #0x37]
005bae68  ldr x26,[sp, #0x90]
005bae6c  ldr x0,[x26]
005bae70  blr x0
005bae74  ldur x29,[sp, #-0x8]
005bae78  ldr x30,[sp], #0xa0
005bae7c  ret
005bae90  str x0,[sp, #0x8]
005bae94  mov x3,x30
005bae98  bl 0x00093ad0
005bae9c  ldr x0,[sp, #0x8]
005baea0  b 0x005bad00
