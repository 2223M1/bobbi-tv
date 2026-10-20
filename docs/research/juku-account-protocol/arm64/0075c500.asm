; main.handleManualInputPage
0075c500  ldr x16,[x28, #0x10]
0075c504  cmp sp,x16
0075c508  b.ls 0x0075c600
0075c50c  str x30,[sp, #-0x50]!
0075c510  stur x29,[sp, #-0x8]
0075c514  sub x29,sp,#0x8
0075c518  str x1,[sp, #0x60]
0075c51c  str x0,[sp, #0x58]
0075c520  ldr x2,[x0, #0x18]
0075c524  mov x0,x1
0075c528  blr x2
0075c52c  str x0,[sp, #0x40]
0075c530  nop
0075c534  adrp x0,0x9e8000
0075c538  add x0,x0,#0xea
0075c53c  orr x1,xzr,#0xc
0075c540  bl 0x00209720
0075c544  str x0,[sp, #0x38]
0075c548  str x1,[sp, #0x28]
0075c54c  adrp x0,0x8b0000
0075c550  add x0,x0,#0x5c0
0075c554  bl 0x0002dd40
0075c558  str x0,[sp, #0x30]
0075c55c  adrp x1,0x9fd000
0075c560  add x1,x1,#0xd42
0075c564  orr x2,xzr,#0x18
0075c568  stp x1,x2,[x0]
0075c56c  adrp x0,0x969000
0075c570  add x0,x0,#0x220
0075c574  ldr x1,[sp, #0x40]
0075c578  ldr x2,[sp, #0x38]
0075c57c  ldr x3,[sp, #0x28]
0075c580  bl 0x00021200
0075c584  orr x1,xzr,#0x1
0075c588  stp x1,x1,[x0, #0x8]
0075c58c  adrp x27,0x147a000
0075c590  ldr w1,[x27, #0x910]
0075c594  cbnz w1,0x0075c5a0
0075c598  ldr x4,[sp, #0x30]
0075c59c  b 0x0075c5b0
0075c5a0  ldr x3,[x0]
0075c5a4  bl 0x000959d0
0075c5a8  ldr x4,[sp, #0x30]
0075c5ac  stp x4,x3,[x25]
0075c5b0  str x4,[x0]
0075c5b4  adrp x27,0x142c000
0075c5b8  add x27,x27,#0x20
0075c5bc  ldp x1,x2,[x27]
0075c5c0  mov x0,xzr
0075c5c4  bl 0x00076e90
0075c5c8  ldr x3,[sp, #0x58]
0075c5cc  ldr x3,[x3, #0x20]
0075c5d0  mov x4,x0
0075c5d4  ldr x0,[sp, #0x60]
0075c5d8  mov x5,x1
0075c5dc  mov x1,x4
0075c5e0  mov x6,x2
0075c5e4  mov x2,x5
0075c5e8  mov x7,x3
0075c5ec  mov x3,x6
0075c5f0  blr x7
0075c5f4  ldur x29,[sp, #-0x8]
0075c5f8  ldr x30,[sp], #0x50
0075c5fc  ret
0075c600  stp x0,x1,[sp, #0x8]
0075c604  str x2,[sp, #0x18]
0075c608  mov x3,x30
0075c60c  bl 0x00093ad0
0075c610  ldp x0,x1,[sp, #0x8]
0075c614  ldr x2,[sp, #0x18]
0075c618  b 0x0075c500
