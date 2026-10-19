; type:.eq.mv-daemon/provider.OfflineCacheStore
00a96bc0  CMP RSP,qword ptr [R14 + 0x10]
00a96bc4  JBE 0x00a96c07
00a96bc6  PUSH RBP
00a96bc7  MOV RBP,RSP
00a96bca  SUB RSP,0x18
00a96bce  MOV EDX,dword ptr [RAX]
00a96bd0  CMP dword ptr [RBX],EDX
00a96bd2  JNZ 0x00a96bff
00a96bd4  MOV EDX,dword ptr [RAX + 0x4]
00a96bd7  CMP dword ptr [RBX + 0x4],EDX
00a96bda  JNZ 0x00a96bff
00a96bdc  MOV RDX,qword ptr [RAX + 0x8]
00a96be0  CMP qword ptr [RBX + 0x8],RDX
00a96be4  JNZ 0x00a96bff
00a96be6  MOV RCX,qword ptr [RAX + 0x18]
00a96bea  CMP qword ptr [RBX + 0x18],RCX
00a96bee  JNZ 0x00a96bff
00a96bf0  MOV RBX,qword ptr [RBX + 0x10]
00a96bf4  MOV RAX,qword ptr [RAX + 0x10]
00a96bf8  CALL 0x00403be0
00a96bfd  JMP 0x00a96c01
00a96bff  XOR EAX,EAX
00a96c01  ADD RSP,0x18
00a96c05  POP RBP
00a96c06  RET
00a96c07  MOV qword ptr [RSP + 0x8],RAX
00a96c0c  MOV qword ptr [RSP + 0x10],RBX
00a96c11  CALL 0x0048a280
00a96c16  MOV RAX,qword ptr [RSP + 0x8]
00a96c1b  MOV RBX,qword ptr [RSP + 0x10]
00a96c20  JMP 0x00a96bc0
