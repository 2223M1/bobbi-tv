; main.handlePlay
00c4bea0  LEA R12,[RSP + -0x2e0]
00c4bea8  CMP R12,qword ptr [R14 + 0x10]
00c4beac  JBE 0x00c4d285
00c4beb2  PUSH RBP
00c4beb3  MOV RBP,RSP
00c4beb6  SUB RSP,0x358
00c4bebd  MOV qword ptr [RSP + 0x378],RCX
00c4bec5  MOV qword ptr [RSP + 0x370],RBX
00c4becd  MOV qword ptr [RSP + 0x368],RAX
00c4bed5  MOV RCX,qword ptr [RAX + 0x18]
00c4bed9  MOV RAX,RBX
00c4bedc  CALL RCX
00c4bede  MOV qword ptr [RSP + 0x190],RAX
00c4bee6  NOP
00c4bee7  LEA RAX,[0xf10b4b]
00c4beee  MOV EBX,0xc
00c4bef3  CALL 0x00640c00
00c4bef8  MOV qword ptr [RSP + 0x1e0],RAX
00c4bf00  MOV qword ptr [RSP + 0x120],RBX
00c4bf08  LEA RAX,[0xddc380]
00c4bf0f  CALL 0x00421f00
00c4bf14  MOV qword ptr [RSP + 0x1d8],RAX
00c4bf1c  MOV qword ptr [RAX + 0x8],0x10
00c4bf24  LEA RCX,[0xf195fc]
00c4bf2b  MOV qword ptr [RAX],RCX
00c4bf2e  LEA RAX,[0xe91b20]
00c4bf35  MOV RBX,qword ptr [RSP + 0x190]
00c4bf3d  MOV RCX,qword ptr [RSP + 0x1e0]
00c4bf45  MOV RDI,qword ptr [RSP + 0x120]
00c4bf4d  CALL 0x00413460
00c4bf52  MOV qword ptr [RAX + 0x8],0x1
00c4bf5a  MOV qword ptr [RAX + 0x10],0x1
00c4bf62  CMP dword ptr [0x019b5f00],0x0
00c4bf69  JNZ 0x00c4bf75
00c4bf6b  MOV RDX,qword ptr [RSP + 0x1d8]
00c4bf73  JMP 0x00c4bf8c
00c4bf75  MOV RCX,qword ptr [RAX]
00c4bf78  CALL 0x0048bc00
00c4bf7d  MOV RDX,qword ptr [RSP + 0x1d8]
00c4bf85  MOV qword ptr [R11],RDX
00c4bf88  MOV qword ptr [R11 + 0x8],RCX
00c4bf8c  MOV qword ptr [RAX],RDX
00c4bf8f  MOV RAX,qword ptr [RSP + 0x378]
00c4bf97  CALL 0x00c4bd40
00c4bf9c  MOV qword ptr [RSP + 0x150],RAX
00c4bfa4  MOV qword ptr [RSP + 0x90],RBX
00c4bfac  MOV RAX,qword ptr [0x0196cdc0]
00c4bfb3  CALL 0x00aa6620
00c4bfb8  MOV RCX,qword ptr [RSP + 0x378]
00c4bfc0  MOV RAX,qword ptr [RCX + 0x10]
00c4bfc4  CALL 0x005bb0e0
00c4bfc9  MOV RBX,RAX
00c4bfcc  LEA RCX,[0xf05a08]
00c4bfd3  MOV EDI,0x9
00c4bfd8  LEA RAX,[0xe9bd40]
00c4bfdf  NOP
00c4bfe0  CALL 0x00412ee0
00c4bfe5  CMP qword ptr [RAX + 0x8],0x0
00c4bfea  JNZ 0x00c4bff2
00c4bfec  XOR EDX,EDX
00c4bfee  XOR ECX,ECX
00c4bff0  JMP 0x00c4bffc
00c4bff2  MOV RCX,qword ptr [RAX]
00c4bff5  MOV RDX,qword ptr [RCX + 0x8]
00c4bff9  MOV RCX,qword ptr [RCX]
00c4bffc  MOV qword ptr [RSP + 0x80],RDX
00c4c004  MOV qword ptr [RSP + 0x148],RCX
00c4c00c  MOV RCX,qword ptr [RSP + 0x378]
00c4c014  MOV RAX,qword ptr [RCX + 0x10]
00c4c018  CALL 0x005bb0e0
00c4c01d  MOV RBX,RAX
00c4c020  LEA RCX,[0xefb56f]
00c4c027  MOV EDI,0x4
00c4c02c  LEA RAX,[0xe9bd40]
00c4c033  CALL 0x00412ee0
00c4c038  CMP qword ptr [RAX + 0x8],0x0
00c4c03d  JNZ 0x00c4c045
00c4c03f  XOR EDX,EDX
00c4c041  XOR ECX,ECX
00c4c043  JMP 0x00c4c04f
00c4c045  MOV RCX,qword ptr [RAX]
00c4c048  MOV RDX,qword ptr [RCX + 0x8]
00c4c04c  MOV RCX,qword ptr [RCX]
00c4c04f  MOV qword ptr [RSP + 0x140],RCX
00c4c057  MOV qword ptr [RSP + 0x78],RDX
00c4c05c  MOV RCX,qword ptr [RSP + 0x378]
00c4c064  MOV RAX,qword ptr [RCX + 0x10]
00c4c068  CALL 0x005bb0e0
00c4c06d  MOV RBX,RAX
00c4c070  LEA RCX,[0xeffe2d]
00c4c077  MOV EDI,0x7
00c4c07c  LEA RAX,[0xe9bd40]
00c4c083  CALL 0x00412ee0
00c4c088  CMP qword ptr [RAX + 0x8],0x0
00c4c08d  JNZ 0x00c4c095
00c4c08f  XOR EDX,EDX
00c4c091  XOR ECX,ECX
00c4c093  JMP 0x00c4c09f
00c4c095  MOV RCX,qword ptr [RAX]
00c4c098  MOV RDX,qword ptr [RCX + 0x8]
00c4c09c  MOV RCX,qword ptr [RCX]
00c4c09f  MOV qword ptr [RSP + 0x70],RDX
00c4c0a4  MOV qword ptr [RSP + 0x138],RCX
00c4c0ac  MOV RCX,qword ptr [RSP + 0x378]
00c4c0b4  MOV RAX,qword ptr [RCX + 0x10]
00c4c0b8  CALL 0x005bb0e0
00c4c0bd  MOV RBX,RAX
00c4c0c0  LEA RCX,[0xefc947]
00c4c0c7  MOV EDI,0x5
00c4c0cc  LEA RAX,[0xe9bd40]
00c4c0d3  CALL 0x00412ee0
00c4c0d8  CMP qword ptr [RAX + 0x8],0x0
00c4c0dd  JNZ 0x00c4c0e5
00c4c0df  XOR EDX,EDX
00c4c0e1  XOR ECX,ECX
00c4c0e3  JMP 0x00c4c0ef
00c4c0e5  MOV RCX,qword ptr [RAX]
00c4c0e8  MOV RDX,qword ptr [RCX + 0x8]
00c4c0ec  MOV RCX,qword ptr [RCX]
00c4c0ef  MOV qword ptr [RSP + 0x68],RDX
00c4c0f4  MOV qword ptr [RSP + 0x130],RCX
00c4c0fc  MOV RCX,qword ptr [RSP + 0x378]
00c4c104  MOV RAX,qword ptr [RCX + 0x10]
00c4c108  CALL 0x005bb0e0
00c4c10d  MOV RBX,RAX
00c4c110  LEA RCX,[0xf05a11]
00c4c117  MOV EDI,0x9
00c4c11c  LEA RAX,[0xe9bd40]
00c4c123  CALL 0x00412ee0
00c4c128  CMP qword ptr [RAX + 0x8],0x0
00c4c12d  JNZ 0x00c4c135
00c4c12f  XOR EDX,EDX
00c4c131  XOR ECX,ECX
00c4c133  JMP 0x00c4c13f
00c4c135  MOV RCX,qword ptr [RAX]
00c4c138  MOV RDX,qword ptr [RCX + 0x8]
00c4c13c  MOV RCX,qword ptr [RCX]
00c4c13f  MOV qword ptr [RSP + 0x60],RDX
00c4c144  MOV qword ptr [RSP + 0x128],RCX
00c4c14c  MOV RCX,qword ptr [RSP + 0x378]
00c4c154  MOV RAX,qword ptr [RCX + 0x10]
00c4c158  CALL 0x005bb0e0
00c4c15d  MOV RBX,RAX
00c4c160  LEA RCX,[0xf05a1a]
00c4c167  MOV EDI,0x9
00c4c16c  LEA RAX,[0xe9bd40]
00c4c173  CALL 0x00412ee0
00c4c178  CMP qword ptr [RAX + 0x8],0x0
00c4c17d  JNZ 0x00c4c185
00c4c17f  XOR EDX,EDX
00c4c181  XOR ECX,ECX
00c4c183  JMP 0x00c4c18f
00c4c185  MOV RCX,qword ptr [RAX]
00c4c188  MOV RDX,qword ptr [RCX + 0x8]
00c4c18c  MOV RCX,qword ptr [RCX]
00c4c18f  TEST RDX,RDX
00c4c192  JNZ 0x00c4c1dc
00c4c194  MOV RCX,qword ptr [RSP + 0x378]
00c4c19c  MOV RAX,qword ptr [RCX + 0x10]
00c4c1a0  CALL 0x005bb0e0
00c4c1a5  MOV RBX,RAX
00c4c1a8  LEA RCX,[0xefb5a3]
00c4c1af  MOV EDI,0x4
00c4c1b4  LEA RAX,[0xe9bd40]
00c4c1bb  NOP dword ptr [RAX + RAX*0x1]
00c4c1c0  CALL 0x00412ee0
00c4c1c5  CMP qword ptr [RAX + 0x8],0x0
00c4c1ca  JNZ 0x00c4c1d2
00c4c1cc  XOR EDX,EDX
00c4c1ce  XOR ECX,ECX
00c4c1d0  JMP 0x00c4c1dc
00c4c1d2  MOV RCX,qword ptr [RAX]
00c4c1d5  MOV RDX,qword ptr [RCX + 0x8]
00c4c1d9  MOV RCX,qword ptr [RCX]
00c4c1dc  MOV qword ptr [RSP + 0xd0],RDX
00c4c1e4  MOV qword ptr [RSP + 0x198],RCX
00c4c1ec  LEA RAX,[0xdd2b80]
00c4c1f3  CALL 0x00421f00
00c4c1f8  MOV qword ptr [RSP + 0x348],RAX
00c4c200  MOV RCX,qword ptr [RSP + 0xd0]
00c4c208  TEST RCX,RCX
00c4c20b  JZ 0x00c4c2ad
00c4c211  LEA RAX,[0xdd29c0]
00c4c218  CALL 0x00421f00
00c4c21d  LEA RCX,[0xdb4420]
00c4c224  MOV qword ptr [RSP + 0x2b8],RCX
00c4c22c  MOV RCX,qword ptr [RSP + 0x348]
00c4c234  MOV qword ptr [RSP + 0x2c0],RCX
00c4c23c  MOV RDX,qword ptr [RSP + 0xd0]
00c4c244  MOV qword ptr [RAX + 0x8],RDX
00c4c248  CMP dword ptr [0x019b5f00],0x0
00c4c24f  JNZ 0x00c4c25b
00c4c251  MOV R10,qword ptr [RSP + 0x198]
00c4c259  JMP 0x00c4c274
00c4c25b  MOV RDX,qword ptr [RAX]
00c4c25e  NOP
00c4c260  CALL 0x0048bc00
00c4c265  MOV R10,qword ptr [RSP + 0x198]
00c4c26d  MOV qword ptr [R11],R10
00c4c270  MOV qword ptr [R11 + 0x8],RDX
00c4c274  MOV qword ptr [RAX],R10
00c4c277  MOV RBX,RAX
00c4c27a  LEA RCX,[0xefa6de]
00c4c281  MOV EDI,0x2
00c4c286  LEA RSI,[RSP + 0x2b8]
00c4c28e  MOV R8D,0x1
00c4c294  MOV R9,R8
00c4c297  LEA RAX,[0x1139840]
00c4c29e  NOP
00c4c2a0  CALL 0x0050c620
00c4c2a5  MOV RAX,qword ptr [RSP + 0x348]
00c4c2ad  CMP qword ptr [RAX],0x0
00c4c2b1  JG 0x00c4c2d6
00c4c2b3  MOV RAX,qword ptr [RSP + 0x148]
00c4c2bb  MOV RBX,qword ptr [RSP + 0x80]
00c4c2c3  CALL 0x009e5d20
00c4c2c8  MOV RCX,qword ptr [RSP + 0x348]
00c4c2d0  MOV qword ptr [RCX],RAX
00c4c2d3  MOV RAX,RCX
00c4c2d6  CMP qword ptr [RAX],0x0
00c4c2da  JG 0x00c4c308
00c4c2dc  MOV RBX,qword ptr [RSP + 0x70]
00c4c2e1  TEST RBX,RBX
00c4c2e4  JZ 0x00c4c30d
00c4c2e6  MOV RAX,qword ptr [RSP + 0x138]
00c4c2ee  CALL 0x009e5d20
00c4c2f3  MOV RCX,qword ptr [RSP + 0x348]
00c4c2fb  MOV qword ptr [RCX],RAX
00c4c2fe  MOV RAX,RCX
00c4c301  MOV RBX,qword ptr [RSP + 0x70]
00c4c306  JMP 0x00c4c30d
00c4c308  MOV RBX,qword ptr [RSP + 0x70]
00c4c30d  TEST RBX,RBX
00c4c310  JZ 0x00c4c31c
00c4c312  MOV RCX,qword ptr [RSP + 0x138]
00c4c31a  JMP 0x00c4c34c
00c4c31c  MOV RAX,qword ptr [RSP + 0x148]
00c4c324  MOV RBX,qword ptr [RSP + 0x80]
00c4c32c  CALL 0x009e50a0
00c4c331  TEST RBX,RBX
00c4c334  MOV RDX,qword ptr [RSP + 0x70]
00c4c339  CMOVNZ RDX,RBX
00c4c33d  MOV RCX,qword ptr [RSP + 0x138]
00c4c345  CMOVNZ RCX,RAX
00c4c349  MOV RBX,RDX
00c4c34c  MOV qword ptr [RSP + 0xd8],RBX
00c4c354  MOV qword ptr [RSP + 0x1a0],RCX
00c4c35c  MOV RAX,qword ptr [RSP + 0x148]
00c4c364  MOV RBX,qword ptr [RSP + 0x80]
00c4c36c  MOV RCX,qword ptr [RSP + 0x140]
00c4c374  MOV RDI,qword ptr [RSP + 0x78]
00c4c379  CALL 0x009e4dc0
00c4c37e  MOV qword ptr [RSP + 0x160],RAX
00c4c386  MOV qword ptr [RSP + 0x1c0],RCX
00c4c38e  MOV qword ptr [RSP + 0xa8],RBX
00c4c396  MOV qword ptr [RSP + 0x100],RDI
00c4c39e  MOV RAX,qword ptr [RSP + 0x1a0]
00c4c3a6  MOV RBX,qword ptr [RSP + 0xd8]
00c4c3ae  LEA RCX,[0xefabb5]
00c4c3b5  MOV EDI,0x3
00c4c3ba  CALL 0x00414f60
00c4c3bf  NOP
00c4c3c0  TEST RAX,RAX
00c4c3c3  JGE 0x00c4c3ce
00c4c3c5  XOR ESI,ESI
00c4c3c7  XOR EDX,EDX
00c4c3c9  JMP 0x00c4c487
00c4c3ce  MOV RAX,qword ptr [RSP + 0x1a0]
00c4c3d6  MOV RBX,qword ptr [RSP + 0xd8]
00c4c3de  NOP
00c4c3e0  CALL 0x009e5f20
00c4c3e5  TEST RBX,RBX
00c4c3e8  JNZ 0x00c4c3f3
00c4c3ea  XOR ESI,ESI
00c4c3ec  XOR EDX,EDX
00c4c3ee  JMP 0x00c4c487
00c4c3f3  MOV qword ptr [RSP + 0x110],RCX
00c4c3fb  MOV qword ptr [RSP + 0x108],RBX
00c4c403  MOV qword ptr [RSP + 0x1c8],RAX
00c4c40b  LEA RAX,[0xe2dd00]
00c4c412  CALL 0x00421f00
00c4c417  MOV qword ptr [RSP + 0x350],RAX
00c4c41f  MOV RBX,qword ptr [RSP + 0x108]
00c4c427  MOV RCX,qword ptr [RSP + 0x110]
00c4c42f  LEA RDI,[0xdc0060]
00c4c436  MOV RSI,RAX
00c4c439  MOV RAX,qword ptr [RSP + 0x1c8]
00c4c441  CALL 0x0052c3c0
00c4c446  TEST RAX,RAX
00c4c449  JZ 0x00c4c451
00c4c44b  XOR ESI,ESI
00c4c44d  XOR EDX,EDX
00c4c44f  JMP 0x00c4c487
00c4c451  MOV RDX,qword ptr [RSP + 0x350]
00c4c459  MOV RSI,qword ptr [RDX + 0x8]
00c4c45d  NOP dword ptr [RAX]
00c4c460  TEST RSI,RSI
00c4c463  JZ 0x00c4c46a
00c4c465  MOV RDX,qword ptr [RDX]
00c4c468  JMP 0x00c4c487
00c4c46a  MOV RDI,qword ptr [RDX + 0x18]
00c4c46e  MOV R8,qword ptr [RDX + 0x10]
00c4c472  TEST RDI,RDI
00c4c475  MOV ESI,0x0
00c4c47a  CMOVNZ RSI,RDI
00c4c47e  MOV EDX,0x0
00c4c483  CMOVNZ RDX,R8
00c4c487  MOV qword ptr [RSP + 0x178],RDX
00c4c48f  MOV qword ptr [RSP + 0xb8],RSI
00c4c497  MOV RDI,qword ptr [RSP + 0x60]
00c4c49c  MOV qword ptr [RSP + 0x320],RDI
00c4c4a4  MOV RDI,qword ptr [RSP + 0x128]
00c4c4ac  MOV qword ptr [RSP + 0x318],RDI
00c4c4b4  MOV qword ptr [RSP + 0x330],RSI
00c4c4bc  MOV qword ptr [RSP + 0x328],RDX
00c4c4c4  MOV RDX,qword ptr [RSP + 0xd8]
00c4c4cc  MOV qword ptr [RSP + 0x340],RDX
00c4c4d4  MOV RDX,qword ptr [RSP + 0x1a0]
00c4c4dc  MOV qword ptr [RSP + 0x338],RDX
00c4c4e4  LEA RAX,[RSP + 0x318]
00c4c4ec  MOV EBX,0x3
00c4c4f1  MOV RCX,RBX
00c4c4f4  CALL 0x00c4b580
00c4c4f9  MOV qword ptr [RSP + 0x1a8],RAX
00c4c501  MOV qword ptr [RSP + 0xe0],RBX
00c4c509  MOV RAX,qword ptr [RSP + 0x160]
00c4c511  MOV RBX,qword ptr [RSP + 0xa8]
00c4c519  CALL 0x00c48020
00c4c51e  NOP
00c4c520  TEST RAX,RAX
00c4c523  JZ 0x00c4d1ae
00c4c529  MOV qword ptr [RSP + 0x170],RBX
00c4c531  MOV qword ptr [RSP + 0xb0],RAX
00c4c539  MOV RDX,qword ptr [RSP + 0x68]
00c4c53e  NOP
00c4c540  TEST RDX,RDX
00c4c543  JZ 0x00c4c54f
00c4c545  MOV RCX,qword ptr [RSP + 0x130]
00c4c54d  JMP 0x00c4c589
00c4c54f  MOV RCX,qword ptr [RAX + 0x28]
00c4c553  MOV RAX,RBX
00c4c556  CALL RCX
00c4c558  MOV RCX,qword ptr [0x019900b0]
00c4c55f  MOV RDX,RAX
00c4c562  MOV RAX,RCX
00c4c565  MOV RSI,RBX
00c4c568  MOV RBX,RDX
00c4c56b  MOV RCX,RSI
00c4c56e  CALL 0x00a63de0
00c4c573  MOV RCX,RAX
00c4c576  MOV RDX,RBX
00c4c579  MOV RAX,qword ptr [RSP + 0xb0]
00c4c581  MOV RBX,qword ptr [RSP + 0x170]
00c4c589  MOV qword ptr [RSP + 0x158],RCX
00c4c591  MOV qword ptr [RSP + 0x98],RDX
00c4c599  LEA R12,[0x11476d0]
00c4c5a0  CMP RAX,R12
00c4c5a3  JNZ 0x00c4c5fe
00c4c5a5  MOV R12,qword ptr [RSP + 0x150]
00c4c5ad  MOV qword ptr [RSP],R12
00c4c5b1  MOV R12,qword ptr [RSP + 0x90]
00c4c5b9  MOV qword ptr [RSP + 0x8],R12
00c4c5be  MOV RAX,RBX
00c4c5c1  MOV RBX,qword ptr [RSP + 0x160]
00c4c5c9  MOV RDI,qword ptr [RSP + 0x1c0]
00c4c5d1  MOV RSI,qword ptr [RSP + 0x100]
00c4c5d9  MOV R8,qword ptr [RSP + 0x1a0]
00c4c5e1  MOV R9,qword ptr [RSP + 0xd8]
00c4c5e9  MOV R10,RCX
00c4c5ec  MOV R11,RDX
00c4c5ef  MOV RCX,qword ptr [RSP + 0xa8]
00c4c5f7  CALL 0x009c52a0
00c4c5fc  JMP 0x00c4c640
00c4c5fe  MOV R12,qword ptr [RAX + 0x38]
00c4c602  MOV RAX,RBX
00c4c605  MOV RBX,qword ptr [RSP + 0x160]
00c4c60d  MOV RDI,qword ptr [RSP + 0x1c0]
00c4c615  MOV RSI,qword ptr [RSP + 0x100]
00c4c61d  MOV R8,qword ptr [RSP + 0x1a0]
00c4c625  MOV R9,qword ptr [RSP + 0xd8]
00c4c62d  MOV R10,RCX
00c4c630  MOV R11,RDX
00c4c633  MOV RCX,qword ptr [RSP + 0xa8]
00c4c63b  CALL R12
00c4c63e  NOP
00c4c640  TEST RBX,RBX
00c4c643  JNZ 0x00c4d07f
00c4c649  MOV qword ptr [RSP + 0x168],RAX
00c4c651  MOV RBX,qword ptr [RAX + 0x20]
00c4c655  TEST RBX,RBX
00c4c658  JZ 0x00c4c69e
00c4c65a  MOV RDX,qword ptr [RAX + 0x18]
00c4c65e  MOV RCX,qword ptr [RAX + 0x28]
00c4c662  MOV RDI,qword ptr [RAX + 0x10]
00c4c666  MOV RAX,RDX
00c4c669  CALL 0x00c487e0
00c4c66e  MOV RDX,qword ptr [RSP + 0x168]
00c4c676  MOV qword ptr [RDX + 0x20],RBX
00c4c67a  MOV qword ptr [RDX + 0x28],RCX
00c4c67e  CMP dword ptr [0x019b5f00],0x0
00c4c685  JZ 0x00c4c697
00c4c687  MOV RSI,qword ptr [RDX + 0x18]
00c4c68b  CALL 0x0048bc00
00c4c690  MOV qword ptr [R11],RAX
00c4c693  MOV qword ptr [R11 + 0x8],RSI
00c4c697  MOV qword ptr [RDX + 0x18],RAX
00c4c69b  MOV RAX,RDX
00c4c69e  MOV RBX,qword ptr [RAX + 0x8]
00c4c6a2  TEST RBX,RBX
00c4c6a5  JZ 0x00c4d04f
00c4c6ab  MOV RAX,qword ptr [RAX]
00c4c6ae  CALL 0x004af740
00c4c6b3  MOV qword ptr [RSP + 0x180],RAX
00c4c6bb  MOV qword ptr [RSP + 0xc0],RBX
00c4c6c3  MOV RCX,qword ptr [RSP + 0x168]
00c4c6cb  MOV RAX,qword ptr [RCX + 0x38]
00c4c6cf  MOV RBX,qword ptr [RCX + 0x40]
00c4c6d3  CALL 0x00c4b980
00c4c6d8  NOP dword ptr [RAX + RAX*0x1]
00c4c6e0  TEST CL,CL
00c4c6e2  JNZ 0x00c4c785
00c4c6e8  LEA RAX,[RSP + 0x318]
00c4c6f0  MOVUPS xmmword ptr [RAX],XMM15
00c4c6f4  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c4c6f9  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c4c6fe  MOV RDX,qword ptr [RSP + 0x168]
00c4c706  MOV RSI,qword ptr [RDX]
00c4c709  MOV RDX,qword ptr [RDX + 0x8]
00c4c70d  MOV qword ptr [RSP + 0x320],RDX
00c4c715  MOV qword ptr [RSP + 0x318],RSI
00c4c71d  MOV RDX,qword ptr [RSP + 0xb8]
00c4c725  MOV qword ptr [RSP + 0x330],RDX
00c4c72d  MOV RDX,qword ptr [RSP + 0x178]
00c4c735  MOV qword ptr [RSP + 0x328],RDX
00c4c73d  MOV RDX,qword ptr [RSP + 0x60]
00c4c742  MOV qword ptr [RSP + 0x340],RDX
00c4c74a  MOV RDX,qword ptr [RSP + 0x128]
00c4c752  MOV qword ptr [RSP + 0x338],RDX
00c4c75a  MOV EBX,0x3
00c4c75f  MOV RCX,RBX
00c4c762  CALL 0x00c4b580
00c4c767  CMP RBX,0x4
00c4c76b  JNZ 0x00c4c785
00c4c76d  CMP dword ptr [RAX],0x34706d2e
00c4c773  JNZ 0x00c4c785
00c4c775  MOV RBX,qword ptr [RSP + 0xe0]
00c4c77d  MOV RAX,qword ptr [RSP + 0x1a8]
00c4c785  MOV qword ptr [RSP + 0xe0],RBX
00c4c78d  MOV qword ptr [RSP + 0x1a8],RAX
00c4c795  MOV RCX,qword ptr [RSP + 0xb0]
00c4c79d  MOV RCX,qword ptr [RCX + 0x28]
00c4c7a1  MOV RAX,qword ptr [RSP + 0x170]
00c4c7a9  CALL RCX
00c4c7ab  CMP RBX,0x8
00c4c7af  JNZ 0x00c4c7c3
00c4c7b1  MOV RDX,0x35313144554f4c43
00c4c7bb  CMP qword ptr [RAX],RDX
00c4c7be  SETZ DL
00c4c7c1  JMP 0x00c4c7c5
00c4c7c3  XOR EDX,EDX
00c4c7c5  MOV byte ptr [RSP + 0x5f],DL
00c4c7c9  MOV RAX,qword ptr [RSP + 0x180]
00c4c7d1  MOV RBX,qword ptr [RSP + 0xc0]
00c4c7d9  LEA RCX,[0xefc93d]
00c4c7e0  MOV EDI,0x5
00c4c7e5  CALL 0x00414f60
00c4c7ea  TEST RAX,RAX
00c4c7ed  JL 0x00c4c7f6
00c4c7ef  MOV EDX,0x1
00c4c7f4  JMP 0x00c4c81d
00c4c7f6  MOV RAX,qword ptr [RSP + 0x180]
00c4c7fe  MOV RBX,qword ptr [RSP + 0xc0]
00c4c806  LEA RCX,[0xefb52f]
00c4c80d  MOV EDI,0x4
00c4c812  CALL 0x00414f60
00c4c817  TEST RAX,RAX
00c4c81a  SETGE DL
00c4c81d  MOV byte ptr [RSP + 0x5e],DL
00c4c821  MOVZX ESI,byte ptr [RSP + 0x5f]
00c4c826  TEST SIL,SIL
00c4c829  JNZ 0x00c4c833
00c4c82b  TEST DL,DL
00c4c82d  JZ 0x00c4c8d2
00c4c833  NOP
00c4c834  LEA RDI,[RSP + 0x2e8]
00c4c83c  MOVUPS xmmword ptr [RDI],XMM15
00c4c840  MOVUPS xmmword ptr [RDI + 0x10],XMM15
00c4c845  MOVUPS xmmword ptr [RDI + 0x20],XMM15
00c4c84a  LEA RDX,[0xc4d740]
00c4c851  MOV qword ptr [RSP + 0x2e8],RDX
00c4c859  MOV qword ptr [RSP + 0x2f8],0x5e
00c4c865  LEA RDX,[0xf5de62]
00c4c86c  MOV qword ptr [RSP + 0x2f0],RDX
00c4c874  MOV RAX,qword ptr [0x01990148]
00c4c87b  XOR EBX,EBX
00c4c87d  MOV ECX,0x2
00c4c882  CALL 0x0054d540
00c4c887  MOVZX EDX,byte ptr [RSP + 0x5e]
00c4c88c  TEST DL,DL
00c4c88e  JZ 0x00c4c8c5
00c4c890  CMP dword ptr [0x019b5f00],0x0
00c4c897  JNZ 0x00c4c8a3
00c4c899  MOV RCX,qword ptr [RSP + 0x168]
00c4c8a1  JMP 0x00c4c8b7
00c4c8a3  MOV RCX,qword ptr [RSP + 0x168]
00c4c8ab  MOV RDX,qword ptr [RCX + 0x10]
00c4c8af  CALL 0x0048bbe0
00c4c8b4  MOV qword ptr [R11],RDX
00c4c8b7  MOV qword ptr [RCX + 0x10],0x0
00c4c8bf  NOP
00c4c8c0  JMP 0x00c4d04c
00c4c8c5  MOV RCX,qword ptr [RSP + 0x168]
00c4c8cd  JMP 0x00c4d04c
00c4c8d2  MOV RDX,qword ptr [RSP + 0x168]
00c4c8da  MOV RAX,qword ptr [RDX + 0x30]
00c4c8de  NOP
00c4c8e0  TEST RAX,RAX
00c4c8e3  JG 0x00c4c9bd
00c4c8e9  MOV RSI,qword ptr [RSP + 0x348]
00c4c8f1  MOV RAX,qword ptr [RSI]
00c4c8f4  TEST RAX,RAX
00c4c8f7  JLE 0x00c4c9a8
00c4c8fd  MOV qword ptr [RSP + 0x118],RAX
00c4c905  MOVUPS xmmword ptr [RSP + 0x278],XMM15
00c4c90e  CALL 0x00481e60
00c4c913  LEA RCX,[0xdd2b80]
00c4c91a  MOV qword ptr [RSP + 0x278],RCX
00c4c922  MOV qword ptr [RSP + 0x280],RAX
00c4c92a  LEA RCX,[0xc4d680]
00c4c931  MOV qword ptr [RSP + 0x2e8],RCX
00c4c939  MOV qword ptr [RSP + 0x2f8],0x28
00c4c945  LEA RCX,[0xf3b70f]
00c4c94c  MOV qword ptr [RSP + 0x2f0],RCX
00c4c954  MOV qword ptr [RSP + 0x308],0x1
00c4c960  MOV qword ptr [RSP + 0x310],0x1
00c4c96c  LEA RCX,[RSP + 0x278]
00c4c974  MOV qword ptr [RSP + 0x300],RCX
00c4c97c  MOV RAX,qword ptr [0x01990148]
00c4c983  XOR EBX,EBX
00c4c985  MOV ECX,0x2
00c4c98a  LEA RDI,[RSP + 0x2e8]
00c4c992  CALL 0x0054d540
00c4c997  MOV RAX,qword ptr [RSP + 0x118]
00c4c99f  XOR EBX,EBX
00c4c9a1  XOR ECX,ECX
00c4c9a3  JMP 0x00c4ca63
00c4c9a8  MOV RBX,qword ptr [RDX + 0x8]
00c4c9ac  MOV RAX,qword ptr [RDX]
00c4c9af  MOV RCX,qword ptr [RDX + 0x10]
00c4c9b3  CALL 0x00a9f520
00c4c9b8  JMP 0x00c4ca63
00c4c9bd  MOV qword ptr [RSP + 0x118],RAX
00c4c9c5  MOVUPS xmmword ptr [RSP + 0x288],XMM15
00c4c9ce  CALL 0x00481e60
00c4c9d3  LEA RCX,[0xdd2b80]
00c4c9da  MOV qword ptr [RSP + 0x288],RCX
00c4c9e2  MOV qword ptr [RSP + 0x290],RAX
00c4c9ea  LEA RCX,[0xc4d6e0]
00c4c9f1  MOV qword ptr [RSP + 0x2e8],RCX
00c4c9f9  MOV qword ptr [RSP + 0x2f8],0x31
00c4ca05  LEA RCX,[0xf453b1]
00c4ca0c  MOV qword ptr [RSP + 0x2f0],RCX
00c4ca14  MOV qword ptr [RSP + 0x308],0x1
00c4ca20  MOV qword ptr [RSP + 0x310],0x1
00c4ca2c  LEA RCX,[RSP + 0x288]
00c4ca34  MOV qword ptr [RSP + 0x300],RCX
00c4ca3c  MOV RAX,qword ptr [0x01990148]
00c4ca43  XOR EBX,EBX
00c4ca45  MOV ECX,0x2
00c4ca4a  LEA RDI,[RSP + 0x2e8]
00c4ca52  CALL 0x0054d540
00c4ca57  XOR EBX,EBX
00c4ca59  MOV RAX,qword ptr [RSP + 0x118]
00c4ca61  XOR ECX,ECX
00c4ca63  MOV qword ptr [RSP + 0x1b0],RCX
00c4ca6b  MOV qword ptr [RSP + 0xe8],RBX
00c4ca73  TEST RBX,RBX
00c4ca76  JNZ 0x00c4ca89
00c4ca78  NOP dword ptr [RAX + RAX*0x1]
00c4ca80  TEST RAX,RAX
00c4ca83  JG 0x00c4cb58
00c4ca89  LEA RCX,[RSP + 0x258]
00c4ca91  MOVUPS xmmword ptr [RCX],XMM15
00c4ca95  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c4ca9a  CALL 0x00481e60
00c4ca9f  LEA RCX,[0xdd2b80]
00c4caa6  MOV qword ptr [RSP + 0x258],RCX
00c4caae  MOV qword ptr [RSP + 0x260],RAX
00c4cab6  MOV RCX,qword ptr [RSP + 0xe8]
00c4cabe  NOP
00c4cac0  TEST RCX,RCX
00c4cac3  JZ 0x00c4cacb
00c4cac5  MOV RBX,qword ptr [RCX + 0x8]
00c4cac9  JMP 0x00c4cace
00c4cacb  MOV RBX,RCX
00c4cace  MOV qword ptr [RSP + 0x268],RBX
00c4cad6  MOV RDX,qword ptr [RSP + 0x1b0]
00c4cade  MOV qword ptr [RSP + 0x270],RDX
00c4cae6  LEA RDX,[0xc4d620]
00c4caed  MOV qword ptr [RSP + 0x2e8],RDX
00c4caf5  MOV qword ptr [RSP + 0x2f8],0x5c
00c4cb01  LEA RDX,[0xf5d780]
00c4cb08  MOV qword ptr [RSP + 0x2f0],RDX
00c4cb10  MOV qword ptr [RSP + 0x308],0x2
00c4cb1c  MOV qword ptr [RSP + 0x310],0x2
00c4cb28  LEA RDX,[RSP + 0x258]
00c4cb30  MOV qword ptr [RSP + 0x300],RDX
00c4cb38  MOV RAX,qword ptr [0x01990148]
00c4cb3f  XOR EBX,EBX
00c4cb41  MOV ECX,0x2
00c4cb46  LEA RDI,[RSP + 0x2e8]
00c4cb4e  CALL 0x0054d540
00c4cb53  MOV EAX,0x80000000
00c4cb58  MOV qword ptr [RSP + 0xa0],RAX
00c4cb60  MOV RCX,qword ptr [RSP + 0xb0]
00c4cb68  MOV RCX,qword ptr [RCX + 0x28]
00c4cb6c  MOV RAX,qword ptr [RSP + 0x170]
00c4cb74  CALL RCX
00c4cb76  CMP RBX,0x6
00c4cb7a  JNZ 0x00c4cb93
00c4cb7c  CMP dword ptr [RAX],0x59494c41
00c4cb82  JNZ 0x00c4cb93
00c4cb84  CMP word ptr [RAX + 0x4],0x4e55
00c4cb8a  JNZ 0x00c4cb93
00c4cb8c  MOV EAX,0x20
00c4cb91  JMP 0x00c4cbcb
00c4cb93  MOV RCX,qword ptr [RSP + 0xb0]
00c4cb9b  MOV RCX,qword ptr [RCX + 0x28]
00c4cb9f  MOV RAX,qword ptr [RSP + 0x170]
00c4cba7  CALL RCX
00c4cba9  CMP RBX,0x6
00c4cbad  JNZ 0x00c4cbc6
00c4cbaf  CMP dword ptr [RAX],0x4c4e5558
00c4cbb5  JNZ 0x00c4cbc6
00c4cbb7  CMP word ptr [RAX + 0x4],0x4945
00c4cbbd  JNZ 0x00c4cbc6
00c4cbbf  MOV EAX,0x10
00c4cbc4  JMP 0x00c4cbcb
00c4cbc6  MOV EAX,0x8
00c4cbcb  CMP qword ptr [0x019900b8],0x0
00c4cbd3  JZ 0x00c4cc06
00c4cbd5  MOV RCX,qword ptr [RSP + 0xb0]
00c4cbdd  MOV RCX,qword ptr [RCX + 0x28]
00c4cbe1  MOV RAX,qword ptr [RSP + 0x170]
00c4cbe9  CALL RCX
00c4cbeb  MOV RCX,qword ptr [0x019900b8]
00c4cbf2  MOV RDX,RAX
00c4cbf5  MOV RAX,RCX
00c4cbf8  MOV RSI,RBX
00c4cbfb  MOV RBX,RDX
00c4cbfe  MOV RCX,RSI
00c4cc01  CALL 0x009e7e60
00c4cc06  MOV qword ptr [RSP + 0xf8],RAX
00c4cc0e  CMP qword ptr [0x01990188],0x0
00c4cc16  JNZ 0x00c4cc1c
00c4cc18  XOR ECX,ECX
00c4cc1a  JMP 0x00c4cc50
00c4cc1c  MOV RCX,qword ptr [RSP + 0xb0]
00c4cc24  MOV RCX,qword ptr [RCX + 0x28]
00c4cc28  MOV RAX,qword ptr [RSP + 0x170]
00c4cc30  CALL RCX
00c4cc32  MOV RCX,qword ptr [0x01990188]
00c4cc39  MOV RDX,RAX
00c4cc3c  MOV RAX,RCX
00c4cc3f  MOV RSI,RBX
00c4cc42  MOV RBX,RDX
00c4cc45  MOV RCX,RSI
00c4cc48  CALL 0x009b86c0
00c4cc4d  MOV RCX,RAX
00c4cc50  MOV qword ptr [RSP + 0x88],RCX
00c4cc58  LEA RAX,[0xe9c520]
00c4cc5f  NOP
00c4cc60  CALL 0x00421f00
00c4cc65  LEA RCX,[0xc4d320]
00c4cc6c  MOV qword ptr [RAX],RCX
00c4cc6f  MOV RCX,qword ptr [RSP + 0x98]
00c4cc77  MOV qword ptr [RAX + 0x10],RCX
00c4cc7b  CMP dword ptr [0x019b5f00],0x0
00c4cc82  JNZ 0x00c4ccae
00c4cc84  MOV RCX,qword ptr [RSP + 0x158]
00c4cc8c  MOV RDX,qword ptr [RSP + 0x170]
00c4cc94  MOV RSI,qword ptr [RSP + 0x160]
00c4cc9c  MOV RDI,qword ptr [RSP + 0x1c0]
00c4cca4  MOV R8,qword ptr [RSP + 0x1a0]
00c4ccac  JMP 0x00c4ccee
00c4ccae  CALL 0x0048bc60
00c4ccb3  MOV RCX,qword ptr [RSP + 0x158]
00c4ccbb  MOV qword ptr [R11],RCX
00c4ccbe  MOV RDX,qword ptr [RSP + 0x170]
00c4ccc6  MOV qword ptr [R11 + 0x8],RDX
00c4ccca  MOV RSI,qword ptr [RSP + 0x160]
00c4ccd2  MOV qword ptr [R11 + 0x10],RSI
00c4ccd6  MOV RDI,qword ptr [RSP + 0x1c0]
00c4ccde  MOV qword ptr [R11 + 0x18],RDI
00c4cce2  MOV R8,qword ptr [RSP + 0x1a0]
00c4ccea  MOV qword ptr [R11 + 0x20],R8
00c4ccee  MOV qword ptr [RSP + 0x1d0],RAX
00c4ccf6  MOV qword ptr [RAX + 0x8],RCX
00c4ccfa  MOV RCX,qword ptr [RSP + 0xb0]
00c4cd02  MOV qword ptr [RAX + 0x18],RCX
00c4cd06  MOV qword ptr [RAX + 0x20],RDX
00c4cd0a  MOV RCX,qword ptr [RSP + 0xa8]
00c4cd12  MOV qword ptr [RAX + 0x30],RCX
00c4cd16  MOV qword ptr [RAX + 0x28],RSI
00c4cd1a  MOV RCX,qword ptr [RSP + 0x100]
00c4cd22  MOV qword ptr [RAX + 0x40],RCX
00c4cd26  MOV qword ptr [RAX + 0x38],RDI
00c4cd2a  MOV RCX,qword ptr [RSP + 0xd8]
00c4cd32  MOV qword ptr [RAX + 0x50],RCX
00c4cd36  MOV qword ptr [RAX + 0x48],R8
00c4cd3a  MOVUPS xmmword ptr [RSP + 0x248],XMM15
00c4cd43  MOV RCX,qword ptr [RSP + 0x168]
00c4cd4b  MOV RAX,qword ptr [RCX]
00c4cd4e  MOV RBX,qword ptr [RCX + 0x8]
00c4cd52  CALL 0x00481ee0
00c4cd57  LEA RCX,[0xdd29c0]
00c4cd5e  MOV qword ptr [RSP + 0x248],RCX
00c4cd66  MOV qword ptr [RSP + 0x250],RAX
00c4cd6e  LEA RCX,[0xc4d2c0]
00c4cd75  MOV qword ptr [RSP + 0x2e8],RCX
00c4cd7d  MOV qword ptr [RSP + 0x2f8],0x1c
00c4cd89  LEA RCX,[0xf2bdce]
00c4cd90  MOV qword ptr [RSP + 0x2f0],RCX
00c4cd98  MOV qword ptr [RSP + 0x308],0x1
00c4cda4  MOV qword ptr [RSP + 0x310],0x1
00c4cdb0  LEA RCX,[RSP + 0x248]
00c4cdb8  MOV qword ptr [RSP + 0x300],RCX
00c4cdc0  MOV RAX,qword ptr [0x01990148]
00c4cdc7  XOR EBX,EBX
00c4cdc9  MOV ECX,0x2
00c4cdce  LEA RDI,[RSP + 0x2e8]
00c4cdd6  CALL 0x0054d540
00c4cddb  MOV RCX,qword ptr [RSP + 0xe0]
00c4cde3  CMP RCX,0x4
00c4cde7  JNZ 0x00c4ce38
00c4cde9  MOV RDX,qword ptr [RSP + 0x1a8]
00c4cdf1  CMP dword ptr [RDX],0x6f73692e
00c4cdf7  JNZ 0x00c4ce05
00c4cdf9  MOV EAX,0x1
00c4cdfe  NOP
00c4ce00  JMP 0x00c4cec0
00c4ce05  CMP RCX,0x4
00c4ce09  JNZ 0x00c4ce38
00c4ce0b  CMP dword ptr [RDX],0x676d692e
00c4ce11  JNZ 0x00c4ce20
00c4ce13  MOV EAX,0x1
00c4ce18  JMP 0x00c4cec0
00c4ce20  CMP RCX,0x4
00c4ce24  JNZ 0x00c4ce38
00c4ce26  CMP dword ptr [RDX],0x67726e2e
00c4ce2c  JNZ 0x00c4ce38
00c4ce2e  MOV EAX,0x1
00c4ce33  JMP 0x00c4cec0
00c4ce38  MOV RAX,qword ptr [RSP + 0x1a0]
00c4ce40  MOV RBX,qword ptr [RSP + 0xd8]
00c4ce48  CALL 0x004af740
00c4ce4d  LEA RCX,[0xefb5a7]
00c4ce54  MOV EDI,0x4
00c4ce59  CALL 0x00414f60
00c4ce5e  NOP
00c4ce60  TEST RAX,RAX
00c4ce63  JL 0x00c4ce7c
00c4ce65  MOV RCX,qword ptr [RSP + 0xe0]
00c4ce6d  MOV RDX,qword ptr [RSP + 0x1a8]
00c4ce75  MOV EAX,0x1
00c4ce7a  JMP 0x00c4cec0
00c4ce7c  MOV RCX,qword ptr [RSP + 0x168]
00c4ce84  MOV RAX,qword ptr [RCX + 0x38]
00c4ce88  MOV RBX,qword ptr [RCX + 0x40]
00c4ce8c  CALL 0x004af740
00c4ce91  LEA RCX,[0xefb5a7]
00c4ce98  MOV EDI,0x4
00c4ce9d  NOP dword ptr [RAX]
00c4cea0  CALL 0x00414f60
00c4cea5  TEST RAX,RAX
00c4cea8  SETGE CL
00c4ceab  MOV RDX,qword ptr [RSP + 0x1a8]
00c4ceb3  MOV EAX,ECX
00c4ceb5  MOV RCX,qword ptr [RSP + 0xe0]
00c4cebd  NOP dword ptr [RAX]
00c4cec0  TEST AL,AL
00c4cec2  JNZ 0x00c4ceec
00c4cec4  MOV RAX,qword ptr [RSP + 0x128]
00c4cecc  MOV RBX,qword ptr [RSP + 0x60]
00c4ced1  CALL 0x004af740
00c4ced6  LEA RCX,[0xefb5a7]
00c4cedd  MOV EDI,0x4
00c4cee2  CALL 0x00414f60
00c4cee7  TEST RAX,RAX
00c4ceea  JL 0x00c4cf29
00c4ceec  MOV RAX,qword ptr [0x0196cdc0]
00c4cef3  MOV RDX,qword ptr [RSP + 0x168]
00c4cefb  MOV RBX,qword ptr [RDX]
00c4cefe  MOV RCX,qword ptr [RDX + 0x8]
00c4cf02  MOV RDI,qword ptr [RDX + 0x10]
00c4cf06  MOV RSI,qword ptr [RSP + 0xa0]
00c4cf0e  XOR R8D,R8D
00c4cf11  MOV R9,R8
00c4cf14  MOV R10D,0x1
00c4cf1a  MOV R11,qword ptr [RSP + 0x1d0]
00c4cf22  CALL 0x00aa4980
00c4cf27  JMP 0x00c4cf6b
00c4cf29  MOV RAX,qword ptr [0x0196cdc0]
00c4cf30  MOV RDX,qword ptr [RSP + 0x168]
00c4cf38  MOV RBX,qword ptr [RDX]
00c4cf3b  MOV RCX,qword ptr [RDX + 0x8]
00c4cf3f  MOV RDI,qword ptr [RDX + 0x10]
00c4cf43  MOV RSI,qword ptr [RSP + 0xa0]
00c4cf4b  MOV R8,qword ptr [RSP + 0xf8]
00c4cf53  MOV R9,qword ptr [RSP + 0x88]
00c4cf5b  XOR R10D,R10D
00c4cf5e  MOV R11,qword ptr [RSP + 0x1d0]
00c4cf66  CALL 0x00aa4980
00c4cf6b  MOV qword ptr [RSP + 0xc8],RBX
00c4cf73  MOV qword ptr [RSP + 0x188],RAX
00c4cf7b  LEA RCX,[RSP + 0x2c8]
00c4cf83  MOVUPS xmmword ptr [RCX],XMM15
00c4cf87  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c4cf8c  MOV RAX,qword ptr [RSP + 0x1a8]
00c4cf94  MOV RBX,qword ptr [RSP + 0xe0]
00c4cf9c  NOP dword ptr [RAX]
00c4cfa0  CALL 0x00481ee0
00c4cfa5  LEA RCX,[0xdd29c0]
00c4cfac  MOV qword ptr [RSP + 0x2c8],RCX
00c4cfb4  MOV qword ptr [RSP + 0x2d0],RAX
00c4cfbc  MOV RAX,qword ptr [RSP + 0x188]
00c4cfc4  MOV RBX,qword ptr [RSP + 0xc8]
00c4cfcc  CALL 0x00481ee0
00c4cfd1  LEA RCX,[0xdd29c0]
00c4cfd8  MOV qword ptr [RSP + 0x2d8],RCX
00c4cfe0  MOV qword ptr [RSP + 0x2e0],RAX
00c4cfe8  LEA RAX,[0xf3ed29]
00c4cfef  MOV EBX,0x2b
00c4cff4  LEA RCX,[RSP + 0x2c8]
00c4cffc  MOV EDI,0x2
00c4d001  MOV RSI,RDI
00c4d004  CALL 0x005055a0
00c4d009  MOV RCX,qword ptr [RSP + 0x168]
00c4d011  MOV qword ptr [RCX + 0x8],RBX
00c4d015  CMP dword ptr [0x019b5f00],0x0
00c4d01c  JZ 0x00c4d035
00c4d01e  MOV RDX,qword ptr [RCX]
00c4d021  MOV RSI,qword ptr [RCX + 0x10]
00c4d025  CALL 0x0048bc20
00c4d02a  MOV qword ptr [R11],RAX
00c4d02d  MOV qword ptr [R11 + 0x8],RDX
00c4d031  MOV qword ptr [R11 + 0x10],RSI
00c4d035  MOV qword ptr [RCX],RAX
00c4d038  MOV qword ptr [RCX + 0x10],0x0
00c4d040  MOV RDX,qword ptr [RSP + 0xa0]
00c4d048  MOV qword ptr [RCX + 0x30],RDX
00c4d04c  MOV RAX,RCX
00c4d04f  MOV RDX,qword ptr [RSP + 0x368]
00c4d057  NOP word ptr [RAX + RAX*0x1]
00c4d060  TEST RDX,RDX
00c4d063  JZ 0x00c4d1dd
00c4d069  MOV RBX,qword ptr [RDX + 0x8]
00c4d06d  MOV RSI,qword ptr [0x01973f20]
00c4d074  MOV RDI,qword ptr [RSI]
00c4d077  MOV EDX,dword ptr [RDX + 0x10]
00c4d07a  JMP 0x00c4d23d
00c4d07f  MOV qword ptr [RSP + 0xf0],RBX
00c4d087  MOV qword ptr [RSP + 0x1b8],RCX
00c4d08f  MOV RCX,qword ptr [RSP + 0xb0]
00c4d097  MOV RCX,qword ptr [RCX + 0x28]
00c4d09b  MOV RAX,qword ptr [RSP + 0x170]
00c4d0a3  CALL RCX
00c4d0a5  LEA RCX,[RSP + 0x298]
00c4d0ad  MOVUPS xmmword ptr [RCX],XMM15
00c4d0b1  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c4d0b6  CALL 0x00481ee0
00c4d0bb  LEA RCX,[0xdd29c0]
00c4d0c2  MOV qword ptr [RSP + 0x298],RCX
00c4d0ca  MOV qword ptr [RSP + 0x2a0],RAX
00c4d0d2  MOV RCX,qword ptr [RSP + 0xf0]
00c4d0da  TEST RCX,RCX
00c4d0dd  JZ 0x00c4d0e5
00c4d0df  MOV RBX,qword ptr [RCX + 0x8]
00c4d0e3  JMP 0x00c4d0e8
00c4d0e5  MOV RBX,RCX
00c4d0e8  MOV qword ptr [RSP + 0x2a8],RBX
00c4d0f0  MOV RDX,qword ptr [RSP + 0x1b8]
00c4d0f8  MOV qword ptr [RSP + 0x2b0],RDX
00c4d100  LEA RDX,[0xc4d7a0]
00c4d107  MOV qword ptr [RSP + 0x2e8],RDX
00c4d10f  MOV qword ptr [RSP + 0x2f8],0x29
00c4d11b  LEA RDX,[0xf3ca4a]
00c4d122  MOV qword ptr [RSP + 0x2f0],RDX
00c4d12a  MOV qword ptr [RSP + 0x308],0x2
00c4d136  MOV qword ptr [RSP + 0x310],0x2
00c4d142  LEA RDX,[RSP + 0x298]
00c4d14a  MOV qword ptr [RSP + 0x300],RDX
00c4d152  MOV RAX,qword ptr [0x01990148]
00c4d159  XOR EBX,EBX
00c4d15b  MOV ECX,0x2
00c4d160  LEA RDI,[RSP + 0x2e8]
00c4d168  CALL 0x0054d540
00c4d16d  MOV RDX,qword ptr [RSP + 0xf0]
00c4d175  MOV RDX,qword ptr [RDX + 0x18]
00c4d179  MOV RAX,qword ptr [RSP + 0x1b8]
00c4d181  CALL RDX
00c4d183  MOV RCX,RAX
00c4d186  MOV RDI,RBX
00c4d189  MOV ESI,0x1f4
00c4d18e  MOV RAX,qword ptr [RSP + 0x368]
00c4d196  MOV RBX,qword ptr [RSP + 0x370]
00c4d19e  NOP
00c4d1a0  CALL 0x00c484c0
00c4d1a5  ADD RSP,0x358
00c4d1ac  POP RBP
00c4d1ad  RET
00c4d1ae  MOV RAX,qword ptr [RSP + 0x368]
00c4d1b6  MOV RBX,qword ptr [RSP + 0x370]
00c4d1be  LEA RCX,[0xf21faa]
00c4d1c5  MOV EDI,0x15
00c4d1ca  MOV ESI,0x190
00c4d1cf  CALL 0x00c484c0
00c4d1d4  ADD RSP,0x358
00c4d1db  POP RBP
00c4d1dc  RET
00c4d1dd  LEA RSI,[RSP + 0x1e8]
00c4d1e5  MOVUPS xmmword ptr [RSI],XMM15
00c4d1e9  MOVUPS xmmword ptr [RSI + 0x10],XMM15
00c4d1ee  MOVUPS xmmword ptr [RSI + 0x20],XMM15
00c4d1f3  MOVUPS xmmword ptr [RSI + 0x30],XMM15
00c4d1f8  MOVUPS xmmword ptr [RSI + 0x40],XMM15
00c4d1fd  MOVUPS xmmword ptr [RSI + 0x50],XMM15
00c4d202  MOV qword ptr [RSP + 0x1e8],RDX
00c4d20a  MOV RDX,qword ptr [RSP + 0x370]
00c4d212  MOV qword ptr [RSP + 0x1f0],RDX
00c4d21a  MOV byte ptr [RSP + 0x208],0x1
00c4d222  LEA RBX,[0xdb1aa0]
00c4d229  MOV RCX,RAX
00c4d22c  MOV RAX,RSI
00c4d22f  CALL 0x0053fda0
00c4d234  ADD RSP,0x358
00c4d23b  POP RBP
00c4d23c  RET
00c4d23d  MOV R8,RDX
00c4d240  AND RDX,RDI
00c4d243  SHL RDX,0x4
00c4d247  MOV R9,qword ptr [RDX + RSI*0x1 + 0x8]
00c4d24c  CMP R9,RBX
00c4d24f  JZ 0x00c4d276
00c4d251  LEA RDX,[R8 + 0x1]
00c4d255  TEST R9,R9
00c4d258  JNZ 0x00c4d23d
00c4d25a  LEA RAX,[0x1973f20]
00c4d261  CALL 0x0041e320
00c4d266  MOV RDX,RAX
00c4d269  MOV RAX,qword ptr [RSP + 0x168]
00c4d271  JMP 0x00c4d1dd
00c4d276  MOV RDX,qword ptr [RDX + RSI*0x1 + 0x10]
00c4d27b  NOP dword ptr [RAX + RAX*0x1]
00c4d280  JMP 0x00c4d1dd
00c4d285  MOV qword ptr [RSP + 0x8],RAX
00c4d28a  MOV qword ptr [RSP + 0x10],RBX
00c4d28f  MOV qword ptr [RSP + 0x18],RCX
00c4d294  CALL 0x0048a280
00c4d299  MOV RAX,qword ptr [RSP + 0x8]
00c4d29e  MOV RBX,qword ptr [RSP + 0x10]
00c4d2a3  MOV RCX,qword ptr [RSP + 0x18]
00c4d2a8  JMP 0x00c4bea0
