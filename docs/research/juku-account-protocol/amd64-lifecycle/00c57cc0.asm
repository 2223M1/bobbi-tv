; main.handle115OfflineDelete.Printf.func1
00c57cc0  CMP RSP,qword ptr [R14 + 0x10]
00c57cc4  JBE 0x00c57cf2
00c57cc6  PUSH RBP
00c57cc7  MOV RBP,RSP
00c57cca  SUB RSP,0x40
00c57cce  MOV qword ptr [RSP + 0x50],RAX
00c57cd3  MOV RDI,qword ptr [RDX + 0x8]
00c57cd7  MOV RSI,qword ptr [RDX + 0x10]
00c57cdb  MOV R8,qword ptr [RDX + 0x18]
00c57cdf  MOV R9,qword ptr [RDX + 0x20]
00c57ce3  MOV R10,qword ptr [RDX + 0x28]
00c57ce7  CALL 0x00505680
00c57cec  ADD RSP,0x40
00c57cf0  POP RBP
00c57cf1  RET
00c57cf2  MOV qword ptr [RSP + 0x8],RAX
00c57cf7  MOV qword ptr [RSP + 0x10],RBX
00c57cfc  MOV qword ptr [RSP + 0x18],RCX
00c57d01  CALL 0x0048a1e0
00c57d06  MOV RAX,qword ptr [RSP + 0x8]
00c57d0b  MOV RBX,qword ptr [RSP + 0x10]
00c57d10  MOV RCX,qword ptr [RSP + 0x18]
00c57d15  JMP 0x00c57cc0
