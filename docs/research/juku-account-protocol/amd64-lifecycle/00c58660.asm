; main.handle115OfflineResolve.Printf.func1
00c58660  CMP RSP,qword ptr [R14 + 0x10]
00c58664  JBE 0x00c58692
00c58666  PUSH RBP
00c58667  MOV RBP,RSP
00c5866a  SUB RSP,0x40
00c5866e  MOV qword ptr [RSP + 0x50],RAX
00c58673  MOV RDI,qword ptr [RDX + 0x8]
00c58677  MOV RSI,qword ptr [RDX + 0x10]
00c5867b  MOV R8,qword ptr [RDX + 0x18]
00c5867f  MOV R9,qword ptr [RDX + 0x20]
00c58683  MOV R10,qword ptr [RDX + 0x28]
00c58687  CALL 0x00505680
00c5868c  ADD RSP,0x40
00c58690  POP RBP
00c58691  RET
00c58692  MOV qword ptr [RSP + 0x8],RAX
00c58697  MOV qword ptr [RSP + 0x10],RBX
00c5869c  MOV qword ptr [RSP + 0x18],RCX
00c586a1  CALL 0x0048a1e0
00c586a6  MOV RAX,qword ptr [RSP + 0x8]
00c586ab  MOV RBX,qword ptr [RSP + 0x10]
00c586b0  MOV RCX,qword ptr [RSP + 0x18]
00c586b5  JMP 0x00c58660
