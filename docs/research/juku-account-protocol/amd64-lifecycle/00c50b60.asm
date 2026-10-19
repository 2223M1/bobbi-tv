; main.handleUserPlay.Printf.func5
00c50b60  CMP RSP,qword ptr [R14 + 0x10]
00c50b64  JBE 0x00c50b92
00c50b66  PUSH RBP
00c50b67  MOV RBP,RSP
00c50b6a  SUB RSP,0x40
00c50b6e  MOV qword ptr [RSP + 0x50],RAX
00c50b73  MOV RDI,qword ptr [RDX + 0x8]
00c50b77  MOV RSI,qword ptr [RDX + 0x10]
00c50b7b  MOV R8,qword ptr [RDX + 0x18]
00c50b7f  MOV R9,qword ptr [RDX + 0x20]
00c50b83  MOV R10,qword ptr [RDX + 0x28]
00c50b87  CALL 0x00505680
00c50b8c  ADD RSP,0x40
00c50b90  POP RBP
00c50b91  RET
00c50b92  MOV qword ptr [RSP + 0x8],RAX
00c50b97  MOV qword ptr [RSP + 0x10],RBX
00c50b9c  MOV qword ptr [RSP + 0x18],RCX
00c50ba1  CALL 0x0048a1e0
00c50ba6  MOV RAX,qword ptr [RSP + 0x8]
00c50bab  MOV RBX,qword ptr [RSP + 0x10]
00c50bb0  MOV RCX,qword ptr [RSP + 0x18]
00c50bb5  JMP 0x00c50b60
