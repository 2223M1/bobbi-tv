; mv-daemon/provider.NewOfflineCacheStore.Printf.func1
00a130e0  CMP RSP,qword ptr [R14 + 0x10]
00a130e4  JBE 0x00a13112
00a130e6  PUSH RBP
00a130e7  MOV RBP,RSP
00a130ea  SUB RSP,0x40
00a130ee  MOV qword ptr [RSP + 0x50],RAX
00a130f3  MOV RDI,qword ptr [RDX + 0x8]
00a130f7  MOV RSI,qword ptr [RDX + 0x10]
00a130fb  MOV R8,qword ptr [RDX + 0x18]
00a130ff  MOV R9,qword ptr [RDX + 0x20]
00a13103  MOV R10,qword ptr [RDX + 0x28]
00a13107  CALL 0x00505680
00a1310c  ADD RSP,0x40
00a13110  POP RBP
00a13111  RET
00a13112  MOV qword ptr [RSP + 0x8],RAX
00a13117  MOV qword ptr [RSP + 0x10],RBX
00a1311c  MOV qword ptr [RSP + 0x18],RCX
00a13121  CALL 0x0048a1e0
00a13126  MOV RAX,qword ptr [RSP + 0x8]
00a1312b  MOV RBX,qword ptr [RSP + 0x10]
00a13130  MOV RCX,qword ptr [RSP + 0x18]
00a13135  JMP 0x00a130e0
