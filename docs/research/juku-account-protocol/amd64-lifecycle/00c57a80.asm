; main.handle115OfflineDelete.Printf.func7
00c57a80  CMP RSP,qword ptr [R14 + 0x10]
00c57a84  JBE 0x00c57ab2
00c57a86  PUSH RBP
00c57a87  MOV RBP,RSP
00c57a8a  SUB RSP,0x40
00c57a8e  MOV qword ptr [RSP + 0x50],RAX
00c57a93  MOV RDI,qword ptr [RDX + 0x8]
00c57a97  MOV RSI,qword ptr [RDX + 0x10]
00c57a9b  MOV R8,qword ptr [RDX + 0x18]
00c57a9f  MOV R9,qword ptr [RDX + 0x20]
00c57aa3  MOV R10,qword ptr [RDX + 0x28]
00c57aa7  CALL 0x00505680
00c57aac  ADD RSP,0x40
00c57ab0  POP RBP
00c57ab1  RET
00c57ab2  MOV qword ptr [RSP + 0x8],RAX
00c57ab7  MOV qword ptr [RSP + 0x10],RBX
00c57abc  MOV qword ptr [RSP + 0x18],RCX
00c57ac1  CALL 0x0048a1e0
00c57ac6  MOV RAX,qword ptr [RSP + 0x8]
00c57acb  MOV RBX,qword ptr [RSP + 0x10]
00c57ad0  MOV RCX,qword ptr [RSP + 0x18]
00c57ad5  JMP 0x00c57a80
