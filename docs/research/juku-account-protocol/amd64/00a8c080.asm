; mv-daemon/provider.ClearAll115DirCache.func1
00a8c080  CMP RSP,qword ptr [R14 + 0x10]
00a8c084  JBE 0x00a8c0c1
00a8c086  PUSH RBP
00a8c087  MOV RBP,RSP
00a8c08a  SUB RSP,0x20
00a8c08e  MOV qword ptr [RSP + 0x30],RAX
00a8c093  MOV qword ptr [RSP + 0x38],RBX
00a8c098  LEA RDX,[0x1158fe0]
00a8c09f  NOP
00a8c0a0  NOP
00a8c0a1  MOV RCX,RAX
00a8c0a4  MOV RDI,RBX
00a8c0a7  LEA RAX,[0x19921a0]
00a8c0ae  MOV RBX,RDX
00a8c0b1  CALL 0x00495c20
00a8c0b6  MOV EAX,0x1
00a8c0bb  ADD RSP,0x20
00a8c0bf  POP RBP
00a8c0c0  RET
00a8c0c1  MOV qword ptr [RSP + 0x8],RAX
00a8c0c6  MOV qword ptr [RSP + 0x10],RBX
00a8c0cb  MOV qword ptr [RSP + 0x18],RCX
00a8c0d0  MOV qword ptr [RSP + 0x20],RDI
00a8c0d5  CALL 0x0048a280
00a8c0da  MOV RAX,qword ptr [RSP + 0x8]
00a8c0df  MOV RBX,qword ptr [RSP + 0x10]
00a8c0e4  MOV RCX,qword ptr [RSP + 0x18]
00a8c0e9  MOV RDI,qword ptr [RSP + 0x20]
00a8c0ee  JMP 0x00a8c080
