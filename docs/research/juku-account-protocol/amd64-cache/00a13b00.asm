; mv-daemon/provider.(*OfflineCacheStore).Set
00a13b00  LEA R12,[RSP + -0x110]
00a13b08  CMP R12,qword ptr [R14 + 0x10]
00a13b0c  JBE 0x00a140bb
00a13b12  PUSH RBP
00a13b13  MOV RBP,RSP
00a13b16  SUB RSP,0x188
00a13b1d  NOP dword ptr [RAX]
00a13b20  TEST RBX,RBX
00a13b23  JZ 0x00a140ae
00a13b29  MOV qword ptr [RSP + 0x198],RAX
00a13b31  MOV qword ptr [RSP + 0x1a0],RBX
00a13b39  MOV RAX,qword ptr [RBX + 0x20]
00a13b3d  MOV RBX,qword ptr [RBX + 0x28]
00a13b41  CALL 0x004b0460
00a13b46  CALL 0x004af740
00a13b4b  MOV qword ptr [RSP + 0x80],RAX
00a13b53  MOV qword ptr [RSP + 0x50],RBX
00a13b58  MOV RCX,qword ptr [RSP + 0x1a0]
00a13b60  MOV RAX,qword ptr [RCX]
00a13b63  MOV RBX,qword ptr [RCX + 0x8]
00a13b67  CALL 0x004b0460
00a13b6c  CALL 0x004af740
00a13b71  MOV qword ptr [RSP + 0x180],RAX
00a13b79  MOV qword ptr [RSP + 0x68],RBX
00a13b7e  MOV RCX,qword ptr [RSP + 0x1a0]
00a13b86  MOV RAX,qword ptr [RCX + 0x10]
00a13b8a  MOV RBX,qword ptr [RCX + 0x18]
00a13b8e  CALL 0x004b0460
00a13b93  CALL 0x004af740
00a13b98  MOV RCX,qword ptr [RSP + 0x50]
00a13b9d  TEST RCX,RCX
00a13ba0  MOV RDX,qword ptr [RSP + 0x68]
00a13ba5  CMOVZ RCX,RDX
00a13ba9  MOV RSI,qword ptr [RSP + 0x80]
00a13bb1  MOV RDI,qword ptr [RSP + 0x180]
00a13bb9  CMOVZ RSI,RDI
00a13bbd  TEST RCX,RCX
00a13bc0  CMOVZ RCX,RBX
00a13bc4  CMOVZ RSI,RAX
00a13bc8  TEST RCX,RCX
00a13bcb  JZ 0x00a1407d
00a13bd1  MOV qword ptr [RSP + 0x50],RBX
00a13bd6  MOV qword ptr [RSP + 0x80],RAX
00a13bde  MOV qword ptr [RSP + 0x178],RSI
00a13be6  MOV qword ptr [RSP + 0x60],RCX
00a13beb  NOP
00a13bec  NOP
00a13bed  MOV R8,RAX
00a13bf0  XOR EAX,EAX
00a13bf2  MOV R9,qword ptr [RSP + 0x198]
00a13bfa  MOV R10D,0x1
00a13c00  CMPXCHG.LOCK dword ptr [R9],R10D
00a13c05  SETZ R10B
00a13c09  TEST R10B,R10B
00a13c0c  JNZ 0x00a13c45
00a13c0e  MOV RAX,R9
00a13c11  CALL 0x00493480
00a13c16  MOV RCX,qword ptr [RSP + 0x60]
00a13c1b  MOV RDX,qword ptr [RSP + 0x68]
00a13c20  MOV RBX,qword ptr [RSP + 0x50]
00a13c25  MOV RSI,qword ptr [RSP + 0x178]
00a13c2d  MOV RDI,qword ptr [RSP + 0x180]
00a13c35  MOV R8,qword ptr [RSP + 0x80]
00a13c3d  MOV R9,qword ptr [RSP + 0x198]
00a13c45  MOV R10,qword ptr [R9 + 0x8]
00a13c49  MOV qword ptr [RSP + 0x78],R10
00a13c4e  NOP
00a13c4f  NOP
00a13c50  MOV R11D,0xffffffff
00a13c56  XADD.LOCK dword ptr [R9],R11D
00a13c5b  NOP dword ptr [RAX + RAX*0x1]
00a13c60  DEC R11D
00a13c63  JZ 0x00a13ca0
00a13c65  MOV RAX,R9
00a13c68  MOV EBX,R11D
00a13c6b  CALL 0x00493760
00a13c70  MOV RCX,qword ptr [RSP + 0x60]
00a13c75  MOV RDX,qword ptr [RSP + 0x68]
00a13c7a  MOV RBX,qword ptr [RSP + 0x50]
00a13c7f  MOV RSI,qword ptr [RSP + 0x178]
00a13c87  MOV RDI,qword ptr [RSP + 0x180]
00a13c8f  MOV R8,qword ptr [RSP + 0x80]
00a13c97  MOV R10,qword ptr [RSP + 0x78]
00a13c9c  NOP dword ptr [RAX]
00a13ca0  TEST R10,R10
00a13ca3  JZ 0x00a1404c
00a13ca9  CALL 0x004c7f40
00a13cae  NOP
00a13caf  BT RAX,0x3f
00a13cb4  JNC 0x00a13ccc
00a13cb6  LEA RDX,[RAX + RAX*0x1]
00a13cba  SHR RDX,0x1f
00a13cbe  MOV RSI,0xdd7b17f80
00a13cc8  LEA RBX,[RDX + RSI*0x1]
00a13ccc  MOV RDX,-0xe7791f700
00a13cd6  ADD RDX,RBX
00a13cd9  MOV RSI,qword ptr [RSP + 0x1a0]
00a13ce1  CMP qword ptr [RSI + 0xc0],0x0
00a13ce9  JNZ 0x00a13cf2
00a13ceb  MOV qword ptr [RSI + 0xc0],RDX
00a13cf2  MOV qword ptr [RSP + 0x40],RDX
00a13cf7  MOV RBX,qword ptr [RSI + 0xa8]
00a13cfe  MOVZX EDI,byte ptr [RSI + 0x98]
00a13d05  MOV qword ptr [RSP + 0x58],RDI
00a13d0a  TEST RBX,RBX
00a13d0d  JNZ 0x00a13d15
00a13d0f  XOR EBX,EBX
00a13d11  XOR EAX,EAX
00a13d13  JMP 0x00a13d4f
00a13d15  MOV RCX,qword ptr [RSI + 0xb0]
00a13d1c  MOV RAX,qword ptr [RSI + 0xa0]
00a13d23  CALL 0x00481f80
00a13d28  MOV RBX,RAX
00a13d2b  LEA RAX,[0xdc15a0]
00a13d32  CALL 0x00532d60
00a13d37  TEST RDI,RDI
00a13d3a  JZ 0x00a13d42
00a13d3c  XOR EBX,EBX
00a13d3e  XOR EAX,EAX
00a13d40  JMP 0x00a13d4f
00a13d42  MOV RCX,RBX
00a13d45  MOV RBX,RAX
00a13d48  XOR EAX,EAX
00a13d4a  CALL 0x0046b920
00a13d4f  MOV qword ptr [RSP + 0x48],RBX
00a13d54  MOV qword ptr [RSP + 0x70],RAX
00a13d59  LEA RCX,[RSP + 0x88]
00a13d61  MOV EDX,0x3
00a13d66  MOVUPS xmmword ptr [RCX],XMM15
00a13d6a  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00a13d6f  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00a13d74  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00a13d79  ADD RCX,0x40
00a13d7d  NOP dword ptr [RAX]
00a13d80  DEC EDX
00a13d82  JNZ 0x00a13d66
00a13d84  MOVUPS xmmword ptr [RCX],XMM15
00a13d88  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00a13d8d  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00a13d92  MOV RAX,qword ptr [RSP + 0x178]
00a13d9a  MOV RBX,qword ptr [RSP + 0x60]
00a13d9f  NOP
00a13da0  CALL 0x00481ee0
00a13da5  LEA RCX,[0xdd29c0]
00a13dac  MOV qword ptr [RSP + 0x88],RCX
00a13db4  MOV qword ptr [RSP + 0x90],RAX
00a13dbc  MOV RAX,qword ptr [RSP + 0x180]
00a13dc4  MOV RBX,qword ptr [RSP + 0x68]
00a13dc9  CALL 0x00481ee0
00a13dce  LEA RCX,[0xdd29c0]
00a13dd5  MOV qword ptr [RSP + 0x98],RCX
00a13ddd  MOV qword ptr [RSP + 0xa0],RAX
00a13de5  MOV RAX,qword ptr [RSP + 0x80]
00a13ded  MOV RBX,qword ptr [RSP + 0x50]
00a13df2  CALL 0x00481ee0
00a13df7  LEA RCX,[0xdd29c0]
00a13dfe  MOV qword ptr [RSP + 0xa8],RCX
00a13e06  MOV qword ptr [RSP + 0xb0],RAX
00a13e0e  MOV RCX,qword ptr [RSP + 0x1a0]
00a13e16  MOV RAX,qword ptr [RCX + 0x30]
00a13e1a  MOV RBX,qword ptr [RCX + 0x38]
00a13e1e  NOP
00a13e20  CALL 0x00481ee0
00a13e25  LEA RCX,[0xdd29c0]
00a13e2c  MOV qword ptr [RSP + 0xb8],RCX
00a13e34  MOV qword ptr [RSP + 0xc0],RAX
00a13e3c  MOV RCX,qword ptr [RSP + 0x1a0]
00a13e44  MOV RAX,qword ptr [RCX + 0x40]
00a13e48  MOV RBX,qword ptr [RCX + 0x48]
00a13e4c  CALL 0x00481ee0
00a13e51  LEA RCX,[0xdd29c0]
00a13e58  MOV qword ptr [RSP + 0xc8],RCX
00a13e60  MOV qword ptr [RSP + 0xd0],RAX
00a13e68  MOV RCX,qword ptr [RSP + 0x1a0]
00a13e70  MOV RAX,qword ptr [RCX + 0x50]
00a13e74  MOV RBX,qword ptr [RCX + 0x58]
00a13e78  CALL 0x00481ee0
00a13e7d  LEA RCX,[0xdd29c0]
00a13e84  MOV qword ptr [RSP + 0xd8],RCX
00a13e8c  MOV qword ptr [RSP + 0xe0],RAX
00a13e94  MOV RCX,qword ptr [RSP + 0x1a0]
00a13e9c  MOV RAX,qword ptr [RCX + 0x60]
00a13ea0  MOV RBX,qword ptr [RCX + 0x68]
00a13ea4  CALL 0x00481ee0
00a13ea9  LEA RCX,[0xdd29c0]
00a13eb0  MOV qword ptr [RSP + 0xe8],RCX
00a13eb8  MOV qword ptr [RSP + 0xf0],RAX
00a13ec0  MOV RCX,qword ptr [RSP + 0x1a0]
00a13ec8  MOV RAX,qword ptr [RCX + 0x70]
00a13ecc  MOV RBX,qword ptr [RCX + 0x78]
00a13ed0  CALL 0x00481ee0
00a13ed5  LEA RCX,[0xdd29c0]
00a13edc  MOV qword ptr [RSP + 0xf8],RCX
00a13ee4  MOV qword ptr [RSP + 0x100],RAX
00a13eec  MOV RCX,qword ptr [RSP + 0x1a0]
00a13ef4  MOV RAX,qword ptr [RCX + 0x80]
00a13efb  MOV RBX,qword ptr [RCX + 0x88]
00a13f02  CALL 0x00481ee0
00a13f07  LEA RCX,[0xdd29c0]
00a13f0e  MOV qword ptr [RSP + 0x108],RCX
00a13f16  MOV qword ptr [RSP + 0x110],RAX
00a13f1e  MOV RCX,qword ptr [RSP + 0x1a0]
00a13f26  MOV RAX,qword ptr [RCX + 0x90]
00a13f2d  CALL 0x00481e60
00a13f32  LEA RCX,[0xdd2b80]
00a13f39  MOV qword ptr [RSP + 0x118],RCX
00a13f41  MOV qword ptr [RSP + 0x120],RAX
00a13f49  MOV RAX,qword ptr [RSP + 0x58]
00a13f4e  CALL 0x00481e60
00a13f53  LEA RCX,[0xdd2c00]
00a13f5a  MOV qword ptr [RSP + 0x128],RCX
00a13f62  MOV qword ptr [RSP + 0x130],RAX
00a13f6a  MOV RAX,qword ptr [RSP + 0x70]
00a13f6f  MOV RBX,qword ptr [RSP + 0x48]
00a13f74  CALL 0x00481ee0
00a13f79  LEA RCX,[0xdd29c0]
00a13f80  MOV qword ptr [RSP + 0x138],RCX
00a13f88  MOV qword ptr [RSP + 0x140],RAX
00a13f90  MOV RCX,qword ptr [RSP + 0x1a0]
00a13f98  MOV RAX,qword ptr [RCX + 0xb8]
00a13f9f  NOP
00a13fa0  CALL 0x00481e60
00a13fa5  LEA RCX,[0xdd2c00]
00a13fac  MOV qword ptr [RSP + 0x148],RCX
00a13fb4  MOV qword ptr [RSP + 0x150],RAX
00a13fbc  MOV RAX,qword ptr [RSP + 0x40]
00a13fc1  CALL 0x00481e60
00a13fc6  LEA RCX,[0xdd2b80]
00a13fcd  MOV qword ptr [RSP + 0x158],RCX
00a13fd5  MOV qword ptr [RSP + 0x160],RAX
00a13fdd  MOV RCX,qword ptr [RSP + 0x1a0]
00a13fe5  MOV RAX,qword ptr [RCX + 0xc0]
00a13fec  CALL 0x00481e60
00a13ff1  LEA RCX,[0xdd2b80]
00a13ff8  MOV qword ptr [RSP + 0x168],RCX
00a14000  MOV qword ptr [RSP + 0x170],RAX
00a14008  MOV RAX,qword ptr [RSP + 0x78]
00a1400d  LEA RBX,[0x113fde8]
00a14014  LEA RCX,[0x19b5220]
00a1401b  LEA RDI,[0xf6db6e]
00a14022  MOV ESI,0x2fe
00a14027  LEA R8,[RSP + 0x88]
00a1402f  MOV R9D,0xf
00a14035  MOV R10,R9
00a14038  CALL 0x00748220
00a1403d  MOV RAX,RCX
00a14040  MOV RBX,RDI
00a14043  ADD RSP,0x188
00a1404a  POP RBP
00a1404b  RET
00a1404c  LEA RAX,[0xe21740]
00a14053  CALL 0x00421f00
00a14058  MOV qword ptr [RAX + 0x8],0x22
00a14060  LEA RCX,[0xf33ff4]
00a14067  MOV qword ptr [RAX],RCX
00a1406a  MOV RBX,RAX
00a1406d  LEA RAX,[0x1139800]
00a14074  ADD RSP,0x188
00a1407b  POP RBP
00a1407c  RET
00a1407d  LEA RAX,[0xe21740]
00a14084  CALL 0x00421f00
00a14089  MOV qword ptr [RAX + 0x8],0x2a
00a14091  LEA RCX,[0xf3e009]
00a14098  MOV qword ptr [RAX],RCX
00a1409b  MOV RBX,RAX
00a1409e  LEA RAX,[0x1139800]
00a140a5  ADD RSP,0x188
00a140ac  POP RBP
00a140ad  RET
00a140ae  XOR EAX,EAX
00a140b0  XOR EBX,EBX
00a140b2  ADD RSP,0x188
00a140b9  POP RBP
00a140ba  RET
00a140bb  MOV qword ptr [RSP + 0x8],RAX
00a140c0  MOV qword ptr [RSP + 0x10],RBX
00a140c5  CALL 0x0048a280
00a140ca  MOV RAX,qword ptr [RSP + 0x8]
00a140cf  MOV RBX,qword ptr [RSP + 0x10]
00a140d4  JMP 0x00a13b00
