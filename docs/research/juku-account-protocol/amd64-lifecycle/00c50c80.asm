; main.handleUserPlay.Printf.func2
00c50c80  CMP RSP,qword ptr [R14 + 0x10]
00c50c84  JBE 0x00c50cb2
00c50c86  PUSH RBP
00c50c87  MOV RBP,RSP
00c50c8a  SUB RSP,0x40
00c50c8e  MOV qword ptr [RSP + 0x50],RAX
00c50c93  MOV RDI,qword ptr [RDX + 0x8]
00c50c97  MOV RSI,qword ptr [RDX + 0x10]
00c50c9b  MOV R8,qword ptr [RDX + 0x18]
00c50c9f  MOV R9,qword ptr [RDX + 0x20]
00c50ca3  MOV R10,qword ptr [RDX + 0x28]
00c50ca7  CALL 0x00505680
00c50cac  ADD RSP,0x40
00c50cb0  POP RBP
00c50cb1  RET
00c50cb2  MOV qword ptr [RSP + 0x8],RAX
00c50cb7  MOV qword ptr [RSP + 0x10],RBX
00c50cbc  MOV qword ptr [RSP + 0x18],RCX
00c50cc1  CALL 0x0048a1e0
00c50cc6  MOV RAX,qword ptr [RSP + 0x8]
00c50ccb  MOV RBX,qword ptr [RSP + 0x10]
00c50cd0  MOV RCX,qword ptr [RSP + 0x18]
00c50cd5  JMP 0x00c50c80
