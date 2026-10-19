; main.handlePlay.Printf.func6
00c4d620  CMP RSP,qword ptr [R14 + 0x10]
00c4d624  JBE 0x00c4d652
00c4d626  PUSH RBP
00c4d627  MOV RBP,RSP
00c4d62a  SUB RSP,0x40
00c4d62e  MOV qword ptr [RSP + 0x50],RAX
00c4d633  MOV RDI,qword ptr [RDX + 0x8]
00c4d637  MOV RSI,qword ptr [RDX + 0x10]
00c4d63b  MOV R8,qword ptr [RDX + 0x18]
00c4d63f  MOV R9,qword ptr [RDX + 0x20]
00c4d643  MOV R10,qword ptr [RDX + 0x28]
00c4d647  CALL 0x00505680
00c4d64c  ADD RSP,0x40
00c4d650  POP RBP
00c4d651  RET
00c4d652  MOV qword ptr [RSP + 0x8],RAX
00c4d657  MOV qword ptr [RSP + 0x10],RBX
00c4d65c  MOV qword ptr [RSP + 0x18],RCX
00c4d661  CALL 0x0048a1e0
00c4d666  MOV RAX,qword ptr [RSP + 0x8]
00c4d66b  MOV RBX,qword ptr [RSP + 0x10]
00c4d670  MOV RCX,qword ptr [RSP + 0x18]
00c4d675  JMP 0x00c4d620
