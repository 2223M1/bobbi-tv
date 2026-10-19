; mv-daemon/provider.(*LifeSyncManager).handleEventForDir
00a04900  LEA R12,[RSP + -0x110]
00a04908  CMP R12,qword ptr [R14 + 0x10]
00a0490c  JBE 0x00a052e8
00a04912  PUSH RBP
00a04913  MOV RBP,RSP
00a04916  SUB RSP,0x188
00a0491d  MOV qword ptr [RSP + 0x218],RAX
00a04925  MOV qword ptr [RSP + 0x230],RDI
00a0492d  MOV qword ptr [RSP + 0x228],RCX
00a04935  MOV qword ptr [RSP + 0x240],R8
00a0493d  MOV qword ptr [RSP + 0x220],RBX
00a04945  MOV qword ptr [RSP + 0x238],RSI
00a0494d  MOV RDX,qword ptr [RSP + 0x1d0]
00a04955  MOV R9,qword ptr [RSP + 0x1c8]
00a0495d  LEA R10,[RDX + -0x1]
00a04961  JMP 0x00a04966
00a04963  DEC R10
00a04966  TEST R10,R10
00a04969  JL 0x00a04984
00a0496b  MOVZX R11D,byte ptr [R9 + R10*0x1]
00a04970  CMP R11B,0x2f
00a04974  JZ 0x00a04984
00a04976  CMP R11B,0x2e
00a0497a  JNZ 0x00a04963
00a0497c  ADD R9,R10
00a0497f  SUB RDX,R10
00a04982  JMP 0x00a04989
00a04984  XOR EDX,EDX
00a04986  XOR R9D,R9D
00a04989  MOV RAX,R9
00a0498c  MOV RBX,RDX
00a0498f  CALL 0x004af740
00a04994  NOP
00a04995  TEST RBX,RBX
00a04998  JZ 0x00a049b2
00a0499a  CMP byte ptr [RAX],0x2e
00a0499d  JNZ 0x00a049b2
00a0499f  DEC RBX
00a049a2  MOV RDX,RBX
00a049a5  NEG RDX
00a049a8  SAR RDX,0x3f
00a049ac  AND EDX,0x1
00a049af  ADD RAX,RDX
00a049b2  CMP qword ptr [RSP + 0x200],0x0
00a049bb  JZ 0x00a049c2
00a049bd  XOR ECX,ECX
00a049bf  NOP
00a049c0  JMP 0x00a049eb
00a049c2  CALL 0x009e5040
00a049c7  MOV RCX,qword ptr [0x01990190]
00a049ce  MOV RDI,RBX
00a049d1  MOV RBX,RCX
00a049d4  MOV RCX,RAX
00a049d7  LEA RAX,[0xe16280]
00a049de  NOP
00a049e0  CALL 0x00412ee0
00a049e5  MOVZX ECX,byte ptr [RAX]
00a049e8  XOR ECX,0x1
00a049eb  MOV RDX,qword ptr [RSP + 0x1a8]
00a049f3  DEC RDX
00a049f6  NOP word ptr [RAX + RAX*0x1]
00a049ff  NOP
00a04a00  CMP RDX,0x17
00a04a04  JA 0x00a052dd
00a04a0a  MOV byte ptr [RSP + 0xb7],CL
00a04a11  LEA RAX,[0x114c640]
00a04a18  JMP qword ptr [RAX + RDX*0x8]
00a04a1b  LEA RAX,[RSP + 0x138]
00a04a23  MOVUPS xmmword ptr [RAX],XMM15
00a04a27  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00a04a2c  MOV RDX,qword ptr [RSP + 0x1b8]
00a04a34  MOV RSI,qword ptr [RSP + 0x1c0]
00a04a3c  MOV qword ptr [RSP + 0x140],RSI
00a04a44  MOV qword ptr [RSP + 0x138],RDX
00a04a4c  MOV RDX,qword ptr [RSP + 0x1d8]
00a04a54  MOV RSI,qword ptr [RSP + 0x1e0]
00a04a5c  MOV qword ptr [RSP + 0x150],RSI
00a04a64  MOV qword ptr [RSP + 0x148],RDX
00a04a6c  MOV EBX,0x2
00a04a71  MOV RCX,RBX
00a04a74  CALL 0x00a01fa0
00a04a79  MOVZX EDX,byte ptr [RSP + 0xb7]
00a04a81  TEST DL,DL
00a04a83  JZ 0x00a04a8a
00a04a85  CALL 0x00a02060
00a04a8a  MOV RAX,qword ptr [RSP + 0x218]
00a04a92  LEA RBX,[RSP + 0x198]
00a04a9a  MOV RCX,qword ptr [RSP + 0x238]
00a04aa2  MOV RDI,qword ptr [RSP + 0x240]
00a04aaa  CALL 0x00a09600
00a04aaf  MOV qword ptr [RSP + 0x130],RBX
00a04ab7  MOV qword ptr [RSP + 0x128],RAX
00a04abf  MOV RAX,qword ptr [0x01990208]
00a04ac6  MOV RDX,qword ptr [RSP + 0x230]
00a04ace  MOV RBX,qword ptr [RDX + 0x10]
00a04ad2  MOV RCX,qword ptr [RDX + 0x18]
00a04ad6  MOV R8,qword ptr [RSP + 0x1b8]
00a04ade  MOV R9,qword ptr [RSP + 0x1c0]
00a04ae6  LEA RDX,[RSP + 0x128]
00a04aee  MOV qword ptr [RSP],RDX
00a04af2  MOV qword ptr [RSP + 0x8],0x1
00a04afb  MOV qword ptr [RSP + 0x10],0x1
00a04b04  LEA RDI,[0xf02951]
00a04b0b  MOV ESI,0x8
00a04b10  CALL 0x00a3d220
00a04b15  TEST RBX,RBX
00a04b18  JZ 0x00a04bb0
00a04b1e  NOP
00a04b20  TEST RAX,RAX
00a04b23  JZ 0x00a04bb0
00a04b29  MOV RDX,RSP
00a04b2c  LEA RSI,[RSP + 0x198]
00a04b34  MOVUPS XMM14,xmmword ptr [RSI]
00a04b38  MOVUPS xmmword ptr [RDX],XMM14
00a04b3c  MOVUPS XMM14,xmmword ptr [RSI + 0x10]
00a04b41  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a04b46  MOVUPS XMM14,xmmword ptr [RSI + 0x20]
00a04b4b  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a04b50  MOVUPS XMM14,xmmword ptr [RSI + 0x30]
00a04b55  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a04b5a  MOVUPS XMM14,xmmword ptr [RSI + 0x40]
00a04b5f  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a04b64  MOVUPS XMM14,xmmword ptr [RSI + 0x50]
00a04b69  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a04b6e  MOVUPS XMM14,xmmword ptr [RSI + 0x60]
00a04b73  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a04b78  MOVUPS XMM14,xmmword ptr [RSI + 0x70]
00a04b7d  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a04b82  MOV RAX,qword ptr [RSP + 0x218]
00a04b8a  MOV RBX,qword ptr [RSP + 0x220]
00a04b92  MOV RCX,qword ptr [RSP + 0x228]
00a04b9a  MOV RDI,qword ptr [RSP + 0x230]
00a04ba2  CALL 0x00a09140
00a04ba7  ADD RSP,0x188
00a04bae  POP RBP
00a04baf  RET
00a04bb0  LEA RCX,[RSP + 0xb8]
00a04bb8  MOVUPS xmmword ptr [RCX],XMM15
00a04bbc  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00a04bc1  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00a04bc6  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00a04bcb  MOV RAX,qword ptr [RSP + 0x1c8]
00a04bd3  MOV RBX,qword ptr [RSP + 0x1d0]
00a04bdb  NOP dword ptr [RAX + RAX*0x1]
00a04be0  CALL 0x00481ee0
00a04be5  LEA RCX,[0xdd29c0]
00a04bec  MOV qword ptr [RSP + 0xb8],RCX
00a04bf4  MOV qword ptr [RSP + 0xc0],RAX
00a04bfc  MOV RBX,qword ptr [RSP + 0x1c0]
00a04c04  MOV RAX,qword ptr [RSP + 0x1b8]
00a04c0c  CALL 0x00481ee0
00a04c11  LEA RCX,[0xdd29c0]
00a04c18  MOV qword ptr [RSP + 0xc8],RCX
00a04c20  MOV qword ptr [RSP + 0xd0],RAX
00a04c28  MOV RAX,qword ptr [RSP + 0x200]
00a04c30  CALL 0x00481e60
00a04c35  LEA RCX,[0xdd2c00]
00a04c3c  MOV qword ptr [RSP + 0xd8],RCX
00a04c44  MOV qword ptr [RSP + 0xe0],RAX
00a04c4c  MOV RCX,qword ptr [RSP + 0x230]
00a04c54  MOV RAX,qword ptr [RCX + 0x40]
00a04c58  MOV RBX,qword ptr [RCX + 0x48]
00a04c5c  NOP dword ptr [RAX]
00a04c60  CALL 0x00481ee0
00a04c65  LEA RCX,[0xdd29c0]
00a04c6c  MOV qword ptr [RSP + 0xe8],RCX
00a04c74  MOV qword ptr [RSP + 0xf0],RAX
00a04c7c  LEA RCX,[0xa05360]
00a04c83  MOV qword ptr [RSP + 0x158],RCX
00a04c8b  MOV qword ptr [RSP + 0x168],0x65
00a04c97  LEA RCX,[0xf5fd86]
00a04c9e  MOV qword ptr [RSP + 0x160],RCX
00a04ca6  MOV qword ptr [RSP + 0x178],0x4
00a04cb2  MOV qword ptr [RSP + 0x180],0x4
00a04cbe  LEA RCX,[RSP + 0xb8]
00a04cc6  MOV qword ptr [RSP + 0x170],RCX
00a04cce  MOV RAX,qword ptr [0x01990148]
00a04cd5  XOR EBX,EBX
00a04cd7  MOV ECX,0x2
00a04cdc  LEA RDI,[RSP + 0x158]
00a04ce4  CALL 0x0054d540
00a04ce9  MOVZX ECX,byte ptr [RSP + 0xb7]
00a04cf1  TEST CL,CL
00a04cf3  JZ 0x00a04d90
00a04cf9  MOV RDX,RSP
00a04cfc  LEA R9,[RSP + 0x198]
00a04d04  MOVUPS XMM14,xmmword ptr [R9]
00a04d08  MOVUPS xmmword ptr [RDX],XMM14
00a04d0c  MOVUPS XMM14,xmmword ptr [R9 + 0x10]
00a04d11  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a04d16  MOVUPS XMM14,xmmword ptr [R9 + 0x20]
00a04d1b  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a04d20  MOVUPS XMM14,xmmword ptr [R9 + 0x30]
00a04d25  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a04d2a  MOVUPS XMM14,xmmword ptr [R9 + 0x40]
00a04d2f  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a04d34  MOVUPS XMM14,xmmword ptr [R9 + 0x50]
00a04d39  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a04d3e  MOVUPS XMM14,xmmword ptr [R9 + 0x60]
00a04d43  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a04d48  MOVUPS XMM14,xmmword ptr [R9 + 0x70]
00a04d4d  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a04d52  MOV RAX,qword ptr [RSP + 0x218]
00a04d5a  MOV RBX,qword ptr [RSP + 0x220]
00a04d62  MOV RCX,qword ptr [RSP + 0x228]
00a04d6a  MOV RDI,qword ptr [RSP + 0x230]
00a04d72  MOV RSI,qword ptr [RSP + 0x238]
00a04d7a  MOV R8,qword ptr [RSP + 0x240]
00a04d82  CALL 0x00a05420
00a04d87  ADD RSP,0x188
00a04d8e  POP RBP
00a04d8f  RET
00a04d90  MOV RDX,RSP
00a04d93  LEA R9,[RSP + 0x198]
00a04d9b  MOVUPS XMM14,xmmword ptr [R9]
00a04d9f  MOVUPS xmmword ptr [RDX],XMM14
00a04da3  MOVUPS XMM14,xmmword ptr [R9 + 0x10]
00a04da8  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a04dad  MOVUPS XMM14,xmmword ptr [R9 + 0x20]
00a04db2  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a04db7  MOVUPS XMM14,xmmword ptr [R9 + 0x30]
00a04dbc  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a04dc1  MOVUPS XMM14,xmmword ptr [R9 + 0x40]
00a04dc6  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a04dcb  MOVUPS XMM14,xmmword ptr [R9 + 0x50]
00a04dd0  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a04dd5  MOVUPS XMM14,xmmword ptr [R9 + 0x60]
00a04dda  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a04ddf  MOVUPS XMM14,xmmword ptr [R9 + 0x70]
00a04de4  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a04de9  MOV RAX,qword ptr [RSP + 0x218]
00a04df1  MOV RBX,qword ptr [RSP + 0x220]
00a04df9  MOV RCX,qword ptr [RSP + 0x228]
00a04e01  MOV RDI,qword ptr [RSP + 0x230]
00a04e09  MOV RSI,qword ptr [RSP + 0x238]
00a04e11  MOV R8,qword ptr [RSP + 0x240]
00a04e19  CALL 0x00a063a0
00a04e1e  ADD RSP,0x188
00a04e25  POP RBP
00a04e26  RET
00a04e27  LEA RAX,[RSP + 0x138]
00a04e2f  MOVUPS xmmword ptr [RAX],XMM15
00a04e33  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00a04e38  MOV RDX,qword ptr [RSP + 0x1b8]
00a04e40  MOV RSI,qword ptr [RSP + 0x1c0]
00a04e48  MOV qword ptr [RSP + 0x140],RSI
00a04e50  MOV qword ptr [RSP + 0x138],RDX
00a04e58  MOV RDX,qword ptr [RSP + 0x1d8]
00a04e60  MOV RSI,qword ptr [RSP + 0x1e0]
00a04e68  MOV qword ptr [RSP + 0x150],RSI
00a04e70  MOV qword ptr [RSP + 0x148],RDX
00a04e78  MOV EBX,0x2
00a04e7d  MOV RCX,RBX
00a04e80  CALL 0x00a01fa0
00a04e85  MOVZX EDX,byte ptr [RSP + 0xb7]
00a04e8d  TEST DL,DL
00a04e8f  JZ 0x00a04f21
00a04e95  CALL 0x00a02060
00a04e9a  MOV RAX,RSP
00a04e9d  LEA RCX,[RSP + 0x198]
00a04ea5  MOVUPS XMM14,xmmword ptr [RCX]
00a04ea9  MOVUPS xmmword ptr [RAX],XMM14
00a04ead  MOVUPS XMM14,xmmword ptr [RCX + 0x10]
00a04eb2  MOVUPS xmmword ptr [RAX + 0x10],XMM14
00a04eb7  MOVUPS XMM14,xmmword ptr [RCX + 0x20]
00a04ebc  MOVUPS xmmword ptr [RAX + 0x20],XMM14
00a04ec1  MOVUPS XMM14,xmmword ptr [RCX + 0x30]
00a04ec6  MOVUPS xmmword ptr [RAX + 0x30],XMM14
00a04ecb  MOVUPS XMM14,xmmword ptr [RCX + 0x40]
00a04ed0  MOVUPS xmmword ptr [RAX + 0x40],XMM14
00a04ed5  MOVUPS XMM14,xmmword ptr [RCX + 0x50]
00a04eda  MOVUPS xmmword ptr [RAX + 0x50],XMM14
00a04edf  MOVUPS XMM14,xmmword ptr [RCX + 0x60]
00a04ee4  MOVUPS xmmword ptr [RAX + 0x60],XMM14
00a04ee9  MOVUPS XMM14,xmmword ptr [RCX + 0x70]
00a04eee  MOVUPS xmmword ptr [RAX + 0x70],XMM14
00a04ef3  MOV RAX,qword ptr [RSP + 0x218]
00a04efb  MOV RBX,qword ptr [RSP + 0x220]
00a04f03  MOV RCX,qword ptr [RSP + 0x228]
00a04f0b  MOV RDI,qword ptr [RSP + 0x230]
00a04f13  CALL 0x00a07d20
00a04f18  ADD RSP,0x188
00a04f1f  POP RBP
00a04f20  RET
00a04f21  MOV RDX,RSP
00a04f24  LEA RSI,[RSP + 0x198]
00a04f2c  MOVUPS XMM14,xmmword ptr [RSI]
00a04f30  MOVUPS xmmword ptr [RDX],XMM14
00a04f34  MOVUPS XMM14,xmmword ptr [RSI + 0x10]
00a04f39  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a04f3e  MOVUPS XMM14,xmmword ptr [RSI + 0x20]
00a04f43  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a04f48  MOVUPS XMM14,xmmword ptr [RSI + 0x30]
00a04f4d  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a04f52  MOVUPS XMM14,xmmword ptr [RSI + 0x40]
00a04f57  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a04f5c  MOVUPS XMM14,xmmword ptr [RSI + 0x50]
00a04f61  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a04f66  MOVUPS XMM14,xmmword ptr [RSI + 0x60]
00a04f6b  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a04f70  MOVUPS XMM14,xmmword ptr [RSI + 0x70]
00a04f75  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a04f7a  MOV RAX,qword ptr [RSP + 0x218]
00a04f82  MOV RBX,qword ptr [RSP + 0x220]
00a04f8a  MOV RCX,qword ptr [RSP + 0x228]
00a04f92  MOV RDI,qword ptr [RSP + 0x230]
00a04f9a  CALL 0x00a08820
00a04f9f  ADD RSP,0x188
00a04fa6  POP RBP
00a04fa7  RET
00a04fa8  TEST CL,CL
00a04faa  JZ 0x00a0514e
00a04fb0  LEA RCX,[RSP + 0xf8]
00a04fb8  MOVUPS xmmword ptr [RCX],XMM15
00a04fbc  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00a04fc1  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00a04fc6  MOV RAX,qword ptr [RSP + 0x1c8]
00a04fce  MOV RBX,qword ptr [RSP + 0x1d0]
00a04fd6  CALL 0x00481ee0
00a04fdb  LEA RCX,[0xdd29c0]
00a04fe2  MOV qword ptr [RSP + 0xf8],RCX
00a04fea  MOV qword ptr [RSP + 0x100],RAX
00a04ff2  MOV RAX,qword ptr [RSP + 0x1b8]
00a04ffa  MOV RBX,qword ptr [RSP + 0x1c0]
00a05002  CALL 0x00481ee0
00a05007  LEA RCX,[0xdd29c0]
00a0500e  MOV qword ptr [RSP + 0x108],RCX
00a05016  MOV qword ptr [RSP + 0x110],RAX
00a0501e  MOV RCX,qword ptr [RSP + 0x230]
00a05026  MOV RAX,qword ptr [RCX + 0x40]
00a0502a  MOV RBX,qword ptr [RCX + 0x48]
00a0502e  CALL 0x00481ee0
00a05033  LEA RCX,[0xdd29c0]
00a0503a  MOV qword ptr [RSP + 0x118],RCX
00a05042  MOV qword ptr [RSP + 0x120],RAX
00a0504a  LEA RCX,[0xa053c0]
00a05051  MOV qword ptr [RSP + 0x158],RCX
00a05059  MOV qword ptr [RSP + 0x168],0x57
00a05065  LEA RCX,[0xf5c50a]
00a0506c  MOV qword ptr [RSP + 0x160],RCX
00a05074  MOV qword ptr [RSP + 0x178],0x3
00a05080  MOV qword ptr [RSP + 0x180],0x3
00a0508c  LEA RCX,[RSP + 0xf8]
00a05094  MOV qword ptr [RSP + 0x170],RCX
00a0509c  MOV RAX,qword ptr [0x01990148]
00a050a3  XOR EBX,EBX
00a050a5  MOV ECX,0x2
00a050aa  LEA RDI,[RSP + 0x158]
00a050b2  CALL 0x0054d540
00a050b7  MOV RCX,RSP
00a050ba  LEA RDX,[RSP + 0x198]
00a050c2  MOVUPS XMM14,xmmword ptr [RDX]
00a050c6  MOVUPS xmmword ptr [RCX],XMM14
00a050ca  MOVUPS XMM14,xmmword ptr [RDX + 0x10]
00a050cf  MOVUPS xmmword ptr [RCX + 0x10],XMM14
00a050d4  MOVUPS XMM14,xmmword ptr [RDX + 0x20]
00a050d9  MOVUPS xmmword ptr [RCX + 0x20],XMM14
00a050de  MOVUPS XMM14,xmmword ptr [RDX + 0x30]
00a050e3  MOVUPS xmmword ptr [RCX + 0x30],XMM14
00a050e8  MOVUPS XMM14,xmmword ptr [RDX + 0x40]
00a050ed  MOVUPS xmmword ptr [RCX + 0x40],XMM14
00a050f2  MOVUPS XMM14,xmmword ptr [RDX + 0x50]
00a050f7  MOVUPS xmmword ptr [RCX + 0x50],XMM14
00a050fc  MOVUPS XMM14,xmmword ptr [RDX + 0x60]
00a05101  MOVUPS xmmword ptr [RCX + 0x60],XMM14
00a05106  MOVUPS XMM14,xmmword ptr [RDX + 0x70]
00a0510b  MOVUPS xmmword ptr [RCX + 0x70],XMM14
00a05110  MOV RAX,qword ptr [RSP + 0x218]
00a05118  MOV RBX,qword ptr [RSP + 0x220]
00a05120  MOV RCX,qword ptr [RSP + 0x228]
00a05128  MOV RDI,qword ptr [RSP + 0x230]
00a05130  MOV RSI,qword ptr [RSP + 0x238]
00a05138  MOV R8,qword ptr [RSP + 0x240]
00a05140  CALL 0x00a05420
00a05145  ADD RSP,0x188
00a0514c  POP RBP
00a0514d  RET
00a0514e  MOV RDX,RSP
00a05151  LEA R9,[RSP + 0x198]
00a05159  MOVUPS XMM14,xmmword ptr [R9]
00a0515d  MOVUPS xmmword ptr [RDX],XMM14
00a05161  MOVUPS XMM14,xmmword ptr [R9 + 0x10]
00a05166  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a0516b  MOVUPS XMM14,xmmword ptr [R9 + 0x20]
00a05170  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a05175  MOVUPS XMM14,xmmword ptr [R9 + 0x30]
00a0517a  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a0517f  MOVUPS XMM14,xmmword ptr [R9 + 0x40]
00a05184  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a05189  MOVUPS XMM14,xmmword ptr [R9 + 0x50]
00a0518e  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a05193  MOVUPS XMM14,xmmword ptr [R9 + 0x60]
00a05198  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a0519d  MOVUPS XMM14,xmmword ptr [R9 + 0x70]
00a051a2  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a051a7  MOV RAX,qword ptr [RSP + 0x218]
00a051af  MOV RBX,qword ptr [RSP + 0x220]
00a051b7  MOV RCX,qword ptr [RSP + 0x228]
00a051bf  MOV RDI,qword ptr [RSP + 0x230]
00a051c7  MOV RSI,qword ptr [RSP + 0x238]
00a051cf  MOV R8,qword ptr [RSP + 0x240]
00a051d7  CALL 0x00a063a0
00a051dc  ADD RSP,0x188
00a051e3  POP RBP
00a051e4  RET
00a051e5  LEA RAX,[RSP + 0x138]
00a051ed  MOVUPS xmmword ptr [RAX],XMM15
00a051f1  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00a051f6  MOV RDX,qword ptr [RSP + 0x1b8]
00a051fe  MOV RSI,qword ptr [RSP + 0x1c0]
00a05206  MOV qword ptr [RSP + 0x140],RSI
00a0520e  MOV qword ptr [RSP + 0x138],RDX
00a05216  MOV RDX,qword ptr [RSP + 0x1d8]
00a0521e  MOV RSI,qword ptr [RSP + 0x1e0]
00a05226  MOV qword ptr [RSP + 0x150],RSI
00a0522e  MOV qword ptr [RSP + 0x148],RDX
00a05236  MOV EBX,0x2
00a0523b  MOV RCX,RBX
00a0523e  NOP
00a05240  CALL 0x00a01fa0
00a05245  MOVZX EDX,byte ptr [RSP + 0xb7]
00a0524d  TEST DL,DL
00a0524f  JZ 0x00a05256
00a05251  CALL 0x00a02060
00a05256  MOV RDX,RSP
00a05259  LEA RSI,[RSP + 0x198]
00a05261  MOVUPS XMM14,xmmword ptr [RSI]
00a05265  MOVUPS xmmword ptr [RDX],XMM14
00a05269  MOVUPS XMM14,xmmword ptr [RSI + 0x10]
00a0526e  MOVUPS xmmword ptr [RDX + 0x10],XMM14
00a05273  MOVUPS XMM14,xmmword ptr [RSI + 0x20]
00a05278  MOVUPS xmmword ptr [RDX + 0x20],XMM14
00a0527d  MOVUPS XMM14,xmmword ptr [RSI + 0x30]
00a05282  MOVUPS xmmword ptr [RDX + 0x30],XMM14
00a05287  MOVUPS XMM14,xmmword ptr [RSI + 0x40]
00a0528c  MOVUPS xmmword ptr [RDX + 0x40],XMM14
00a05291  MOVUPS XMM14,xmmword ptr [RSI + 0x50]
00a05296  MOVUPS xmmword ptr [RDX + 0x50],XMM14
00a0529b  MOVUPS XMM14,xmmword ptr [RSI + 0x60]
00a052a0  MOVUPS xmmword ptr [RDX + 0x60],XMM14
00a052a5  MOVUPS XMM14,xmmword ptr [RSI + 0x70]
00a052aa  MOVUPS xmmword ptr [RDX + 0x70],XMM14
00a052af  MOV RAX,qword ptr [RSP + 0x218]
00a052b7  MOV RBX,qword ptr [RSP + 0x220]
00a052bf  MOV RCX,qword ptr [RSP + 0x228]
00a052c7  MOV RDI,qword ptr [RSP + 0x230]
00a052cf  CALL 0x00a09140
00a052d4  ADD RSP,0x188
00a052db  POP RBP
00a052dc  RET
00a052dd  XOR EAX,EAX
00a052df  ADD RSP,0x188
00a052e6  POP RBP
00a052e7  RET
00a052e8  MOV qword ptr [RSP + 0x88],RAX
00a052f0  MOV qword ptr [RSP + 0x90],RBX
00a052f8  MOV qword ptr [RSP + 0x98],RCX
00a05300  MOV qword ptr [RSP + 0xa0],RDI
00a05308  MOV qword ptr [RSP + 0xa8],RSI
00a05310  MOV qword ptr [RSP + 0xb0],R8
00a05318  CALL 0x0048a280
00a0531d  MOV RAX,qword ptr [RSP + 0x88]
00a05325  MOV RBX,qword ptr [RSP + 0x90]
00a0532d  MOV RCX,qword ptr [RSP + 0x98]
00a05335  MOV RDI,qword ptr [RSP + 0xa0]
00a0533d  MOV RSI,qword ptr [RSP + 0xa8]
00a05345  MOV R8,qword ptr [RSP + 0xb0]
00a0534d  JMP 0x00a04900
