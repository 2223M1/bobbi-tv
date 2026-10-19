; main.handlePlay.Printf.func5
00c4d680  CMP RSP,qword ptr [R14 + 0x10]
00c4d684  JBE 0x00c4d6b2
00c4d686  PUSH RBP
00c4d687  MOV RBP,RSP
00c4d68a  SUB RSP,0x40
00c4d68e  MOV qword ptr [RSP + 0x50],RAX
00c4d693  MOV RDI,qword ptr [RDX + 0x8]
00c4d697  MOV RSI,qword ptr [RDX + 0x10]
00c4d69b  MOV R8,qword ptr [RDX + 0x18]
00c4d69f  MOV R9,qword ptr [RDX + 0x20]
00c4d6a3  MOV R10,qword ptr [RDX + 0x28]
00c4d6a7  CALL 0x00505680
00c4d6ac  ADD RSP,0x40
00c4d6b0  POP RBP
00c4d6b1  RET
00c4d6b2  MOV qword ptr [RSP + 0x8],RAX
00c4d6b7  MOV qword ptr [RSP + 0x10],RBX
00c4d6bc  MOV qword ptr [RSP + 0x18],RCX
00c4d6c1  CALL 0x0048a1e0
00c4d6c6  MOV RAX,qword ptr [RSP + 0x8]
00c4d6cb  MOV RBX,qword ptr [RSP + 0x10]
00c4d6d0  MOV RCX,qword ptr [RSP + 0x18]
00c4d6d5  JMP 0x00c4d680
