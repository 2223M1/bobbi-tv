; main.handlePlay.Printf.func4
00c4d6e0  CMP RSP,qword ptr [R14 + 0x10]
00c4d6e4  JBE 0x00c4d712
00c4d6e6  PUSH RBP
00c4d6e7  MOV RBP,RSP
00c4d6ea  SUB RSP,0x40
00c4d6ee  MOV qword ptr [RSP + 0x50],RAX
00c4d6f3  MOV RDI,qword ptr [RDX + 0x8]
00c4d6f7  MOV RSI,qword ptr [RDX + 0x10]
00c4d6fb  MOV R8,qword ptr [RDX + 0x18]
00c4d6ff  MOV R9,qword ptr [RDX + 0x20]
00c4d703  MOV R10,qword ptr [RDX + 0x28]
00c4d707  CALL 0x00505680
00c4d70c  ADD RSP,0x40
00c4d710  POP RBP
00c4d711  RET
00c4d712  MOV qword ptr [RSP + 0x8],RAX
00c4d717  MOV qword ptr [RSP + 0x10],RBX
00c4d71c  MOV qword ptr [RSP + 0x18],RCX
00c4d721  CALL 0x0048a1e0
00c4d726  MOV RAX,qword ptr [RSP + 0x8]
00c4d72b  MOV RBX,qword ptr [RSP + 0x10]
00c4d730  MOV RCX,qword ptr [RSP + 0x18]
00c4d735  JMP 0x00c4d6e0
