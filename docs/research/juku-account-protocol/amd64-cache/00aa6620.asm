; mv-daemon/pkg/proxy.(*ProxyManager).CloseAll
00aa6620  LEA R12,[RSP + -0x38]
00aa6625  CMP R12,qword ptr [R14 + 0x10]
00aa6629  JBE 0x00aa6768
00aa662f  PUSH RBP
00aa6630  MOV RBP,RSP
00aa6633  SUB RSP,0xb0
00aa663a  MOVQ qword ptr [RSP + 0xa8],XMM15
00aa6644  MOV qword ptr [RSP + 0xc0],RAX
00aa664c  MOV byte ptr [RSP + 0x27],0x0
00aa6651  NOP
00aa6652  NOP
00aa6653  MOV RCX,RAX
00aa6656  XOR EAX,EAX
00aa6658  MOV EDX,0x1
00aa665d  CMPXCHG.LOCK dword ptr [RCX],EDX
00aa6661  SETZ DL
00aa6664  TEST DL,DL
00aa6666  JNZ 0x00aa6678
00aa6668  MOV RAX,RCX
00aa666b  CALL 0x00493480
00aa6670  MOV RCX,qword ptr [RSP + 0xc0]
00aa6678  LEA RDX,[0xaa6780]
00aa667f  MOV qword ptr [RSP + 0x98],RDX
00aa6687  MOV qword ptr [RSP + 0xa0],RCX
00aa668f  LEA RDX,[RSP + 0x98]
00aa6697  MOV qword ptr [RSP + 0xa8],RDX
00aa669f  MOV byte ptr [RSP + 0x27],0x1
00aa66a4  MOV RBX,qword ptr [RCX + 0x8]
00aa66a8  LEA RCX,[RSP + 0x38]
00aa66ad  MOVUPS xmmword ptr [RCX],XMM15
00aa66b1  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00aa66b6  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00aa66bb  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00aa66c0  MOVUPS xmmword ptr [RCX + 0x40],XMM15
00aa66c5  MOVUPS xmmword ptr [RCX + 0x50],XMM15
00aa66ca  LEA RAX,[0xe18f00]
00aa66d1  CALL 0x004225e0
00aa66d6  JMP 0x00aa6725
00aa66d8  MOV RDX,qword ptr [RCX]
00aa66db  MOV qword ptr [RSP + 0x30],RDX
00aa66e0  MOV RCX,qword ptr [RCX + 0x8]
00aa66e4  MOV qword ptr [RSP + 0x28],RCX
00aa66e9  MOV RCX,qword ptr [RSP + 0x40]
00aa66ee  MOV RAX,qword ptr [RCX]
00aa66f1  CALL 0x00aa3220
00aa66f6  MOV RCX,qword ptr [RSP + 0xc0]
00aa66fe  MOV RBX,qword ptr [RCX + 0x8]
00aa6702  LEA RAX,[0xe18f00]
00aa6709  MOV RCX,qword ptr [RSP + 0x30]
00aa670e  MOV RDI,qword ptr [RSP + 0x28]
00aa6713  CALL 0x00413a00
00aa6718  LEA RAX,[RSP + 0x38]
00aa671d  NOP dword ptr [RAX]
00aa6720  CALL 0x00422640
00aa6725  MOV RCX,qword ptr [RSP + 0x38]
00aa672a  TEST RCX,RCX
00aa672d  JNZ 0x00aa66d8
00aa672f  MOV RAX,qword ptr [RSP + 0xc0]
00aa6737  MOV qword ptr [RAX + 0x18],0x0
00aa673f  MOV byte ptr [RSP + 0x27],0x0
00aa6744  MOV RDX,qword ptr [RSP + 0xa8]
00aa674c  MOV RAX,qword ptr [RDX]
00aa674f  CALL RAX
00aa6751  ADD RSP,0xb0
00aa6758  POP RBP
00aa6759  RET
00aa6768  MOV qword ptr [RSP + 0x8],RAX
00aa676d  CALL 0x0048a280
00aa6772  MOV RAX,qword ptr [RSP + 0x8]
00aa6777  JMP 0x00aa6620
