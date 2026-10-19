; main.handleUserPlay.Printf.func3
00c50c20  CMP RSP,qword ptr [R14 + 0x10]
00c50c24  JBE 0x00c50c52
00c50c26  PUSH RBP
00c50c27  MOV RBP,RSP
00c50c2a  SUB RSP,0x40
00c50c2e  MOV qword ptr [RSP + 0x50],RAX
00c50c33  MOV RDI,qword ptr [RDX + 0x8]
00c50c37  MOV RSI,qword ptr [RDX + 0x10]
00c50c3b  MOV R8,qword ptr [RDX + 0x18]
00c50c3f  MOV R9,qword ptr [RDX + 0x20]
00c50c43  MOV R10,qword ptr [RDX + 0x28]
00c50c47  CALL 0x00505680
00c50c4c  ADD RSP,0x40
00c50c50  POP RBP
00c50c51  RET
00c50c52  MOV qword ptr [RSP + 0x8],RAX
00c50c57  MOV qword ptr [RSP + 0x10],RBX
00c50c5c  MOV qword ptr [RSP + 0x18],RCX
00c50c61  CALL 0x0048a1e0
00c50c66  MOV RAX,qword ptr [RSP + 0x8]
00c50c6b  MOV RBX,qword ptr [RSP + 0x10]
00c50c70  MOV RCX,qword ptr [RSP + 0x18]
00c50c75  JMP 0x00c50c20
