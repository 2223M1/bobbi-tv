; mv-daemon/provider.ClearAll115DirCache.func1
005daf60  ldr x16,[x28, #0x10]
005daf64  cmp sp,x16
005daf68  b.ls 0x005dafb8
005daf6c  str x30,[sp, #-0x30]!
005daf70  stur x29,[sp, #-0x8]
005daf74  sub x29,sp,#0x8
005daf78  str x0,[sp, #0x38]
005daf7c  str x1,[sp, #0x40]
005daf80  adrp x4,0xc2d000
005daf84  add x4,x4,#0xa80
005daf88  nop
005daf8c  nop
005daf90  mov x2,x0
005daf94  mov x3,x1
005daf98  adrp x0,0x1450000
005daf9c  add x0,x0,#0x5c0
005dafa0  mov x1,x4
005dafa4  bl 0x0009f3d0
005dafa8  orr x0,xzr,#0x1
005dafac  ldur x29,[sp, #-0x8]
005dafb0  ldr x30,[sp], #0x30
005dafb4  ret
005dafb8  stp x0,x1,[sp, #0x8]
005dafbc  stp x2,x3,[sp, #0x18]
005dafc0  mov x3,x30
005dafc4  bl 0x00093ad0
005dafc8  ldp x0,x1,[sp, #0x8]
005dafcc  ldp x2,x3,[sp, #0x18]
005dafd0  b 0x005daf60
