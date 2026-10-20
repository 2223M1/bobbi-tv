; main.handlePlay.Printf.func2
00c4d7a0  CMP RSP,qword ptr [R14 + 0x10]
00c4d7a4  JBE 0x00c4d7d2
00c4d7a6  PUSH RBP
00c4d7a7  MOV RBP,RSP
00c4d7aa  SUB RSP,0x40
00c4d7ae  MOV qword ptr [RSP + 0x50],RAX
00c4d7b3  MOV RDI,qword ptr [RDX + 0x8]
00c4d7b7  MOV RSI,qword ptr [RDX + 0x10]
00c4d7bb  MOV R8,qword ptr [RDX + 0x18]
00c4d7bf  MOV R9,qword ptr [RDX + 0x20]
00c4d7c3  MOV R10,qword ptr [RDX + 0x28]
00c4d7c7  CALL 0x00505680
00c4d7cc  ADD RSP,0x40
00c4d7d0  POP RBP
00c4d7d1  RET
00c4d7d2  MOV qword ptr [RSP + 0x8],RAX
00c4d7d7  MOV qword ptr [RSP + 0x10],RBX
00c4d7dc  MOV qword ptr [RSP + 0x18],RCX
00c4d7e1  CALL 0x0048a1e0
00c4d7e6  MOV RAX,qword ptr [RSP + 0x8]
00c4d7eb  MOV RBX,qword ptr [RSP + 0x10]
00c4d7f0  MOV RCX,qword ptr [RSP + 0x18]
00c4d7f5  JMP 0x00c4d7a0
