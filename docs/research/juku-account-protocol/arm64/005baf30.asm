; mv-daemon/provider.(*TokenStore).Save
005baf30  ldr x16,[x28, #0x10]
005baf34  sub x17,sp,#0x30
005baf38  cmp x17,x16
005baf3c  b.ls 0x005bb1b8
005baf40  str x30,[sp, #-0xb0]!
005baf44  stur x29,[sp, #-0x8]
005baf48  sub x29,sp,#0x8
005baf4c  str x1,[sp, #0xc0]
005baf50  str x3,[sp, #0xd0]
005baf54  str xzr,[sp, #0xa0]
005baf58  strb wzr,[sp, #0x47]
005baf5c  stp xzr,xzr,[sp, #0x78]
005baf60  ldrsb x27,[x0]
005baf64  nop
005baf68  adrp x27,0x1479000
005baf6c  ldrb w5,[x27, #0xc55]
005baf70  tbz w5,#0x0,0x005baf8c
005baf74  orr x5,xzr,#0x1
005baf78  mov w27,wzr
005baf7c  casal w27,w5,[x0]
005baf80  cmp w27,wzr
005baf84  cset x6,eq
005baf88  b 0x005bafa8
005baf8c  orr x5,xzr,#0x1
005baf90  ldaxr w27,[x0]
005baf94  cmp w27,wzr
005baf98  b.ne 0x005bafa4
005baf9c  stlxr w27,w5,[x0]
005bafa0  cbnz x27,0x005baf90
005bafa4  cset x6,eq
005bafa8  str x0,[sp, #0xb8]
005bafac  str x4,[sp, #0xd8]
005bafb0  str x2,[sp, #0xc8]
005bafb4  str x1,[sp, #0xc0]
005bafb8  str x3,[sp, #0xd0]
005bafbc  tbnz w6,#0x0,0x005bafd8
005bafc0  bl 0x0009c680
005bafc4  ldr x0,[sp, #0xb8]
005bafc8  ldr x1,[sp, #0xc0]
005bafcc  ldr x2,[sp, #0xc8]
005bafd0  ldr x3,[sp, #0xd0]
005bafd4  ldr x4,[sp, #0xd8]
005bafd8  adrp x5,0x5bb000
005bafdc  add x5,x5,#0x1e0
005bafe0  stp x5,x0,[sp, #0x90]
005bafe4  add x5,sp,#0x90
005bafe8  str x5,[sp, #0xa0]
005bafec  orr x5,xzr,#0x1
005baff0  strb w5,[sp, #0x47]
005baff4  ldr x5,[x0, #0x18]
005baff8  cbnz x5,0x005bb030
005baffc  bl 0x0008c430
005bb000  adrp x27,0x147a000
005bb004  ldr w1,[x27, #0x910]
005bb008  cbnz w1,0x005bb014
005bb00c  ldr x2,[sp, #0xb8]
005bb010  b 0x005bb024
005bb014  ldr x2,[sp, #0xb8]
005bb018  ldr x3,[x2, #0x18]
005bb01c  bl 0x000959d0
005bb020  stp x0,x3,[x25]
005bb024  str x0,[x2, #0x18]
005bb028  ldr x3,[sp, #0xd0]
005bb02c  ldr x4,[sp, #0xd8]
005bb030  mov x0,x3
005bb034  mov x1,x4
005bb038  bl 0x000b89d0
005bb03c  cbnz x1,0x005bb060
005bb040  ldr x4,[sp, #0xb8]
005bb044  ldr x1,[x4, #0x18]
005bb048  adrp x0,0x8ec000
005bb04c  add x0,x0,#0xae0
005bb050  ldr x2,[sp, #0xc0]
005bb054  ldr x3,[sp, #0xc8]
005bb058  bl 0x000216c0
005bb05c  b 0x005bb0ac
005bb060  ldr x4,[sp, #0xb8]
005bb064  ldr x1,[x4, #0x18]
005bb068  adrp x0,0x8ec000
005bb06c  add x0,x0,#0xae0
005bb070  ldr x2,[sp, #0xc0]
005bb074  ldr x3,[sp, #0xc8]
005bb078  bl 0x00021200
005bb07c  ldr x4,[sp, #0xd8]
005bb080  str x4,[x0, #0x8]
005bb084  adrp x27,0x147a000
005bb088  ldr w4,[x27, #0x910]
005bb08c  cbnz w4,0x005bb098
005bb090  ldr x3,[sp, #0xd0]
005bb094  b 0x005bb0a8
005bb098  ldr x2,[x0]
005bb09c  bl 0x000959d0
005bb0a0  ldr x3,[sp, #0xd0]
005bb0a4  stp x3,x2,[x25]
005bb0a8  str x3,[x0]
005bb0ac  ldr x2,[sp, #0xb8]
005bb0b0  ldr x1,[x2, #0x18]
005bb0b4  adrp x0,0x8ec000
005bb0b8  add x0,x0,#0xae0
005bb0bc  bl 0x001296e0
005bb0c0  cbnz x3,0x005bb17c
005bb0c4  str x1,[sp, #0x68]
005bb0c8  str x0,[sp, #0x88]
005bb0cc  str x2,[sp, #0x70]
005bb0d0  bl 0x004f1a40
005bb0d4  mov x3,x0
005bb0d8  mov x4,x1
005bb0dc  mov x5,x2
005bb0e0  ldr x0,[sp, #0x88]
005bb0e4  ldr x1,[sp, #0x68]
005bb0e8  ldr x2,[sp, #0x70]
005bb0ec  bl 0x004f1500
005bb0f0  cbz x2,0x005bb118
005bb0f4  stp x2,x3,[sp, #0x78]
005bb0f8  strb wzr,[sp, #0x47]
005bb0fc  ldr x26,[sp, #0xa0]
005bb100  ldr x0,[x26]
005bb104  blr x0
005bb108  ldp x0,x1,[sp, #0x78]
005bb10c  ldur x29,[sp, #-0x8]
005bb110  ldr x30,[sp], #0xb0
005bb114  ret
005bb118  mov x2,x1
005bb11c  mov x1,x0
005bb120  add x0,sp,#0x48
005bb124  bl 0x00076e90
005bb128  ldr x3,[sp, #0xb8]
005bb12c  ldp x3,x4,[x3, #0x8]
005bb130  orr x5,xzr,#0x180
005bb134  mov x6,x0
005bb138  mov x0,x3
005bb13c  mov x7,x1
005bb140  mov x1,x4
005bb144  mov x8,x2
005bb148  mov x2,x6
005bb14c  mov x3,x7
005bb150  mov x4,x8
005bb154  bl 0x000dd5a0
005bb158  stp x0,x1,[sp, #0x78]
005bb15c  strb wzr,[sp, #0x47]
005bb160  ldr x26,[sp, #0xa0]
005bb164  ldr x3,[x26]
005bb168  blr x3
005bb16c  ldp x0,x1,[sp, #0x78]
005bb170  ldur x29,[sp, #-0x8]
005bb174  ldr x30,[sp], #0xb0
005bb178  ret
005bb17c  stp x3,x4,[sp, #0x78]
005bb180  strb wzr,[sp, #0x47]
005bb184  ldr x26,[sp, #0xa0]
005bb188  ldr x0,[x26]
005bb18c  blr x0
005bb190  ldp x0,x1,[sp, #0x78]
005bb194  ldur x29,[sp, #-0x8]
005bb198  ldr x30,[sp], #0xb0
005bb19c  ret
005bb1b8  stp x0,x1,[sp, #0x8]
005bb1bc  stp x2,x3,[sp, #0x18]
005bb1c0  str x4,[sp, #0x28]
005bb1c4  mov x3,x30
005bb1c8  bl 0x00093ad0
005bb1cc  ldp x0,x1,[sp, #0x8]
005bb1d0  ldp x2,x3,[sp, #0x18]
005bb1d4  ldr x4,[sp, #0x28]
005bb1d8  b 0x005baf30
