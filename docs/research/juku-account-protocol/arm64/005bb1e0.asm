; mv-daemon/provider.(*TokenStore).Save.deferwrap1
005bb1e0  ldr x16,[x28, #0x10]
005bb1e4  cmp sp,x16
005bb1e8  b.ls 0x005bb248
005bb1ec  str x30,[sp, #-0x20]!
005bb1f0  stur x29,[sp, #-0x8]
005bb1f4  sub x29,sp,#0x8
005bb1f8  ldr x0,[x26, #0x8]
005bb1fc  ldrsb x27,[x0]
005bb200  adrp x27,0x1479000
005bb204  ldrb w2,[x27, #0xc55]
005bb208  tbz w2,#0x0,0x005bb21c
005bb20c  mov x2,#-0x1
005bb210  ldaddal w2,w3,[x0]
005bb214  add x3,x3,x2
005bb218  b 0x005bb230
005bb21c  mov x2,#-0x1
005bb220  ldaxr w3,[x0]
005bb224  add x3,x3,x2
005bb228  stlxr w27,w3,[x0]
005bb22c  cbnz x27,0x005bb220
005bb230  cbz w3,0x005bb23c
005bb234  mov x1,x3
005bb238  bl 0x0009c9e0
005bb23c  ldur x29,[sp, #-0x8]
005bb240  ldr x30,[sp], #0x20
005bb244  ret
005bb248  mov x3,x30
005bb24c  bl 0x00093a50
005bb250  b 0x005bb1e0
