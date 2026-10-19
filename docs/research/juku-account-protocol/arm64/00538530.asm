; mv-daemon/provider.(*Cloud115Provider).StartQrLoginWithType
00538530  ldr x16,[x28, #0x10]
00538534  sub x17,sp,#0x450
00538538  cmp x17,x16
0053853c  b.ls 0x0053907c
00538540  sub x20,sp,#0x4d0
00538544  stp x29,x30,[x20, #-0x8]
00538548  mov sp,x20
0053854c  sub x29,sp,#0x8
00538550  str x1,[sp, #0x4e0]
00538554  str xzr,[sp, #0x4b8]
00538558  str xzr,[sp, #0x4c0]
0053855c  strb wzr,[sp, #0x57]
00538560  str xzr,[sp, #0xb0]
00538564  stp xzr,xzr,[sp, #0x90]
00538568  mov x0,x1
0053856c  mov x1,x2
00538570  bl 0x00537e10
00538574  str x0,[sp, #0xf0]
00538578  str x1,[sp, #0x80]
0053857c  bl 0x00537b10
00538580  str x0,[sp, #0xb8]
00538584  str x1,[sp, #0x58]
00538588  add x2,sp,#0x188
0053858c  stp xzr,xzr,[x2]
00538590  stp xzr,xzr,[x2, #0x10]
00538594  adrp x27,0x142c000
00538598  add x27,x27,#0x210
0053859c  ldp x0,x1,[x27]
005385a0  bl 0x0008bd90
005385a4  adrp x2,0x8a6000
005385a8  add x2,x2,#0x880
005385ac  stp x2,x0,[sp, #0x188]
005385b0  ldr x0,[sp, #0xf0]
005385b4  ldr x1,[sp, #0x80]
005385b8  bl 0x0008bd90
005385bc  adrp x2,0x8a6000
005385c0  add x2,x2,#0x880
005385c4  stp x2,x0,[sp, #0x198]
005385c8  adrp x0,0x9fc000
005385cc  add x0,x0,#0x8ab
005385d0  mov x1,#0x17
005385d4  add x2,sp,#0x188
005385d8  orr x3,xzr,#0x2
005385dc  mov x4,x3
005385e0  bl 0x001042e0
005385e4  nop
005385e8  adrp x2,0x9d2000
005385ec  add x2,x2,#0x101
005385f0  orr x3,xzr,#0x3
005385f4  mov x4,x0
005385f8  mov x5,x1
005385fc  mov x6,xzr
00538600  mov x7,xzr
00538604  adrp x0,0xc18000
00538608  add x0,x0,#0xa8
0053860c  adrp x1,0x1479000
00538610  add x1,x1,#0xc40
00538614  bl 0x00269cd0
00538618  cbnz x1,0x00538794
0053861c  str x0,[sp, #0xd0]
00538620  add x0,sp,#0x430
00538624  stp xzr,xzr,[x0]
00538628  stp xzr,xzr,[x0, #0x10]
0053862c  stp xzr,xzr,[x0, #0x20]
00538630  add x0,sp,#0x328
00538634  orr x1,xzr,#0x4
00538638  stp xzr,xzr,[x0], #0x10
0053863c  stp xzr,xzr,[x0], #0x10
00538640  stp xzr,xzr,[x0], #0x10
00538644  stp xzr,xzr,[x0], #0x10
00538648  sub x1,x1,#0x1
0053864c  cbnz x1,0x00538638
00538650  str xzr,[x0]
00538654  orr x0,xzr,#-0x7f7f7f7f7f7f7f80
00538658  str x0,[sp, #0x328]
0053865c  add x0,sp,#0x328
00538660  str x0,[sp, #0x440]
00538664  bl 0x0008ef50
00538668  str x0,[sp, #0x438]
0053866c  adrp x0,0x8ec000
00538670  add x0,x0,#0xae0
00538674  add x1,sp,#0x430
00538678  adrp x2,0x9d5000
0053867c  add x2,x2,#0xbdd
00538680  orr x3,xzr,#0x6
00538684  bl 0x00021200
00538688  mov x1,#0x12
0053868c  str x1,[x0, #0x8]
00538690  adrp x27,0x147a000
00538694  ldr w1,[x27, #0x910]
00538698  cbz w1,0x005386a8
0053869c  ldr x4,[x0]
005386a0  bl 0x000959c0
005386a4  str x4,[x25]
005386a8  adrp x4,0x9f4000
005386ac  add x4,x4,#0xeb0
005386b0  str x4,[x0]
005386b4  adrp x0,0x8ec000
005386b8  add x0,x0,#0xae0
005386bc  add x1,sp,#0x430
005386c0  adrp x2,0x9d7000
005386c4  add x2,x2,#0x3cc
005386c8  orr x3,xzr,#0x7
005386cc  bl 0x00021200
005386d0  mov x4,#0x13
005386d4  str x4,[x0, #0x8]
005386d8  adrp x27,0x147a000
005386dc  ldr w4,[x27, #0x910]
005386e0  cbz w4,0x005386f0
005386e4  ldr x4,[x0]
005386e8  bl 0x000959c0
005386ec  str x4,[x25]
005386f0  adrp x4,0x9f6000
005386f4  add x4,x4,#0x896
005386f8  str x4,[x0]
005386fc  ldr x0,[sp, #0xf0]
00538700  ldr x1,[sp, #0x80]
00538704  ldr x2,[sp, #0xb8]
00538708  ldr x3,[sp, #0x58]
0053870c  bl 0x00538200
00538710  str x1,[sp, #0x88]
00538714  str x0,[sp, #0x1b8]
00538718  adrp x0,0x8ec000
0053871c  add x0,x0,#0xae0
00538720  add x1,sp,#0x430
00538724  adrp x2,0x9e1000
00538728  add x2,x2,#0x73b
0053872c  mov x3,#0xa
00538730  bl 0x00021200
00538734  ldr x4,[sp, #0x88]
00538738  str x4,[x0, #0x8]
0053873c  adrp x27,0x147a000
00538740  ldr w4,[x27, #0x910]
00538744  cbnz w4,0x00538750
00538748  ldr x4,[sp, #0x1b8]
0053874c  b 0x00538760
00538750  ldr x3,[x0]
00538754  bl 0x000959d0
00538758  ldr x4,[sp, #0x1b8]
0053875c  stp x4,x3,[x25]
00538760  str x4,[x0]
00538764  add x2,sp,#0x128
00538768  stp xzr,xzr,[x2]
0053876c  stp xzr,xzr,[x2, #0x10]
00538770  stp xzr,xzr,[x2, #0x20]
00538774  stp xzr,xzr,[x2, #0x30]
00538778  stp xzr,xzr,[x2, #0x40]
0053877c  stp xzr,xzr,[x2, #0x50]
00538780  adrp x0,0x8ec000
00538784  add x0,x0,#0xae0
00538788  add x1,sp,#0x430
0053878c  bl 0x0002e450
00538790  b 0x005387b8
00538794  str xzr,[sp, #0xb0]
00538798  stp x1,x2,[sp, #0x90]
0053879c  ldr x0,[sp, #0xb0]
005387a0  ldp x29,x30,[sp, #-0x8]
005387a4  add sp,sp,#0x4d0
005387a8  ret
005387ac  str x2,[x0]
005387b0  add x0,sp,#0x128
005387b4  bl 0x0002e4c0
005387b8  ldr x2,[sp, #0x128]
005387bc  cbz x2,0x00538874
005387c0  ldp x0,x1,[x2]
005387c4  ldr x2,[sp, #0x130]
005387c8  ldp x2,x3,[x2]
005387cc  str x3,[sp, #0x68]
005387d0  str x2,[sp, #0xc8]
005387d4  ldr x2,[sp, #0xd0]
005387d8  ldr x2,[x2, #0x38]
005387dc  str x2,[sp, #0x1b0]
005387e0  nop
005387e4  bl 0x00209720
005387e8  str x0,[sp, #0x1b8]
005387ec  str x1,[sp, #0x88]
005387f0  adrp x0,0x8b0000
005387f4  add x0,x0,#0x5c0
005387f8  bl 0x0002dd40
005387fc  ldr x2,[sp, #0x68]
00538800  str x2,[x0, #0x8]
00538804  adrp x27,0x147a000
00538808  ldr w2,[x27, #0x910]
0053880c  cbnz w2,0x00538818
00538810  ldr x4,[sp, #0xc8]
00538814  b 0x00538824
00538818  bl 0x000959c0
0053881c  ldr x4,[sp, #0xc8]
00538820  str x4,[x25]
00538824  str x0,[sp, #0x1a8]
00538828  str x4,[x0]
0053882c  adrp x0,0x969000
00538830  add x0,x0,#0x220
00538834  ldr x1,[sp, #0x1b0]
00538838  ldr x2,[sp, #0x1b8]
0053883c  ldr x3,[sp, #0x88]
00538840  bl 0x00021200
00538844  orr x4,xzr,#0x1
00538848  stp x4,x4,[x0, #0x8]
0053884c  adrp x27,0x147a000
00538850  ldr w4,[x27, #0x910]
00538854  cbnz w4,0x00538860
00538858  ldr x2,[sp, #0x1a8]
0053885c  b 0x005387ac
00538860  ldr x1,[x0]
00538864  bl 0x000959d0
00538868  ldr x2,[sp, #0x1a8]
0053886c  stp x2,x1,[x25]
00538870  b 0x005387ac
00538874  adrp x27,0x142b000
00538878  ldr x0,[x27, #0x120]
0053887c  ldr x1,[sp, #0xd0]
00538880  bl 0x00232f70
00538884  cbnz x1,0x005388f4
00538888  str x0,[sp, #0xa8]
0053888c  ldp x1,x2,[x0, #0x40]
00538890  ldrsb x27,[x1]
00538894  adrp x3,0x539000
00538898  add x3,x3,#0xe0
0053889c  str x3,[sp, #0x310]
005388a0  str x1,[sp, #0x318]
005388a4  str x2,[sp, #0x320]
005388a8  add x1,sp,#0x310
005388ac  str x1,[sp, #0x4b8]
005388b0  orr x1,xzr,#0x1
005388b4  strb w1,[sp, #0x57]
005388b8  adrp x0,0x909000
005388bc  add x0,x0,#0xfe0
005388c0  bl 0x0002dd40
005388c4  str x0,[sp, #0x4b0]
005388c8  ldr x1,[sp, #0xa8]
005388cc  ldp x1,x2,[x1, #0x40]
005388d0  str x2,[sp, #0xd8]
005388d4  cbz x1,0x0053890c
005388d8  ldr x3,[x1, #0x8]
005388dc  adrp x4,0x1434000
005388e0  add x4,x4,#0xa20
005388e4  ldar x5,[x4]
005388e8  ldr w6,[x1, #0x10]
005388ec  ldr x7,[x5]
005388f0  b 0x00539020
005388f4  str xzr,[sp, #0xb0]
005388f8  stp x1,x2,[sp, #0x90]
005388fc  ldr x0,[sp, #0xb0]
00538900  ldp x29,x30,[sp, #-0x8]
00538904  add sp,sp,#0x4d0
00538908  ret
0053890c  str x1,[sp, #0x1b8]
00538910  adrp x0,0x991000
00538914  add x0,x0,#0xb80
00538918  bl 0x0002dd40
0053891c  ldr x1,[sp, #0x1b8]
00538920  str x1,[x0]
00538924  adrp x27,0x147a000
00538928  ldr w1,[x27, #0x910]
0053892c  cbnz w1,0x00538938
00538930  ldr x3,[sp, #0xd8]
00538934  b 0x00538944
00538938  bl 0x000959c0
0053893c  ldr x3,[sp, #0xd8]
00538940  str x3,[x25]
00538944  str x3,[x0, #0x8]
00538948  adrp x1,0x899000
0053894c  add x1,x1,#0xee0
00538950  ldr x2,[sp, #0x4b0]
00538954  bl 0x00134740
00538958  cbnz x0,0x00538c00
0053895c  ldr x2,[sp, #0x4b0]
00538960  ldr x3,[x2]
00538964  cmp x3,#0x1
00538968  b.ne 0x00538bb0
0053896c  ldp x2,x3,[x2, #0x30]
00538970  str x3,[sp, #0x70]
00538974  str x2,[sp, #0xe0]
00538978  add x2,sp,#0xf8
0053897c  stp xzr,xzr,[x2]
00538980  stp xzr,xzr,[x2, #0x10]
00538984  stp xzr,xzr,[x2, #0x20]
00538988  adrp x27,0x142c000
0053898c  add x27,x27,#0x210
00538990  ldp x0,x1,[x27]
00538994  bl 0x0008bd90
00538998  adrp x2,0x8a6000
0053899c  add x2,x2,#0x880
005389a0  stp x2,x0,[sp, #0xf8]
005389a4  ldr x0,[sp, #0xf0]
005389a8  ldr x1,[sp, #0x80]
005389ac  bl 0x0008bd90
005389b0  adrp x2,0x8a6000
005389b4  add x2,x2,#0x880
005389b8  stp x2,x0,[sp, #0x108]
005389bc  ldr x2,[sp, #0x4b0]
005389c0  ldp x0,x1,[x2, #0x8]
005389c4  bl 0x0008bd90
005389c8  adrp x2,0x8a6000
005389cc  add x2,x2,#0x880
005389d0  stp x2,x0,[sp, #0x118]
005389d4  adrp x0,0xa07000
005389d8  add x0,x0,#0x372
005389dc  orr x1,xzr,#0x1f
005389e0  add x2,sp,#0xf8
005389e4  orr x3,xzr,#0x3
005389e8  mov x4,x3
005389ec  bl 0x001042e0
005389f0  nop
005389f4  adrp x2,0x9d2000
005389f8  add x2,x2,#0x101
005389fc  orr x3,xzr,#0x3
00538a00  mov x4,x0
00538a04  mov x5,x1
00538a08  mov x6,xzr
00538a0c  mov x7,xzr
00538a10  adrp x0,0xc18000
00538a14  add x0,x0,#0xa8
00538a18  adrp x1,0x1479000
00538a1c  add x1,x1,#0xc40
00538a20  bl 0x00269cd0
00538a24  cbnz x1,0x00538ba0
00538a28  str x0,[sp, #0xa0]
00538a2c  add x0,sp,#0x2e0
00538a30  stp xzr,xzr,[x0]
00538a34  stp xzr,xzr,[x0, #0x10]
00538a38  stp xzr,xzr,[x0, #0x20]
00538a3c  add x0,sp,#0x1d8
00538a40  orr x1,xzr,#0x4
00538a44  stp xzr,xzr,[x0], #0x10
00538a48  stp xzr,xzr,[x0], #0x10
00538a4c  stp xzr,xzr,[x0], #0x10
00538a50  stp xzr,xzr,[x0], #0x10
00538a54  sub x1,x1,#0x1
00538a58  cbnz x1,0x00538a44
00538a5c  str xzr,[x0]
00538a60  orr x0,xzr,#-0x7f7f7f7f7f7f7f80
00538a64  str x0,[sp, #0x1d8]
00538a68  add x0,sp,#0x1d8
00538a6c  str x0,[sp, #0x2f0]
00538a70  bl 0x0008ef50
00538a74  str x0,[sp, #0x2e8]
00538a78  adrp x0,0x8ec000
00538a7c  add x0,x0,#0xae0
00538a80  add x1,sp,#0x2e0
00538a84  adrp x2,0x9d5000
00538a88  add x2,x2,#0xbdd
00538a8c  orr x3,xzr,#0x6
00538a90  bl 0x00021200
00538a94  mov x1,#0x12
00538a98  str x1,[x0, #0x8]
00538a9c  adrp x27,0x147a000
00538aa0  ldr w1,[x27, #0x910]
00538aa4  cbz w1,0x00538ab4
00538aa8  ldr x4,[x0]
00538aac  bl 0x000959c0
00538ab0  str x4,[x25]
00538ab4  adrp x4,0x9f4000
00538ab8  add x4,x4,#0xeb0
00538abc  str x4,[x0]
00538ac0  adrp x0,0x8ec000
00538ac4  add x0,x0,#0xae0
00538ac8  add x1,sp,#0x2e0
00538acc  adrp x2,0x9d7000
00538ad0  add x2,x2,#0x3cc
00538ad4  orr x3,xzr,#0x7
00538ad8  bl 0x00021200
00538adc  mov x4,#0x13
00538ae0  str x4,[x0, #0x8]
00538ae4  adrp x27,0x147a000
00538ae8  ldr w4,[x27, #0x910]
00538aec  cbz w4,0x00538afc
00538af0  ldr x4,[x0]
00538af4  bl 0x000959c0
00538af8  str x4,[x25]
00538afc  adrp x4,0x9f6000
00538b00  add x4,x4,#0x896
00538b04  str x4,[x0]
00538b08  ldr x0,[sp, #0xf0]
00538b0c  ldr x1,[sp, #0x80]
00538b10  ldr x2,[sp, #0xb8]
00538b14  ldr x3,[sp, #0x58]
00538b18  bl 0x00538200
00538b1c  str x1,[sp, #0x88]
00538b20  str x0,[sp, #0x1b8]
00538b24  adrp x0,0x8ec000
00538b28  add x0,x0,#0xae0
00538b2c  add x1,sp,#0x2e0
00538b30  adrp x2,0x9e1000
00538b34  add x2,x2,#0x73b
00538b38  mov x3,#0xa
00538b3c  bl 0x00021200
00538b40  ldr x4,[sp, #0x88]
00538b44  str x4,[x0, #0x8]
00538b48  adrp x27,0x147a000
00538b4c  ldr w4,[x27, #0x910]
00538b50  cbnz w4,0x00538b5c
00538b54  ldr x4,[sp, #0x1b8]
00538b58  b 0x00538b6c
00538b5c  ldr x3,[x0]
00538b60  bl 0x000959d0
00538b64  ldr x4,[sp, #0x1b8]
00538b68  stp x4,x3,[x25]
00538b6c  str x4,[x0]
00538b70  add x2,sp,#0x128
00538b74  stp xzr,xzr,[x2]
00538b78  stp xzr,xzr,[x2, #0x10]
00538b7c  stp xzr,xzr,[x2, #0x20]
00538b80  stp xzr,xzr,[x2, #0x30]
00538b84  stp xzr,xzr,[x2, #0x40]
00538b88  stp xzr,xzr,[x2, #0x50]
00538b8c  adrp x0,0x8ec000
00538b90  add x0,x0,#0xae0
00538b94  add x1,sp,#0x2e0
00538b98  bl 0x0002e450
00538b9c  b 0x00538dd0
00538ba0  orr x0,xzr,#0x1
00538ba4  ldr x1,[sp, #0xe0]
00538ba8  ldr x2,[sp, #0x70]
00538bac  b 0x00538c2c
00538bb0  adrp x0,0x8f8000
00538bb4  add x0,x0,#0x5a0
00538bb8  bl 0x0002dd40
00538bbc  adrp x1,0xa00000
00538bc0  add x1,x1,#0x9fa
00538bc4  mov x2,#0x1a
00538bc8  stp x1,x2,[x0]
00538bcc  str xzr,[sp, #0xb0]
00538bd0  adrp x1,0xc11000
00538bd4  add x1,x1,#0xa38
00538bd8  stp x1,x0,[sp, #0x90]
00538bdc  strb wzr,[sp, #0x57]
00538be0  ldr x26,[sp, #0x4b8]
00538be4  ldr x1,[x26]
00538be8  blr x1
00538bec  ldp x1,x2,[sp, #0x90]
00538bf0  ldr x0,[sp, #0xb0]
00538bf4  ldp x29,x30,[sp, #-0x8]
00538bf8  add sp,sp,#0x4d0
00538bfc  ret
00538c00  str xzr,[sp, #0xb0]
00538c04  stp x0,x1,[sp, #0x90]
00538c08  strb wzr,[sp, #0x57]
00538c0c  ldr x26,[sp, #0x4b8]
00538c10  ldr x0,[x26]
00538c14  blr x0
00538c18  ldp x1,x2,[sp, #0x90]
00538c1c  ldr x0,[sp, #0xb0]
00538c20  ldp x29,x30,[sp, #-0x8]
00538c24  add sp,sp,#0x4d0
00538c28  ret
00538c2c  strb w0,[sp, #0x56]
00538c30  str x1,[sp, #0xe0]
00538c34  str x2,[sp, #0x70]
00538c38  add x2,sp,#0x460
00538c3c  stp xzr,xzr,[x2]
00538c40  stp xzr,xzr,[x2, #0x10]
00538c44  stp xzr,xzr,[x2, #0x20]
00538c48  stp xzr,xzr,[x2, #0x30]
00538c4c  stp xzr,xzr,[x2, #0x40]
00538c50  ldr x2,[sp, #0x4b0]
00538c54  ldp x0,x1,[x2, #0x8]
00538c58  bl 0x0008bd90
00538c5c  adrp x2,0x8a6000
00538c60  add x2,x2,#0x880
00538c64  add x27,sp,#0x460
00538c68  stp x2,x0,[x27]
00538c6c  ldr x2,[sp, #0x4b0]
00538c70  ldp x0,x1,[x2, #0x20]
00538c74  bl 0x0008bd90
00538c78  adrp x2,0x8a6000
00538c7c  add x2,x2,#0x880
00538c80  add x27,sp,#0x470
00538c84  stp x2,x0,[x27]
00538c88  ldr x2,[sp, #0x4b0]
00538c8c  ldr x0,[x2, #0x18]
00538c90  bl 0x0008bd10
00538c94  adrp x2,0x8a6000
00538c98  add x2,x2,#0xa40
00538c9c  add x27,sp,#0x480
00538ca0  stp x2,x0,[x27]
00538ca4  ldr x0,[sp, #0xb8]
00538ca8  ldr x1,[sp, #0x58]
00538cac  bl 0x0008bd90
00538cb0  adrp x2,0x8a6000
00538cb4  add x2,x2,#0x880
00538cb8  add x27,sp,#0x490
00538cbc  stp x2,x0,[x27]
00538cc0  ldr x0,[sp, #0xf0]
00538cc4  ldr x1,[sp, #0x80]
00538cc8  bl 0x0008bd90
00538ccc  adrp x2,0x8a6000
00538cd0  add x2,x2,#0x880
00538cd4  add x27,sp,#0x4a0
00538cd8  stp x2,x0,[x27]
00538cdc  adrp x0,0x9ec000
00538ce0  add x0,x0,#0xd01
00538ce4  orr x1,xzr,#0xe
00538ce8  add x2,sp,#0x460
00538cec  mov x3,#0x5
00538cf0  mov x4,x3
00538cf4  bl 0x001042e0
00538cf8  str x1,[sp, #0x78]
00538cfc  str x0,[sp, #0xe8]
00538d00  adrp x0,0x941000
00538d04  add x0,x0,#0x60
00538d08  bl 0x0002dd40
00538d0c  ldr x2,[sp, #0x78]
00538d10  str x2,[x0, #0x28]
00538d14  adrp x27,0x147a000
00538d18  ldr w2,[x27, #0x910]
00538d1c  cbnz w2,0x00538d2c
00538d20  ldr x3,[sp, #0xe8]
00538d24  ldr x4,[sp, #0xe0]
00538d28  b 0x00538d3c
00538d2c  bl 0x000959d0
00538d30  ldr x3,[sp, #0xe8]
00538d34  ldr x4,[sp, #0xe0]
00538d38  stp x3,x4,[x25]
00538d3c  str x3,[x0, #0x20]
00538d40  ldr x3,[sp, #0x70]
00538d44  stp x4,x3,[x0, #0x10]
00538d48  ldr x3,[sp, #0x4b0]
00538d4c  ldp x3,x4,[x3, #0x30]
00538d50  str x4,[x0, #0x8]
00538d54  adrp x27,0x147a000
00538d58  ldr w4,[x27, #0x910]
00538d5c  cbz w4,0x00538d68
00538d60  bl 0x000959c0
00538d64  str x3,[x25]
00538d68  str x3,[x0]
00538d6c  str x0,[sp, #0xb0]
00538d70  stp xzr,xzr,[sp, #0x90]
00538d74  ldrb w0,[sp, #0x56]
00538d78  tbz w0,#0x1,0x00538d98
00538d7c  and x0,x0,#-0x3
00538d80  strb w0,[sp, #0x56]
00538d84  strb w0,[sp, #0x57]
00538d88  ldr x26,[sp, #0x4c0]
00538d8c  ldr x0,[x26]
00538d90  blr x0
00538d94  ldrb w0,[sp, #0x56]
00538d98  tbz w0,#0x0,0x00538db0
00538d9c  and x0,x0,#-0x2
00538da0  strb w0,[sp, #0x57]
00538da4  ldr x26,[sp, #0x4b8]
00538da8  ldr x0,[x26]
00538dac  blr x0
00538db0  ldp x1,x2,[sp, #0x90]
00538db4  ldr x0,[sp, #0xb0]
00538db8  ldp x29,x30,[sp, #-0x8]
00538dbc  add sp,sp,#0x4d0
00538dc0  ret
00538dc4  str x2,[x0]
00538dc8  add x0,sp,#0x128
00538dcc  bl 0x0002e4c0
00538dd0  ldr x2,[sp, #0x128]
00538dd4  cbz x2,0x00538e8c
00538dd8  ldp x0,x1,[x2]
00538ddc  ldr x2,[sp, #0x130]
00538de0  ldp x2,x3,[x2]
00538de4  str x3,[sp, #0x60]
00538de8  str x2,[sp, #0xc0]
00538dec  ldr x2,[sp, #0xa0]
00538df0  ldr x2,[x2, #0x38]
00538df4  str x2,[sp, #0x1b0]
00538df8  nop
00538dfc  bl 0x00209720
00538e00  str x0,[sp, #0x1b8]
00538e04  str x1,[sp, #0x88]
00538e08  adrp x0,0x8b0000
00538e0c  add x0,x0,#0x5c0
00538e10  bl 0x0002dd40
00538e14  ldr x2,[sp, #0x60]
00538e18  str x2,[x0, #0x8]
00538e1c  adrp x27,0x147a000
00538e20  ldr w2,[x27, #0x910]
00538e24  cbnz w2,0x00538e30
00538e28  ldr x4,[sp, #0xc0]
00538e2c  b 0x00538e3c
00538e30  bl 0x000959c0
00538e34  ldr x4,[sp, #0xc0]
00538e38  str x4,[x25]
00538e3c  str x0,[sp, #0x1a8]
00538e40  str x4,[x0]
00538e44  adrp x0,0x969000
00538e48  add x0,x0,#0x220
00538e4c  ldr x1,[sp, #0x1b0]
00538e50  ldr x2,[sp, #0x1b8]
00538e54  ldr x3,[sp, #0x88]
00538e58  bl 0x00021200
00538e5c  orr x4,xzr,#0x1
00538e60  stp x4,x4,[x0, #0x8]
00538e64  adrp x27,0x147a000
00538e68  ldr w4,[x27, #0x910]
00538e6c  cbnz w4,0x00538e78
00538e70  ldr x2,[sp, #0x1a8]
00538e74  b 0x00538dc4
00538e78  ldr x1,[x0]
00538e7c  bl 0x000959d0
00538e80  ldr x2,[sp, #0x1a8]
00538e84  stp x2,x1,[x25]
00538e88  b 0x00538dc4
00538e8c  adrp x27,0x142b000
00538e90  ldr x0,[x27, #0x120]
00538e94  ldr x1,[sp, #0xa0]
00538e98  bl 0x00232f70
00538e9c  cbnz x1,0x00538ef0
00538ea0  ldp x2,x3,[x0, #0x40]
00538ea4  ldrsb x27,[x2]
00538ea8  adrp x4,0x539000
00538eac  add x4,x4,#0xa0
00538eb0  str x4,[sp, #0x1c0]
00538eb4  str x2,[sp, #0x1c8]
00538eb8  str x3,[sp, #0x1d0]
00538ebc  add x2,sp,#0x1c0
00538ec0  str x2,[sp, #0x4c0]
00538ec4  orr x2,xzr,#0x3
00538ec8  strb w2,[sp, #0x57]
00538ecc  ldp x2,x1,[x0, #0x40]
00538ed0  cbz x2,0x00538f0c
00538ed4  ldr x3,[x2, #0x8]
00538ed8  adrp x0,0x1434000
00538edc  add x0,x0,#0xa40
00538ee0  ldar x4,[x0]
00538ee4  ldr w2,[x2, #0x10]
00538ee8  ldr x5,[x4]
00538eec  b 0x00538fdc
00538ef0  orr x0,xzr,#0x1
00538ef4  ldr x1,[sp, #0x70]
00538ef8  ldr x2,[sp, #0xe0]
00538efc  mov x3,x1
00538f00  mov x1,x2
00538f04  mov x2,x3
00538f08  b 0x00538c2c
00538f0c  mov x0,x2
00538f10  bl 0x000a27d0
00538f14  cbz x3,0x00538f24
00538f18  ldr x1,[sp, #0x70]
00538f1c  ldr x0,[sp, #0xe0]
00538f20  b 0x00538fd0
00538f24  cmp x1,#0x8
00538f28  b.le 0x00538fc8
00538f2c  ldrb w4,[x0]
00538f30  cmp w4,#0x89
00538f34  b.ne 0x00538fbc
00538f38  ldrb w4,[x0, #0x1]
00538f3c  cmp w4,#0x50
00538f40  b.ne 0x00538fb0
00538f44  ldrb w4,[x0, #0x2]
00538f48  cmp w4,#0x4e
00538f4c  b.ne 0x00538fa4
00538f50  ldrb w4,[x0, #0x3]
00538f54  cmp w4,#0x47
00538f58  b.eq 0x00538f68
00538f5c  ldr x1,[sp, #0x70]
00538f60  ldr x0,[sp, #0xe0]
00538f64  b 0x00538fd0
00538f68  adrp x27,0x144e000
00538f6c  ldr x4,[x27, #0x890]
00538f70  mov x3,x2
00538f74  mov x2,x1
00538f78  mov x1,x0
00538f7c  mov x0,x4
00538f80  bl 0x001229a0
00538f84  mov x2,#0x16
00538f88  mov x3,x0
00538f8c  mov x4,x1
00538f90  mov x0,xzr
00538f94  adrp x1,0x9fa000
00538f98  add x1,x1,#0xfac
00538f9c  bl 0x00076780
00538fa0  b 0x00538fd0
00538fa4  ldr x1,[sp, #0x70]
00538fa8  ldr x0,[sp, #0xe0]
00538fac  b 0x00538fd0
00538fb0  ldr x1,[sp, #0x70]
00538fb4  ldr x0,[sp, #0xe0]
00538fb8  b 0x00538fd0
00538fbc  ldr x1,[sp, #0x70]
00538fc0  ldr x0,[sp, #0xe0]
00538fc4  b 0x00538fd0
00538fc8  ldr x1,[sp, #0x70]
00538fcc  ldr x0,[sp, #0xe0]
00538fd0  mov x2,x0
00538fd4  orr x0,xzr,#0x3
00538fd8  b 0x00538efc
00538fdc  and x6,x2,x5
00538fe0  lsl x6,x6,#0x4
00538fe4  add x6,x6,#0x8
00538fe8  ldr x7,[x4, x6#0x0]
00538fec  add x6,x4,x6
00538ff0  cmp x7,x3
00538ff4  b.eq 0x00539018
00538ff8  add x2,x2,#0x1
00538ffc  cbnz x7,0x00538fdc
00539000  str x1,[sp, #0x1b8]
00539004  mov x1,x3
00539008  bl 0x0002a110
0053900c  ldr x1,[sp, #0x1b8]
00539010  mov x2,x0
00539014  b 0x00538f0c
00539018  ldr x2,[x6, #0x8]
0053901c  b 0x00538f0c
00539020  and x8,x6,x7
00539024  lsl x8,x8,#0x4
00539028  add x8,x8,#0x8
0053902c  ldr x9,[x5, x8#0x0]
00539030  add x8,x5,x8
00539034  cmp x9,x3
00539038  b.eq 0x00539058
0053903c  add x6,x6,#0x1
00539040  cbnz x9,0x00539020
00539044  mov x0,x4
00539048  mov x1,x3
0053904c  bl 0x0002a110
00539050  mov x1,x0
00539054  b 0x0053890c
00539058  ldr x1,[x8, #0x8]
0053905c  b 0x0053890c
0053907c  stp x0,x1,[sp, #0x8]
00539080  str x2,[sp, #0x18]
00539084  mov x3,x30
00539088  bl 0x00093ad0
0053908c  ldp x0,x1,[sp, #0x8]
00539090  ldr x2,[sp, #0x18]
00539094  b 0x00538530
