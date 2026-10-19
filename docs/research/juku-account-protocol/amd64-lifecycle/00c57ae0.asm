; main.handle115OfflineDelete.Printf.func6
00c57ae0  CMP RSP,qword ptr [R14 + 0x10]
00c57ae4  JBE 0x00c57b12
00c57ae6  PUSH RBP
00c57ae7  MOV RBP,RSP
00c57aea  SUB RSP,0x40
00c57aee  MOV qword ptr [RSP + 0x50],RAX
00c57af3  MOV RDI,qword ptr [RDX + 0x8]
00c57af7  MOV RSI,qword ptr [RDX + 0x10]
00c57afb  MOV R8,qword ptr [RDX + 0x18]
00c57aff  MOV R9,qword ptr [RDX + 0x20]
00c57b03  MOV R10,qword ptr [RDX + 0x28]
00c57b07  CALL 0x00505680
00c57b0c  ADD RSP,0x40
00c57b10  POP RBP
00c57b11  RET
00c57b12  MOV qword ptr [RSP + 0x8],RAX
00c57b17  MOV qword ptr [RSP + 0x10],RBX
00c57b1c  MOV qword ptr [RSP + 0x18],RCX
00c57b21  CALL 0x0048a1e0
00c57b26  MOV RAX,qword ptr [RSP + 0x8]
00c57b2b  MOV RBX,qword ptr [RSP + 0x10]
00c57b30  MOV RCX,qword ptr [RSP + 0x18]
00c57b35  JMP 0x00c57ae0
