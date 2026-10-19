; main.handlePlay.func1.Printf.1
00c4d5c0  CMP RSP,qword ptr [R14 + 0x10]
00c4d5c4  JBE 0x00c4d5f2
00c4d5c6  PUSH RBP
00c4d5c7  MOV RBP,RSP
00c4d5ca  SUB RSP,0x40
00c4d5ce  MOV qword ptr [RSP + 0x50],RAX
00c4d5d3  MOV RDI,qword ptr [RDX + 0x8]
00c4d5d7  MOV RSI,qword ptr [RDX + 0x10]
00c4d5db  MOV R8,qword ptr [RDX + 0x18]
00c4d5df  MOV R9,qword ptr [RDX + 0x20]
00c4d5e3  MOV R10,qword ptr [RDX + 0x28]
00c4d5e7  CALL 0x00505680
00c4d5ec  ADD RSP,0x40
00c4d5f0  POP RBP
00c4d5f1  RET
00c4d5f2  MOV qword ptr [RSP + 0x8],RAX
00c4d5f7  MOV qword ptr [RSP + 0x10],RBX
00c4d5fc  MOV qword ptr [RSP + 0x18],RCX
00c4d601  CALL 0x0048a1e0
00c4d606  MOV RAX,qword ptr [RSP + 0x8]
00c4d60b  MOV RBX,qword ptr [RSP + 0x10]
00c4d610  MOV RCX,qword ptr [RSP + 0x18]
00c4d615  JMP 0x00c4d5c0
