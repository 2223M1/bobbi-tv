; main.handle115OfflineDelete.Printf.func5
00c57b40  CMP RSP,qword ptr [R14 + 0x10]
00c57b44  JBE 0x00c57b72
00c57b46  PUSH RBP
00c57b47  MOV RBP,RSP
00c57b4a  SUB RSP,0x40
00c57b4e  MOV qword ptr [RSP + 0x50],RAX
00c57b53  MOV RDI,qword ptr [RDX + 0x8]
00c57b57  MOV RSI,qword ptr [RDX + 0x10]
00c57b5b  MOV R8,qword ptr [RDX + 0x18]
00c57b5f  MOV R9,qword ptr [RDX + 0x20]
00c57b63  MOV R10,qword ptr [RDX + 0x28]
00c57b67  CALL 0x00505680
00c57b6c  ADD RSP,0x40
00c57b70  POP RBP
00c57b71  RET
00c57b72  MOV qword ptr [RSP + 0x8],RAX
00c57b77  MOV qword ptr [RSP + 0x10],RBX
00c57b7c  MOV qword ptr [RSP + 0x18],RCX
00c57b81  CALL 0x0048a1e0
00c57b86  MOV RAX,qword ptr [RSP + 0x8]
00c57b8b  MOV RBX,qword ptr [RSP + 0x10]
00c57b90  MOV RCX,qword ptr [RSP + 0x18]
00c57b95  JMP 0x00c57b40
