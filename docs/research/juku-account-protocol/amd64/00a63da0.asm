; mv-daemon/provider.(*TokenStore).Save.deferwrap1
00a63da0  CMP RSP,qword ptr [R14 + 0x10]
00a63da4  JBE 0x00a63dcf
00a63da6  PUSH RBP
00a63da7  MOV RBP,RSP
00a63daa  SUB RSP,0x10
00a63dae  MOV RAX,qword ptr [RDX + 0x8]
00a63db2  NOP
00a63db3  MOV EBX,0xffffffff
00a63db8  XADD.LOCK dword ptr [RAX],EBX
00a63dbc  NOP dword ptr [RAX]
00a63dc0  DEC EBX
00a63dc2  JZ 0x00a63dc9
00a63dc4  CALL 0x00493760
00a63dc9  ADD RSP,0x10
00a63dcd  POP RBP
00a63dce  RET
00a63dcf  CALL 0x0048a1e0
00a63dd4  JMP 0x00a63da0
