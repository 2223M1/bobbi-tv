; mv-daemon/provider.(*TokenStore).Save
00a63a60  LEA R12,[RSP + -0x20]
00a63a65  CMP R12,qword ptr [R14 + 0x10]
00a63a69  JBE 0x00a63d58
00a63a6f  PUSH RBP
00a63a70  MOV RBP,RSP
00a63a73  SUB RSP,0x98
00a63a7a  MOVQ qword ptr [RSP + 0x90],XMM15
00a63a84  MOV qword ptr [RSP + 0xa8],RAX
00a63a8c  MOV qword ptr [RSP + 0xc8],RSI
00a63a94  MOV qword ptr [RSP + 0xb8],RCX
00a63a9c  MOV qword ptr [RSP + 0xb0],RBX
00a63aa4  MOV qword ptr [RSP + 0xc0],RDI
00a63aac  MOV byte ptr [RSP + 0x37],0x0
00a63ab1  MOVUPS xmmword ptr [RSP + 0x68],XMM15
00a63ab7  NOP
00a63ab8  NOP
00a63ab9  MOV RDX,RAX
00a63abc  XOR EAX,EAX
00a63abe  MOV R8D,0x1
00a63ac4  CMPXCHG.LOCK dword ptr [RDX],R8D
00a63ac9  SETZ R8B
00a63acd  TEST R8B,R8B
00a63ad0  JNZ 0x00a63b02
00a63ad2  MOV RAX,RDX
00a63ad5  CALL 0x00493480
00a63ada  MOV RCX,qword ptr [RSP + 0xb8]
00a63ae2  MOV RDX,qword ptr [RSP + 0xa8]
00a63aea  MOV RBX,qword ptr [RSP + 0xb0]
00a63af2  MOV RSI,qword ptr [RSP + 0xc8]
00a63afa  MOV RDI,qword ptr [RSP + 0xc0]
00a63b02  LEA R8,[0xa63da0]
00a63b09  MOV qword ptr [RSP + 0x80],R8
00a63b11  MOV qword ptr [RSP + 0x88],RDX
00a63b19  LEA R8,[RSP + 0x80]
00a63b21  MOV qword ptr [RSP + 0x90],R8
00a63b29  MOV byte ptr [RSP + 0x37],0x1
00a63b2e  CMP qword ptr [RDX + 0x18],0x0
00a63b33  JNZ 0x00a63b79
00a63b35  CALL 0x004825c0
00a63b3a  CMP dword ptr [0x019b5f00],0x0
00a63b41  JNZ 0x00a63b4d
00a63b43  MOV RCX,qword ptr [RSP + 0xa8]
00a63b4b  JMP 0x00a63b65
00a63b4d  MOV RCX,qword ptr [RSP + 0xa8]
00a63b55  MOV RDX,qword ptr [RCX + 0x18]
00a63b59  CALL 0x0048bc00
00a63b5e  MOV qword ptr [R11],RAX
00a63b61  MOV qword ptr [R11 + 0x8],RDX
00a63b65  MOV qword ptr [RCX + 0x18],RAX
00a63b69  MOV RSI,qword ptr [RSP + 0xc8]
00a63b71  MOV RDI,qword ptr [RSP + 0xc0]
00a63b79  MOV RAX,RDI
00a63b7c  MOV RBX,RSI
00a63b7f  NOP
00a63b80  CALL 0x004b0460
00a63b85  TEST RBX,RBX
00a63b88  JNZ 0x00a63bb4
00a63b8a  MOV RDX,qword ptr [RSP + 0xa8]
00a63b92  MOV RBX,qword ptr [RDX + 0x18]
00a63b96  LEA RAX,[0xe16200]
00a63b9d  MOV RCX,qword ptr [RSP + 0xb0]
00a63ba5  MOV RDI,qword ptr [RSP + 0xb8]
00a63bad  CALL 0x00413a00
00a63bb2  JMP 0x00a63c17
00a63bb4  MOV RDX,qword ptr [RSP + 0xa8]
00a63bbc  MOV RBX,qword ptr [RDX + 0x18]
00a63bc0  LEA RAX,[0xe16200]
00a63bc7  MOV RCX,qword ptr [RSP + 0xb0]
00a63bcf  MOV RDI,qword ptr [RSP + 0xb8]
00a63bd7  CALL 0x00413460
00a63bdc  MOV RDX,qword ptr [RSP + 0xc8]
00a63be4  MOV qword ptr [RAX + 0x8],RDX
00a63be8  CMP dword ptr [0x019b5f00],0x0
00a63bef  JNZ 0x00a63bfb
00a63bf1  MOV RDX,qword ptr [RSP + 0xc0]
00a63bf9  JMP 0x00a63c14
00a63bfb  MOV RCX,qword ptr [RAX]
00a63bfe  NOP
00a63c00  CALL 0x0048bc00
00a63c05  MOV RDX,qword ptr [RSP + 0xc0]
00a63c0d  MOV qword ptr [R11],RDX
00a63c10  MOV qword ptr [R11 + 0x8],RCX
00a63c14  MOV qword ptr [RAX],RDX
00a63c17  MOV RCX,qword ptr [RSP + 0xa8]
00a63c1f  MOV RBX,qword ptr [RCX + 0x18]
00a63c23  LEA RAX,[0xe16200]
00a63c2a  CALL 0x00532d60
00a63c2f  TEST RDI,RDI
00a63c32  JNZ 0x00a63d0c
00a63c38  MOV qword ptr [RSP + 0x58],RBX
00a63c3d  MOV qword ptr [RSP + 0x78],RAX
00a63c42  MOV qword ptr [RSP + 0x60],RCX
00a63c47  CALL 0x0095fac0
00a63c4c  MOV RDI,RAX
00a63c4f  MOV RSI,RBX
00a63c52  MOV R8,RCX
00a63c55  MOV RAX,qword ptr [RSP + 0x78]
00a63c5a  MOV RBX,qword ptr [RSP + 0x58]
00a63c5f  MOV RCX,qword ptr [RSP + 0x60]
00a63c64  CALL 0x0095f4e0
00a63c69  TEST RCX,RCX
00a63c6c  JZ 0x00a63c9d
00a63c6e  MOV qword ptr [RSP + 0x68],RCX
00a63c73  MOV qword ptr [RSP + 0x70],RDI
00a63c78  MOV byte ptr [RSP + 0x37],0x0
00a63c7d  MOV RDX,qword ptr [RSP + 0x90]
00a63c85  MOV RAX,qword ptr [RDX]
00a63c88  CALL RAX
00a63c8a  MOV RAX,qword ptr [RSP + 0x68]
00a63c8f  MOV RBX,qword ptr [RSP + 0x70]
00a63c94  ADD RSP,0x98
00a63c9b  POP RBP
00a63c9c  RET
00a63c9d  MOV RCX,RBX
00a63ca0  MOV RBX,RAX
00a63ca3  LEA RAX,[RSP + 0x38]
00a63ca8  CALL 0x0046bae0
00a63cad  MOV RDX,qword ptr [RSP + 0xa8]
00a63cb5  MOV RSI,qword ptr [RDX + 0x8]
00a63cb9  MOV RDX,qword ptr [RDX + 0x10]
00a63cbd  MOV RDI,RBX
00a63cc0  MOV R8D,0x180
00a63cc6  MOV RBX,RDX
00a63cc9  MOV RDX,RAX
00a63ccc  MOV RAX,RSI
00a63ccf  MOV R9,RCX
00a63cd2  MOV RCX,RDX
00a63cd5  MOV RSI,R9
00a63cd8  CALL 0x004d8e20
00a63cdd  MOV qword ptr [RSP + 0x68],RAX
00a63ce2  MOV qword ptr [RSP + 0x70],RBX
00a63ce7  MOV byte ptr [RSP + 0x37],0x0
00a63cec  MOV RDX,qword ptr [RSP + 0x90]
00a63cf4  MOV RSI,qword ptr [RDX]
00a63cf7  CALL RSI
00a63cf9  MOV RAX,qword ptr [RSP + 0x68]
00a63cfe  MOV RBX,qword ptr [RSP + 0x70]
00a63d03  ADD RSP,0x98
00a63d0a  POP RBP
00a63d0b  RET
00a63d0c  MOV qword ptr [RSP + 0x68],RDI
00a63d11  MOV qword ptr [RSP + 0x70],RSI
00a63d16  MOV byte ptr [RSP + 0x37],0x0
00a63d1b  MOV RDX,qword ptr [RSP + 0x90]
00a63d23  MOV RAX,qword ptr [RDX]
00a63d26  CALL RAX
00a63d28  MOV RAX,qword ptr [RSP + 0x68]
00a63d2d  MOV RBX,qword ptr [RSP + 0x70]
00a63d32  ADD RSP,0x98
00a63d39  POP RBP
00a63d3a  RET
00a63d58  MOV qword ptr [RSP + 0x8],RAX
00a63d5d  MOV qword ptr [RSP + 0x10],RBX
00a63d62  MOV qword ptr [RSP + 0x18],RCX
00a63d67  MOV qword ptr [RSP + 0x20],RDI
00a63d6c  MOV qword ptr [RSP + 0x28],RSI
00a63d71  CALL 0x0048a280
00a63d76  MOV RAX,qword ptr [RSP + 0x8]
00a63d7b  MOV RBX,qword ptr [RSP + 0x10]
00a63d80  MOV RCX,qword ptr [RSP + 0x18]
00a63d85  MOV RDI,qword ptr [RSP + 0x20]
00a63d8a  MOV RSI,qword ptr [RSP + 0x28]
00a63d8f  JMP 0x00a63a60
