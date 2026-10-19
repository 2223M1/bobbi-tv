; main.handle115OfflineDelete.Printf.func2
00c57c60  CMP RSP,qword ptr [R14 + 0x10]
00c57c64  JBE 0x00c57c92
00c57c66  PUSH RBP
00c57c67  MOV RBP,RSP
00c57c6a  SUB RSP,0x40
00c57c6e  MOV qword ptr [RSP + 0x50],RAX
00c57c73  MOV RDI,qword ptr [RDX + 0x8]
00c57c77  MOV RSI,qword ptr [RDX + 0x10]
00c57c7b  MOV R8,qword ptr [RDX + 0x18]
00c57c7f  MOV R9,qword ptr [RDX + 0x20]
00c57c83  MOV R10,qword ptr [RDX + 0x28]
00c57c87  CALL 0x00505680
00c57c8c  ADD RSP,0x40
00c57c90  POP RBP
00c57c91  RET
00c57c92  MOV qword ptr [RSP + 0x8],RAX
00c57c97  MOV qword ptr [RSP + 0x10],RBX
00c57c9c  MOV qword ptr [RSP + 0x18],RCX
00c57ca1  CALL 0x0048a1e0
00c57ca6  MOV RAX,qword ptr [RSP + 0x8]
00c57cab  MOV RBX,qword ptr [RSP + 0x10]
00c57cb0  MOV RCX,qword ptr [RSP + 0x18]
00c57cb5  JMP 0x00c57c60
