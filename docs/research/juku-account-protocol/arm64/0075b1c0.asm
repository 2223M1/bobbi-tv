; main.getRealProvider
0075b1c0  ldr x16,[x28, #0x10]
0075b1c4  cmp sp,x16
0075b1c8  b.ls 0x0075b290
0075b1cc  str x30,[sp, #-0x40]!
0075b1d0  stur x29,[sp, #-0x8]
0075b1d4  sub x29,sp,#0x8
0075b1d8  str x0,[sp, #0x48]
0075b1dc  bl 0x000b89d0
0075b1e0  cbz x1,0x0075b27c
0075b1e4  str x0,[sp, #0x30]
0075b1e8  str x1,[sp, #0x28]
0075b1ec  adrp x27,0x144e000
0075b1f0  ldr x4,[x27, #0x530]
0075b1f4  mov x2,x0
0075b1f8  mov x3,x1
0075b1fc  adrp x0,0x8ed000
0075b200  add x0,x0,#0xb60
0075b204  mov x1,x4
0075b208  bl 0x00020f70
0075b20c  tbnz w1,#0x0,0x0075b268
0075b210  ldr x0,[sp, #0x30]
0075b214  ldr x1,[sp, #0x28]
0075b218  bl 0x000b7d50
0075b21c  adrp x27,0x144e000
0075b220  ldr x2,[x27, #0x528]
0075b224  mov x3,x1
0075b228  mov x1,x2
0075b22c  mov x2,x0
0075b230  adrp x0,0x8ec000
0075b234  add x0,x0,#0xae0
0075b238  bl 0x00020f70
0075b23c  ldp x0,x2,[x0]
0075b240  tbz w1,#0x0,0x0075b254
0075b244  mov x1,x2
0075b248  ldur x29,[sp, #-0x8]
0075b24c  ldr x30,[sp], #0x40
0075b250  ret
0075b254  ldr x0,[sp, #0x30]
0075b258  ldr x1,[sp, #0x28]
0075b25c  ldur x29,[sp, #-0x8]
0075b260  ldr x30,[sp], #0x40
0075b264  ret
0075b268  ldr x0,[sp, #0x30]
0075b26c  ldr x1,[sp, #0x28]
0075b270  ldur x29,[sp, #-0x8]
0075b274  ldr x30,[sp], #0x40
0075b278  ret
0075b27c  mov x0,xzr
0075b280  mov x1,xzr
0075b284  ldur x29,[sp, #-0x8]
0075b288  ldr x30,[sp], #0x40
0075b28c  ret
0075b290  stp x0,x1,[sp, #0x8]
0075b294  mov x3,x30
0075b298  bl 0x00093ad0
0075b29c  ldp x0,x1,[sp, #0x8]
0075b2a0  b 0x0075b1c0
