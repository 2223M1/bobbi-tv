; main.handleQrCodeStatus
00c4afc0  LEA R12,[RSP + -0x168]
00c4afc8  CMP R12,qword ptr [R14 + 0x10]
00c4afcc  JBE 0x00c4b545
00c4afd2  PUSH RBP
00c4afd3  MOV RBP,RSP
00c4afd6  SUB RSP,0x1e0
00c4afdd  MOV qword ptr [RSP + 0x200],RCX
00c4afe5  MOV qword ptr [RSP + 0x1f8],RBX
00c4afed  MOV qword ptr [RSP + 0x1f0],RAX
00c4aff5  MOV RCX,qword ptr [RAX + 0x18]
00c4aff9  MOV RAX,RBX
00c4affc  CALL RCX
00c4affe  MOV qword ptr [RSP + 0x68],RAX
00c4b003  NOP
00c4b004  LEA RAX,[0xf10b4b]
00c4b00b  MOV EBX,0xc
00c4b010  CALL 0x00640c00
00c4b015  MOV qword ptr [RSP + 0x78],RAX
00c4b01a  MOV qword ptr [RSP + 0x40],RBX
00c4b01f  LEA RAX,[0xddc380]
00c4b026  CALL 0x00421f00
00c4b02b  MOV qword ptr [RSP + 0x70],RAX
00c4b030  MOV qword ptr [RAX + 0x8],0x10
00c4b038  LEA RCX,[0xf195fc]
00c4b03f  MOV qword ptr [RAX],RCX
00c4b042  LEA RAX,[0xe91b20]
00c4b049  MOV RBX,qword ptr [RSP + 0x68]
00c4b04e  MOV RCX,qword ptr [RSP + 0x78]
00c4b053  MOV RDI,qword ptr [RSP + 0x40]
00c4b058  CALL 0x00413460
00c4b05d  MOV qword ptr [RAX + 0x8],0x1
00c4b065  MOV qword ptr [RAX + 0x10],0x1
00c4b06d  CMP dword ptr [0x019b5f00],0x0
00c4b074  JNZ 0x00c4b07d
00c4b076  MOV RDX,qword ptr [RSP + 0x70]
00c4b07b  JMP 0x00c4b091
00c4b07d  MOV RCX,qword ptr [RAX]
00c4b080  CALL 0x0048bc00
00c4b085  MOV RDX,qword ptr [RSP + 0x70]
00c4b08a  MOV qword ptr [R11],RDX
00c4b08d  MOV qword ptr [R11 + 0x8],RCX
00c4b091  MOV qword ptr [RAX],RDX
00c4b094  MOV RCX,qword ptr [RSP + 0x200]
00c4b09c  MOV RAX,qword ptr [RCX + 0x10]
00c4b0a0  CALL 0x005bb0e0
00c4b0a5  MOV RBX,RAX
00c4b0a8  LEA RCX,[0xf02a51]
00c4b0af  MOV EDI,0x8
00c4b0b4  LEA RAX,[0xe9bd40]
00c4b0bb  NOP dword ptr [RAX + RAX*0x1]
00c4b0c0  CALL 0x00412ee0
00c4b0c5  CMP qword ptr [RAX + 0x8],0x0
00c4b0ca  JNZ 0x00c4b0d2
00c4b0cc  XOR EDX,EDX
00c4b0ce  XOR ECX,ECX
00c4b0d0  JMP 0x00c4b0dc
00c4b0d2  MOV RCX,qword ptr [RAX]
00c4b0d5  MOV RDX,qword ptr [RCX + 0x8]
00c4b0d9  MOV RCX,qword ptr [RCX]
00c4b0dc  MOV RAX,RCX
00c4b0df  MOV RBX,RDX
00c4b0e2  CALL 0x00c47f20
00c4b0e7  MOV qword ptr [RSP + 0x60],RAX
00c4b0ec  MOV qword ptr [RSP + 0x38],RBX
00c4b0f1  MOV RCX,qword ptr [RSP + 0x200]
00c4b0f9  MOV RAX,qword ptr [RCX + 0x10]
00c4b0fd  NOP dword ptr [RAX]
00c4b100  CALL 0x005bb0e0
00c4b105  MOV RBX,RAX
00c4b108  LEA RCX,[0xefabaf]
00c4b10f  MOV EDI,0x3
00c4b114  LEA RAX,[0xe9bd40]
00c4b11b  NOP dword ptr [RAX + RAX*0x1]
00c4b120  CALL 0x00412ee0
00c4b125  CMP qword ptr [RAX + 0x8],0x0
00c4b12a  JNZ 0x00c4b132
00c4b12c  XOR EDX,EDX
00c4b12e  XOR ESI,ESI
00c4b130  JMP 0x00c4b13c
00c4b132  MOV RDX,qword ptr [RAX]
00c4b135  MOV RSI,qword ptr [RDX + 0x8]
00c4b139  MOV RDX,qword ptr [RDX]
00c4b13c  MOV qword ptr [RSP + 0x28],RSI
00c4b141  MOV qword ptr [RSP + 0x48],RDX
00c4b146  MOV RBX,qword ptr [0x019900d0]
00c4b14d  LEA RAX,[0xe17280]
00c4b154  MOV RCX,qword ptr [RSP + 0x60]
00c4b159  MOV RDI,qword ptr [RSP + 0x38]
00c4b15e  NOP
00c4b160  CALL 0x004131a0
00c4b165  TEST BL,BL
00c4b167  JZ 0x00c4b2ce
00c4b16d  MOV RCX,qword ptr [RSP + 0x28]
00c4b172  CMP RCX,0x6
00c4b176  JNZ 0x00c4b20d
00c4b17c  MOV RBX,qword ptr [RSP + 0x48]
00c4b181  CMP dword ptr [RBX],0x756e616d
00c4b187  JNZ 0x00c4b212
00c4b18d  CMP word ptr [RBX + 0x4],0x6c61
00c4b193  JNZ 0x00c4b212
00c4b195  MOV RAX,qword ptr [0x019900b0]
00c4b19c  NOP dword ptr [RAX]
00c4b1a0  TEST RAX,RAX
00c4b1a3  JNZ 0x00c4b1ab
00c4b1a5  XOR EBX,EBX
00c4b1a7  XOR EAX,EAX
00c4b1a9  JMP 0x00c4b1ba
00c4b1ab  MOV RBX,qword ptr [RSP + 0x60]
00c4b1b0  MOV RCX,qword ptr [RSP + 0x38]
00c4b1b5  CALL 0x00a63de0
00c4b1ba  TEST RBX,RBX
00c4b1bd  JZ 0x00c4b1e6
00c4b1bf  MOV RCX,qword ptr [RSP + 0x1f0]
00c4b1c7  TEST RCX,RCX
00c4b1ca  JZ 0x00c4b439
00c4b1d0  MOV RDX,qword ptr [RCX + 0x8]
00c4b1d4  MOV RSI,qword ptr [0x01973ec0]
00c4b1db  MOV RDI,qword ptr [RSI]
00c4b1de  MOV ECX,dword ptr [RCX + 0x10]
00c4b1e1  JMP 0x00c4b4f3
00c4b1e6  MOV RDX,qword ptr [RSP + 0x1f0]
00c4b1ee  TEST RDX,RDX
00c4b1f1  JZ 0x00c4b39d
00c4b1f7  MOV RBX,qword ptr [RDX + 0x8]
00c4b1fb  MOV RSI,qword ptr [0x01973ee0]
00c4b202  MOV RDI,qword ptr [RSI]
00c4b205  MOV EDX,dword ptr [RDX + 0x10]
00c4b208  JMP 0x00c4b3fe
00c4b20d  MOV RBX,qword ptr [RSP + 0x48]
00c4b212  MOV RDX,qword ptr [RAX]
00c4b215  MOV RAX,qword ptr [RAX + 0x8]
00c4b219  MOV RDX,qword ptr [RDX + 0x30]
00c4b21d  CALL RDX
00c4b21f  NOP
00c4b220  TEST RBX,RBX
00c4b223  JNZ 0x00c4b29b
00c4b225  MOV qword ptr [RSP + 0x58],RAX
00c4b22a  CMP qword ptr [RAX + 0x8],0x9
00c4b22f  JNZ 0x00c4b273
00c4b231  MOV RDX,qword ptr [RAX]
00c4b234  MOV R8,0x656d7269666e6f63
00c4b23e  NOP
00c4b240  CMP qword ptr [RDX],R8
00c4b243  JNZ 0x00c4b273
00c4b245  CMP byte ptr [RDX + 0x8],0x64
00c4b249  JNZ 0x00c4b273
00c4b24b  MOV RSI,qword ptr [RAX + 0x18]
00c4b24f  TEST RSI,RSI
00c4b252  JZ 0x00c4b273
00c4b254  MOV RDI,qword ptr [RAX + 0x10]
00c4b258  MOV RAX,qword ptr [0x019900b0]
00c4b25f  MOV RBX,qword ptr [RSP + 0x60]
00c4b264  MOV RCX,qword ptr [RSP + 0x38]
00c4b269  CALL 0x00a63a60
00c4b26e  MOV RAX,qword ptr [RSP + 0x58]
00c4b273  MOV RDX,qword ptr [RSP + 0x1f0]
00c4b27b  NOP dword ptr [RAX + RAX*0x1]
00c4b280  TEST RDX,RDX
00c4b283  JZ 0x00c4b2fd
00c4b285  MOV RBX,qword ptr [RDX + 0x8]
00c4b289  MOV RSI,qword ptr [0x01973f00]
00c4b290  MOV RDI,qword ptr [RSI]
00c4b293  MOV EDX,dword ptr [RDX + 0x10]
00c4b296  JMP 0x00c4b35d
00c4b29b  MOV RDX,qword ptr [RBX + 0x18]
00c4b29f  MOV RAX,RCX
00c4b2a2  CALL RDX
00c4b2a4  MOV RCX,RAX
00c4b2a7  MOV RDI,RBX
00c4b2aa  MOV ESI,0x1f4
00c4b2af  MOV RAX,qword ptr [RSP + 0x1f0]
00c4b2b7  MOV RBX,qword ptr [RSP + 0x1f8]
00c4b2bf  NOP
00c4b2c0  CALL 0x00c484c0
00c4b2c5  ADD RSP,0x1e0
00c4b2cc  POP RBP
00c4b2cd  RET
00c4b2ce  MOV RAX,qword ptr [RSP + 0x1f0]
00c4b2d6  MOV RBX,qword ptr [RSP + 0x1f8]
00c4b2de  LEA RCX,[0xf1962c]
00c4b2e5  MOV EDI,0x10
00c4b2ea  MOV ESI,0x190
00c4b2ef  CALL 0x00c484c0
00c4b2f4  ADD RSP,0x1e0
00c4b2fb  POP RBP
00c4b2fc  RET
00c4b2fd  LEA RSI,[RSP + 0x80]
00c4b305  MOVUPS xmmword ptr [RSI],XMM15
00c4b309  MOVUPS xmmword ptr [RSI + 0x10],XMM15
00c4b30e  MOVUPS xmmword ptr [RSI + 0x20],XMM15
00c4b313  MOVUPS xmmword ptr [RSI + 0x30],XMM15
00c4b318  MOVUPS xmmword ptr [RSI + 0x40],XMM15
00c4b31d  MOVUPS xmmword ptr [RSI + 0x50],XMM15
00c4b322  MOV qword ptr [RSP + 0x80],RDX
00c4b32a  MOV RDX,qword ptr [RSP + 0x1f8]
00c4b332  MOV qword ptr [RSP + 0x88],RDX
00c4b33a  MOV byte ptr [RSP + 0xa0],0x1
00c4b342  LEA RBX,[0xdb1a20]
00c4b349  MOV RCX,RAX
00c4b34c  MOV RAX,RSI
00c4b34f  CALL 0x0053fda0
00c4b354  ADD RSP,0x1e0
00c4b35b  POP RBP
00c4b35c  RET
00c4b35d  MOV R8,RDX
00c4b360  AND RDX,RDI
00c4b363  SHL RDX,0x4
00c4b367  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
00c4b36c  CMP R9,RBX
00c4b36f  JZ 0x00c4b393
00c4b371  LEA RDX,[R8 + 0x1]
00c4b375  TEST R9,R9
00c4b378  JNZ 0x00c4b35d
00c4b37a  LEA RAX,[0x1973f00]
00c4b381  CALL 0x0041e320
00c4b386  MOV RDX,RAX
00c4b389  MOV RAX,qword ptr [RSP + 0x58]
00c4b38e  JMP 0x00c4b2fd
00c4b393  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
00c4b398  JMP 0x00c4b2fd
00c4b39d  LEA RAX,[RSP + 0xe0]
00c4b3a5  MOVUPS xmmword ptr [RAX],XMM15
00c4b3a9  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c4b3ae  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c4b3b3  MOVUPS xmmword ptr [RAX + 0x30],XMM15
00c4b3b8  MOVUPS xmmword ptr [RAX + 0x40],XMM15
00c4b3bd  MOVUPS xmmword ptr [RAX + 0x50],XMM15
00c4b3c2  MOV qword ptr [RSP + 0xe0],RDX
00c4b3ca  MOV RDX,qword ptr [RSP + 0x1f8]
00c4b3d2  MOV qword ptr [RSP + 0xe8],RDX
00c4b3da  MOV byte ptr [RSP + 0x100],0x1
00c4b3e2  LEA RBX,[0xe836e0]
00c4b3e9  LEA RCX,[0x1143ac0]
00c4b3f0  CALL 0x0053fda0
00c4b3f5  ADD RSP,0x1e0
00c4b3fc  POP RBP
00c4b3fd  RET
00c4b3fe  MOV R8,RDX
00c4b401  AND RDX,RDI
00c4b404  SHL RDX,0x4
00c4b408  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
00c4b40d  CMP R9,RBX
00c4b410  JZ 0x00c4b42f
00c4b412  LEA RDX,[R8 + 0x1]
00c4b416  TEST R9,R9
00c4b419  JNZ 0x00c4b3fe
00c4b41b  LEA RAX,[0x1973ee0]
00c4b422  CALL 0x0041e320
00c4b427  MOV RDX,RAX
00c4b42a  JMP 0x00c4b39d
00c4b42f  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
00c4b434  JMP 0x00c4b39d
00c4b439  LEA RDX,[RSP + 0x140]
00c4b441  MOVUPS xmmword ptr [RDX],XMM15
00c4b445  MOVUPS xmmword ptr [RDX + 0x10],XMM15
00c4b44a  MOVUPS xmmword ptr [RDX + 0x20],XMM15
00c4b44f  MOVUPS xmmword ptr [RDX + 0x30],XMM15
00c4b454  MOVUPS xmmword ptr [RDX + 0x40],XMM15
00c4b459  MOVUPS xmmword ptr [RDX + 0x50],XMM15
00c4b45e  MOV qword ptr [RSP + 0x140],RCX
00c4b466  MOV RCX,qword ptr [RSP + 0x1f8]
00c4b46e  MOV qword ptr [RSP + 0x148],RCX
00c4b476  MOV byte ptr [RSP + 0x160],0x1
00c4b47e  LEA RCX,[RSP + 0x1a0]
00c4b486  MOVUPS xmmword ptr [RCX],XMM15
00c4b48a  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c4b48f  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00c4b494  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00c4b499  LEA RDX,[0xf059ff]
00c4b4a0  MOV qword ptr [RSP + 0x1a0],RDX
00c4b4a8  MOV qword ptr [RSP + 0x1a8],0x9
00c4b4b4  MOV qword ptr [RSP + 0x1b0],RAX
00c4b4bc  MOV qword ptr [RSP + 0x1b8],RBX
00c4b4c4  LEA RAX,[0xe836e0]
00c4b4cb  MOV RBX,RCX
00c4b4ce  CALL 0x0041e0e0
00c4b4d3  LEA RBX,[0xe836e0]
00c4b4da  MOV RCX,RAX
00c4b4dd  LEA RAX,[RSP + 0x140]
00c4b4e5  CALL 0x0053fda0
00c4b4ea  ADD RSP,0x1e0
00c4b4f1  POP RBP
00c4b4f2  RET
00c4b4f3  MOV R8,RCX
00c4b4f6  AND RCX,RDI
00c4b4f9  SHL RCX,0x4
00c4b4fd  MOV R9,qword ptr [RSI + RCX*0x1 + 0x8]
00c4b502  CMP R9,RDX
00c4b505  JZ 0x00c4b53b
00c4b507  LEA RCX,[R8 + 0x1]
00c4b50b  TEST R9,R9
00c4b50e  JNZ 0x00c4b4f3
00c4b510  MOV qword ptr [RSP + 0x30],RBX
00c4b515  MOV qword ptr [RSP + 0x50],RAX
00c4b51a  LEA RAX,[0x1973ec0]
00c4b521  MOV RBX,RDX
00c4b524  CALL 0x0041e320
00c4b529  MOV RBX,qword ptr [RSP + 0x30]
00c4b52e  MOV RCX,RAX
00c4b531  MOV RAX,qword ptr [RSP + 0x50]
00c4b536  JMP 0x00c4b439
00c4b53b  MOV RCX,qword ptr [RSI + RCX*0x1 + 0x10]
00c4b540  JMP 0x00c4b439
00c4b545  MOV qword ptr [RSP + 0x8],RAX
00c4b54a  MOV qword ptr [RSP + 0x10],RBX
00c4b54f  MOV qword ptr [RSP + 0x18],RCX
00c4b554  CALL 0x0048a280
00c4b559  MOV RAX,qword ptr [RSP + 0x8]
00c4b55e  MOV RBX,qword ptr [RSP + 0x10]
00c4b563  MOV RCX,qword ptr [RSP + 0x18]
00c4b568  JMP 0x00c4afc0
