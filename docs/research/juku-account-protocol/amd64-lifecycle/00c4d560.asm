; main.handlePlay.func1.Printf.2
00c4d560  CMP RSP,qword ptr [R14 + 0x10]
00c4d564  JBE 0x00c4d592
00c4d566  PUSH RBP
00c4d567  MOV RBP,RSP
00c4d56a  SUB RSP,0x40
00c4d56e  MOV qword ptr [RSP + 0x50],RAX
00c4d573  MOV RDI,qword ptr [RDX + 0x8]
00c4d577  MOV RSI,qword ptr [RDX + 0x10]
00c4d57b  MOV R8,qword ptr [RDX + 0x18]
00c4d57f  MOV R9,qword ptr [RDX + 0x20]
00c4d583  MOV R10,qword ptr [RDX + 0x28]
00c4d587  CALL 0x00505680
00c4d58c  ADD RSP,0x40
00c4d590  POP RBP
00c4d591  RET
00c4d592  MOV qword ptr [RSP + 0x8],RAX
00c4d597  MOV qword ptr [RSP + 0x10],RBX
00c4d59c  MOV qword ptr [RSP + 0x18],RCX
00c4d5a1  CALL 0x0048a1e0
00c4d5a6  MOV RAX,qword ptr [RSP + 0x8]
00c4d5ab  MOV RBX,qword ptr [RSP + 0x10]
00c4d5b0  MOV RCX,qword ptr [RSP + 0x18]
00c4d5b5  JMP 0x00c4d560
