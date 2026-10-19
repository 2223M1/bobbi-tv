; mv-daemon/provider.ClearAll115DirCache
00570b20  ldr x16,[x28, #0x10]
00570b24  cmp sp,x16
00570b28  b.ls 0x00570b64
00570b2c  str x30,[sp, #-0x30]!
00570b30  stur x29,[sp, #-0x8]
00570b34  sub x29,sp,#0x8
00570b38  nop
00570b3c  adrp x0,0x1450000
00570b40  add x0,x0,#0x5c0
00570b44  adrp x1,0xc2d000
00570b48  add x1,x1,#0xa80
00570b4c  adrp x2,0xc06000
00570b50  add x2,x2,#0xe70
00570b54  bl 0x0009eb90
00570b58  ldur x29,[sp, #-0x8]
00570b5c  ldr x30,[sp], #0x30
00570b60  ret
00570b64  mov x3,x30
00570b68  bl 0x00093ad0
00570b6c  b 0x00570b20
