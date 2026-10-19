; main.handle115OfflineDelete.Printf.func3
00c57c00  CMP RSP,qword ptr [R14 + 0x10]
00c57c04  JBE 0x00c57c32
00c57c06  PUSH RBP
00c57c07  MOV RBP,RSP
00c57c0a  SUB RSP,0x40
00c57c0e  MOV qword ptr [RSP + 0x50],RAX
00c57c13  MOV RDI,qword ptr [RDX + 0x8]
00c57c17  MOV RSI,qword ptr [RDX + 0x10]
00c57c1b  MOV R8,qword ptr [RDX + 0x18]
00c57c1f  MOV R9,qword ptr [RDX + 0x20]
00c57c23  MOV R10,qword ptr [RDX + 0x28]
00c57c27  CALL 0x00505680
00c57c2c  ADD RSP,0x40
00c57c30  POP RBP
00c57c31  RET
00c57c32  MOV qword ptr [RSP + 0x8],RAX
00c57c37  MOV qword ptr [RSP + 0x10],RBX
00c57c3c  MOV qword ptr [RSP + 0x18],RCX
00c57c41  CALL 0x0048a1e0
00c57c46  MOV RAX,qword ptr [RSP + 0x8]
00c57c4b  MOV RBX,qword ptr [RSP + 0x10]
00c57c50  MOV RCX,qword ptr [RSP + 0x18]
00c57c55  JMP 0x00c57c00
