; main.handleManualInputUrl
0075d320  ldr x16,[x28, #0x10]
0075d324  sub x17,sp,#0xb0
0075d328  cmp x17,x16
0075d32c  b.ls 0x0075d764
0075d330  sub x20,sp,#0x130
0075d334  stp x29,x30,[x20, #-0x8]
0075d338  mov sp,x20
0075d33c  sub x29,sp,#0x8
0075d340  str x2,[sp, #0x148]
0075d344  str x1,[sp, #0x140]
0075d348  str x0,[sp, #0x138]
0075d34c  ldr x2,[x0, #0x18]
0075d350  mov x0,x1
0075d354  blr x2
0075d358  str x0,[sp, #0x80]
0075d35c  nop
0075d360  adrp x0,0x9e8000
0075d364  add x0,x0,#0xea
0075d368  orr x1,xzr,#0xc
0075d36c  bl 0x00209720
0075d370  str x0,[sp, #0xa0]
0075d374  str x1,[sp, #0x58]
0075d378  adrp x0,0x8b0000
0075d37c  add x0,x0,#0x5c0
0075d380  bl 0x0002dd40
0075d384  str x0,[sp, #0x98]
0075d388  adrp x1,0x9f0000
0075d38c  add x1,x1,#0xb73
0075d390  orr x2,xzr,#0x10
0075d394  stp x1,x2,[x0]
0075d398  adrp x0,0x969000
0075d39c  add x0,x0,#0x220
0075d3a0  ldr x1,[sp, #0x80]
0075d3a4  ldr x2,[sp, #0xa0]
0075d3a8  ldr x3,[sp, #0x58]
0075d3ac  bl 0x00021200
0075d3b0  orr x1,xzr,#0x1
0075d3b4  stp x1,x1,[x0, #0x8]
0075d3b8  adrp x27,0x147a000
0075d3bc  ldr w1,[x27, #0x910]
0075d3c0  cbnz w1,0x0075d3cc
0075d3c4  ldr x2,[sp, #0x98]
0075d3c8  b 0x0075d3dc
0075d3cc  ldr x1,[x0]
0075d3d0  bl 0x000959d0
0075d3d4  ldr x2,[sp, #0x98]
0075d3d8  stp x2,x1,[x25]
0075d3dc  str x2,[x0]
0075d3e0  ldr x1,[sp, #0x148]
0075d3e4  ldr x0,[x1, #0x10]
0075d3e8  bl 0x001a0640
0075d3ec  mov x1,x0
0075d3f0  adrp x2,0x9d9000
0075d3f4  add x2,x2,#0xf87
0075d3f8  orr x3,xzr,#0x8
0075d3fc  adrp x0,0x973000
0075d400  add x0,x0,#0x360
0075d404  bl 0x00020d00
0075d408  ldp x1,x2,[x0]
0075d40c  cbnz x2,0x0075d41c
0075d410  mov x3,xzr
0075d414  mov x2,xzr
0075d418  b 0x0075d420
0075d41c  ldp x2,x3,[x1]
0075d420  mov x0,x2
0075d424  mov x1,x3
0075d428  bl 0x0075b1c0
0075d42c  str x0,[sp, #0x68]
0075d430  str x1,[sp, #0x30]
0075d434  adrp x27,0x144e000
0075d438  ldr x2,[x27, #0x530]
0075d43c  mov x3,x1
0075d440  mov x1,x2
0075d444  mov x2,x0
0075d448  adrp x0,0x8ed000
0075d44c  add x0,x0,#0xb60
0075d450  bl 0x00020f70
0075d454  tbz w1,#0x0,0x0075d6b8
0075d458  bl 0x0075c3a0
0075d45c  str x0,[sp, #0x78]
0075d460  str x1,[sp, #0x40]
0075d464  ldr x0,[sp, #0x148]
0075d468  ldr x0,[x0, #0x10]
0075d46c  bl 0x001a0640
0075d470  mov x1,x0
0075d474  adrp x2,0x9d9000
0075d478  add x2,x2,#0xf87
0075d47c  orr x3,xzr,#0x8
0075d480  adrp x0,0x973000
0075d484  add x0,x0,#0x360
0075d488  bl 0x00020d00
0075d48c  ldp x0,x1,[x0]
0075d490  cbnz x1,0x0075d4a0
0075d494  mov x3,xzr
0075d498  mov x2,xzr
0075d49c  b 0x0075d4a4
0075d4a0  ldp x2,x3,[x0]
0075d4a4  mov x0,x2
0075d4a8  mov x1,x3
0075d4ac  bl 0x000b89d0
0075d4b0  str x0,[sp, #0x90]
0075d4b4  str x1,[sp, #0x50]
0075d4b8  add x2,sp,#0x108
0075d4bc  stp xzr,xzr,[x2]
0075d4c0  stp xzr,xzr,[x2, #0x10]
0075d4c4  ldr x0,[sp, #0x78]
0075d4c8  ldr x1,[sp, #0x40]
0075d4cc  bl 0x0008bd90
0075d4d0  adrp x2,0x8a6000
0075d4d4  add x2,x2,#0x880
0075d4d8  stp x2,x0,[sp, #0x108]
0075d4dc  ldr x2,[sp, #0x50]
0075d4e0  cmp x2,#0x0
0075d4e4  ldr x3,[sp, #0x30]
0075d4e8  csel x1,x3,x2,eq
0075d4ec  ldr x2,[sp, #0x68]
0075d4f0  ldr x3,[sp, #0x90]
0075d4f4  csel x0,x2,x3,eq
0075d4f8  bl 0x0008bd90
0075d4fc  adrp x2,0x8a6000
0075d500  add x2,x2,#0x880
0075d504  stp x2,x0,[sp, #0x118]
0075d508  adrp x0,0x9fa000
0075d50c  add x0,x0,#0xfc2
0075d510  mov x1,#0x16
0075d514  add x2,sp,#0x108
0075d518  orr x3,xzr,#0x2
0075d51c  mov x4,x3
0075d520  bl 0x001042e0
0075d524  str x0,[sp, #0x70]
0075d528  str x1,[sp, #0x38]
0075d52c  orr x2,xzr,#0x1
0075d530  mov x3,#0x12c
0075d534  bl 0x005592f0
0075d538  cbnz x3,0x0075d688
0075d53c  adrp x27,0x144e000
0075d540  ldr x4,[x27, #0x890]
0075d544  mov x3,x2
0075d548  mov x2,x1
0075d54c  mov x1,x0
0075d550  mov x0,x4
0075d554  bl 0x001229a0
0075d558  mov x2,#0x16
0075d55c  mov x3,x0
0075d560  mov x4,x1
0075d564  mov x0,xzr
0075d568  adrp x1,0x9fa000
0075d56c  add x1,x1,#0xfac
0075d570  bl 0x00076780
0075d574  str x0,[sp, #0x88]
0075d578  str x1,[sp, #0x48]
0075d57c  bl 0x0008c430
0075d580  str x0,[sp, #0x60]
0075d584  mov x1,x0
0075d588  adrp x2,0x9d2000
0075d58c  add x2,x2,#0x10d
0075d590  orr x3,xzr,#0x3
0075d594  adrp x0,0x8ec000
0075d598  add x0,x0,#0xae0
0075d59c  bl 0x00021200
0075d5a0  orr x4,xzr,#0x6
0075d5a4  str x4,[x0, #0x8]
0075d5a8  adrp x27,0x147a000
0075d5ac  ldr w4,[x27, #0x910]
0075d5b0  cbz w4,0x0075d5c0
0075d5b4  ldr x4,[x0]
0075d5b8  bl 0x000959c0
0075d5bc  str x4,[x25]
0075d5c0  adrp x4,0x9d5000
0075d5c4  add x4,x4,#0x82f
0075d5c8  str x4,[x0]
0075d5cc  adrp x0,0x8ec000
0075d5d0  add x0,x0,#0xae0
0075d5d4  ldr x1,[sp, #0x60]
0075d5d8  adrp x2,0x9d2000
0075d5dc  add x2,x2,#0x104
0075d5e0  orr x3,xzr,#0x3
0075d5e4  bl 0x00021200
0075d5e8  ldr x4,[sp, #0x38]
0075d5ec  str x4,[x0, #0x8]
0075d5f0  adrp x27,0x147a000
0075d5f4  ldr w4,[x27, #0x910]
0075d5f8  cbnz w4,0x0075d604
0075d5fc  ldr x5,[sp, #0x70]
0075d600  b 0x0075d614
0075d604  ldr x4,[x0]
0075d608  bl 0x000959d0
0075d60c  ldr x5,[sp, #0x70]
0075d610  stp x5,x4,[x25]
0075d614  str x5,[x0]
0075d618  adrp x0,0x8ec000
0075d61c  add x0,x0,#0xae0
0075d620  ldr x1,[sp, #0x60]
0075d624  adrp x2,0x9d5000
0075d628  add x2,x2,#0x835
0075d62c  orr x3,xzr,#0x6
0075d630  bl 0x00021200
0075d634  ldr x4,[sp, #0x48]
0075d638  str x4,[x0, #0x8]
0075d63c  adrp x27,0x147a000
0075d640  ldr w4,[x27, #0x910]
0075d644  cbnz w4,0x0075d650
0075d648  ldr x4,[sp, #0x88]
0075d64c  b 0x0075d660
0075d650  ldr x3,[x0]
0075d654  bl 0x000959d0
0075d658  ldr x4,[sp, #0x88]
0075d65c  stp x4,x3,[x25]
0075d660  str x4,[x0]
0075d664  ldr x0,[sp, #0x138]
0075d668  cbz x0,0x0075d6e0
0075d66c  ldr x1,[x0, #0x8]
0075d670  adrp x3,0x1432000
0075d674  add x3,x3,#0x2c0
0075d678  ldar x4,[x3]
0075d67c  ldr w5,[x0, #0x10]
0075d680  ldr x6,[x4]
0075d684  b 0x0075d72c
0075d688  ldr x1,[x3, #0x18]
0075d68c  mov x0,x4
0075d690  blr x1
0075d694  mov x2,x0
0075d698  mov x3,x1
0075d69c  mov x4,#0x1f4
0075d6a0  ldr x0,[sp, #0x138]
0075d6a4  ldr x1,[sp, #0x140]
0075d6a8  bl 0x0075b720
0075d6ac  ldp x29,x30,[sp, #-0x8]
0075d6b0  add sp,sp,#0x130
0075d6b4  ret
0075d6b8  ldr x0,[sp, #0x138]
0075d6bc  ldr x1,[sp, #0x140]
0075d6c0  adrp x2,0x9f0000
0075d6c4  add x2,x2,#0xba3
0075d6c8  orr x3,xzr,#0x10
0075d6cc  mov x4,#0x190
0075d6d0  bl 0x0075b720
0075d6d4  ldp x29,x30,[sp, #-0x8]
0075d6d8  add sp,sp,#0x130
0075d6dc  ret
0075d6e0  add x3,sp,#0xa8
0075d6e4  stp xzr,xzr,[x3]
0075d6e8  stp xzr,xzr,[x3, #0x10]
0075d6ec  stp xzr,xzr,[x3, #0x20]
0075d6f0  stp xzr,xzr,[x3, #0x30]
0075d6f4  stp xzr,xzr,[x3, #0x40]
0075d6f8  stp xzr,xzr,[x3, #0x50]
0075d6fc  ldr x4,[sp, #0x140]
0075d700  stp x0,x4,[sp, #0xa8]
0075d704  orr x4,xzr,#0x1
0075d708  strb w4,[sp, #0xc8]
0075d70c  mov x0,x3
0075d710  adrp x1,0x8ec000
0075d714  add x1,x1,#0xae0
0075d718  ldr x2,[sp, #0x60]
0075d71c  bl 0x00134da0
0075d720  ldp x29,x30,[sp, #-0x8]
0075d724  add sp,sp,#0x130
0075d728  ret
0075d72c  and x7,x5,x6
0075d730  lsl x7,x7,#0x4
0075d734  add x7,x7,#0x8
0075d738  ldr x8,[x4, x7#0x0]
0075d73c  add x7,x4,x7
0075d740  cmp x8,x1
0075d744  b.eq 0x0075d75c
0075d748  add x5,x5,#0x1
0075d74c  cbnz x8,0x0075d72c
0075d750  mov x0,x3
0075d754  bl 0x0002a110
0075d758  b 0x0075d6e0
0075d75c  ldr x0,[x7, #0x8]
0075d760  b 0x0075d6e0
0075d764  stp x0,x1,[sp, #0x8]
0075d768  str x2,[sp, #0x18]
0075d76c  mov x3,x30
0075d770  bl 0x00093ad0
0075d774  ldp x0,x1,[sp, #0x8]
0075d778  ldr x2,[sp, #0x18]
0075d77c  b 0x0075d320
