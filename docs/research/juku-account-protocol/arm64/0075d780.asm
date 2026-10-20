; main.handleManualInput
0075d780  ldr x16,[x28, #0x10]
0075d784  sub x17,sp,#0x80
0075d788  cmp x17,x16
0075d78c  b.ls 0x0075dcd0
0075d790  sub x20,sp,#0x100
0075d794  stp x29,x30,[x20, #-0x8]
0075d798  mov sp,x20
0075d79c  sub x29,sp,#0x8
0075d7a0  str x2,[sp, #0x118]
0075d7a4  str x1,[sp, #0x110]
0075d7a8  str x0,[sp, #0x108]
0075d7ac  ldr x2,[x0, #0x18]
0075d7b0  mov x0,x1
0075d7b4  blr x2
0075d7b8  str x0,[sp, #0x58]
0075d7bc  nop
0075d7c0  adrp x0,0x9e8000
0075d7c4  add x0,x0,#0xea
0075d7c8  orr x1,xzr,#0xc
0075d7cc  bl 0x00209720
0075d7d0  str x0,[sp, #0xe8]
0075d7d4  str x1,[sp, #0x40]
0075d7d8  adrp x0,0x8b0000
0075d7dc  add x0,x0,#0x5c0
0075d7e0  bl 0x0002dd40
0075d7e4  str x0,[sp, #0xe0]
0075d7e8  adrp x1,0x9f0000
0075d7ec  add x1,x1,#0xb73
0075d7f0  orr x2,xzr,#0x10
0075d7f4  stp x1,x2,[x0]
0075d7f8  adrp x0,0x969000
0075d7fc  add x0,x0,#0x220
0075d800  ldr x1,[sp, #0x58]
0075d804  ldr x2,[sp, #0xe8]
0075d808  ldr x3,[sp, #0x40]
0075d80c  bl 0x00021200
0075d810  orr x1,xzr,#0x1
0075d814  stp x1,x1,[x0, #0x8]
0075d818  adrp x27,0x147a000
0075d81c  ldr w1,[x27, #0x910]
0075d820  cbnz w1,0x0075d82c
0075d824  ldr x6,[sp, #0xe0]
0075d828  b 0x0075d83c
0075d82c  ldr x5,[x0]
0075d830  bl 0x000959d0
0075d834  ldr x6,[sp, #0xe0]
0075d838  stp x6,x5,[x25]
0075d83c  str x6,[x0]
0075d840  ldr x5,[sp, #0x118]
0075d844  ldp x6,x7,[x5]
0075d848  cmp x7,#0x4
0075d84c  b.ne 0x0075d8a0
0075d850  ldr w6,[x6]
0075d854  mov x7,#0x4f50
0075d858  movk x7,#0x5453, LSL #16
0075d85c  cmp w6,w7
0075d860  b.ne 0x0075d8a0
0075d864  adrp x0,0x905000
0075d868  add x0,x0,#0x3e0
0075d86c  bl 0x0002dd40
0075d870  str x0,[sp, #0xf0]
0075d874  ldr x1,[sp, #0x118]
0075d878  ldp x1,x2,[x1, #0x40]
0075d87c  str x2,[sp, #0x50]
0075d880  cbz x1,0x0075d8c8
0075d884  ldr x3,[x1, #0x8]
0075d888  adrp x4,0x1432000
0075d88c  add x4,x4,#0x2e0
0075d890  ldar x5,[x4]
0075d894  ldr w6,[x1, #0x10]
0075d898  ldr x7,[x5]
0075d89c  b 0x0075dc90
0075d8a0  ldr x0,[sp, #0x108]
0075d8a4  ldr x1,[sp, #0x110]
0075d8a8  adrp x2,0x9f4000
0075d8ac  add x2,x2,#0xa9c
0075d8b0  mov x3,#0x12
0075d8b4  mov x4,#0x195
0075d8b8  bl 0x0075b720
0075d8bc  ldp x29,x30,[sp, #-0x8]
0075d8c0  add sp,sp,#0x100
0075d8c4  ret
0075d8c8  str x1,[sp, #0xe8]
0075d8cc  adrp x0,0x991000
0075d8d0  add x0,x0,#0xb80
0075d8d4  bl 0x0002dd40
0075d8d8  ldr x1,[sp, #0xe8]
0075d8dc  str x1,[x0]
0075d8e0  adrp x27,0x147a000
0075d8e4  ldr w1,[x27, #0x910]
0075d8e8  cbnz w1,0x0075d8f4
0075d8ec  ldr x3,[sp, #0x50]
0075d8f0  b 0x0075d900
0075d8f4  bl 0x000959c0
0075d8f8  ldr x3,[sp, #0x50]
0075d8fc  str x3,[x25]
0075d900  str x3,[x0, #0x8]
0075d904  adrp x1,0x894000
0075d908  add x1,x1,#0x1e0
0075d90c  ldr x2,[sp, #0xf0]
0075d910  bl 0x00134740
0075d914  cbnz x0,0x0075db90
0075d918  ldr x2,[sp, #0xf0]
0075d91c  ldp x0,x1,[x2]
0075d920  bl 0x0075b1c0
0075d924  ldr x2,[sp, #0xf0]
0075d928  str x1,[x2, #0x8]
0075d92c  adrp x27,0x147a000
0075d930  ldr w3,[x27, #0x910]
0075d934  cbz w3,0x0075d944
0075d938  ldr x4,[x2]
0075d93c  bl 0x000959d0
0075d940  stp x0,x4,[x25]
0075d944  str x0,[x2]
0075d948  adrp x27,0x144e000
0075d94c  ldr x4,[x27, #0x530]
0075d950  mov x2,x0
0075d954  mov x3,x1
0075d958  adrp x0,0x8ed000
0075d95c  add x0,x0,#0xb60
0075d960  mov x1,x4
0075d964  bl 0x00020f70
0075d968  tbz w1,#0x0,0x0075db68
0075d96c  ldr x5,[sp, #0xf0]
0075d970  ldp x0,x1,[x5, #0x10]
0075d974  ldp x6,x7,[x5]
0075d978  cmp x7,#0x6
0075d97c  b.ne 0x0075da0c
0075d980  ldr w7,[x6]
0075d984  mov x8,#0x4c41
0075d988  movk x8,#0x5949, LSL #16
0075d98c  cmp w7,w8
0075d990  b.ne 0x0075da0c
0075d994  ldrh w6,[x6, #0x4]
0075d998  mov x7,#0x4e55
0075d99c  cmp w6,w7
0075d9a0  b.ne 0x0075da0c
0075d9a4  str x1,[sp, #0x30]
0075d9a8  str x0,[sp, #0x48]
0075d9ac  nop
0075d9b0  adrp x2,0x9ee000
0075d9b4  add x2,x2,#0xc2e
0075d9b8  orr x3,xzr,#0xf
0075d9bc  bl 0x00021980
0075d9c0  tbnz x0,#0x3f,0x0075d9d0
0075d9c4  ldr x1,[sp, #0x30]
0075d9c8  ldr x0,[sp, #0x48]
0075d9cc  b 0x0075da08
0075d9d0  stp xzr,xzr,[sp, #0xc0]
0075d9d4  ldr x0,[sp, #0x48]
0075d9d8  ldr x1,[sp, #0x30]
0075d9dc  bl 0x0008bd90
0075d9e0  adrp x2,0x8a6000
0075d9e4  add x2,x2,#0x880
0075d9e8  stp x2,x0,[sp, #0xc0]
0075d9ec  adrp x0,0x9f6000
0075d9f0  add x0,x0,#0x5d7
0075d9f4  mov x1,#0x13
0075d9f8  add x2,sp,#0xc0
0075d9fc  orr x3,xzr,#0x1
0075da00  mov x4,x3
0075da04  bl 0x001042e0
0075da08  ldr x5,[sp, #0xf0]
0075da0c  ldp x6,x7,[x5]
0075da10  cmp x7,#0x6
0075da14  b.ne 0x0075dad0
0075da18  ldr w7,[x6]
0075da1c  mov x8,#0x5558
0075da20  movk x8,#0x4c4e, LSL #16
0075da24  cmp w7,w8
0075da28  b.ne 0x0075dad0
0075da2c  ldrh w6,[x6, #0x4]
0075da30  mov x7,#0x4945
0075da34  cmp w6,w7
0075da38  b.ne 0x0075dad0
0075da3c  str x1,[sp, #0x38]
0075da40  str x0,[sp, #0xd8]
0075da44  nop
0075da48  adrp x2,0x9ee000
0075da4c  add x2,x2,#0xc2e
0075da50  orr x3,xzr,#0xf
0075da54  bl 0x00021980
0075da58  tbnz x0,#0x3f,0x0075da68
0075da5c  ldr x1,[sp, #0x38]
0075da60  ldr x0,[sp, #0xd8]
0075da64  b 0x0075dacc
0075da68  nop
0075da6c  ldr x0,[sp, #0xd8]
0075da70  ldr x1,[sp, #0x38]
0075da74  adrp x2,0x9ec000
0075da78  add x2,x2,#0x9e3
0075da7c  orr x3,xzr,#0xe
0075da80  bl 0x00021980
0075da84  tbnz x0,#0x3f,0x0075da94
0075da88  ldr x1,[sp, #0x38]
0075da8c  ldr x0,[sp, #0xd8]
0075da90  b 0x0075dacc
0075da94  stp xzr,xzr,[sp, #0xc0]
0075da98  ldr x0,[sp, #0xd8]
0075da9c  ldr x1,[sp, #0x38]
0075daa0  bl 0x0008bd90
0075daa4  adrp x2,0x8a6000
0075daa8  add x2,x2,#0x880
0075daac  stp x2,x0,[sp, #0xc0]
0075dab0  adrp x0,0x9f6000
0075dab4  add x0,x0,#0x5d7
0075dab8  mov x1,#0x13
0075dabc  add x2,sp,#0xc0
0075dac0  orr x3,xzr,#0x1
0075dac4  mov x4,x3
0075dac8  bl 0x001042e0
0075dacc  ldr x5,[sp, #0xf0]
0075dad0  adrp x27,0x144e000
0075dad4  ldr x6,[x27, #0x510]
0075dad8  cbz x6,0x0075daf8
0075dadc  ldp x5,x2,[x5]
0075dae0  mov x3,x0
0075dae4  mov x4,x1
0075dae8  mov x0,x6
0075daec  mov x1,x5
0075daf0  bl 0x005baf30
0075daf4  cbnz x0,0x0075db1c
0075daf8  ldr x0,[sp, #0x108]
0075dafc  cbz x0,0x0075dbb8
0075db00  ldr x1,[x0, #0x8]
0075db04  adrp x2,0x1432000
0075db08  add x2,x2,#0x300
0075db0c  ldar x3,[x2]
0075db10  ldr w4,[x0, #0x10]
0075db14  ldr x5,[x3]
0075db18  b 0x0075dc58
0075db1c  ldr x2,[x0, #0x18]
0075db20  mov x0,x1
0075db24  blr x2
0075db28  mov x2,#0x16
0075db2c  mov x3,x0
0075db30  mov x4,x1
0075db34  mov x0,xzr
0075db38  adrp x1,0x9fa000
0075db3c  add x1,x1,#0xfd8
0075db40  bl 0x00076780
0075db44  mov x2,x0
0075db48  mov x3,x1
0075db4c  mov x4,#0x1f4
0075db50  ldr x0,[sp, #0x108]
0075db54  ldr x1,[sp, #0x110]
0075db58  bl 0x0075b720
0075db5c  ldp x29,x30,[sp, #-0x8]
0075db60  add sp,sp,#0x100
0075db64  ret
0075db68  ldr x0,[sp, #0x108]
0075db6c  ldr x1,[sp, #0x110]
0075db70  adrp x2,0x9f0000
0075db74  add x2,x2,#0xba3
0075db78  orr x3,xzr,#0x10
0075db7c  mov x4,#0x190
0075db80  bl 0x0075b720
0075db84  ldp x29,x30,[sp, #-0x8]
0075db88  add sp,sp,#0x100
0075db8c  ret
0075db90  ldr x0,[sp, #0x108]
0075db94  ldr x1,[sp, #0x110]
0075db98  adrp x2,0x9e4000
0075db9c  add x2,x2,#0x35a
0075dba0  mov x3,#0xb
0075dba4  mov x4,#0x190
0075dba8  bl 0x0075b720
0075dbac  ldp x29,x30,[sp, #-0x8]
0075dbb0  add sp,sp,#0x100
0075dbb4  ret
0075dbb8  add x1,sp,#0x60
0075dbbc  stp xzr,xzr,[x1]
0075dbc0  stp xzr,xzr,[x1, #0x10]
0075dbc4  stp xzr,xzr,[x1, #0x20]
0075dbc8  stp xzr,xzr,[x1, #0x30]
0075dbcc  stp xzr,xzr,[x1, #0x40]
0075dbd0  stp xzr,xzr,[x1, #0x50]
0075dbd4  ldr x1,[sp, #0x110]
0075dbd8  stp x0,x1,[sp, #0x60]
0075dbdc  orr x0,xzr,#0x1
0075dbe0  strb w0,[sp, #0x80]
0075dbe4  bl 0x0008c430
0075dbe8  str x0,[sp, #0xd0]
0075dbec  mov x1,x0
0075dbf0  adrp x2,0x9d7000
0075dbf4  add x2,x2,#0x39b
0075dbf8  orr x3,xzr,#0x7
0075dbfc  adrp x0,0x8ec000
0075dc00  add x0,x0,#0xbe0
0075dc04  bl 0x00021200
0075dc08  adrp x1,0x8a6000
0075dc0c  add x1,x1,#0xc80
0075dc10  str x1,[x0]
0075dc14  adrp x27,0x147a000
0075dc18  ldr w1,[x27, #0x910]
0075dc1c  cbz w1,0x0075dc2c
0075dc20  ldr x3,[x0, #0x8]
0075dc24  bl 0x000959c0
0075dc28  str x3,[x25]
0075dc2c  adrp x3,0xc32000
0075dc30  add x3,x3,#0x7c8
0075dc34  str x3,[x0, #0x8]
0075dc38  add x0,sp,#0x60
0075dc3c  adrp x1,0x8ec000
0075dc40  add x1,x1,#0xbe0
0075dc44  ldr x2,[sp, #0xd0]
0075dc48  bl 0x00134da0
0075dc4c  ldp x29,x30,[sp, #-0x8]
0075dc50  add sp,sp,#0x100
0075dc54  ret
0075dc58  and x6,x4,x5
0075dc5c  lsl x6,x6,#0x4
0075dc60  add x6,x6,#0x8
0075dc64  ldr x7,[x3, x6#0x0]
0075dc68  add x6,x3,x6
0075dc6c  cmp x7,x1
0075dc70  b.eq 0x0075dc88
0075dc74  add x4,x4,#0x1
0075dc78  cbnz x7,0x0075dc58
0075dc7c  mov x0,x2
0075dc80  bl 0x0002a110
0075dc84  b 0x0075dbb8
0075dc88  ldr x0,[x6, #0x8]
0075dc8c  b 0x0075dbb8
0075dc90  and x8,x6,x7
0075dc94  lsl x8,x8,#0x4
0075dc98  add x8,x8,#0x8
0075dc9c  ldr x9,[x5, x8#0x0]
0075dca0  add x8,x5,x8
0075dca4  cmp x9,x3
0075dca8  b.eq 0x0075dcc8
0075dcac  add x6,x6,#0x1
0075dcb0  cbnz x9,0x0075dc90
0075dcb4  mov x0,x4
0075dcb8  mov x1,x3
0075dcbc  bl 0x0002a110
0075dcc0  mov x1,x0
0075dcc4  b 0x0075d8c8
0075dcc8  ldr x1,[x8, #0x8]
0075dccc  b 0x0075d8c8
0075dcd0  stp x0,x1,[sp, #0x8]
0075dcd4  str x2,[sp, #0x18]
0075dcd8  mov x3,x30
0075dcdc  bl 0x00093ad0
0075dce0  ldp x0,x1,[sp, #0x8]
0075dce4  ldr x2,[sp, #0x18]
0075dce8  b 0x0075d780
