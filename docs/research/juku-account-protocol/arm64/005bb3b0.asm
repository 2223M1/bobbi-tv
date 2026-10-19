; mv-daemon/provider.(*TokenStore).Get.deferwrap1
005bb3b0  ldr x16,[x28, #0x10]
005bb3b4  cmp sp,x16
005bb3b8  b.ls 0x005bb418
005bb3bc  str x30,[sp, #-0x20]!
005bb3c0  stur x29,[sp, #-0x8]
005bb3c4  sub x29,sp,#0x8
005bb3c8  ldr x0,[x26, #0x8]
005bb3cc  ldrsb x27,[x0]
005bb3d0  adrp x27,0x1479000
005bb3d4  ldrb w2,[x27, #0xc55]
005bb3d8  tbz w2,#0x0,0x005bb3ec
005bb3dc  mov x2,#-0x1
005bb3e0  ldaddal w2,w3,[x0]
005bb3e4  add x3,x3,x2
005bb3e8  b 0x005bb400
005bb3ec  mov x2,#-0x1
005bb3f0  ldaxr w3,[x0]
005bb3f4  add x3,x3,x2
005bb3f8  stlxr w27,w3,[x0]
005bb3fc  cbnz x27,0x005bb3f0
005bb400  cbz w3,0x005bb40c
005bb404  mov x1,x3
005bb408  bl 0x0009c9e0
005bb40c  ldur x29,[sp, #-0x8]
005bb410  ldr x30,[sp], #0x20
005bb414  ret
005bb418  mov x3,x30
005bb41c  bl 0x00093a50
005bb420  b 0x005bb3b0
