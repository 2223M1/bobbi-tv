; main.handlePlay.Printf.func7
00c4d2c0  CMP RSP,qword ptr [R14 + 0x10]
00c4d2c4  JBE 0x00c4d2f2
00c4d2c6  PUSH RBP
00c4d2c7  MOV RBP,RSP
00c4d2ca  SUB RSP,0x40
00c4d2ce  MOV qword ptr [RSP + 0x50],RAX
00c4d2d3  MOV RDI,qword ptr [RDX + 0x8]
00c4d2d7  MOV RSI,qword ptr [RDX + 0x10]
00c4d2db  MOV R8,qword ptr [RDX + 0x18]
00c4d2df  MOV R9,qword ptr [RDX + 0x20]
00c4d2e3  MOV R10,qword ptr [RDX + 0x28]
00c4d2e7  CALL 0x00505680
00c4d2ec  ADD RSP,0x40
00c4d2f0  POP RBP
00c4d2f1  RET
00c4d2f2  MOV qword ptr [RSP + 0x8],RAX
00c4d2f7  MOV qword ptr [RSP + 0x10],RBX
00c4d2fc  MOV qword ptr [RSP + 0x18],RCX
00c4d301  CALL 0x0048a1e0
00c4d306  MOV RAX,qword ptr [RSP + 0x8]
00c4d30b  MOV RBX,qword ptr [RSP + 0x10]
00c4d310  MOV RCX,qword ptr [RSP + 0x18]
00c4d315  JMP 0x00c4d2c0
