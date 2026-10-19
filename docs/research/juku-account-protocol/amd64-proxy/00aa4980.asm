; mv-daemon/pkg/proxy.(*ProxyManager).RegisterFull
00aa4980  LEA R12,[RSP + -0x340]
00aa4988  CMP R12,qword ptr [R14 + 0x10]
00aa498c  JBE 0x00aa6098
00aa4992  PUSH RBP
00aa4993  MOV RBP,RSP
00aa4996  SUB RSP,0x3b8
00aa499d  MOVQ qword ptr [RSP + 0x3b0],XMM15
00aa49a7  MOV qword ptr [RSP + 0x3c8],RAX
00aa49af  MOV qword ptr [RSP + 0x3e0],RDI
00aa49b7  MOV qword ptr [RSP + 0x3e8],RSI
00aa49bf  MOV qword ptr [RSP + 0x3f0],R8
00aa49c7  MOV qword ptr [RSP + 0x3f8],R9
00aa49cf  MOV byte ptr [RSP + 0x400],R10B
00aa49d7  MOV qword ptr [RSP + 0x408],R11
00aa49df  MOV qword ptr [RSP + 0x3d8],RCX
00aa49e7  MOV qword ptr [RSP + 0x3d0],RBX
00aa49ef  MOV byte ptr [RSP + 0x47],0x0
00aa49f4  MOVUPS xmmword ptr [RSP + 0x1e0],XMM15
00aa49fd  NOP
00aa49fe  NOP
00aa49ff  LEA RAX,[RSP + 0x160]
00aa4a07  MOVUPS xmmword ptr [RAX],XMM15
00aa4a0b  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00aa4a10  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00aa4a15  MOVUPS xmmword ptr [RAX + 0x30],XMM15
00aa4a1a  MOVUPS xmmword ptr [RAX + 0x40],XMM15
00aa4a1f  MOVUPS xmmword ptr [RAX + 0x50],XMM15
00aa4a24  MOVUPS xmmword ptr [RAX + 0x60],XMM15
00aa4a29  MOVUPS xmmword ptr [RAX + 0x68],XMM15
00aa4a2e  CALL 0x00d05cc0
00aa4a33  LEA RAX,[RSP + 0x88]
00aa4a3b  MOV RBX,qword ptr [RSP + 0x3d0]
00aa4a43  MOV RCX,qword ptr [RSP + 0x3d8]
00aa4a4b  CALL 0x0046bae0
00aa4a50  MOV RDI,RCX
00aa4a53  MOV RCX,RBX
00aa4a56  MOV RBX,RAX
00aa4a59  LEA RAX,[RSP + 0x160]
00aa4a61  CALL 0x00d05dc0
00aa4a66  MOVUPS xmmword ptr [RSP + 0x390],XMM15
00aa4a6f  MOV RAX,qword ptr [RSP + 0x3e8]
00aa4a77  CALL 0x00481e60
00aa4a7c  LEA RCX,[0xdd2b80]
00aa4a83  MOV qword ptr [RSP + 0x390],RCX
00aa4a8b  MOV qword ptr [RSP + 0x398],RAX
00aa4a93  LEA RAX,[0xefa6de]
00aa4a9a  MOV EBX,0x2
00aa4a9f  LEA RCX,[RSP + 0x390]
00aa4aa7  MOV EDI,0x1
00aa4aac  MOV RSI,RDI
00aa4aaf  CALL 0x005055a0
00aa4ab4  MOV RCX,RBX
00aa4ab7  MOV RBX,RAX
00aa4aba  LEA RAX,[RSP + 0x68]
00aa4abf  NOP
00aa4ac0  CALL 0x0046bae0
00aa4ac5  MOV RDI,RCX
00aa4ac8  MOV RCX,RBX
00aa4acb  MOV RBX,RAX
00aa4ace  LEA RAX,[RSP + 0x160]
00aa4ad6  CALL 0x00d05dc0
00aa4adb  LEA RCX,[RSP + 0x330]
00aa4ae3  MOVUPS xmmword ptr [RCX],XMM15
00aa4ae7  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00aa4aec  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00aa4af1  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00aa4af6  MOVUPS xmmword ptr [RCX + 0x40],XMM15
00aa4afb  MOVUPS xmmword ptr [RCX + 0x50],XMM15
00aa4b00  LEA RAX,[0xe16200]
00aa4b07  MOV RBX,qword ptr [RSP + 0x3e0]
00aa4b0f  CALL 0x004225e0
00aa4b14  XOR EAX,EAX
00aa4b16  XOR ECX,ECX
00aa4b18  XOR EDX,EDX
00aa4b1a  XOR EBX,EBX
00aa4b1c  JMP 0x00aa4b54
00aa4b1e  MOV qword ptr [RSP + 0x218],RBX
00aa4b26  MOV qword ptr [RBX + RCX*0x1],R10
00aa4b2a  LEA RAX,[RSP + 0x330]
00aa4b32  CALL 0x00422640
00aa4b37  MOVZX EAX,byte ptr [RSP + 0x45]
00aa4b3c  MOV RCX,qword ptr [RSP + 0xe8]
00aa4b44  MOV RDX,qword ptr [RSP + 0xf0]
00aa4b4c  MOV RBX,qword ptr [RSP + 0x218]
00aa4b54  MOV R8,qword ptr [RSP + 0x330]
00aa4b5c  NOP dword ptr [RAX]
00aa4b60  TEST R8,R8
00aa4b63  JZ 0x00aa4c34
00aa4b69  LEA R9,[RCX + 0x1]
00aa4b6d  MOV R10,qword ptr [R8]
00aa4b70  MOV R8,qword ptr [R8 + 0x8]
00aa4b74  CMP RDX,R9
00aa4b77  JNC 0x00aa4bf1
00aa4b79  MOV qword ptr [RSP + 0x228],R10
00aa4b81  MOV qword ptr [RSP + 0x100],R8
00aa4b89  MOV byte ptr [RSP + 0x46],AL
00aa4b8d  CMP R9,0x2
00aa4b91  JG 0x00aa4bb9
00aa4b93  TEST AL,AL
00aa4b95  JNZ 0x00aa4bb9
00aa4b97  TEST RCX,RCX
00aa4b9a  JNZ 0x00aa4bb9
00aa4b9c  LEA RBX,[RSP + 0x260]
00aa4ba4  MOVUPS xmmword ptr [RBX],XMM15
00aa4ba8  MOVUPS xmmword ptr [RBX + 0x10],XMM15
00aa4bad  MOV EDX,0x2
00aa4bb2  MOV EAX,0x1
00aa4bb7  JMP 0x00aa4bf1
00aa4bb9  MOV RAX,RBX
00aa4bbc  MOV RBX,R9
00aa4bbf  MOV RCX,RDX
00aa4bc2  MOV EDI,0x1
00aa4bc7  LEA RSI,[0xdd29c0]
00aa4bce  CALL 0x00486be0
00aa4bd3  MOV R8,qword ptr [RSP + 0x100]
00aa4bdb  MOV R10,qword ptr [RSP + 0x228]
00aa4be3  MOV R9,RBX
00aa4be6  MOV RDX,RCX
00aa4be9  MOV RBX,RAX
00aa4bec  MOVZX EAX,byte ptr [RSP + 0x46]
00aa4bf1  MOV qword ptr [RSP + 0xe8],R9
00aa4bf9  MOV qword ptr [RSP + 0xf0],RDX
00aa4c01  MOV byte ptr [RSP + 0x45],AL
00aa4c05  LEA RCX,[R9 + -0x1]
00aa4c09  SHL RCX,0x4
00aa4c0d  MOV qword ptr [RBX + RCX*0x1 + 0x8],R8
00aa4c12  CMP dword ptr [0x019b5f00],0x0
00aa4c19  JZ 0x00aa4b1e
00aa4c1f  MOV RSI,qword ptr [RCX + RBX*0x1]
00aa4c23  CALL 0x0048bc00
00aa4c28  MOV qword ptr [R11],R10
00aa4c2b  MOV qword ptr [R11 + 0x8],RSI
00aa4c2f  JMP 0x00aa4b1e
00aa4c34  MOV qword ptr [RSP + 0xe8],RCX
00aa4c3c  MOV qword ptr [RSP + 0x258],RBX
00aa4c44  MOV RAX,RBX
00aa4c47  MOV RBX,RCX
00aa4c4a  MOV RCX,RDX
00aa4c4d  CALL 0x005fb600
00aa4c52  MOV RDX,qword ptr [RSP + 0x258]
00aa4c5a  XOR EAX,EAX
00aa4c5c  NOP dword ptr [RAX]
00aa4c60  JMP 0x00aa4cff
00aa4c65  MOV qword ptr [RSP + 0x138],RAX
00aa4c6d  MOV qword ptr [RSP + 0x250],RDX
00aa4c75  MOV RCX,qword ptr [RDX]
00aa4c78  MOV qword ptr [RSP + 0x220],RCX
00aa4c80  MOV RDI,qword ptr [RDX + 0x8]
00aa4c84  MOV qword ptr [RSP + 0xf8],RDI
00aa4c8c  LEA RAX,[0xe16200]
00aa4c93  MOV RBX,qword ptr [RSP + 0x3e0]
00aa4c9b  NOP dword ptr [RAX + RAX*0x1]
00aa4ca0  CALL 0x00412ee0
00aa4ca5  MOV R8,qword ptr [RAX]
00aa4ca8  MOV R9,qword ptr [RAX + 0x8]
00aa4cac  LEA RAX,[RSP + 0x48]
00aa4cb1  MOV RBX,qword ptr [RSP + 0x220]
00aa4cb9  MOV RCX,qword ptr [RSP + 0xf8]
00aa4cc1  LEA RDI,[0x1133210]
00aa4cc8  MOV ESI,0x1
00aa4ccd  CALL 0x0046b780
00aa4cd2  MOV RDI,RCX
00aa4cd5  MOV RCX,RBX
00aa4cd8  MOV RBX,RAX
00aa4cdb  LEA RAX,[RSP + 0x160]
00aa4ce3  CALL 0x00d05dc0
00aa4ce8  MOV RDX,qword ptr [RSP + 0x250]
00aa4cf0  ADD RDX,0x10
00aa4cf4  MOV RAX,qword ptr [RSP + 0x138]
00aa4cfc  INC RAX
00aa4cff  MOV RSI,qword ptr [RSP + 0xe8]
00aa4d07  CMP RAX,RSI
00aa4d0a  JL 0x00aa4c65
00aa4d10  LEA RAX,[RSP + 0x160]
00aa4d18  XOR EBX,EBX
00aa4d1a  XOR ECX,ECX
00aa4d1c  MOV RDI,RCX
00aa4d1f  NOP
00aa4d20  CALL 0x00d06060
00aa4d25  LEA RCX,[RBX + RBX*0x1]
00aa4d29  CMP RCX,0x20
00aa4d2d  JA 0x00aa4d4a
00aa4d2f  LEA RDX,[RSP + 0x140]
00aa4d37  MOVUPS xmmword ptr [RDX],XMM15
00aa4d3b  MOVUPS xmmword ptr [RDX + 0x10],XMM15
00aa4d40  LEA RDX,[RSP + 0x140]
00aa4d48  JMP 0x00aa4d8c
00aa4d4a  MOV qword ptr [RSP + 0xb8],RCX
00aa4d52  MOV qword ptr [RSP + 0xc8],RBX
00aa4d5a  MOV qword ptr [RSP + 0x1f0],RAX
00aa4d62  LEA RAX,[0xdd2a40]
00aa4d69  MOV RBX,RCX
00aa4d6c  CALL 0x00486b00
00aa4d71  MOV RCX,qword ptr [RSP + 0xb8]
00aa4d79  MOV RBX,qword ptr [RSP + 0xc8]
00aa4d81  MOV RDX,RAX
00aa4d84  MOV RAX,qword ptr [RSP + 0x1f0]
00aa4d8c  XOR ESI,ESI
00aa4d8e  XOR EDI,EDI
00aa4d90  JMP 0x00aa4da0
00aa4d92  MOV byte ptr [RDI + RDX*0x1 + 0x1],R9B
00aa4d97  INC RSI
00aa4d9a  ADD RDI,0x2
00aa4d9e  NOP
00aa4da0  CMP RBX,RSI
00aa4da3  JLE 0x00aa4dea
00aa4da5  MOVZX R8D,byte ptr [RAX + RSI*0x1]
00aa4daa  MOV R9D,R8D
00aa4dad  SHR R8B,0x4
00aa4db1  MOVZX R8D,R8B
00aa4db5  LEA R10,[0xf1956c]
00aa4dbc  MOVZX R8D,byte ptr [R10 + R8*0x1]
00aa4dc1  CMP RDI,RCX
00aa4dc4  JNC 0x00aa6074
00aa4dca  MOV byte ptr [RDX + RDI*0x1],R8B
00aa4dce  LEA R8,[RDI + 0x1]
00aa4dd2  AND R9D,0xf
00aa4dd6  MOVZX R9D,byte ptr [R9 + R10*0x1]
00aa4ddb  NOP dword ptr [RAX + RAX*0x1]
00aa4de0  CMP R8,RCX
00aa4de3  JC 0x00aa4d92
00aa4de5  JMP 0x00aa606f
00aa4dea  XOR EAX,EAX
00aa4dec  MOV RBX,RDX
00aa4def  CALL 0x0046b920
00aa4df4  MOV qword ptr [RSP + 0x1d8],RAX
00aa4dfc  MOV qword ptr [RSP + 0xa8],RBX
00aa4e04  NOP
00aa4e05  NOP
00aa4e06  MOV RCX,RAX
00aa4e09  XOR EAX,EAX
00aa4e0b  MOV RDX,qword ptr [RSP + 0x3c8]
00aa4e13  MOV ESI,0x1
00aa4e18  CMPXCHG.LOCK dword ptr [RDX],ESI
00aa4e1c  SETZ SIL
00aa4e20  TEST SIL,SIL
00aa4e23  JNZ 0x00aa4e45
00aa4e25  MOV RAX,RDX
00aa4e28  CALL 0x00493480
00aa4e2d  MOV RCX,qword ptr [RSP + 0x1d8]
00aa4e35  MOV RDX,qword ptr [RSP + 0x3c8]
00aa4e3d  MOV RBX,qword ptr [RSP + 0xa8]
00aa4e45  LEA RSI,[0xaa6220]
00aa4e4c  MOV qword ptr [RSP + 0x2f0],RSI
00aa4e54  MOV qword ptr [RSP + 0x2f8],RDX
00aa4e5c  LEA RSI,[RSP + 0x2f0]
00aa4e64  MOV qword ptr [RSP + 0x3b0],RSI
00aa4e6c  MOV byte ptr [RSP + 0x47],0x1
00aa4e71  MOV RDX,qword ptr [RDX + 0x8]
00aa4e75  LEA RAX,[0xe18f00]
00aa4e7c  MOV RDI,RBX
00aa4e7f  MOV RBX,RDX
00aa4e82  CALL 0x004131a0
00aa4e87  TEST BL,BL
00aa4e89  JZ 0x00aa4ef0
00aa4e8b  MOV RAX,qword ptr [RAX]
00aa4e8e  MOV RBX,qword ptr [RSP + 0x408]
00aa4e96  TEST RBX,RBX
00aa4e99  JZ 0x00aa4eb0
00aa4e9b  MOV qword ptr [RSP + 0x240],RAX
00aa4ea3  CALL 0x00a9e780
00aa4ea8  MOV RAX,qword ptr [RSP + 0x240]
00aa4eb0  MOVZX R8D,byte ptr [RSP + 0x400]
00aa4eb9  TEST R8B,R8B
00aa4ebc  JZ 0x00aa4ec8
00aa4ebe  MOV EBX,0x1
00aa4ec3  CALL 0x00a9d580
00aa4ec8  MOV R8,qword ptr [RSP + 0x3c8]
00aa4ed0  MOV R9,qword ptr [R8 + 0x10]
00aa4ed4  NOP
00aa4ed5  MOV R10,qword ptr [R8 + 0x18]
00aa4ed9  MOV qword ptr [RSP + 0x138],R10
00aa4ee1  MOV R11,qword ptr [RSP + 0xa8]
00aa4ee9  XOR EAX,EAX
00aa4eeb  JMP 0x00aa5df6
00aa4ef0  MOV RDX,qword ptr [RSP + 0x3c8]
00aa4ef8  MOV RSI,qword ptr [RDX + 0x8]
00aa4efc  NOP dword ptr [RAX]
00aa4f00  TEST RSI,RSI
00aa4f03  JZ 0x00aa4f0a
00aa4f05  MOV RSI,qword ptr [RSI]
00aa4f08  JMP 0x00aa4f0c
00aa4f0a  XOR ESI,ESI
00aa4f0c  CMP qword ptr [RDX + 0x28],RSI
00aa4f10  JG 0x00aa508a
00aa4f16  MOV RSI,qword ptr [RDX + 0x18]
00aa4f1a  NOP word ptr [RAX + RAX*0x1]
00aa4f20  TEST RSI,RSI
00aa4f23  JZ 0x00aa508a
00aa4f29  MOV R8,qword ptr [RDX + 0x10]
00aa4f2d  MOV R9,qword ptr [RDX + 0x20]
00aa4f31  DEC R9
00aa4f34  MOV R10,R9
00aa4f37  NEG R9
00aa4f3a  SAR R9,0x3f
00aa4f3e  AND R9D,0x10
00aa4f42  DEC RSI
00aa4f45  MOV RDI,qword ptr [R8 + 0x8]
00aa4f49  MOV RCX,qword ptr [R8]
00aa4f4c  MOV qword ptr [RDX + 0x18],RSI
00aa4f50  MOV qword ptr [RDX + 0x20],R10
00aa4f54  LEA RSI,[R9 + R8*0x1]
00aa4f58  CMP dword ptr [0x019b5f00],0x0
00aa4f5f  NOP
00aa4f60  JZ 0x00aa4f72
00aa4f62  MOV R8,qword ptr [RDX + 0x10]
00aa4f66  CALL 0x0048bc00
00aa4f6b  MOV qword ptr [R11],RSI
00aa4f6e  MOV qword ptr [R11 + 0x8],R8
00aa4f72  MOV qword ptr [RSP + 0x200],RCX
00aa4f7a  MOV qword ptr [RSP + 0xd8],RDI
00aa4f82  MOV qword ptr [RDX + 0x10],RSI
00aa4f86  MOV RBX,qword ptr [RDX + 0x8]
00aa4f8a  LEA RAX,[0xe18f00]
00aa4f91  CALL 0x004131a0
00aa4f96  TEST BL,BL
00aa4f98  JZ 0x00aa4ef0
00aa4f9e  MOV RCX,qword ptr [RAX]
00aa4fa1  MOV qword ptr [RSP + 0x208],RCX
00aa4fa9  MOVUPS xmmword ptr [RSP + 0x2e0],XMM15
00aa4fb2  MOV RAX,qword ptr [RSP + 0x200]
00aa4fba  MOV RBX,qword ptr [RSP + 0xd8]
00aa4fc2  CALL 0x00481ee0
00aa4fc7  LEA RCX,[0xdd29c0]
00aa4fce  MOV qword ptr [RSP + 0x2e0],RCX
00aa4fd6  MOV qword ptr [RSP + 0x2e8],RAX
00aa4fde  LEA RCX,[0xaa61c0]
00aa4fe5  MOV qword ptr [RSP + 0x300],RCX
00aa4fed  MOV qword ptr [RSP + 0x310],0x30
00aa4ff9  LEA RCX,[0xf44a80]
00aa5000  MOV qword ptr [RSP + 0x308],RCX
00aa5008  MOV qword ptr [RSP + 0x320],0x1
00aa5014  MOV qword ptr [RSP + 0x328],0x1
00aa5020  LEA RCX,[RSP + 0x2e0]
00aa5028  MOV qword ptr [RSP + 0x318],RCX
00aa5030  MOV RAX,qword ptr [0x01990148]
00aa5037  XOR EBX,EBX
00aa5039  MOV ECX,0x2
00aa503e  LEA RDI,[RSP + 0x300]
00aa5046  CALL 0x0054d540
00aa504b  MOV RAX,qword ptr [RSP + 0x208]
00aa5053  CALL 0x00aa3220
00aa5058  MOV RCX,qword ptr [RSP + 0x3c8]
00aa5060  MOV RBX,qword ptr [RCX + 0x8]
00aa5064  LEA RAX,[0xe18f00]
00aa506b  MOV RCX,qword ptr [RSP + 0x200]
00aa5073  MOV RDI,qword ptr [RSP + 0xd8]
00aa507b  NOP dword ptr [RAX + RAX*0x1]
00aa5080  CALL 0x00413a00
00aa5085  JMP 0x00aa4ef0
00aa508a  MOV RAX,qword ptr [RSP + 0x3d0]
00aa5092  MOV RBX,qword ptr [RSP + 0x3d8]
00aa509a  CALL 0x004af740
00aa509f  MOV qword ptr [RSP + 0x210],RAX
00aa50a7  MOV qword ptr [RSP + 0xe0],RBX
00aa50af  MOVZX ECX,byte ptr [RSP + 0x400]
00aa50b7  TEST CL,CL
00aa50b9  JZ 0x00aa50c5
00aa50bb  XOR ESI,ESI
00aa50bd  NOP dword ptr [RAX]
00aa50c0  JMP 0x00aa51a9
00aa50c5  LEA RCX,[0xefb583]
00aa50cc  MOV EDI,0x4
00aa50d1  CALL 0x00414f60
00aa50d6  TEST RAX,RAX
00aa50d9  JL 0x00aa50e2
00aa50db  MOV EDX,0x1
00aa50e0  JMP 0x00aa5138
00aa50e2  MOV RAX,qword ptr [RSP + 0x210]
00aa50ea  MOV RBX,qword ptr [RSP + 0xe0]
00aa50f2  LEA RCX,[0xefb557]
00aa50f9  MOV EDI,0x4
00aa50fe  NOP
00aa5100  CALL 0x00414f60
00aa5105  TEST RAX,RAX
00aa5108  JL 0x00aa5111
00aa510a  MOV EDX,0x1
00aa510f  JMP 0x00aa5138
00aa5111  MOV RAX,qword ptr [RSP + 0x210]
00aa5119  MOV RBX,qword ptr [RSP + 0xe0]
00aa5121  LEA RCX,[0xefb84f]
00aa5128  MOV EDI,0x4
00aa512d  CALL 0x00414f60
00aa5132  TEST RAX,RAX
00aa5135  SETGE DL
00aa5138  TEST DL,DL
00aa513a  JZ 0x00aa514b
00aa513c  MOV RDX,qword ptr [RSP + 0x3e8]
00aa5144  MOV ESI,0x1
00aa5149  JMP 0x00aa5191
00aa514b  MOV RAX,qword ptr [RSP + 0x210]
00aa5153  MOV RBX,qword ptr [RSP + 0xe0]
00aa515b  LEA RCX,[0xefb5a7]
00aa5162  MOV EDI,0x4
00aa5167  CALL 0x00414f60
00aa516c  TEST RAX,RAX
00aa516f  JL 0x00aa5182
00aa5171  MOV RDX,qword ptr [RSP + 0x3e8]
00aa5179  MOV ESI,0x1
00aa517e  NOP
00aa5180  JMP 0x00aa5191
00aa5182  MOV RDX,qword ptr [RSP + 0x3e8]
00aa518a  TEST RDX,RDX
00aa518d  SETLE SIL
00aa5191  MOV RAX,qword ptr [RSP + 0x210]
00aa5199  MOVZX ECX,byte ptr [RSP + 0x400]
00aa51a1  MOV RBX,qword ptr [RSP + 0xe0]
00aa51a9  TEST SIL,SIL
00aa51ac  JNZ 0x00aa51b6
00aa51ae  TEST CL,CL
00aa51b0  JZ 0x00aa5351
00aa51b6  LEA RCX,[RSP + 0x2c0]
00aa51be  MOVUPS xmmword ptr [RCX],XMM15
00aa51c2  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00aa51c7  MOV RAX,qword ptr [RSP + 0x3d0]
00aa51cf  MOV RBX,qword ptr [RSP + 0x3d8]
00aa51d7  CALL 0x00481ee0
00aa51dc  LEA RCX,[0xdd29c0]
00aa51e3  MOV qword ptr [RSP + 0x2c0],RCX
00aa51eb  MOV qword ptr [RSP + 0x2c8],RAX
00aa51f3  MOV RAX,qword ptr [RSP + 0x3e8]
00aa51fb  NOP dword ptr [RAX + RAX*0x1]
00aa5200  CALL 0x00481e60
00aa5205  LEA RCX,[0xdd2b80]
00aa520c  MOV qword ptr [RSP + 0x2d0],RCX
00aa5214  MOV qword ptr [RSP + 0x2d8],RAX
00aa521c  LEA RCX,[0xaa6160]
00aa5223  MOV qword ptr [RSP + 0x300],RCX
00aa522b  MOV qword ptr [RSP + 0x310],0x60
00aa5237  LEA RCX,[0xf5e8c1]
00aa523e  MOV qword ptr [RSP + 0x308],RCX
00aa5246  MOV qword ptr [RSP + 0x320],0x2
00aa5252  MOV qword ptr [RSP + 0x328],0x2
00aa525e  LEA RCX,[RSP + 0x2c0]
00aa5266  MOV qword ptr [RSP + 0x318],RCX
00aa526e  MOV RAX,qword ptr [0x01990148]
00aa5275  XOR EBX,EBX
00aa5277  MOV ECX,0x2
00aa527c  LEA RDI,[RSP + 0x300]
00aa5284  CALL 0x0054d540
00aa5289  MOV RAX,qword ptr [RSP + 0x3d0]
00aa5291  MOV RBX,qword ptr [RSP + 0x3d8]
00aa5299  MOV RCX,qword ptr [RSP + 0x3e0]
00aa52a1  MOV RDI,qword ptr [RSP + 0x3e8]
00aa52a9  MOV ESI,0x100000
00aa52ae  XOR R8D,R8D
00aa52b1  MOV R9,R8
00aa52b4  MOV R10D,0x1
00aa52ba  CALL 0x00a9dc40
00aa52bf  MOV qword ptr [RSP + 0x238],RAX
00aa52c7  MOV RBX,qword ptr [RSP + 0x408]
00aa52cf  CALL 0x00a9e780
00aa52d4  MOV RCX,qword ptr [RSP + 0x3c8]
00aa52dc  MOV RBX,qword ptr [RCX + 0x8]
00aa52e0  LEA RAX,[0xe18f00]
00aa52e7  MOV RCX,qword ptr [RSP + 0x1d8]
00aa52ef  MOV RDI,qword ptr [RSP + 0xa8]
00aa52f7  CALL 0x00413460
00aa52fc  CMP dword ptr [0x019b5f00],0x0
00aa5303  JNZ 0x00aa530f
00aa5305  MOV R9,qword ptr [RSP + 0x238]
00aa530d  JMP 0x00aa5326
00aa530f  MOV R8,qword ptr [RAX]
00aa5312  CALL 0x0048bc00
00aa5317  MOV R9,qword ptr [RSP + 0x238]
00aa531f  MOV qword ptr [R11],R9
00aa5322  MOV qword ptr [R11 + 0x8],R8
00aa5326  MOV qword ptr [RAX],R9
00aa5329  MOV R8,qword ptr [RSP + 0x3c8]
00aa5331  MOV R9,qword ptr [R8 + 0x10]
00aa5335  NOP
00aa5336  MOV R10,qword ptr [R8 + 0x18]
00aa533a  MOV qword ptr [RSP + 0x138],R10
00aa5342  MOV R11,qword ptr [RSP + 0xa8]
00aa534a  XOR EAX,EAX
00aa534c  JMP 0x00aa5b76
00aa5351  NOP
00aa5352  LEA RCX,[0xefc8bb]
00aa5359  MOV EDI,0x5
00aa535e  NOP
00aa5360  CALL 0x00414f60
00aa5365  MOV qword ptr [RSP + 0xb0],RAX
00aa536d  MOV RAX,qword ptr [RSP + 0x210]
00aa5375  MOV RBX,qword ptr [RSP + 0xe0]
00aa537d  LEA RCX,[0xf0d4bc]
00aa5384  MOV EDI,0xb
00aa5389  CALL 0x00414f60
00aa538e  TEST RAX,RAX
00aa5391  JL 0x00aa539a
00aa5393  MOV EDX,0x1
00aa5398  JMP 0x00aa53c1
00aa539a  MOV RAX,qword ptr [RSP + 0x210]
00aa53a2  MOV RBX,qword ptr [RSP + 0xe0]
00aa53aa  LEA RCX,[0xefe953]
00aa53b1  MOV EDI,0x6
00aa53b6  CALL 0x00414f60
00aa53bb  TEST RAX,RAX
00aa53be  SETGE DL
00aa53c1  MOV RSI,qword ptr [RSP + 0x3f0]
00aa53c9  CMP RSI,0x10
00aa53cd  MOV EDI,0x10
00aa53d2  MOV R8,RSI
00aa53d5  CMOVL RSI,RDI
00aa53d9  MOV RDI,qword ptr [RSP + 0x3f8]
00aa53e1  TEST RDI,RDI
00aa53e4  JG 0x00aa5662
00aa53ea  MOV qword ptr [RSP + 0xc0],RSI
00aa53f2  MOV R9,qword ptr [RSP + 0xb0]
00aa53fa  TEST R9,R9
00aa53fd  JGE 0x00aa5411
00aa53ff  NOP
00aa5400  TEST DL,DL
00aa5402  JZ 0x00aa563f
00aa5408  TEST R9,R9
00aa540b  JL 0x00aa54e0
00aa5411  MOV RDX,qword ptr [0x01990f90]
00aa5418  TEST RDX,RDX
00aa541b  JNZ 0x00aa5425
00aa541d  XOR ECX,ECX
00aa541f  NOP
00aa5420  JMP 0x00aa558b
00aa5425  MOV RAX,qword ptr [0x01990f98]
00aa542c  MOV RDX,qword ptr [RDX + 0x18]
00aa5430  LEA RBX,[0xefc8c5]
00aa5437  MOV ECX,0x5
00aa543c  CALL RDX
00aa543e  NOP
00aa5440  TEST RBX,RBX
00aa5443  JNZ 0x00aa5449
00aa5445  XOR ECX,ECX
00aa5447  JMP 0x00aa54c4
00aa5449  MOV qword ptr [RSP + 0xd0],RBX
00aa5451  MOV qword ptr [RSP + 0x1f8],RAX
00aa5459  CALL 0x004b0460
00aa545e  NOP
00aa5460  TEST RBX,RBX
00aa5463  JZ 0x00aa546d
00aa5465  CMP byte ptr [RAX],0x7b
00aa5468  SETZ CL
00aa546b  JMP 0x00aa546f
00aa546d  XOR ECX,ECX
00aa546f  TEST CL,CL
00aa5471  JNZ 0x00aa5477
00aa5473  XOR ECX,ECX
00aa5475  JMP 0x00aa54c4
00aa5477  LEA RAX,[0xe0d840]
00aa547e  NOP
00aa5480  CALL 0x00421f00
00aa5485  MOV qword ptr [RSP + 0x3a0],RAX
00aa548d  XOR EAX,EAX
00aa548f  MOV RBX,qword ptr [RSP + 0x1f8]
00aa5497  MOV RCX,qword ptr [RSP + 0xd0]
00aa549f  NOP
00aa54a0  CALL 0x0046bae0
00aa54a5  LEA RDI,[0xdc01e0]
00aa54ac  MOV RSI,qword ptr [RSP + 0x3a0]
00aa54b4  CALL 0x0052c3c0
00aa54b9  MOV RCX,qword ptr [RSP + 0x3a0]
00aa54c1  MOVZX ECX,byte ptr [RCX]
00aa54c4  MOV RSI,qword ptr [RSP + 0xc0]
00aa54cc  MOV R9,qword ptr [RSP + 0xb0]
00aa54d4  JMP 0x00aa558b
00aa54e0  TEST DL,DL
00aa54e2  JZ 0x00aa5589
00aa54e8  MOV RDX,qword ptr [0x01990f90]
00aa54ef  TEST RDX,RDX
00aa54f2  JNZ 0x00aa54fb
00aa54f4  XOR ECX,ECX
00aa54f6  JMP 0x00aa558b
00aa54fb  MOV RAX,qword ptr [0x01990f98]
00aa5502  MOV RDX,qword ptr [RDX + 0x18]
00aa5506  LEA RBX,[0xefe18b]
00aa550d  MOV ECX,0x6
00aa5512  CALL RDX
00aa5514  TEST RBX,RBX
00aa5517  JNZ 0x00aa551d
00aa5519  XOR ECX,ECX
00aa551b  JMP 0x00aa5577
00aa551d  MOV qword ptr [RSP + 0x128],RBX
00aa5525  MOV qword ptr [RSP + 0x248],RAX
00aa552d  LEA RAX,[0xe0d840]
00aa5534  CALL 0x00421f00
00aa5539  MOV qword ptr [RSP + 0x3a8],RAX
00aa5541  XOR EAX,EAX
00aa5543  MOV RBX,qword ptr [RSP + 0x248]
00aa554b  MOV RCX,qword ptr [RSP + 0x128]
00aa5553  CALL 0x0046bae0
00aa5558  LEA RDI,[0xdc01e0]
00aa555f  MOV RSI,qword ptr [RSP + 0x3a8]
00aa5567  CALL 0x0052c3c0
00aa556c  MOV RCX,qword ptr [RSP + 0x3a8]
00aa5574  MOVZX ECX,byte ptr [RCX]
00aa5577  MOV RSI,qword ptr [RSP + 0xc0]
00aa557f  MOV R9,qword ptr [RSP + 0xb0]
00aa5587  JMP 0x00aa558b
00aa5589  XOR ECX,ECX
00aa558b  TEST CL,CL
00aa558d  JZ 0x00aa5600
00aa558f  MOV RAX,qword ptr [RSP + 0x3e8]
00aa5597  MOV RCX,0x3c0000000
00aa55a1  CMP RAX,RCX
00aa55a4  JLE 0x00aa55bc
00aa55a6  MOV RDX,0x140000000
00aa55b0  MOV ESI,0x20
00aa55b5  MOV EDI,0x400000
00aa55ba  JMP 0x00aa55f5
00aa55bc  MOV RDX,0x140000000
00aa55c6  CMP RAX,RDX
00aa55c9  JLE 0x00aa55d7
00aa55cb  MOV ESI,0x20
00aa55d0  MOV EDI,0x200000
00aa55d5  JMP 0x00aa55f5
00aa55d7  CMP RAX,0x40000000
00aa55dd  MOV EBX,0x18
00aa55e2  CMOVG RSI,RBX
00aa55e6  MOV EDI,0x80000
00aa55eb  MOV R8D,0x100000
00aa55f1  CMOVG RDI,R8
00aa55f5  MOV EBX,0x8
00aa55fa  JMP 0x00aa5681
00aa5600  TEST R9,R9
00aa5603  JL 0x00aa5611
00aa5605  MOV EAX,0xc
00aa560a  MOV ECX,0x80000
00aa560f  JMP 0x00aa561b
00aa5611  MOV EAX,0x20
00aa5616  MOV ECX,0x20000
00aa561b  MOV RDX,0x140000000
00aa5625  MOV RBX,RAX
00aa5628  MOV RDI,RCX
00aa562b  MOV RAX,qword ptr [RSP + 0x3e8]
00aa5633  MOV RCX,0x3c0000000
00aa563d  JMP 0x00aa5681
00aa563f  MOV RAX,qword ptr [RSP + 0x3e8]
00aa5647  MOV RCX,0x3c0000000
00aa5651  MOV RDX,0x140000000
00aa565b  MOV RBX,R8
00aa565e  NOP
00aa5660  JMP 0x00aa5681
00aa5662  MOV RAX,qword ptr [RSP + 0x3e8]
00aa566a  MOV RCX,0x3c0000000
00aa5674  MOV RDX,0x140000000
00aa567e  MOV RBX,R8
00aa5681  MOV qword ptr [RSP + 0x138],RBX
00aa5689  TEST RDI,RDI
00aa568c  JLE 0x00aa56c2
00aa568e  CMP RSI,0x18
00aa5692  JGE 0x00aa56bb
00aa5694  CMP RDI,0x800000
00aa569b  JL 0x00aa56a4
00aa569d  MOV ECX,0x10
00aa56a2  JMP 0x00aa56fe
00aa56a4  CMP RDI,0x400000
00aa56ab  MOV ECX,0x20
00aa56b0  MOV EDX,0x18
00aa56b5  CMOVGE RCX,RDX
00aa56b9  JMP 0x00aa56fe
00aa56bb  MOV RCX,RSI
00aa56be  NOP
00aa56c0  JMP 0x00aa56fe
00aa56c2  CMP RAX,RCX
00aa56c5  JLE 0x00aa56d3
00aa56c7  MOV ESI,0x20
00aa56cc  MOV ECX,0x400000
00aa56d1  JMP 0x00aa56f8
00aa56d3  CMP RAX,RDX
00aa56d6  JLE 0x00aa56e4
00aa56d8  MOV ESI,0x20
00aa56dd  MOV ECX,0x200000
00aa56e2  JMP 0x00aa56f8
00aa56e4  CMP RAX,0x40000000
00aa56ea  MOV ECX,0x18
00aa56ef  CMOVG RSI,RCX
00aa56f3  MOV ECX,0x100000
00aa56f8  MOV RDI,RCX
00aa56fb  MOV RCX,RSI
00aa56fe  MOV qword ptr [RSP + 0x120],RDI
00aa5706  MOV qword ptr [RSP + 0xc0],RCX
00aa570e  LEA RCX,[RSP + 0x280]
00aa5716  MOVUPS xmmword ptr [RCX],XMM15
00aa571a  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00aa571f  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00aa5724  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00aa5729  CALL 0x00481e60
00aa572e  LEA RCX,[0xdd2b80]
00aa5735  MOV qword ptr [RSP + 0x280],RCX
00aa573d  MOV qword ptr [RSP + 0x288],RAX
00aa5745  MOV RAX,qword ptr [RSP + 0x138]
00aa574d  CALL 0x00481e60
00aa5752  LEA RCX,[0xdd2c00]
00aa5759  MOV qword ptr [RSP + 0x290],RCX
00aa5761  MOV qword ptr [RSP + 0x298],RAX
00aa5769  MOV RAX,qword ptr [RSP + 0x120]
00aa5771  CALL 0x00481e60
00aa5776  LEA RCX,[0xdd2c00]
00aa577d  MOV qword ptr [RSP + 0x2a0],RCX
00aa5785  MOV qword ptr [RSP + 0x2a8],RAX
00aa578d  MOV RAX,qword ptr [RSP + 0xc0]
00aa5795  CALL 0x00481e60
00aa579a  LEA RCX,[0xdd2c00]
00aa57a1  MOV qword ptr [RSP + 0x2b0],RCX
00aa57a9  MOV qword ptr [RSP + 0x2b8],RAX
00aa57b1  LEA RCX,[0xaa6100]
00aa57b8  MOV qword ptr [RSP + 0x300],RCX
00aa57c0  MOV qword ptr [RSP + 0x310],0x51
00aa57cc  LEA RCX,[0xf59eb9]
00aa57d3  MOV qword ptr [RSP + 0x308],RCX
00aa57db  MOV qword ptr [RSP + 0x320],0x4
00aa57e7  MOV qword ptr [RSP + 0x328],0x4
00aa57f3  LEA RCX,[RSP + 0x280]
00aa57fb  MOV qword ptr [RSP + 0x318],RCX
00aa5803  MOV RAX,qword ptr [0x01990148]
00aa580a  XOR EBX,EBX
00aa580c  MOV ECX,0x2
00aa5811  LEA RDI,[RSP + 0x300]
00aa5819  CALL 0x0054d540
00aa581e  MOV RAX,qword ptr [RSP + 0x3d0]
00aa5826  MOV RBX,qword ptr [RSP + 0x3d8]
00aa582e  MOV RCX,qword ptr [RSP + 0x3e0]
00aa5836  MOV RDI,qword ptr [RSP + 0x3e8]
00aa583e  MOV RSI,qword ptr [RSP + 0x120]
00aa5846  MOV R8,qword ptr [RSP + 0xc0]
00aa584e  MOV R9,qword ptr [RSP + 0x138]
00aa5856  XOR R10D,R10D
00aa5859  CALL 0x00a9dc40
00aa585e  MOV qword ptr [RSP + 0x230],RAX
00aa5866  MOV RBX,qword ptr [RSP + 0x408]
00aa586e  CALL 0x00a9e780
00aa5873  MOV RCX,qword ptr [RSP + 0x3c8]
00aa587b  MOV RBX,qword ptr [RCX + 0x8]
00aa587f  LEA RAX,[0xe18f00]
00aa5886  MOV RCX,qword ptr [RSP + 0x1d8]
00aa588e  MOV RDI,qword ptr [RSP + 0xa8]
00aa5896  CALL 0x00413460
00aa589b  CMP dword ptr [0x019b5f00],0x0
00aa58a2  JNZ 0x00aa58ae
00aa58a4  MOV R9,qword ptr [RSP + 0x230]
00aa58ac  JMP 0x00aa58c5
00aa58ae  MOV R8,qword ptr [RAX]
00aa58b1  CALL 0x0048bc00
00aa58b6  MOV R9,qword ptr [RSP + 0x230]
00aa58be  MOV qword ptr [R11],R9
00aa58c1  MOV qword ptr [R11 + 0x8],R8
00aa58c5  MOV qword ptr [RAX],R9
00aa58c8  MOV R8,qword ptr [RSP + 0x3c8]
00aa58d0  MOV R9,qword ptr [R8 + 0x10]
00aa58d4  NOP
00aa58d5  MOV R10,qword ptr [R8 + 0x18]
00aa58d9  MOV qword ptr [RSP + 0x138],R10
00aa58e1  MOV R11,qword ptr [RSP + 0xa8]
00aa58e9  XOR EAX,EAX
00aa58eb  JMP 0x00aa58f4
00aa58ed  ADD R9,0x10
00aa58f1  INC RAX
00aa58f4  CMP RAX,R10
00aa58f7  JGE 0x00aa5a8b
00aa58fd  MOV RCX,qword ptr [R9 + 0x8]
00aa5901  CMP R11,RCX
00aa5904  JNZ 0x00aa58ed
00aa5906  MOV qword ptr [RSP + 0x108],RAX
00aa590e  MOV qword ptr [RSP + 0x250],R9
00aa5916  MOV RAX,qword ptr [R9]
00aa5919  MOV RBX,qword ptr [RSP + 0x1d8]
00aa5921  CALL 0x00403be0
00aa5926  TEST AL,AL
00aa5928  JNZ 0x00aa5954
00aa592a  MOV RAX,qword ptr [RSP + 0x108]
00aa5932  MOV R8,qword ptr [RSP + 0x3c8]
00aa593a  MOV R9,qword ptr [RSP + 0x250]
00aa5942  MOV R10,qword ptr [RSP + 0x138]
00aa594a  MOV R11,qword ptr [RSP + 0xa8]
00aa5952  JMP 0x00aa58ed
00aa5954  MOV RDX,qword ptr [RSP + 0x3c8]
00aa595c  MOV RCX,qword ptr [RDX + 0x20]
00aa5960  MOV R8,qword ptr [RSP + 0x108]
00aa5968  CMP R8,RCX
00aa596b  JA 0x00aa5b6a
00aa5971  MOV RBX,qword ptr [RDX + 0x18]
00aa5975  LEA R9,[R8 + 0x1]
00aa5979  NOP dword ptr [RAX]
00aa5980  CMP RBX,R9
00aa5983  JC 0x00aa5b65
00aa5989  LEA R10,[RBX + -0x1]
00aa598d  MOV RAX,qword ptr [RDX + 0x10]
00aa5991  MOV R11,RCX
00aa5994  SUB R11,R8
00aa5997  SUB RBX,R8
00aa599a  DEC R11
00aa599d  NEG R11
00aa59a0  SHL R9,0x4
00aa59a4  SAR R11,0x3f
00aa59a8  AND R9,R11
00aa59ab  LEA RDI,[RAX + R9*0x1]
00aa59af  LEA RSI,[RBX + -0x1]
00aa59b3  CMP RCX,R10
00aa59b6  JNC 0x00aa59f5
00aa59b8  MOV qword ptr [RSP + 0x138],RSI
00aa59c0  MOV qword ptr [RSP + 0x258],RDI
00aa59c8  MOV RBX,R10
00aa59cb  MOV RDI,RSI
00aa59ce  LEA RSI,[0xdd29c0]
00aa59d5  CALL 0x00486be0
00aa59da  MOV RSI,qword ptr [RSP + 0x138]
00aa59e2  MOV RDI,qword ptr [RSP + 0x258]
00aa59ea  MOV R8,qword ptr [RSP + 0x108]
00aa59f2  MOV R10,RBX
00aa59f5  MOV qword ptr [RSP + 0x258],RAX
00aa59fd  MOV qword ptr [RSP + 0x138],R10
00aa5a05  MOV qword ptr [RSP + 0x130],RCX
00aa5a0d  MOV RDX,R8
00aa5a10  SUB R8,RCX
00aa5a13  MOV RCX,R10
00aa5a16  SUB RCX,RDX
00aa5a19  SHL RDX,0x4
00aa5a1d  SAR R8,0x3f
00aa5a21  AND R8,RDX
00aa5a24  LEA RBX,[RAX + R8*0x1]
00aa5a28  LEA RAX,[0xdd29c0]
00aa5a2f  CALL 0x00482bc0
00aa5a34  MOV RDX,qword ptr [RSP + 0x138]
00aa5a3c  MOV R8,qword ptr [RSP + 0x3c8]
00aa5a44  MOV qword ptr [R8 + 0x18],RDX
00aa5a48  MOV RDX,qword ptr [RSP + 0x130]
00aa5a50  MOV qword ptr [R8 + 0x20],RDX
00aa5a54  CMP dword ptr [0x019b5f00],0x0
00aa5a5b  JNZ 0x00aa5a67
00aa5a5d  MOV R10,qword ptr [RSP + 0x258]
00aa5a65  JMP 0x00aa5a7f
00aa5a67  MOV R9,qword ptr [R8 + 0x10]
00aa5a6b  CALL 0x0048bc00
00aa5a70  MOV R10,qword ptr [RSP + 0x258]
00aa5a78  MOV qword ptr [R11],R10
00aa5a7b  MOV qword ptr [R11 + 0x8],R9
00aa5a7f  MOV qword ptr [R8 + 0x10],R10
00aa5a83  MOV R11,qword ptr [RSP + 0xa8]
00aa5a8b  MOV RCX,qword ptr [R8 + 0x20]
00aa5a8f  MOV RBX,qword ptr [R8 + 0x18]
00aa5a93  INC RBX
00aa5a96  MOV RAX,qword ptr [R8 + 0x10]
00aa5a9a  CMP RCX,RBX
00aa5a9d  JNC 0x00aa5ae4
00aa5a9f  MOV EDI,0x1
00aa5aa4  LEA RSI,[0xdd29c0]
00aa5aab  CALL 0x00486be0
00aa5ab0  MOV RDX,qword ptr [RSP + 0x3c8]
00aa5ab8  MOV qword ptr [RDX + 0x20],RCX
00aa5abc  CMP dword ptr [0x019b5f00],0x0
00aa5ac3  JZ 0x00aa5ad5
00aa5ac5  MOV RCX,qword ptr [RDX + 0x10]
00aa5ac9  CALL 0x0048bc00
00aa5ace  MOV qword ptr [R11],RAX
00aa5ad1  MOV qword ptr [R11 + 0x8],RCX
00aa5ad5  MOV qword ptr [RDX + 0x10],RAX
00aa5ad9  MOV R8,RDX
00aa5adc  MOV R11,qword ptr [RSP + 0xa8]
00aa5ae4  MOV qword ptr [R8 + 0x18],RBX
00aa5ae8  LEA RCX,[RBX + -0x1]
00aa5aec  SHL RCX,0x4
00aa5af0  MOV qword ptr [RAX + RCX*0x1 + 0x8],R11
00aa5af5  CMP dword ptr [0x019b5f00],0x0
00aa5afc  JNZ 0x00aa5b0b
00aa5afe  MOV RDX,R11
00aa5b01  MOV RSI,qword ptr [RSP + 0x1d8]
00aa5b09  JMP 0x00aa5b26
00aa5b0b  MOV RBX,qword ptr [RCX + RAX*0x1]
00aa5b0f  MOV RDX,R11
00aa5b12  CALL 0x0048bc00
00aa5b17  MOV RSI,qword ptr [RSP + 0x1d8]
00aa5b1f  MOV qword ptr [R11],RSI
00aa5b22  MOV qword ptr [R11 + 0x8],RBX
00aa5b26  MOV qword ptr [RAX + RCX*0x1],RSI
00aa5b2a  MOV qword ptr [RSP + 0x1e0],RSI
00aa5b32  MOV qword ptr [RSP + 0x1e8],RDX
00aa5b3a  MOV byte ptr [RSP + 0x47],0x0
00aa5b3f  MOV RDX,qword ptr [RSP + 0x3b0]
00aa5b47  MOV RAX,qword ptr [RDX]
00aa5b4a  CALL RAX
00aa5b4c  MOV RAX,qword ptr [RSP + 0x1e0]
00aa5b54  MOV RBX,qword ptr [RSP + 0x1e8]
00aa5b5c  ADD RSP,0x3b8
00aa5b63  POP RBP
00aa5b64  RET
00aa5b65  CALL 0x0048bfa0
00aa5b6a  CALL 0x0048bfa0
00aa5b6f  ADD R9,0x10
00aa5b73  INC RAX
00aa5b76  CMP RAX,R10
00aa5b79  JGE 0x00aa5d0b
00aa5b7f  MOV RCX,qword ptr [R9 + 0x8]
00aa5b83  CMP R11,RCX
00aa5b86  JNZ 0x00aa5b6f
00aa5b88  MOV qword ptr [RSP + 0x110],RAX
00aa5b90  MOV qword ptr [RSP + 0x250],R9
00aa5b98  MOV RAX,qword ptr [R9]
00aa5b9b  MOV RBX,qword ptr [RSP + 0x1d8]
00aa5ba3  CALL 0x00403be0
00aa5ba8  TEST AL,AL
00aa5baa  JNZ 0x00aa5bd6
00aa5bac  MOV RAX,qword ptr [RSP + 0x110]
00aa5bb4  MOV R8,qword ptr [RSP + 0x3c8]
00aa5bbc  MOV R9,qword ptr [RSP + 0x250]
00aa5bc4  MOV R10,qword ptr [RSP + 0x138]
00aa5bcc  MOV R11,qword ptr [RSP + 0xa8]
00aa5bd4  JMP 0x00aa5b6f
00aa5bd6  MOV RDX,qword ptr [RSP + 0x3c8]
00aa5bde  MOV RCX,qword ptr [RDX + 0x20]
00aa5be2  MOV R8,qword ptr [RSP + 0x110]
00aa5bea  CMP R8,RCX
00aa5bed  JA 0x00aa5dea
00aa5bf3  MOV RBX,qword ptr [RDX + 0x18]
00aa5bf7  LEA R9,[R8 + 0x1]
00aa5bfb  NOP dword ptr [RAX + RAX*0x1]
00aa5c00  CMP RBX,R9
00aa5c03  JC 0x00aa5de5
00aa5c09  LEA R10,[RBX + -0x1]
00aa5c0d  MOV RAX,qword ptr [RDX + 0x10]
00aa5c11  MOV R11,RCX
00aa5c14  SUB R11,R8
00aa5c17  SUB RBX,R8
00aa5c1a  DEC R11
00aa5c1d  NEG R11
00aa5c20  SHL R9,0x4
00aa5c24  SAR R11,0x3f
00aa5c28  AND R9,R11
00aa5c2b  LEA RDI,[RAX + R9*0x1]
00aa5c2f  LEA RSI,[RBX + -0x1]
00aa5c33  CMP RCX,R10
00aa5c36  JNC 0x00aa5c75
00aa5c38  MOV qword ptr [RSP + 0x138],RSI
00aa5c40  MOV qword ptr [RSP + 0x258],RDI
00aa5c48  MOV RBX,R10
00aa5c4b  MOV RDI,RSI
00aa5c4e  LEA RSI,[0xdd29c0]
00aa5c55  CALL 0x00486be0
00aa5c5a  MOV RSI,qword ptr [RSP + 0x138]
00aa5c62  MOV RDI,qword ptr [RSP + 0x258]
00aa5c6a  MOV R8,qword ptr [RSP + 0x110]
00aa5c72  MOV R10,RBX
00aa5c75  MOV qword ptr [RSP + 0x138],R10
00aa5c7d  MOV qword ptr [RSP + 0x258],RAX
00aa5c85  MOV qword ptr [RSP + 0x130],RCX
00aa5c8d  MOV RDX,R8
00aa5c90  SUB R8,RCX
00aa5c93  MOV RCX,R10
00aa5c96  SUB RCX,RDX
00aa5c99  SHL RDX,0x4
00aa5c9d  SAR R8,0x3f
00aa5ca1  AND R8,RDX
00aa5ca4  LEA RBX,[RAX + R8*0x1]
00aa5ca8  LEA RAX,[0xdd29c0]
00aa5caf  CALL 0x00482bc0
00aa5cb4  MOV RDX,qword ptr [RSP + 0x138]
00aa5cbc  MOV R8,qword ptr [RSP + 0x3c8]
00aa5cc4  MOV qword ptr [R8 + 0x18],RDX
00aa5cc8  MOV RDX,qword ptr [RSP + 0x130]
00aa5cd0  MOV qword ptr [R8 + 0x20],RDX
00aa5cd4  CMP dword ptr [0x019b5f00],0x0
00aa5cdb  JNZ 0x00aa5ce7
00aa5cdd  MOV R10,qword ptr [RSP + 0x258]
00aa5ce5  JMP 0x00aa5cff
00aa5ce7  MOV R9,qword ptr [R8 + 0x10]
00aa5ceb  CALL 0x0048bc00
00aa5cf0  MOV R10,qword ptr [RSP + 0x258]
00aa5cf8  MOV qword ptr [R11],R10
00aa5cfb  MOV qword ptr [R11 + 0x8],R9
00aa5cff  MOV qword ptr [R8 + 0x10],R10
00aa5d03  MOV R11,qword ptr [RSP + 0xa8]
00aa5d0b  MOV RCX,qword ptr [R8 + 0x20]
00aa5d0f  MOV RBX,qword ptr [R8 + 0x18]
00aa5d13  INC RBX
00aa5d16  MOV RAX,qword ptr [R8 + 0x10]
00aa5d1a  CMP RCX,RBX
00aa5d1d  JNC 0x00aa5d64
00aa5d1f  MOV EDI,0x1
00aa5d24  LEA RSI,[0xdd29c0]
00aa5d2b  CALL 0x00486be0
00aa5d30  MOV RDX,qword ptr [RSP + 0x3c8]
00aa5d38  MOV qword ptr [RDX + 0x20],RCX
00aa5d3c  CMP dword ptr [0x019b5f00],0x0
00aa5d43  JZ 0x00aa5d55
00aa5d45  MOV RCX,qword ptr [RDX + 0x10]
00aa5d49  CALL 0x0048bc00
00aa5d4e  MOV qword ptr [R11],RAX
00aa5d51  MOV qword ptr [R11 + 0x8],RCX
00aa5d55  MOV qword ptr [RDX + 0x10],RAX
00aa5d59  MOV R8,RDX
00aa5d5c  MOV R11,qword ptr [RSP + 0xa8]
00aa5d64  MOV qword ptr [R8 + 0x18],RBX
00aa5d68  LEA RCX,[RBX + -0x1]
00aa5d6c  SHL RCX,0x4
00aa5d70  MOV qword ptr [RAX + RCX*0x1 + 0x8],R11
00aa5d75  CMP dword ptr [0x019b5f00],0x0
00aa5d7c  JNZ 0x00aa5d8b
00aa5d7e  MOV RDX,R11
00aa5d81  MOV RSI,qword ptr [RSP + 0x1d8]
00aa5d89  JMP 0x00aa5da6
00aa5d8b  MOV RBX,qword ptr [RCX + RAX*0x1]
00aa5d8f  MOV RDX,R11
00aa5d92  CALL 0x0048bc00
00aa5d97  MOV RSI,qword ptr [RSP + 0x1d8]
00aa5d9f  MOV qword ptr [R11],RSI
00aa5da2  MOV qword ptr [R11 + 0x8],RBX
00aa5da6  MOV qword ptr [RAX + RCX*0x1],RSI
00aa5daa  MOV qword ptr [RSP + 0x1e0],RSI
00aa5db2  MOV qword ptr [RSP + 0x1e8],RDX
00aa5dba  MOV byte ptr [RSP + 0x47],0x0
00aa5dbf  MOV RDX,qword ptr [RSP + 0x3b0]
00aa5dc7  MOV RAX,qword ptr [RDX]
00aa5dca  CALL RAX
00aa5dcc  MOV RAX,qword ptr [RSP + 0x1e0]
00aa5dd4  MOV RBX,qword ptr [RSP + 0x1e8]
00aa5ddc  ADD RSP,0x3b8
00aa5de3  POP RBP
00aa5de4  RET
00aa5de5  CALL 0x0048bfa0
00aa5dea  CALL 0x0048bfa0
00aa5def  ADD R9,0x10
00aa5df3  INC RAX
00aa5df6  CMP RAX,R10
00aa5df9  JGE 0x00aa5f8b
00aa5dff  MOV RCX,qword ptr [R9 + 0x8]
00aa5e03  CMP R11,RCX
00aa5e06  JNZ 0x00aa5def
00aa5e08  MOV qword ptr [RSP + 0x118],RAX
00aa5e10  MOV qword ptr [RSP + 0x250],R9
00aa5e18  MOV RAX,qword ptr [R9]
00aa5e1b  MOV RBX,qword ptr [RSP + 0x1d8]
00aa5e23  CALL 0x00403be0
00aa5e28  TEST AL,AL
00aa5e2a  JNZ 0x00aa5e56
00aa5e2c  MOV RAX,qword ptr [RSP + 0x118]
00aa5e34  MOV R8,qword ptr [RSP + 0x3c8]
00aa5e3c  MOV R9,qword ptr [RSP + 0x250]
00aa5e44  MOV R10,qword ptr [RSP + 0x138]
00aa5e4c  MOV R11,qword ptr [RSP + 0xa8]
00aa5e54  JMP 0x00aa5def
00aa5e56  MOV RDX,qword ptr [RSP + 0x3c8]
00aa5e5e  MOV RCX,qword ptr [RDX + 0x20]
00aa5e62  MOV R8,qword ptr [RSP + 0x118]
00aa5e6a  CMP R8,RCX
00aa5e6d  JA 0x00aa606a
00aa5e73  MOV RBX,qword ptr [RDX + 0x18]
00aa5e77  LEA R9,[R8 + 0x1]
00aa5e7b  NOP dword ptr [RAX + RAX*0x1]
00aa5e80  CMP RBX,R9
00aa5e83  JC 0x00aa6065
00aa5e89  LEA R10,[RBX + -0x1]
00aa5e8d  MOV RAX,qword ptr [RDX + 0x10]
00aa5e91  MOV R11,RCX
00aa5e94  SUB R11,R8
00aa5e97  SUB RBX,R8
00aa5e9a  DEC R11
00aa5e9d  NEG R11
00aa5ea0  SHL R9,0x4
00aa5ea4  SAR R11,0x3f
00aa5ea8  AND R9,R11
00aa5eab  LEA RDI,[RAX + R9*0x1]
00aa5eaf  LEA RSI,[RBX + -0x1]
00aa5eb3  CMP RCX,R10
00aa5eb6  JNC 0x00aa5ef5
00aa5eb8  MOV qword ptr [RSP + 0x138],RSI
00aa5ec0  MOV qword ptr [RSP + 0x258],RDI
00aa5ec8  MOV RBX,R10
00aa5ecb  MOV RDI,RSI
00aa5ece  LEA RSI,[0xdd29c0]
00aa5ed5  CALL 0x00486be0
00aa5eda  MOV RSI,qword ptr [RSP + 0x138]
00aa5ee2  MOV RDI,qword ptr [RSP + 0x258]
00aa5eea  MOV R8,qword ptr [RSP + 0x118]
00aa5ef2  MOV R10,RBX
00aa5ef5  MOV qword ptr [RSP + 0x138],RCX
00aa5efd  MOV qword ptr [RSP + 0x130],R10
00aa5f05  MOV qword ptr [RSP + 0x258],RAX
00aa5f0d  SUB R10,R8
00aa5f10  MOV RDX,R8
00aa5f13  SUB R8,RCX
00aa5f16  SHL RDX,0x4
00aa5f1a  SAR R8,0x3f
00aa5f1e  AND R8,RDX
00aa5f21  LEA RBX,[RAX + R8*0x1]
00aa5f25  LEA RAX,[0xdd29c0]
00aa5f2c  MOV RCX,R10
00aa5f2f  CALL 0x00482bc0
00aa5f34  MOV RDX,qword ptr [RSP + 0x130]
00aa5f3c  MOV R8,qword ptr [RSP + 0x3c8]
00aa5f44  MOV qword ptr [R8 + 0x18],RDX
00aa5f48  MOV RDX,qword ptr [RSP + 0x138]
00aa5f50  MOV qword ptr [R8 + 0x20],RDX
00aa5f54  CMP dword ptr [0x019b5f00],0x0
00aa5f5b  JNZ 0x00aa5f67
00aa5f5d  MOV R10,qword ptr [RSP + 0x258]
00aa5f65  JMP 0x00aa5f7f
00aa5f67  MOV R9,qword ptr [R8 + 0x10]
00aa5f6b  CALL 0x0048bc00
00aa5f70  MOV R10,qword ptr [RSP + 0x258]
00aa5f78  MOV qword ptr [R11],R10
00aa5f7b  MOV qword ptr [R11 + 0x8],R9
00aa5f7f  MOV qword ptr [R8 + 0x10],R10
00aa5f83  MOV R11,qword ptr [RSP + 0xa8]
00aa5f8b  MOV RCX,qword ptr [R8 + 0x20]
00aa5f8f  MOV RBX,qword ptr [R8 + 0x18]
00aa5f93  INC RBX
00aa5f96  MOV RAX,qword ptr [R8 + 0x10]
00aa5f9a  CMP RCX,RBX
00aa5f9d  JNC 0x00aa5fe4
00aa5f9f  MOV EDI,0x1
00aa5fa4  LEA RSI,[0xdd29c0]
00aa5fab  CALL 0x00486be0
00aa5fb0  MOV RDX,qword ptr [RSP + 0x3c8]
00aa5fb8  MOV qword ptr [RDX + 0x20],RCX
00aa5fbc  CMP dword ptr [0x019b5f00],0x0
00aa5fc3  JZ 0x00aa5fd5
00aa5fc5  MOV RCX,qword ptr [RDX + 0x10]
00aa5fc9  CALL 0x0048bc00
00aa5fce  MOV qword ptr [R11],RAX
00aa5fd1  MOV qword ptr [R11 + 0x8],RCX
00aa5fd5  MOV qword ptr [RDX + 0x10],RAX
00aa5fd9  MOV R8,RDX
00aa5fdc  MOV R11,qword ptr [RSP + 0xa8]
00aa5fe4  MOV qword ptr [R8 + 0x18],RBX
00aa5fe8  LEA RCX,[RBX + -0x1]
00aa5fec  SHL RCX,0x4
00aa5ff0  MOV qword ptr [RAX + RCX*0x1 + 0x8],R11
00aa5ff5  CMP dword ptr [0x019b5f00],0x0
00aa5ffc  JNZ 0x00aa600b
00aa5ffe  MOV RDX,R11
00aa6001  MOV RSI,qword ptr [RSP + 0x1d8]
00aa6009  JMP 0x00aa6026
00aa600b  MOV RBX,qword ptr [RCX + RAX*0x1]
00aa600f  MOV RDX,R11
00aa6012  CALL 0x0048bc00
00aa6017  MOV RSI,qword ptr [RSP + 0x1d8]
00aa601f  MOV qword ptr [R11],RSI
00aa6022  MOV qword ptr [R11 + 0x8],RBX
00aa6026  MOV qword ptr [RAX + RCX*0x1],RSI
00aa602a  MOV qword ptr [RSP + 0x1e0],RSI
00aa6032  MOV qword ptr [RSP + 0x1e8],RDX
00aa603a  MOV byte ptr [RSP + 0x47],0x0
00aa603f  MOV RDX,qword ptr [RSP + 0x3b0]
00aa6047  MOV RAX,qword ptr [RDX]
00aa604a  CALL RAX
00aa604c  MOV RAX,qword ptr [RSP + 0x1e0]
00aa6054  MOV RBX,qword ptr [RSP + 0x1e8]
00aa605c  ADD RSP,0x3b8
00aa6063  POP RBP
00aa6064  RET
00aa6065  CALL 0x0048bfa0
00aa606a  CALL 0x0048bfa0
00aa606f  CALL 0x0048bfa0
00aa6074  CALL 0x0048bfa0
00aa6098  MOV qword ptr [RSP + 0x8],RAX
00aa609d  MOV qword ptr [RSP + 0x10],RBX
00aa60a2  MOV qword ptr [RSP + 0x18],RCX
00aa60a7  MOV qword ptr [RSP + 0x20],RDI
00aa60ac  MOV qword ptr [RSP + 0x28],RSI
00aa60b1  MOV qword ptr [RSP + 0x30],R8
00aa60b6  MOV qword ptr [RSP + 0x38],R9
00aa60bb  MOV byte ptr [RSP + 0x40],R10B
00aa60c0  MOV qword ptr [RSP + 0x48],R11
00aa60c5  CALL 0x0048a280
00aa60ca  MOV RAX,qword ptr [RSP + 0x8]
00aa60cf  MOV RBX,qword ptr [RSP + 0x10]
00aa60d4  MOV RCX,qword ptr [RSP + 0x18]
00aa60d9  MOV RDI,qword ptr [RSP + 0x20]
00aa60de  MOV RSI,qword ptr [RSP + 0x28]
00aa60e3  MOV R8,qword ptr [RSP + 0x30]
00aa60e8  MOV R9,qword ptr [RSP + 0x38]
00aa60ed  MOVZX R10D,byte ptr [RSP + 0x40]
00aa60f3  MOV R11,qword ptr [RSP + 0x48]
00aa60f8  JMP 0x00aa4980
