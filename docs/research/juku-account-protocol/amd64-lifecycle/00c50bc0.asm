; main.handleUserPlay.Printf.func4
00c50bc0  CMP RSP,qword ptr [R14 + 0x10]
00c50bc4  JBE 0x00c50bf2
00c50bc6  PUSH RBP
00c50bc7  MOV RBP,RSP
00c50bca  SUB RSP,0x40
00c50bce  MOV qword ptr [RSP + 0x50],RAX
00c50bd3  MOV RDI,qword ptr [RDX + 0x8]
00c50bd7  MOV RSI,qword ptr [RDX + 0x10]
00c50bdb  MOV R8,qword ptr [RDX + 0x18]
00c50bdf  MOV R9,qword ptr [RDX + 0x20]
00c50be3  MOV R10,qword ptr [RDX + 0x28]
00c50be7  CALL 0x00505680
00c50bec  ADD RSP,0x40
00c50bf0  POP RBP
00c50bf1  RET
00c50bf2  MOV qword ptr [RSP + 0x8],RAX
00c50bf7  MOV qword ptr [RSP + 0x10],RBX
00c50bfc  MOV qword ptr [RSP + 0x18],RCX
00c50c01  CALL 0x0048a1e0
00c50c06  MOV RAX,qword ptr [RSP + 0x8]
00c50c0b  MOV RBX,qword ptr [RSP + 0x10]
00c50c10  MOV RCX,qword ptr [RSP + 0x18]
00c50c15  JMP 0x00c50bc0
