; mv-daemon/provider.(*TokenStore).Get
00a63de0  CMP RSP,qword ptr [R14 + 0x10]
00a63de4  JBE 0x00a63ef5
00a63dea  PUSH RBP
00a63deb  MOV RBP,RSP
00a63dee  SUB RSP,0x58
00a63df2  MOV qword ptr [RSP + 0x70],RBX
00a63df7  MOVQ qword ptr [RSP + 0x50],XMM15
00a63dfe  MOV byte ptr [RSP + 0x27],0x0
00a63e03  MOVUPS xmmword ptr [RSP + 0x28],XMM15
00a63e09  NOP
00a63e0a  NOP
00a63e0b  MOV RDX,RAX
00a63e0e  XOR EAX,EAX
00a63e10  MOV ESI,0x1
00a63e15  CMPXCHG.LOCK dword ptr [RDX],ESI
00a63e19  SETZ SIL
00a63e1d  NOP dword ptr [RAX]
00a63e20  TEST SIL,SIL
00a63e23  JNZ 0x00a63e4b
00a63e25  MOV qword ptr [RSP + 0x48],RDX
00a63e2a  MOV qword ptr [RSP + 0x78],RCX
00a63e2f  MOV qword ptr [RSP + 0x70],RBX
00a63e34  MOV RAX,RDX
00a63e37  CALL 0x00493480
00a63e3c  MOV RCX,qword ptr [RSP + 0x78]
00a63e41  MOV RDX,qword ptr [RSP + 0x48]
00a63e46  MOV RBX,qword ptr [RSP + 0x70]
00a63e4b  LEA RSI,[0xa63f20]
00a63e52  MOV qword ptr [RSP + 0x38],RSI
00a63e57  MOV qword ptr [RSP + 0x40],RDX
00a63e5c  LEA RSI,[RSP + 0x38]
00a63e61  MOV qword ptr [RSP + 0x50],RSI
00a63e66  MOV byte ptr [RSP + 0x27],0x1
00a63e6b  MOV RSI,qword ptr [RDX + 0x18]
00a63e6f  TEST RSI,RSI
00a63e72  JZ 0x00a63eb9
00a63e74  LEA RAX,[0xe16200]
00a63e7b  MOV RDI,RCX
00a63e7e  MOV RCX,RBX
00a63e81  MOV RBX,RSI
00a63e84  CALL 0x00412ee0
00a63e89  MOV RDX,qword ptr [RAX]
00a63e8c  MOV RSI,qword ptr [RAX + 0x8]
00a63e90  MOV qword ptr [RSP + 0x28],RDX
00a63e95  MOV qword ptr [RSP + 0x30],RSI
00a63e9a  MOV byte ptr [RSP + 0x27],0x0
00a63e9f  MOV RDX,qword ptr [RSP + 0x50]
00a63ea4  MOV RSI,qword ptr [RDX]
00a63ea7  CALL RSI
00a63ea9  MOV RAX,qword ptr [RSP + 0x28]
00a63eae  MOV RBX,qword ptr [RSP + 0x30]
00a63eb3  ADD RSP,0x58
00a63eb7  POP RBP
00a63eb8  RET
00a63eb9  MOVUPS xmmword ptr [RSP + 0x28],XMM15
00a63ebf  MOV byte ptr [RSP + 0x27],0x0
00a63ec4  MOV RDX,qword ptr [RSP + 0x50]
00a63ec9  MOV RAX,qword ptr [RDX]
00a63ecc  CALL RAX
00a63ece  MOV RBX,qword ptr [RSP + 0x30]
00a63ed3  MOV RAX,qword ptr [RSP + 0x28]
00a63ed8  ADD RSP,0x58
00a63edc  POP RBP
00a63edd  RET
00a63ef5  MOV qword ptr [RSP + 0x8],RAX
00a63efa  MOV qword ptr [RSP + 0x10],RBX
00a63eff  MOV qword ptr [RSP + 0x18],RCX
00a63f04  CALL 0x0048a280
00a63f09  MOV RAX,qword ptr [RSP + 0x8]
00a63f0e  MOV RBX,qword ptr [RSP + 0x10]
00a63f13  MOV RCX,qword ptr [RSP + 0x18]
00a63f18  JMP 0x00a63de0
