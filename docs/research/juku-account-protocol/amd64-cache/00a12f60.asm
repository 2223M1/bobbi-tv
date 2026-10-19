; mv-daemon/provider.NewOfflineCacheStore
00a12f60  LEA R12,[RSP + -0x10]
00a12f65  CMP R12,qword ptr [R14 + 0x10]
00a12f69  JBE 0x00a130a3
00a12f6f  PUSH RBP
00a12f70  MOV RBP,RSP
00a12f73  SUB RSP,0x88
00a12f7a  MOV qword ptr [RSP + 0x98],RAX
00a12f82  MOV qword ptr [RSP + 0xa0],RBX
00a12f8a  LEA RAX,[0xe6a560]
00a12f91  CALL 0x00421f00
00a12f96  MOV RCX,qword ptr [RSP + 0xa0]
00a12f9e  MOV qword ptr [RAX + 0x18],RCX
00a12fa2  CMP dword ptr [0x019b5f00],0x0
00a12fa9  JNZ 0x00a12fb5
00a12fab  MOV RDX,qword ptr [RSP + 0x98]
00a12fb3  JMP 0x00a12fc5
00a12fb5  CALL 0x0048bbe0
00a12fba  MOV RDX,qword ptr [RSP + 0x98]
00a12fc2  MOV qword ptr [R11],RDX
00a12fc5  MOV qword ptr [RSP + 0x28],RAX
00a12fca  MOV qword ptr [RAX + 0x10],RDX
00a12fce  CALL 0x00a13140
00a12fd3  TEST RAX,RAX
00a12fd6  JZ 0x00a13095
00a12fdc  MOV qword ptr [RSP + 0x30],RBX
00a12fe1  MOV qword ptr [RSP + 0x20],RAX
00a12fe6  LEA RCX,[RSP + 0x38]
00a12feb  MOVUPS xmmword ptr [RCX],XMM15
00a12fef  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00a12ff4  MOV RAX,qword ptr [RSP + 0x98]
00a12ffc  MOV RBX,qword ptr [RSP + 0xa0]
00a13004  CALL 0x00481ee0
00a13009  LEA RCX,[0xdd29c0]
00a13010  MOV qword ptr [RSP + 0x38],RCX
00a13015  MOV qword ptr [RSP + 0x40],RAX
00a1301a  MOV RCX,qword ptr [RSP + 0x20]
00a1301f  NOP
00a13020  TEST RCX,RCX
00a13023  JZ 0x00a1302b
00a13025  MOV RAX,qword ptr [RCX + 0x8]
00a13029  JMP 0x00a1302e
00a1302b  MOV RAX,RCX
00a1302e  MOV qword ptr [RSP + 0x48],RAX
00a13033  MOV RDX,qword ptr [RSP + 0x30]
00a13038  MOV qword ptr [RSP + 0x50],RDX
00a1303d  LEA RDX,[0xa130e0]
00a13044  MOV qword ptr [RSP + 0x58],RDX
00a13049  MOV qword ptr [RSP + 0x68],0x3c
00a13052  LEA RDX,[0xf4e7dc]
00a13059  MOV qword ptr [RSP + 0x60],RDX
00a1305e  MOV qword ptr [RSP + 0x78],0x2
00a13067  MOV qword ptr [RSP + 0x80],0x2
00a13073  LEA RDX,[RSP + 0x38]
00a13078  MOV qword ptr [RSP + 0x70],RDX
00a1307d  MOV RAX,qword ptr [0x01990148]
00a13084  XOR EBX,EBX
00a13086  MOV ECX,0x2
00a1308b  LEA RDI,[RSP + 0x58]
00a13090  CALL 0x0054d540
00a13095  MOV RAX,qword ptr [RSP + 0x28]
00a1309a  ADD RSP,0x88
00a130a1  POP RBP
00a130a2  RET
00a130a3  MOV qword ptr [RSP + 0x8],RAX
00a130a8  MOV qword ptr [RSP + 0x10],RBX
00a130ad  CALL 0x0048a280
00a130b2  MOV RAX,qword ptr [RSP + 0x8]
00a130b7  MOV RBX,qword ptr [RSP + 0x10]
00a130bc  NOP dword ptr [RAX]
00a130c0  JMP 0x00a12f60
