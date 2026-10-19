; main.handleUserFiles.Printf.func1
00c4f340  CMP RSP,qword ptr [R14 + 0x10]
00c4f344  JBE 0x00c4f372
00c4f346  PUSH RBP
00c4f347  MOV RBP,RSP
00c4f34a  SUB RSP,0x40
00c4f34e  MOV qword ptr [RSP + 0x50],RAX
00c4f353  MOV RDI,qword ptr [RDX + 0x8]
00c4f357  MOV RSI,qword ptr [RDX + 0x10]
00c4f35b  MOV R8,qword ptr [RDX + 0x18]
00c4f35f  MOV R9,qword ptr [RDX + 0x20]
00c4f363  MOV R10,qword ptr [RDX + 0x28]
00c4f367  CALL 0x00505680
00c4f36c  ADD RSP,0x40
00c4f370  POP RBP
00c4f371  RET
00c4f372  MOV qword ptr [RSP + 0x8],RAX
00c4f377  MOV qword ptr [RSP + 0x10],RBX
00c4f37c  MOV qword ptr [RSP + 0x18],RCX
00c4f381  CALL 0x0048a1e0
00c4f386  MOV RAX,qword ptr [RSP + 0x8]
00c4f38b  MOV RBX,qword ptr [RSP + 0x10]
00c4f390  MOV RCX,qword ptr [RSP + 0x18]
00c4f395  JMP 0x00c4f340
