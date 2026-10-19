; main.handle115OfflineAdd.Printf.func1
00c539a0  CMP RSP,qword ptr [R14 + 0x10]
00c539a4  JBE 0x00c539d2
00c539a6  PUSH RBP
00c539a7  MOV RBP,RSP
00c539aa  SUB RSP,0x40
00c539ae  MOV qword ptr [RSP + 0x50],RAX
00c539b3  MOV RDI,qword ptr [RDX + 0x8]
00c539b7  MOV RSI,qword ptr [RDX + 0x10]
00c539bb  MOV R8,qword ptr [RDX + 0x18]
00c539bf  MOV R9,qword ptr [RDX + 0x20]
00c539c3  MOV R10,qword ptr [RDX + 0x28]
00c539c7  CALL 0x00505680
00c539cc  ADD RSP,0x40
00c539d0  POP RBP
00c539d1  RET
00c539d2  MOV qword ptr [RSP + 0x8],RAX
00c539d7  MOV qword ptr [RSP + 0x10],RBX
00c539dc  MOV qword ptr [RSP + 0x18],RCX
00c539e1  CALL 0x0048a1e0
00c539e6  MOV RAX,qword ptr [RSP + 0x8]
00c539eb  MOV RBX,qword ptr [RSP + 0x10]
00c539f0  MOV RCX,qword ptr [RSP + 0x18]
00c539f5  JMP 0x00c539a0
