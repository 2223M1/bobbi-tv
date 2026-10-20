; mv-daemon/provider.(*TokenStore).load.deferwrap1
005baeb0  ldr x16,[x28, #0x10]
005baeb4  cmp sp,x16
005baeb8  b.ls 0x005baf18
005baebc  str x30,[sp, #-0x20]!
005baec0  stur x29,[sp, #-0x8]
005baec4  sub x29,sp,#0x8
005baec8  ldr x0,[x26, #0x8]
005baecc  ldrsb x27,[x0]
005baed0  adrp x27,0x1479000
005baed4  ldrb w2,[x27, #0xc55]
005baed8  tbz w2,#0x0,0x005baeec
005baedc  mov x2,#-0x1
005baee0  ldaddal w2,w3,[x0]
005baee4  add x3,x3,x2
005baee8  b 0x005baf00
005baeec  mov x2,#-0x1
005baef0  ldaxr w3,[x0]
005baef4  add x3,x3,x2
005baef8  stlxr w27,w3,[x0]
005baefc  cbnz x27,0x005baef0
005baf00  cbz w3,0x005baf0c
005baf04  mov x1,x3
005baf08  bl 0x0009c9e0
005baf0c  ldur x29,[sp, #-0x8]
005baf10  ldr x30,[sp], #0x20
005baf14  ret
005baf18  mov x3,x30
005baf1c  bl 0x00093a50
005baf20  b 0x005baeb0
