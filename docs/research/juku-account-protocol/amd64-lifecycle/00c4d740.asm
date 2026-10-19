; main.handlePlay.Printf.func3
00c4d740  CMP RSP,qword ptr [R14 + 0x10]
00c4d744  JBE 0x00c4d772
00c4d746  PUSH RBP
00c4d747  MOV RBP,RSP
00c4d74a  SUB RSP,0x40
00c4d74e  MOV qword ptr [RSP + 0x50],RAX
00c4d753  MOV RDI,qword ptr [RDX + 0x8]
00c4d757  MOV RSI,qword ptr [RDX + 0x10]
00c4d75b  MOV R8,qword ptr [RDX + 0x18]
00c4d75f  MOV R9,qword ptr [RDX + 0x20]
00c4d763  MOV R10,qword ptr [RDX + 0x28]
00c4d767  CALL 0x00505680
00c4d76c  ADD RSP,0x40
00c4d770  POP RBP
00c4d771  RET
00c4d772  MOV qword ptr [RSP + 0x8],RAX
00c4d777  MOV qword ptr [RSP + 0x10],RBX
00c4d77c  MOV qword ptr [RSP + 0x18],RCX
00c4d781  CALL 0x0048a1e0
00c4d786  MOV RAX,qword ptr [RSP + 0x8]
00c4d78b  MOV RBX,qword ptr [RSP + 0x10]
00c4d790  MOV RCX,qword ptr [RSP + 0x18]
00c4d795  JMP 0x00c4d740
