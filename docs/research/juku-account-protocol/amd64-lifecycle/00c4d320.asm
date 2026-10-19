; main.handlePlay.func1
00c4d320  LEA R12,[RSP + -0x68]
00c4d325  CMP R12,qword ptr [R14 + 0x10]
00c4d329  JBE 0x00c4d548
00c4d32f  PUSH RBP
00c4d330  MOV RBP,RSP
00c4d333  SUB RSP,0xe0
00c4d33a  MOV RCX,qword ptr [RDX + 0x10]
00c4d33e  MOV RBX,qword ptr [RDX + 0x18]
00c4d342  MOV qword ptr [RSP + 0x50],RBX
00c4d347  MOV RAX,qword ptr [RDX + 0x20]
00c4d34b  MOV qword ptr [RSP + 0x80],RAX
00c4d353  MOV RSI,qword ptr [RDX + 0x8]
00c4d357  MOV RDI,qword ptr [RDX + 0x28]
00c4d35b  MOV qword ptr [RSP + 0x70],RDI
00c4d360  MOV R8,qword ptr [RDX + 0x30]
00c4d364  MOV qword ptr [RSP + 0x48],R8
00c4d369  MOV R9,qword ptr [RDX + 0x38]
00c4d36d  MOV qword ptr [RSP + 0x98],R9
00c4d375  MOV R10,qword ptr [RDX + 0x40]
00c4d379  MOV qword ptr [RSP + 0x68],R10
00c4d37e  MOV R11,qword ptr [RDX + 0x48]
00c4d382  MOV qword ptr [RSP + 0x88],R11
00c4d38a  MOV RDX,qword ptr [RDX + 0x50]
00c4d38e  MOV qword ptr [RSP + 0x58],RDX
00c4d393  TEST RCX,RCX
00c4d396  JNZ 0x00c4d3cc
00c4d398  MOV RCX,qword ptr [RBX + 0x28]
00c4d39c  CALL RCX
00c4d39e  MOV RCX,qword ptr [0x019900b0]
00c4d3a5  MOV RDX,RAX
00c4d3a8  MOV RAX,RCX
00c4d3ab  MOV RSI,RBX
00c4d3ae  MOV RBX,RDX
00c4d3b1  MOV RCX,RSI
00c4d3b4  CALL 0x00a63de0
00c4d3b9  MOV RCX,RBX
00c4d3bc  MOV RSI,RAX
00c4d3bf  MOV RAX,qword ptr [RSP + 0x80]
00c4d3c7  MOV RBX,qword ptr [RSP + 0x50]
00c4d3cc  MOV qword ptr [RSP + 0x60],RCX
00c4d3d1  MOV qword ptr [RSP + 0x90],RSI
00c4d3d9  MOV RCX,qword ptr [RBX + 0x28]
00c4d3dd  CALL RCX
00c4d3df  MOVUPS xmmword ptr [RSP + 0xa0],XMM15
00c4d3e8  CALL 0x00481ee0
00c4d3ed  LEA RCX,[0xdd29c0]
00c4d3f4  MOV qword ptr [RSP + 0xa0],RCX
00c4d3fc  MOV qword ptr [RSP + 0xa8],RAX
00c4d404  LEA RCX,[0xc4d5c0]
00c4d40b  MOV qword ptr [RSP + 0xb0],RCX
00c4d413  MOV qword ptr [RSP + 0xc0],0x35
00c4d41f  LEA RCX,[0xf48bc6]
00c4d426  MOV qword ptr [RSP + 0xb8],RCX
00c4d42e  MOV qword ptr [RSP + 0xd0],0x1
00c4d43a  MOV qword ptr [RSP + 0xd8],0x1
00c4d446  LEA RCX,[RSP + 0xa0]
00c4d44e  MOV qword ptr [RSP + 0xc8],RCX
00c4d456  MOV RAX,qword ptr [0x01990148]
00c4d45d  XOR EBX,EBX
00c4d45f  MOV ECX,0x2
00c4d464  LEA RDI,[RSP + 0xb0]
00c4d46c  CALL 0x0054d540
00c4d471  MOV RCX,qword ptr [RSP + 0x50]
00c4d476  MOV RCX,qword ptr [RCX + 0x38]
00c4d47a  MOV RAX,qword ptr [RSP + 0x80]
00c4d482  MOV RBX,qword ptr [RSP + 0x70]
00c4d487  MOV RDI,qword ptr [RSP + 0x98]
00c4d48f  MOV RSI,qword ptr [RSP + 0x68]
00c4d494  MOV R8,qword ptr [RSP + 0x88]
00c4d49c  MOV R9,qword ptr [RSP + 0x58]
00c4d4a1  MOV R10,qword ptr [RSP + 0x90]
00c4d4a9  MOV R11,qword ptr [RSP + 0x60]
00c4d4ae  MOV RDX,RCX
00c4d4b1  MOV RCX,qword ptr [RSP + 0x48]
00c4d4b6  CALL RDX
00c4d4b8  TEST RBX,RBX
00c4d4bb  JZ 0x00c4d4d2
00c4d4bd  XOR EAX,EAX
00c4d4bf  MOV RDI,RBX
00c4d4c2  MOV RSI,RCX
00c4d4c5  XOR EBX,EBX
00c4d4c7  XOR ECX,ECX
00c4d4c9  ADD RSP,0xe0
00c4d4d0  POP RBP
00c4d4d1  RET
00c4d4d2  MOV qword ptr [RSP + 0x78],RAX
00c4d4d7  NOP
00c4d4d8  LEA RDI,[RSP + 0xb0]
00c4d4e0  MOVUPS xmmword ptr [RDI],XMM15
00c4d4e4  MOVUPS xmmword ptr [RDI + 0x10],XMM15
00c4d4e9  MOVUPS xmmword ptr [RDI + 0x20],XMM15
00c4d4ee  LEA RDX,[0xc4d560]
00c4d4f5  MOV qword ptr [RSP + 0xb0],RDX
00c4d4fd  MOV qword ptr [RSP + 0xc0],0x35
00c4d509  LEA RDX,[0xf48bfb]
00c4d510  MOV qword ptr [RSP + 0xb8],RDX
00c4d518  MOV RAX,qword ptr [0x01990148]
00c4d51f  XOR EBX,EBX
00c4d521  MOV ECX,0x2
00c4d526  CALL 0x0054d540
00c4d52b  MOV RDX,qword ptr [RSP + 0x78]
00c4d530  MOV RAX,qword ptr [RDX]
00c4d533  MOV RBX,qword ptr [RDX + 0x8]
00c4d537  MOV RCX,qword ptr [RDX + 0x10]
00c4d53b  XOR EDI,EDI
00c4d53d  XOR ESI,ESI
00c4d53f  ADD RSP,0xe0
00c4d546  POP RBP
00c4d547  RET
00c4d548  CALL 0x0048a1e0
00c4d54d  JMP 0x00c4d320
