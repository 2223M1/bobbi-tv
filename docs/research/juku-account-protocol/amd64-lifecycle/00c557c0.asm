; main.handle115OfflineTasks
00c557c0  LEA R12,[RSP + -0x80]
00c557c5  CMP R12,qword ptr [R14 + 0x10]
00c557c9  JBE 0x00c55fff
00c557cf  PUSH RBP
00c557d0  MOV RBP,RSP
00c557d3  SUB RSP,0xf8
00c557da  MOV qword ptr [RSP + 0x118],RCX
00c557e2  MOV qword ptr [RSP + 0x110],RBX
00c557ea  MOV qword ptr [RSP + 0x108],RAX
00c557f2  MOV RCX,qword ptr [RAX + 0x18]
00c557f6  MOV RAX,RBX
00c557f9  CALL RCX
00c557fb  MOV qword ptr [RSP + 0x60],RAX
00c55800  NOP
00c55801  LEA RAX,[0xf10b4b]
00c55808  MOV EBX,0xc
00c5580d  CALL 0x00640c00
00c55812  MOV qword ptr [RSP + 0xf0],RAX
00c5581a  MOV qword ptr [RSP + 0x40],RBX
00c5581f  LEA RAX,[0xddc380]
00c55826  CALL 0x00421f00
00c5582b  MOV qword ptr [RSP + 0xe8],RAX
00c55833  MOV qword ptr [RAX + 0x8],0x10
00c5583b  LEA RCX,[0xf195fc]
00c55842  MOV qword ptr [RAX],RCX
00c55845  LEA RAX,[0xe91b20]
00c5584c  MOV RBX,qword ptr [RSP + 0x60]
00c55851  MOV RCX,qword ptr [RSP + 0xf0]
00c55859  MOV RDI,qword ptr [RSP + 0x40]
00c5585e  NOP
00c55860  CALL 0x00413460
00c55865  MOV qword ptr [RAX + 0x8],0x1
00c5586d  MOV qword ptr [RAX + 0x10],0x1
00c55875  CMP dword ptr [0x019b5f00],0x0
00c5587c  JNZ 0x00c55888
00c5587e  MOV RDX,qword ptr [RSP + 0xe8]
00c55886  JMP 0x00c5589f
00c55888  MOV RCX,qword ptr [RAX]
00c5588b  CALL 0x0048bc00
00c55890  MOV RDX,qword ptr [RSP + 0xe8]
00c55898  MOV qword ptr [R11],RDX
00c5589b  MOV qword ptr [R11 + 0x8],RCX
00c5589f  MOV qword ptr [RAX],RDX
00c558a2  MOV RCX,qword ptr [RSP + 0x118]
00c558aa  MOV RAX,qword ptr [RCX + 0x10]
00c558ae  CALL 0x005bb0e0
00c558b3  MOV RBX,RAX
00c558b6  LEA RCX,[0xefc947]
00c558bd  MOV EDI,0x5
00c558c2  LEA RAX,[0xe9bd40]
00c558c9  CALL 0x00412ee0
00c558ce  CMP qword ptr [RAX + 0x8],0x0
00c558d3  JNZ 0x00c558dc
00c558d5  XOR R8D,R8D
00c558d8  XOR EDX,EDX
00c558da  JMP 0x00c558e6
00c558dc  MOV RDX,qword ptr [RAX]
00c558df  MOV R8,qword ptr [RDX + 0x8]
00c558e3  MOV RDX,qword ptr [RDX]
00c558e6  TEST R8,R8
00c558e9  JNZ 0x00c5590e
00c558eb  MOV RAX,qword ptr [0x019900b0]
00c558f2  TEST RAX,RAX
00c558f5  JZ 0x00c5590e
00c558f7  LEA RBX,[0xf02951]
00c558fe  MOV ECX,0x8
00c55903  CALL 0x00a63de0
00c55908  MOV R8,RBX
00c5590b  MOV RDX,RAX
00c5590e  TEST R8,R8
00c55911  JZ 0x00c55a9f
00c55917  MOV qword ptr [RSP + 0x48],RDX
00c5591c  MOV qword ptr [RSP + 0x28],R8
00c55921  MOV RBX,qword ptr [0x019900d0]
00c55928  LEA RAX,[0xe17280]
00c5592f  LEA RCX,[0xf02951]
00c55936  MOV EDI,0x8
00c5593b  NOP dword ptr [RAX + RAX*0x1]
00c55940  CALL 0x004131a0
00c55945  MOV RDX,qword ptr [RAX + 0x8]
00c55949  TEST BL,BL
00c5594b  JZ 0x00c55a70
00c55951  MOV R8,qword ptr [RAX]
00c55954  LEA R9,[0x11476d0]
00c5595b  NOP dword ptr [RAX + RAX*0x1]
00c55960  CMP R8,R9
00c55963  JNZ 0x00c55a41
00c55969  MOV qword ptr [RSP + 0x58],RDX
00c5596e  MOV RCX,qword ptr [RSP + 0x118]
00c55976  MOV RAX,qword ptr [RCX + 0x10]
00c5597a  CALL 0x005bb0e0
00c5597f  MOV RBX,RAX
00c55982  LEA RCX,[0xefb5af]
00c55989  MOV EDI,0x4
00c5598e  LEA RAX,[0xe9bd40]
00c55995  CALL 0x00412ee0
00c5599a  CMP qword ptr [RAX + 0x8],0x0
00c5599f  NOP
00c559a0  JNZ 0x00c559a8
00c559a2  XOR EDX,EDX
00c559a4  XOR ECX,ECX
00c559a6  JMP 0x00c559b2
00c559a8  MOV RCX,qword ptr [RAX]
00c559ab  MOV RDX,qword ptr [RCX + 0x8]
00c559af  MOV RCX,qword ptr [RCX]
00c559b2  MOV RAX,RCX
00c559b5  MOV RBX,RDX
00c559b8  CALL 0x0049c040
00c559bd  NOP dword ptr [RAX]
00c559c0  TEST RBX,RBX
00c559c3  JNZ 0x00c559ca
00c559c5  TEST RAX,RAX
00c559c8  JG 0x00c559cf
00c559ca  MOV EAX,0x1
00c559cf  MOV RBX,RAX
00c559d2  MOV RCX,qword ptr [RSP + 0x48]
00c559d7  MOV RDI,qword ptr [RSP + 0x28]
00c559dc  MOV RAX,qword ptr [RSP + 0x58]
00c559e1  CALL 0x00a0e920
00c559e6  TEST RBX,RBX
00c559e9  JNZ 0x00c55a0e
00c559eb  MOV qword ptr [RSP + 0x50],RAX
00c559f0  CMP qword ptr [0x01990200],0x0
00c559f8  JZ 0x00c55ace
00c559fe  MOV RCX,qword ptr [RAX + 0x8]
00c55a02  MOV qword ptr [RSP + 0x40],RCX
00c55a07  XOR EDX,EDX
00c55a09  JMP 0x00c55ea1
00c55a0e  MOV RDX,qword ptr [RBX + 0x18]
00c55a12  MOV RAX,RCX
00c55a15  CALL RDX
00c55a17  MOV RCX,RAX
00c55a1a  MOV RDI,RBX
00c55a1d  MOV ESI,0x1f4
00c55a22  MOV RAX,qword ptr [RSP + 0x108]
00c55a2a  MOV RBX,qword ptr [RSP + 0x110]
00c55a32  CALL 0x00c484c0
00c55a37  ADD RSP,0xf8
00c55a3e  POP RBP
00c55a3f  NOP
00c55a40  RET
00c55a41  MOV RAX,qword ptr [RSP + 0x108]
00c55a49  MOV RBX,qword ptr [RSP + 0x110]
00c55a51  LEA RCX,[0xf3a315]
00c55a58  MOV EDI,0x27
00c55a5d  MOV ESI,0x1f4
00c55a62  CALL 0x00c484c0
00c55a67  ADD RSP,0xf8
00c55a6e  POP RBP
00c55a6f  RET
00c55a70  MOV RAX,qword ptr [RSP + 0x108]
00c55a78  MOV RBX,qword ptr [RSP + 0x110]
00c55a80  LEA RCX,[0xf2d163]
00c55a87  MOV EDI,0x1d
00c55a8c  MOV ESI,0x1f4
00c55a91  CALL 0x00c484c0
00c55a96  ADD RSP,0xf8
00c55a9d  POP RBP
00c55a9e  RET
00c55a9f  MOV RAX,qword ptr [RSP + 0x108]
00c55aa7  MOV RBX,qword ptr [RSP + 0x110]
00c55aaf  LEA RCX,[0xf3daf3]
00c55ab6  MOV EDI,0x2a
00c55abb  MOV ESI,0x191
00c55ac0  CALL 0x00c484c0
00c55ac5  ADD RSP,0xf8
00c55acc  POP RBP
00c55acd  RET
00c55ace  MOV RCX,qword ptr [RSP + 0x108]
00c55ad6  TEST RCX,RCX
00c55ad9  JZ 0x00c55af1
00c55adb  MOV RBX,qword ptr [RCX + 0x8]
00c55adf  MOV RDX,qword ptr [0x01974120]
00c55ae6  MOV RSI,qword ptr [RDX]
00c55ae9  MOV ECX,dword ptr [RCX + 0x10]
00c55aec  JMP 0x00c55e4e
00c55af1  LEA RAX,[RSP + 0x70]
00c55af6  MOVUPS xmmword ptr [RAX],XMM15
00c55afa  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c55aff  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c55b04  MOVUPS xmmword ptr [RAX + 0x30],XMM15
00c55b09  MOVUPS xmmword ptr [RAX + 0x40],XMM15
00c55b0e  MOVUPS xmmword ptr [RAX + 0x50],XMM15
00c55b13  MOV qword ptr [RSP + 0x70],RCX
00c55b18  MOV RAX,qword ptr [RSP + 0x110]
00c55b20  MOV qword ptr [RSP + 0x78],RAX
00c55b25  MOV byte ptr [RSP + 0x90],0x1
00c55b2d  CALL 0x004825c0
00c55b32  MOV qword ptr [RSP + 0xe0],RAX
00c55b3a  MOV RBX,RAX
00c55b3d  LEA RCX,[0xeffdf5]
00c55b44  MOV EDI,0x7
00c55b49  LEA RAX,[0xe16300]
00c55b50  CALL 0x00413460
00c55b55  LEA RCX,[0xdd2dc0]
00c55b5c  MOV qword ptr [RAX],RCX
00c55b5f  CMP dword ptr [0x019b5f00],0x0
00c55b66  JZ 0x00c55b74
00c55b68  MOV RDX,qword ptr [RAX + 0x8]
00c55b6c  CALL 0x0048bbe0
00c55b71  MOV qword ptr [R11],RDX
00c55b74  LEA RDX,[0x115e2c8]
00c55b7b  MOV qword ptr [RAX + 0x8],RDX
00c55b7f  MOV RDX,qword ptr [RSP + 0x50]
00c55b84  MOV RAX,qword ptr [RDX]
00c55b87  MOV RBX,qword ptr [RDX + 0x8]
00c55b8b  MOV RCX,qword ptr [RDX + 0x10]
00c55b8f  CALL 0x00481f80
00c55b94  MOV qword ptr [RSP + 0xd8],RAX
00c55b9c  LEA RAX,[0xe16300]
00c55ba3  MOV RBX,qword ptr [RSP + 0xe0]
00c55bab  LEA RCX,[0xefc979]
00c55bb2  MOV EDI,0x5
00c55bb7  CALL 0x00413460
00c55bbc  LEA RDX,[0xdc15e0]
00c55bc3  MOV qword ptr [RAX],RDX
00c55bc6  CMP dword ptr [0x019b5f00],0x0
00c55bcd  JNZ 0x00c55bd9
00c55bcf  MOV RDX,qword ptr [RSP + 0xd8]
00c55bd7  JMP 0x00c55bf4
00c55bd9  MOV RCX,qword ptr [RAX + 0x8]
00c55bdd  NOP dword ptr [RAX]
00c55be0  CALL 0x0048bc00
00c55be5  MOV RDX,qword ptr [RSP + 0xd8]
00c55bed  MOV qword ptr [R11],RDX
00c55bf0  MOV qword ptr [R11 + 0x8],RCX
00c55bf4  MOV qword ptr [RAX + 0x8],RDX
00c55bf8  MOV RCX,qword ptr [RSP + 0x50]
00c55bfd  MOV RAX,qword ptr [RCX + 0x18]
00c55c01  CALL 0x00481e60
00c55c06  MOV qword ptr [RSP + 0xd8],RAX
00c55c0e  LEA RAX,[0xe16300]
00c55c15  MOV RBX,qword ptr [RSP + 0xe0]
00c55c1d  LEA RCX,[0xefc97e]
00c55c24  MOV EDI,0x5
00c55c29  CALL 0x00413460
00c55c2e  LEA RCX,[0xdd2c00]
00c55c35  MOV qword ptr [RAX],RCX
00c55c38  CMP dword ptr [0x019b5f00],0x0
00c55c3f  NOP
00c55c40  JNZ 0x00c55c4c
00c55c42  MOV RDX,qword ptr [RSP + 0xd8]
00c55c4a  JMP 0x00c55c64
00c55c4c  MOV RCX,qword ptr [RAX + 0x8]
00c55c50  CALL 0x0048bc00
00c55c55  MOV RDX,qword ptr [RSP + 0xd8]
00c55c5d  MOV qword ptr [R11],RDX
00c55c60  MOV qword ptr [R11 + 0x8],RCX
00c55c64  MOV qword ptr [RAX + 0x8],RDX
00c55c68  MOV RCX,qword ptr [RSP + 0x50]
00c55c6d  MOV RAX,qword ptr [RCX + 0x20]
00c55c71  CALL 0x00481e60
00c55c76  MOV qword ptr [RSP + 0xd8],RAX
00c55c7e  LEA RAX,[0xe16300]
00c55c85  MOV RBX,qword ptr [RSP + 0xe0]
00c55c8d  LEA RCX,[0xefb5af]
00c55c94  MOV EDI,0x4
00c55c99  CALL 0x00413460
00c55c9e  LEA RCX,[0xdd2c00]
00c55ca5  MOV qword ptr [RAX],RCX
00c55ca8  CMP dword ptr [0x019b5f00],0x0
00c55caf  JNZ 0x00c55cbb
00c55cb1  MOV RDX,qword ptr [RSP + 0xd8]
00c55cb9  JMP 0x00c55cd4
00c55cbb  MOV RCX,qword ptr [RAX + 0x8]
00c55cbf  NOP
00c55cc0  CALL 0x0048bc00
00c55cc5  MOV RDX,qword ptr [RSP + 0xd8]
00c55ccd  MOV qword ptr [R11],RDX
00c55cd0  MOV qword ptr [R11 + 0x8],RCX
00c55cd4  MOV qword ptr [RAX + 0x8],RDX
00c55cd8  MOV RCX,qword ptr [RSP + 0x50]
00c55cdd  MOV RAX,qword ptr [RCX + 0x28]
00c55ce1  CALL 0x00481e60
00c55ce6  MOV qword ptr [RSP + 0xd8],RAX
00c55cee  LEA RAX,[0xe16300]
00c55cf5  MOV RBX,qword ptr [RSP + 0xe0]
00c55cfd  LEA RCX,[0xf0a1cb]
00c55d04  MOV EDI,0xa
00c55d09  CALL 0x00413460
00c55d0e  LEA RCX,[0xdd2c00]
00c55d15  MOV qword ptr [RAX],RCX
00c55d18  CMP dword ptr [0x019b5f00],0x0
00c55d1f  NOP
00c55d20  JNZ 0x00c55d2c
00c55d22  MOV RDX,qword ptr [RSP + 0xd8]
00c55d2a  JMP 0x00c55d44
00c55d2c  MOV RCX,qword ptr [RAX + 0x8]
00c55d30  CALL 0x0048bc00
00c55d35  MOV RDX,qword ptr [RSP + 0xd8]
00c55d3d  MOV qword ptr [R11],RDX
00c55d40  MOV qword ptr [R11 + 0x8],RCX
00c55d44  MOV qword ptr [RAX + 0x8],RDX
00c55d48  MOV RCX,qword ptr [RSP + 0x50]
00c55d4d  MOV RAX,qword ptr [RCX + 0x30]
00c55d51  CALL 0x00481e60
00c55d56  MOV qword ptr [RSP + 0xd8],RAX
00c55d5e  LEA RAX,[0xe16300]
00c55d65  MOV RBX,qword ptr [RSP + 0xe0]
00c55d6d  LEA RCX,[0xefc983]
00c55d74  MOV EDI,0x5
00c55d79  CALL 0x00413460
00c55d7e  LEA RCX,[0xdd2c00]
00c55d85  MOV qword ptr [RAX],RCX
00c55d88  CMP dword ptr [0x019b5f00],0x0
00c55d8f  JNZ 0x00c55d9b
00c55d91  MOV RDX,qword ptr [RSP + 0xd8]
00c55d99  JMP 0x00c55db4
00c55d9b  MOV RCX,qword ptr [RAX + 0x8]
00c55d9f  NOP
00c55da0  CALL 0x0048bc00
00c55da5  MOV RDX,qword ptr [RSP + 0xd8]
00c55dad  MOV qword ptr [R11],RDX
00c55db0  MOV qword ptr [R11 + 0x8],RCX
00c55db4  MOV qword ptr [RAX + 0x8],RDX
00c55db8  MOV RCX,qword ptr [RSP + 0x50]
00c55dbd  MOV RAX,qword ptr [RCX + 0x38]
00c55dc1  CALL 0x00481e60
00c55dc6  MOV qword ptr [RSP + 0xd8],RAX
00c55dce  LEA RAX,[0xe16300]
00c55dd5  MOV RBX,qword ptr [RSP + 0xe0]
00c55ddd  LEA RCX,[0xf0cdb0]
00c55de4  MOV EDI,0xb
00c55de9  CALL 0x00413460
00c55dee  LEA RCX,[0xdd2c00]
00c55df5  MOV qword ptr [RAX],RCX
00c55df8  CMP dword ptr [0x019b5f00],0x0
00c55dff  NOP
00c55e00  JNZ 0x00c55e0c
00c55e02  MOV RSI,qword ptr [RSP + 0xd8]
00c55e0a  JMP 0x00c55e24
00c55e0c  MOV RDX,qword ptr [RAX + 0x8]
00c55e10  CALL 0x0048bc00
00c55e15  MOV RSI,qword ptr [RSP + 0xd8]
00c55e1d  MOV qword ptr [R11],RSI
00c55e20  MOV qword ptr [R11 + 0x8],RDX
00c55e24  MOV qword ptr [RAX + 0x8],RSI
00c55e28  LEA RAX,[RSP + 0x70]
00c55e2d  LEA RBX,[0xe16300]
00c55e34  MOV RCX,qword ptr [RSP + 0xe0]
00c55e3c  NOP dword ptr [RAX]
00c55e40  CALL 0x0053fda0
00c55e45  ADD RSP,0xf8
00c55e4c  POP RBP
00c55e4d  RET
00c55e4e  MOV RDI,RCX
00c55e51  AND RCX,RSI
00c55e54  SHL RCX,0x4
00c55e58  MOV R8,qword ptr [RCX + RDX*0x1 + 0x8]
00c55e5d  NOP dword ptr [RAX]
00c55e60  CMP R8,RBX
00c55e63  JZ 0x00c55e85
00c55e65  LEA RCX,[RDI + 0x1]
00c55e69  TEST R8,R8
00c55e6c  JNZ 0x00c55e4e
00c55e6e  LEA RAX,[0x1974120]
00c55e75  CALL 0x0041e320
00c55e7a  MOV RCX,RAX
00c55e7d  NOP dword ptr [RAX]
00c55e80  JMP 0x00c55af1
00c55e85  MOV RCX,qword ptr [RCX + RDX*0x1 + 0x10]
00c55e8a  JMP 0x00c55af1
00c55e8f  MOV RDX,qword ptr [RSP + 0x30]
00c55e94  INC RDX
00c55e97  MOV RAX,qword ptr [RSP + 0x50]
00c55e9c  MOV RCX,qword ptr [RSP + 0x40]
00c55ea1  CMP RDX,RCX
00c55ea4  JGE 0x00c55ace
00c55eaa  MOV RSI,qword ptr [RAX + 0x8]
00c55eae  CMP RDX,RSI
00c55eb1  JNC 0x00c55ff9
00c55eb7  MOV qword ptr [RSP + 0x30],RDX
00c55ebc  MOV RCX,qword ptr [RAX]
00c55ebf  MOV qword ptr [RSP + 0xd0],RCX
00c55ec7  IMUL RDX,RDX,0xe0
00c55ece  MOV qword ptr [RSP + 0x38],RDX
00c55ed3  MOV RAX,qword ptr [RCX + RDX*0x1]
00c55ed7  MOV RBX,qword ptr [RCX + RDX*0x1 + 0x8]
00c55edc  NOP dword ptr [RAX]
00c55ee0  CALL 0x004b0460
00c55ee5  TEST RBX,RBX
00c55ee8  JNZ 0x00c55eee
00c55eea  XOR EAX,EAX
00c55eec  JMP 0x00c55f05
00c55eee  MOV RDX,qword ptr [0x01990200]
00c55ef5  MOV RCX,RBX
00c55ef8  MOV RBX,RAX
00c55efb  MOV RAX,RDX
00c55efe  NOP
00c55f00  CALL 0x00a13680
00c55f05  MOV qword ptr [RSP + 0x68],RAX
00c55f0a  MOV RCX,qword ptr [RSP + 0x38]
00c55f0f  MOV RDX,qword ptr [RSP + 0xd0]
00c55f17  MOV RAX,qword ptr [RDX + RCX*0x1 + 0x88]
00c55f1f  MOV RBX,qword ptr [RDX + RCX*0x1 + 0x90]
00c55f27  CALL 0x004b0460
00c55f2c  MOV RCX,qword ptr [RSP + 0x68]
00c55f31  TEST RCX,RCX
00c55f34  JNZ 0x00c55f53
00c55f36  TEST RBX,RBX
00c55f39  JZ 0x00c55f53
00c55f3b  MOV RDX,qword ptr [0x01990200]
00c55f42  MOV RCX,RBX
00c55f45  MOV RBX,RAX
00c55f48  MOV RAX,RDX
00c55f4b  CALL 0x00a13680
00c55f50  MOV RCX,RAX
00c55f53  TEST RCX,RCX
00c55f56  JZ 0x00c55e8f
00c55f5c  MOV RDX,qword ptr [RCX + 0x48]
00c55f60  TEST RDX,RDX
00c55f63  JZ 0x00c55fa5
00c55f65  MOV RSI,qword ptr [RCX + 0x40]
00c55f69  MOV RDI,qword ptr [RSP + 0x38]
00c55f6e  MOV R8,qword ptr [RSP + 0xd0]
00c55f76  MOV qword ptr [R8 + RDI*0x1 + 0xb8],RDX
00c55f7e  CMP dword ptr [0x019b5f00],0x0
00c55f85  JZ 0x00c55f9b
00c55f87  MOV RDX,qword ptr [R8 + RDI*0x1 + 0xb0]
00c55f8f  CALL 0x0048bc00
00c55f94  MOV qword ptr [R11],RSI
00c55f97  MOV qword ptr [R11 + 0x8],RDX
00c55f9b  MOV qword ptr [R8 + RDI*0x1 + 0xb0],RSI
00c55fa3  JMP 0x00c55fb2
00c55fa5  MOV RDI,qword ptr [RSP + 0x38]
00c55faa  MOV R8,qword ptr [RSP + 0xd0]
00c55fb2  MOV RDX,qword ptr [RCX + 0x58]
00c55fb6  TEST RDX,RDX
00c55fb9  JZ 0x00c55e8f
00c55fbf  MOV RCX,qword ptr [RCX + 0x50]
00c55fc3  MOV qword ptr [R8 + RDI*0x1 + 0xc8],RDX
00c55fcb  CMP dword ptr [0x019b5f00],0x0
00c55fd2  JZ 0x00c55fec
00c55fd4  MOV RDX,qword ptr [R8 + RDI*0x1 + 0xc0]
00c55fdc  NOP dword ptr [RAX]
00c55fe0  CALL 0x0048bc00
00c55fe5  MOV qword ptr [R11],RCX
00c55fe8  MOV qword ptr [R11 + 0x8],RDX
00c55fec  MOV qword ptr [R8 + RDI*0x1 + 0xc0],RCX
00c55ff4  JMP 0x00c55e8f
00c55ff9  CALL 0x0048bfa0
00c55fff  MOV qword ptr [RSP + 0x8],RAX
00c56004  MOV qword ptr [RSP + 0x10],RBX
00c56009  MOV qword ptr [RSP + 0x18],RCX
00c5600e  CALL 0x0048a280
00c56013  MOV RAX,qword ptr [RSP + 0x8]
00c56018  MOV RBX,qword ptr [RSP + 0x10]
00c5601d  MOV RCX,qword ptr [RSP + 0x18]
00c56022  JMP 0x00c557c0
