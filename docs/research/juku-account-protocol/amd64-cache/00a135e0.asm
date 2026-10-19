; mv-daemon/provider.(*OfflineCacheStore).init.Printf.func1
00a135e0  CMP RSP,qword ptr [R14 + 0x10]
00a135e4  JBE 0x00a13612
00a135e6  PUSH RBP
00a135e7  MOV RBP,RSP
00a135ea  SUB RSP,0x40
00a135ee  MOV qword ptr [RSP + 0x50],RAX
00a135f3  MOV RDI,qword ptr [RDX + 0x8]
00a135f7  MOV RSI,qword ptr [RDX + 0x10]
00a135fb  MOV R8,qword ptr [RDX + 0x18]
00a135ff  MOV R9,qword ptr [RDX + 0x20]
00a13603  MOV R10,qword ptr [RDX + 0x28]
00a13607  CALL 0x00505680
00a1360c  ADD RSP,0x40
00a13610  POP RBP
00a13611  RET
00a13612  MOV qword ptr [RSP + 0x8],RAX
00a13617  MOV qword ptr [RSP + 0x10],RBX
00a1361c  MOV qword ptr [RSP + 0x18],RCX
00a13621  CALL 0x0048a1e0
00a13626  MOV RAX,qword ptr [RSP + 0x8]
00a1362b  MOV RBX,qword ptr [RSP + 0x10]
00a13630  MOV RCX,qword ptr [RSP + 0x18]
00a13635  JMP 0x00a135e0
