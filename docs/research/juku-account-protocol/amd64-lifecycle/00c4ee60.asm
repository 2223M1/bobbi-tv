; main.handleUserFiles
00c4ee60  LEA R12,[RSP + -0xc8]
00c4ee68  CMP R12,qword ptr [R14 + 0x10]
00c4ee6c  JBE 0x00c4f2ff
00c4ee72  PUSH RBP
00c4ee73  MOV RBP,RSP
00c4ee76  SUB RSP,0x140
00c4ee7d  MOV qword ptr [RSP + 0x160],RCX
00c4ee85  MOV qword ptr [RSP + 0x158],RBX
00c4ee8d  MOV qword ptr [RSP + 0x150],RAX
00c4ee95  MOV RCX,qword ptr [RAX + 0x18]
00c4ee99  MOV RAX,RBX
00c4ee9c  CALL RCX
00c4ee9e  MOV qword ptr [RSP + 0x70],RAX
00c4eea3  NOP
00c4eea4  LEA RAX,[0xf10b4b]
00c4eeab  MOV EBX,0xc
00c4eeb0  CALL 0x00640c00
00c4eeb5  MOV qword ptr [RSP + 0x138],RAX
00c4eebd  MOV qword ptr [RSP + 0x48],RBX
00c4eec2  LEA RAX,[0xddc380]
00c4eec9  CALL 0x00421f00
00c4eece  MOV qword ptr [RSP + 0x130],RAX
00c4eed6  MOV qword ptr [RAX + 0x8],0x10
00c4eede  LEA RCX,[0xf195fc]
00c4eee5  MOV qword ptr [RAX],RCX
00c4eee8  LEA RAX,[0xe91b20]
00c4eeef  MOV RBX,qword ptr [RSP + 0x70]
00c4eef4  MOV RCX,qword ptr [RSP + 0x138]
00c4eefc  MOV RDI,qword ptr [RSP + 0x48]
00c4ef01  CALL 0x00413460
00c4ef06  MOV qword ptr [RAX + 0x8],0x1
00c4ef0e  MOV qword ptr [RAX + 0x10],0x1
00c4ef16  CMP dword ptr [0x019b5f00],0x0
00c4ef1d  JNZ 0x00c4ef29
00c4ef1f  MOV RDX,qword ptr [RSP + 0x130]
00c4ef27  JMP 0x00c4ef40
00c4ef29  MOV RCX,qword ptr [RAX]
00c4ef2c  CALL 0x0048bc00
00c4ef31  MOV RDX,qword ptr [RSP + 0x130]
00c4ef39  MOV qword ptr [R11],RDX
00c4ef3c  MOV qword ptr [R11 + 0x8],RCX
00c4ef40  MOV qword ptr [RAX],RDX
00c4ef43  MOV RCX,qword ptr [RSP + 0x160]
00c4ef4b  MOV RAX,qword ptr [RCX + 0x10]
00c4ef4f  CALL 0x005bb0e0
00c4ef54  MOV RBX,RAX
00c4ef57  LEA RCX,[0xf02a51]
00c4ef5e  MOV EDI,0x8
00c4ef63  LEA RAX,[0xe9bd40]
00c4ef6a  CALL 0x00412ee0
00c4ef6f  CMP qword ptr [RAX + 0x8],0x0
00c4ef74  JNZ 0x00c4ef7c
00c4ef76  XOR EDX,EDX
00c4ef78  XOR ECX,ECX
00c4ef7a  JMP 0x00c4ef86
00c4ef7c  MOV RCX,qword ptr [RAX]
00c4ef7f  MOV RDX,qword ptr [RCX + 0x8]
00c4ef83  MOV RCX,qword ptr [RCX]
00c4ef86  MOV RAX,RCX
00c4ef89  MOV RBX,RDX
00c4ef8c  CALL 0x00c47f20
00c4ef91  MOV qword ptr [RSP + 0x60],RAX
00c4ef96  MOV qword ptr [RSP + 0x30],RBX
00c4ef9b  MOV RCX,qword ptr [0x019900d0]
00c4efa2  MOV RDI,RBX
00c4efa5  MOV RBX,RCX
00c4efa8  MOV RCX,RAX
00c4efab  LEA RAX,[0xe17280]
00c4efb2  CALL 0x004131a0
00c4efb7  MOV RCX,qword ptr [RAX]
00c4efba  MOV RDX,qword ptr [RAX + 0x8]
00c4efbe  NOP
00c4efc0  TEST BL,BL
00c4efc2  JZ 0x00c4f214
00c4efc8  MOV qword ptr [RSP + 0x68],RDX
00c4efcd  MOV qword ptr [RSP + 0x38],RCX
00c4efd2  MOV RCX,qword ptr [RSP + 0x160]
00c4efda  MOV RAX,qword ptr [RCX + 0x10]
00c4efde  NOP
00c4efe0  CALL 0x005bb0e0
00c4efe5  MOV RBX,RAX
00c4efe8  LEA RCX,[0xf1546b]
00c4efef  MOV EDI,0xe
00c4eff4  LEA RAX,[0xe9bd40]
00c4effb  NOP dword ptr [RAX + RAX*0x1]
00c4f000  CALL 0x00412ee0
00c4f005  CMP qword ptr [RAX + 0x8],0x0
00c4f00a  JNZ 0x00c4f012
00c4f00c  XOR EDX,EDX
00c4f00e  XOR ECX,ECX
00c4f010  JMP 0x00c4f01c
00c4f012  MOV RCX,qword ptr [RAX]
00c4f015  MOV RDX,qword ptr [RCX + 0x8]
00c4f019  MOV RCX,qword ptr [RCX]
00c4f01c  MOV qword ptr [RSP + 0x28],RDX
00c4f021  MOV qword ptr [RSP + 0x50],RCX
00c4f026  MOV RCX,qword ptr [RSP + 0x160]
00c4f02e  MOV RAX,qword ptr [RCX + 0x10]
00c4f032  CALL 0x005bb0e0
00c4f037  MOV RBX,RAX
00c4f03a  LEA RCX,[0xefc947]
00c4f041  MOV EDI,0x5
00c4f046  LEA RAX,[0xe9bd40]
00c4f04d  CALL 0x00412ee0
00c4f052  CMP qword ptr [RAX + 0x8],0x0
00c4f057  JNZ 0x00c4f062
00c4f059  XOR R8D,R8D
00c4f05c  XOR EDX,EDX
00c4f05e  NOP
00c4f060  JMP 0x00c4f06c
00c4f062  MOV RDX,qword ptr [RAX]
00c4f065  MOV R8,qword ptr [RDX + 0x8]
00c4f069  MOV RDX,qword ptr [RDX]
00c4f06c  TEST R8,R8
00c4f06f  JNZ 0x00c4f0ac
00c4f071  CMP qword ptr [0x019900b0],0x0
00c4f079  JZ 0x00c4f0ac
00c4f07b  MOV RCX,qword ptr [RSP + 0x38]
00c4f080  MOV RCX,qword ptr [RCX + 0x28]
00c4f084  MOV RAX,qword ptr [RSP + 0x68]
00c4f089  CALL RCX
00c4f08b  MOV RCX,qword ptr [0x019900b0]
00c4f092  MOV RDX,RAX
00c4f095  MOV RAX,RCX
00c4f098  MOV RSI,RBX
00c4f09b  MOV RBX,RDX
00c4f09e  MOV RCX,RSI
00c4f0a1  CALL 0x00a63de0
00c4f0a6  MOV R8,RBX
00c4f0a9  MOV RDX,RAX
00c4f0ac  MOV R9,qword ptr [RSP + 0x38]
00c4f0b1  MOV R9,qword ptr [R9 + 0x20]
00c4f0b5  MOV RAX,qword ptr [RSP + 0x68]
00c4f0ba  MOV RBX,qword ptr [RSP + 0x50]
00c4f0bf  MOV RCX,qword ptr [RSP + 0x28]
00c4f0c4  MOV RDI,RDX
00c4f0c7  MOV RSI,R8
00c4f0ca  CALL R9
00c4f0cd  TEST RBX,RBX
00c4f0d0  JNZ 0x00c4f0ff
00c4f0d2  MOV RDX,qword ptr [RSP + 0x150]
00c4f0da  NOP word ptr [RAX + RAX*0x1]
00c4f0e0  TEST RDX,RDX
00c4f0e3  JZ 0x00c4f25a
00c4f0e9  MOV RBX,qword ptr [RDX + 0x8]
00c4f0ed  MOV RSI,qword ptr [0x01973fa0]
00c4f0f4  MOV RDI,qword ptr [RSI]
00c4f0f7  MOV EDX,dword ptr [RDX + 0x10]
00c4f0fa  JMP 0x00c4f2ba
00c4f0ff  MOV qword ptr [RSP + 0x78],RCX
00c4f104  MOV qword ptr [RSP + 0x40],RBX
00c4f109  MOV RCX,qword ptr [RSP + 0x38]
00c4f10e  MOV RCX,qword ptr [RCX + 0x28]
00c4f112  MOV RAX,qword ptr [RSP + 0x68]
00c4f117  CALL RCX
00c4f119  LEA RCX,[RSP + 0xe0]
00c4f121  MOVUPS xmmword ptr [RCX],XMM15
00c4f125  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c4f12a  CALL 0x00481ee0
00c4f12f  LEA RCX,[0xdd29c0]
00c4f136  MOV qword ptr [RSP + 0xe0],RCX
00c4f13e  MOV qword ptr [RSP + 0xe8],RAX
00c4f146  MOV RCX,qword ptr [RSP + 0x40]
00c4f14b  TEST RCX,RCX
00c4f14e  JZ 0x00c4f156
00c4f150  MOV RBX,qword ptr [RCX + 0x8]
00c4f154  JMP 0x00c4f159
00c4f156  MOV RBX,RCX
00c4f159  MOV qword ptr [RSP + 0xf0],RBX
00c4f161  MOV RDX,qword ptr [RSP + 0x78]
00c4f166  MOV qword ptr [RSP + 0xf8],RDX
00c4f16e  LEA RDX,[0xc4f340]
00c4f175  MOV qword ptr [RSP + 0x100],RDX
00c4f17d  MOV qword ptr [RSP + 0x110],0x30
00c4f189  LEA RDX,[0xf44120]
00c4f190  MOV qword ptr [RSP + 0x108],RDX
00c4f198  MOV qword ptr [RSP + 0x120],0x2
00c4f1a4  MOV qword ptr [RSP + 0x128],0x2
00c4f1b0  LEA RDX,[RSP + 0xe0]
00c4f1b8  MOV qword ptr [RSP + 0x118],RDX
00c4f1c0  MOV RAX,qword ptr [0x01990148]
00c4f1c7  XOR EBX,EBX
00c4f1c9  MOV ECX,0x2
00c4f1ce  LEA RDI,[RSP + 0x100]
00c4f1d6  CALL 0x0054d540
00c4f1db  MOV RDX,qword ptr [RSP + 0x40]
00c4f1e0  MOV RDX,qword ptr [RDX + 0x18]
00c4f1e4  MOV RAX,qword ptr [RSP + 0x78]
00c4f1e9  CALL RDX
00c4f1eb  MOV RCX,RAX
00c4f1ee  MOV RDI,RBX
00c4f1f1  MOV ESI,0x1f4
00c4f1f6  MOV RAX,qword ptr [RSP + 0x150]
00c4f1fe  MOV RBX,qword ptr [RSP + 0x158]
00c4f206  CALL 0x00c484c0
00c4f20b  ADD RSP,0x140
00c4f212  POP RBP
00c4f213  RET
00c4f214  XOR EAX,EAX
00c4f216  LEA RBX,[0xf1d559]
00c4f21d  MOV ECX,0x12
00c4f222  MOV RDI,qword ptr [RSP + 0x60]
00c4f227  MOV RSI,qword ptr [RSP + 0x30]
00c4f22c  CALL 0x0046b1e0
00c4f231  MOV RCX,RAX
00c4f234  MOV RDI,RBX
00c4f237  MOV ESI,0x190
00c4f23c  MOV RAX,qword ptr [RSP + 0x150]
00c4f244  MOV RBX,qword ptr [RSP + 0x158]
00c4f24c  CALL 0x00c484c0
00c4f251  ADD RSP,0x140
00c4f258  POP RBP
00c4f259  RET
00c4f25a  LEA RSI,[RSP + 0x80]
00c4f262  MOVUPS xmmword ptr [RSI],XMM15
00c4f266  MOVUPS xmmword ptr [RSI + 0x10],XMM15
00c4f26b  MOVUPS xmmword ptr [RSI + 0x20],XMM15
00c4f270  MOVUPS xmmword ptr [RSI + 0x30],XMM15
00c4f275  MOVUPS xmmword ptr [RSI + 0x40],XMM15
00c4f27a  MOVUPS xmmword ptr [RSI + 0x50],XMM15
00c4f27f  MOV qword ptr [RSP + 0x80],RDX
00c4f287  MOV RDX,qword ptr [RSP + 0x158]
00c4f28f  MOV qword ptr [RSP + 0x88],RDX
00c4f297  MOV byte ptr [RSP + 0xa0],0x1
00c4f29f  LEA RBX,[0xdb19e0]
00c4f2a6  MOV RCX,RAX
00c4f2a9  MOV RAX,RSI
00c4f2ac  CALL 0x0053fda0
00c4f2b1  ADD RSP,0x140
00c4f2b8  POP RBP
00c4f2b9  RET
00c4f2ba  MOV R8,RDX
00c4f2bd  AND RDX,RDI
00c4f2c0  SHL RDX,0x4
00c4f2c4  MOV R9,qword ptr [RDX + RSI*0x1 + 0x8]
00c4f2c9  CMP R9,RBX
00c4f2cc  JZ 0x00c4f2f5
00c4f2ce  LEA RDX,[R8 + 0x1]
00c4f2d2  TEST R9,R9
00c4f2d5  JNZ 0x00c4f2ba
00c4f2d7  MOV qword ptr [RSP + 0x58],RAX
00c4f2dc  LEA RAX,[0x1973fa0]
00c4f2e3  CALL 0x0041e320
00c4f2e8  MOV RDX,RAX
00c4f2eb  MOV RAX,qword ptr [RSP + 0x58]
00c4f2f0  JMP 0x00c4f25a
00c4f2f5  MOV RDX,qword ptr [RDX + RSI*0x1 + 0x10]
00c4f2fa  JMP 0x00c4f25a
00c4f2ff  MOV qword ptr [RSP + 0x8],RAX
00c4f304  MOV qword ptr [RSP + 0x10],RBX
00c4f309  MOV qword ptr [RSP + 0x18],RCX
00c4f30e  CALL 0x0048a280
00c4f313  MOV RAX,qword ptr [RSP + 0x8]
00c4f318  MOV RBX,qword ptr [RSP + 0x10]
00c4f31d  MOV RCX,qword ptr [RSP + 0x18]
00c4f322  JMP 0x00c4ee60
