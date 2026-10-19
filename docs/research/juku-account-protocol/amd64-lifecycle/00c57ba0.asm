; main.handle115OfflineDelete.Printf.func4
00c57ba0  CMP RSP,qword ptr [R14 + 0x10]
00c57ba4  JBE 0x00c57bd2
00c57ba6  PUSH RBP
00c57ba7  MOV RBP,RSP
00c57baa  SUB RSP,0x40
00c57bae  MOV qword ptr [RSP + 0x50],RAX
00c57bb3  MOV RDI,qword ptr [RDX + 0x8]
00c57bb7  MOV RSI,qword ptr [RDX + 0x10]
00c57bbb  MOV R8,qword ptr [RDX + 0x18]
00c57bbf  MOV R9,qword ptr [RDX + 0x20]
00c57bc3  MOV R10,qword ptr [RDX + 0x28]
00c57bc7  CALL 0x00505680
00c57bcc  ADD RSP,0x40
00c57bd0  POP RBP
00c57bd1  RET
00c57bd2  MOV qword ptr [RSP + 0x8],RAX
00c57bd7  MOV qword ptr [RSP + 0x10],RBX
00c57bdc  MOV qword ptr [RSP + 0x18],RCX
00c57be1  CALL 0x0048a1e0
00c57be6  MOV RAX,qword ptr [RSP + 0x8]
00c57beb  MOV RBX,qword ptr [RSP + 0x10]
00c57bf0  MOV RCX,qword ptr [RSP + 0x18]
00c57bf5  JMP 0x00c57ba0
