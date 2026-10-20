; mv-daemon/provider.(*Cloud115Provider).resolve115Subtitles
009c45a0  LEA R12,[RSP + -0x2a0]
009c45a8  CMP R12,qword ptr [R14 + 0x10]
009c45ac  JBE 0x009c5188
009c45b2  PUSH RBP
009c45b3  MOV RBP,RSP
009c45b6  SUB RSP,0x318
009c45bd  MOV qword ptr [RSP + 0x378],R8
009c45c5  MOV qword ptr [RSP + 0x370],RSI
009c45cd  MOV qword ptr [RSP + 0x368],RDI
009c45d5  MOV qword ptr [RSP + 0x380],R9
009c45dd  MOV qword ptr [RSP + 0x360],RCX
009c45e5  MOV qword ptr [RSP + 0x358],RBX
009c45ed  MOV qword ptr [RSP + 0x390],R11
009c45f5  MOV qword ptr [RSP + 0x388],R10
009c45fd  LEA RAX,[RSP + 0x2a0]
009c4605  MOVUPS xmmword ptr [RAX],XMM15
009c4609  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009c460e  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009c4613  LEA RAX,[RSP + 0x1d8]
009c461b  MOV ECX,0x3
009c4620  MOVUPS xmmword ptr [RAX],XMM15
009c4624  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009c4629  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009c462e  MOVUPS xmmword ptr [RAX + 0x30],XMM15
009c4633  ADD RAX,0x40
009c4637  DEC ECX
009c4639  JNZ 0x009c4620
009c463b  MOVUPS xmmword ptr [RAX + -0x8],XMM15
009c4640  MOV RAX,-0x7f7f7f7f7f7f7f80
009c464a  MOV qword ptr [RSP + 0x1d8],RAX
009c4652  LEA RAX,[RSP + 0x1d8]
009c465a  MOV qword ptr [RSP + 0x2b0],RAX
009c4662  CALL 0x00485080
009c4667  MOV qword ptr [RSP + 0x2a8],RAX
009c466f  MOV RAX,qword ptr [RSP + 0x328]
009c4677  MOV RCX,qword ptr [RSP + 0x330]
009c467f  XOR EDX,EDX
009c4681  XOR EBX,EBX
009c4683  XOR ESI,ESI
009c4685  XOR EDI,EDI
009c4687  JMP 0x009c4690
009c4689  ADD RAX,0x20
009c468d  INC RDX
009c4690  MOV qword ptr [RSP + 0x78],RBX
009c4695  MOV qword ptr [RSP + 0x100],RDI
009c469d  MOV qword ptr [RSP + 0x80],RSI
009c46a5  CMP RCX,RDX
009c46a8  JLE 0x009c4988
009c46ae  MOV qword ptr [RSP + 0xf8],RDX
009c46b6  MOV qword ptr [RSP + 0x310],RAX
009c46be  MOV R11,qword ptr [RAX + 0x8]
009c46c2  MOV qword ptr [RSP + 0xf0],R11
009c46ca  MOV R12,qword ptr [RAX]
009c46cd  MOV qword ptr [RSP + 0x308],R12
009c46d5  MOV R13,qword ptr [RAX + 0x18]
009c46d9  MOV qword ptr [RSP + 0xe8],R13
009c46e1  MOV R15,qword ptr [RAX + 0x10]
009c46e5  MOV qword ptr [RSP + 0x300],R15
009c46ed  TEST R11,R11
009c46f0  JNZ 0x009c46fa
009c46f2  MOV R8D,0x1
009c46f8  JMP 0x009c4767
009c46fa  LEA RAX,[0xe16280]
009c4701  LEA RBX,[RSP + 0x2a0]
009c4709  MOV RCX,R12
009c470c  MOV RDI,R11
009c470f  CALL 0x00412ee0
009c4714  MOVZX EDX,byte ptr [RAX]
009c4717  MOV RAX,qword ptr [RSP + 0x310]
009c471f  MOV RCX,qword ptr [RSP + 0x330]
009c4727  MOV RBX,qword ptr [RSP + 0x78]
009c472c  MOV RSI,qword ptr [RSP + 0x80]
009c4734  MOV RDI,qword ptr [RSP + 0x100]
009c473c  MOV R11,qword ptr [RSP + 0xf0]
009c4744  MOV R12,qword ptr [RSP + 0x308]
009c474c  MOV R13,qword ptr [RSP + 0xe8]
009c4754  MOV R15,qword ptr [RSP + 0x300]
009c475c  MOV R8D,EDX
009c475f  MOV RDX,qword ptr [RSP + 0xf8]
009c4767  TEST R8B,R8B
009c476a  JNZ 0x009c4689
009c4770  LEA RAX,[0xe16280]
009c4777  LEA RBX,[RSP + 0x2a0]
009c477f  MOV RCX,R12
009c4782  MOV RDI,R11
009c4785  CALL 0x00413460
009c478a  MOV byte ptr [RAX],0x1
009c478d  MOV RAX,qword ptr [RSP + 0x358]
009c4795  MOV RBX,qword ptr [RSP + 0x360]
009c479d  MOV RCX,qword ptr [RSP + 0x368]
009c47a5  MOV RDI,qword ptr [RSP + 0x370]
009c47ad  MOV RSI,qword ptr [RSP + 0x308]
009c47b5  MOV R8,qword ptr [RSP + 0xf0]
009c47bd  MOV R9,qword ptr [RSP + 0x340]
009c47c5  MOV R10,qword ptr [RSP + 0x348]
009c47cd  CALL 0x009c3260
009c47d2  TEST RSI,RSI
009c47d5  JNZ 0x009c47dc
009c47d7  TEST RBX,RBX
009c47da  JNZ 0x009c482f
009c47dc  MOVUPS xmmword ptr [RSP],XMM15
009c47e1  MOV qword ptr [RSP + 0x10],0x0
009c47ea  MOV RAX,qword ptr [RSP + 0x358]
009c47f2  MOV RBX,qword ptr [RSP + 0x360]
009c47fa  MOV RCX,qword ptr [RSP + 0x368]
009c4802  MOV RDI,qword ptr [RSP + 0x370]
009c480a  MOV RSI,qword ptr [RSP + 0x308]
009c4812  MOV R8,qword ptr [RSP + 0xf0]
009c481a  MOV R9,qword ptr [RSP + 0x340]
009c4822  MOV R10,qword ptr [RSP + 0x348]
009c482a  CALL 0x009c1f20
009c482f  TEST RBX,RBX
009c4832  JZ 0x009c4950
009c4838  MOV RDX,qword ptr [RSP + 0x78]
009c483d  INC RDX
009c4840  MOV R11,qword ptr [RSP + 0xe8]
009c4848  TEST R11,R11
009c484b  CMOVZ R11,RDI
009c484f  MOV R12,qword ptr [RSP + 0x300]
009c4857  CMOVZ R12,RCX
009c485b  MOV qword ptr [RSP + 0x110],R12
009c4863  MOV qword ptr [RSP + 0x118],R11
009c486b  MOV qword ptr [RSP + 0x120],RAX
009c4873  MOV qword ptr [RSP + 0x128],RBX
009c487b  MOV qword ptr [RSP + 0x130],0x64
009c4887  MOV RCX,qword ptr [RSP + 0x80]
009c488f  CMP RCX,RDX
009c4892  JC 0x009c48a2
009c4894  MOV RBX,RDX
009c4897  MOV RAX,qword ptr [RSP + 0x100]
009c489f  NOP
009c48a0  JMP 0x009c48be
009c48a2  MOV RAX,qword ptr [RSP + 0x100]
009c48aa  MOV RBX,RDX
009c48ad  MOV EDI,0x1
009c48b2  LEA RSI,[0xe698a0]
009c48b9  CALL 0x00486be0
009c48be  LEA RDX,[RBX + RBX*0x4]
009c48c2  LEA RDX,[RAX + RDX*0x8]
009c48c6  LEA RDX,[RDX + -0x28]
009c48ca  CMP dword ptr [0x019b5f00],0x0
009c48d1  JZ 0x009c492a
009c48d3  MOV qword ptr [RSP + 0x2f8],RAX
009c48db  MOV qword ptr [RSP + 0xe0],RBX
009c48e3  MOV qword ptr [RSP + 0xd8],RCX
009c48eb  MOV qword ptr [RSP + 0x2f0],RDX
009c48f3  LEA RAX,[0xe698a0]
009c48fa  MOV RBX,RDX
009c48fd  LEA RCX,[RSP + 0x110]
009c4905  CALL 0x004226a0
009c490a  MOV RAX,qword ptr [RSP + 0x2f8]
009c4912  MOV RCX,qword ptr [RSP + 0xd8]
009c491a  MOV RDX,qword ptr [RSP + 0x2f0]
009c4922  MOV RBX,qword ptr [RSP + 0xe0]
009c492a  LEA R11,[RSP + 0x110]
009c4932  MOVUPS XMM14,xmmword ptr [R11]
009c4936  MOVUPS xmmword ptr [RDX],XMM14
009c493a  MOVUPS XMM14,xmmword ptr [R11 + 0x10]
009c493f  MOVUPS xmmword ptr [RDX + 0x10],XMM14
009c4944  MOVUPS XMM14,xmmword ptr [R11 + 0x18]
009c4949  MOVUPS xmmword ptr [RDX + 0x18],XMM14
009c494e  JMP 0x009c4965
009c4950  MOV RCX,qword ptr [RSP + 0x80]
009c4958  MOV RBX,qword ptr [RSP + 0x78]
009c495d  MOV RAX,qword ptr [RSP + 0x100]
009c4965  MOV RDX,qword ptr [RSP + 0xf8]
009c496d  MOV RSI,RCX
009c4970  MOV RDI,RAX
009c4973  MOV RAX,qword ptr [RSP + 0x310]
009c497b  MOV RCX,qword ptr [RSP + 0x330]
009c4983  JMP 0x009c4689
009c4988  TEST RBX,RBX
009c498b  JNZ 0x009c4a6d
009c4991  MOV R8,qword ptr [RSP + 0x380]
009c4999  NOP dword ptr [RAX]
009c49a0  TEST R8,R8
009c49a3  JZ 0x009c4a6d
009c49a9  CMP R8,0x1
009c49ad  JZ 0x009c49b9
009c49af  MOV RDX,qword ptr [RSP + 0x378]
009c49b7  JMP 0x009c49ca
009c49b9  MOV RDX,qword ptr [RSP + 0x378]
009c49c1  CMP byte ptr [RDX],0x30
009c49c4  JZ 0x009c4a6d
009c49ca  MOV RAX,qword ptr [RSP + 0x358]
009c49d2  MOV RBX,qword ptr [RSP + 0x360]
009c49da  MOV RCX,qword ptr [RSP + 0x368]
009c49e2  MOV RDI,qword ptr [RSP + 0x370]
009c49ea  MOV RSI,RDX
009c49ed  MOV R9D,0x1
009c49f3  MOV R10D,0x64
009c49f9  CALL 0x009bdfe0
009c49fe  NOP
009c4a00  TEST RBX,RBX
009c4a03  JNZ 0x009c4a56
009c4a05  TEST RAX,RAX
009c4a08  JZ 0x009c4a3f
009c4a0a  MOV RDX,qword ptr [RAX + 0x8]
009c4a0e  TEST RDX,RDX
009c4a11  JZ 0x009c4a28
009c4a13  MOV qword ptr [RSP + 0xf8],RDX
009c4a1b  MOV R12,qword ptr [RAX]
009c4a1e  XOR EAX,EAX
009c4a20  XOR ECX,ECX
009c4a22  XOR EBX,EBX
009c4a24  XOR ESI,ESI
009c4a26  JMP 0x009c4a8e
009c4a28  MOV RAX,qword ptr [RSP + 0x78]
009c4a2d  MOV RCX,qword ptr [RSP + 0x80]
009c4a35  MOV RDX,qword ptr [RSP + 0x100]
009c4a3d  JMP 0x009c4a7c
009c4a3f  MOV RAX,qword ptr [RSP + 0x78]
009c4a44  MOV RCX,qword ptr [RSP + 0x80]
009c4a4c  MOV RDX,qword ptr [RSP + 0x100]
009c4a54  JMP 0x009c4a7c
009c4a56  MOV RAX,qword ptr [RSP + 0x78]
009c4a5b  MOV RCX,qword ptr [RSP + 0x80]
009c4a63  MOV RDX,qword ptr [RSP + 0x100]
009c4a6b  JMP 0x009c4a7c
009c4a6d  MOV RAX,RDI
009c4a70  MOV RCX,RSI
009c4a73  ADD RSP,0x318
009c4a7a  POP RBP
009c4a7b  RET
009c4a7c  MOV RSI,RCX
009c4a7f  MOV RBX,RAX
009c4a82  MOV RDI,RDX
009c4a85  JMP 0x009c4a6d
009c4a87  ADD R12,0x70
009c4a8b  INC RAX
009c4a8e  MOV qword ptr [RSP + 0xa0],RCX
009c4a96  MOV qword ptr [RSP + 0x98],RBX
009c4a9e  MOV qword ptr [RSP + 0x180],RSI
009c4aa6  CMP RAX,RDX
009c4aa9  JGE 0x009c4de0
009c4aaf  LEA R13,[RSP + 0x110]
009c4ab7  MOVUPS XMM14,xmmword ptr [R12]
009c4abc  MOVUPS xmmword ptr [R13],XMM14
009c4ac1  MOVUPS XMM14,xmmword ptr [R12 + 0x10]
009c4ac7  MOVUPS xmmword ptr [R13 + 0x10],XMM14
009c4acc  MOVUPS XMM14,xmmword ptr [R12 + 0x20]
009c4ad2  MOVUPS xmmword ptr [R13 + 0x20],XMM14
009c4ad7  MOVUPS XMM14,xmmword ptr [R12 + 0x30]
009c4add  MOVUPS xmmword ptr [R13 + 0x30],XMM14
009c4ae2  MOVUPS XMM14,xmmword ptr [R12 + 0x40]
009c4ae8  MOVUPS xmmword ptr [R13 + 0x40],XMM14
009c4aed  MOVUPS XMM14,xmmword ptr [R12 + 0x50]
009c4af3  MOVUPS xmmword ptr [R13 + 0x50],XMM14
009c4af8  MOVUPS XMM14,xmmword ptr [R12 + 0x60]
009c4afe  MOVUPS xmmword ptr [R13 + 0x60],XMM14
009c4b03  CMP byte ptr [RSP + 0x130],0x0
009c4b0b  JNZ 0x009c4a87
009c4b11  MOV qword ptr [RSP + 0xf0],RAX
009c4b19  MOV qword ptr [RSP + 0x310],R12
009c4b21  MOV RAX,qword ptr [RSP + 0x120]
009c4b29  MOV RBX,qword ptr [RSP + 0x128]
009c4b31  CALL 0x00708680
009c4b36  TEST RBX,RBX
009c4b39  JNZ 0x009c4b70
009c4b3b  MOV RAX,qword ptr [RSP + 0xf0]
009c4b43  MOV RDX,qword ptr [RSP + 0xf8]
009c4b4b  MOV R12,qword ptr [RSP + 0x310]
009c4b53  MOV RCX,qword ptr [RSP + 0xa0]
009c4b5b  MOV RBX,qword ptr [RSP + 0x98]
009c4b63  MOV RSI,qword ptr [RSP + 0x180]
009c4b6b  JMP 0x009c4a87
009c4b70  MOV RAX,qword ptr [RSP + 0x110]
009c4b78  MOV RBX,qword ptr [RSP + 0x118]
009c4b80  CALL 0x009e6160
009c4b85  TEST RBX,RBX
009c4b88  JNZ 0x009c4ba7
009c4b8a  MOV RCX,qword ptr [RSP + 0xa0]
009c4b92  MOV RBX,qword ptr [RSP + 0x98]
009c4b9a  MOV RAX,qword ptr [RSP + 0x180]
009c4ba2  JMP 0x009c4dbb
009c4ba7  MOV qword ptr [RSP + 0x88],RBX
009c4baf  MOV qword ptr [RSP + 0x108],RAX
009c4bb7  MOV RCX,RAX
009c4bba  MOV RDI,RBX
009c4bbd  LEA RAX,[0xe16280]
009c4bc4  LEA RBX,[RSP + 0x2a0]
009c4bcc  CALL 0x00412ee0
009c4bd1  CMP byte ptr [RAX],0x0
009c4bd4  JZ 0x009c4bf3
009c4bd6  MOV RCX,qword ptr [RSP + 0xa0]
009c4bde  MOV RBX,qword ptr [RSP + 0x98]
009c4be6  MOV RAX,qword ptr [RSP + 0x180]
009c4bee  JMP 0x009c4dbb
009c4bf3  LEA RDX,[RSP + 0x188]
009c4bfb  MOVUPS xmmword ptr [RDX],XMM15
009c4bff  MOVUPS xmmword ptr [RDX + 0x10],XMM15
009c4c04  MOVUPS xmmword ptr [RDX + 0x20],XMM15
009c4c09  MOVUPS xmmword ptr [RDX + 0x30],XMM15
009c4c0e  MOVUPS xmmword ptr [RDX + 0x40],XMM15
009c4c13  MOV RDX,qword ptr [RSP + 0x108]
009c4c1b  MOV qword ptr [RSP + 0x188],RDX
009c4c23  MOV RDX,qword ptr [RSP + 0x88]
009c4c2b  MOV qword ptr [RSP + 0x190],RDX
009c4c33  MOV RDX,qword ptr [RSP + 0x98]
009c4c3b  INC RDX
009c4c3e  MOV qword ptr [RSP + 0xe8],RDX
009c4c46  MOV RDX,qword ptr [RSP + 0x120]
009c4c4e  MOV R12,qword ptr [RSP + 0x128]
009c4c56  MOV qword ptr [RSP + 0x198],RDX
009c4c5e  MOV qword ptr [RSP + 0x1a0],R12
009c4c66  XOR EAX,EAX
009c4c68  LEA RBX,[0xf05ed9]
009c4c6f  MOV ECX,0x9
009c4c74  MOV RDI,qword ptr [RSP + 0x358]
009c4c7c  MOV RSI,qword ptr [RSP + 0x360]
009c4c84  LEA R8,[0x1133210]
009c4c8b  MOV R9D,0x1
009c4c91  MOV R10,qword ptr [RSP + 0x378]
009c4c99  MOV R11,qword ptr [RSP + 0x380]
009c4ca1  CALL 0x0046b340
009c4ca6  MOV qword ptr [RSP + 0x1a8],RAX
009c4cae  MOV qword ptr [RSP + 0x1b0],RBX
009c4cb6  MOV RDX,qword ptr [RSP + 0x108]
009c4cbe  MOV qword ptr [RSP + 0x1b8],RDX
009c4cc6  MOV RDX,qword ptr [RSP + 0x88]
009c4cce  MOV qword ptr [RSP + 0x1c0],RDX
009c4cd6  MOV RCX,qword ptr [RSP + 0xa0]
009c4cde  MOV RBX,qword ptr [RSP + 0xe8]
009c4ce6  CMP RCX,RBX
009c4ce9  JC 0x009c4cf5
009c4ceb  MOV RAX,qword ptr [RSP + 0x180]
009c4cf3  JMP 0x009c4d0e
009c4cf5  MOV RAX,qword ptr [RSP + 0x180]
009c4cfd  MOV EDI,0x1
009c4d02  LEA RSI,[0xe960a0]
009c4d09  CALL 0x00486be0
009c4d0e  LEA RDX,[RBX + RBX*0x4]
009c4d12  SHL RDX,0x4
009c4d16  LEA RDX,[RDX + RAX*0x1]
009c4d1a  LEA RDX,[RDX + -0x50]
009c4d1e  CMP dword ptr [0x019b5f00],0x0
009c4d25  JZ 0x009c4d7e
009c4d27  MOV qword ptr [RSP + 0x2e8],RAX
009c4d2f  MOV qword ptr [RSP + 0xd0],RBX
009c4d37  MOV qword ptr [RSP + 0xc8],RCX
009c4d3f  MOV qword ptr [RSP + 0x2e0],RDX
009c4d47  LEA RAX,[0xe960a0]
009c4d4e  MOV RBX,RDX
009c4d51  LEA RCX,[RSP + 0x188]
009c4d59  CALL 0x004226a0
009c4d5e  MOV RAX,qword ptr [RSP + 0x2e8]
009c4d66  MOV RCX,qword ptr [RSP + 0xc8]
009c4d6e  MOV RDX,qword ptr [RSP + 0x2e0]
009c4d76  MOV RBX,qword ptr [RSP + 0xd0]
009c4d7e  LEA R12,[RSP + 0x188]
009c4d86  MOVUPS XMM14,xmmword ptr [R12]
009c4d8b  MOVUPS xmmword ptr [RDX],XMM14
009c4d8f  MOVUPS XMM14,xmmword ptr [R12 + 0x10]
009c4d95  MOVUPS xmmword ptr [RDX + 0x10],XMM14
009c4d9a  MOVUPS XMM14,xmmword ptr [R12 + 0x20]
009c4da0  MOVUPS xmmword ptr [RDX + 0x20],XMM14
009c4da5  MOVUPS XMM14,xmmword ptr [R12 + 0x30]
009c4dab  MOVUPS xmmword ptr [RDX + 0x30],XMM14
009c4db0  MOVUPS XMM14,xmmword ptr [R12 + 0x40]
009c4db6  MOVUPS xmmword ptr [RDX + 0x40],XMM14
009c4dbb  MOV RDX,qword ptr [RSP + 0xf8]
009c4dc3  MOV R12,qword ptr [RSP + 0x310]
009c4dcb  MOV RSI,RAX
009c4dce  MOV RAX,qword ptr [RSP + 0xf0]
009c4dd6  JMP 0x009c4a87
009c4de0  TEST RBX,RBX
009c4de3  JZ 0x009c4e82
009c4de9  LEA RAX,[RSP + 0x58]
009c4dee  LEA RBX,[0xf05ed9]
009c4df5  MOV ECX,0x9
009c4dfa  MOV RDI,qword ptr [RSP + 0x358]
009c4e02  MOV RSI,qword ptr [RSP + 0x360]
009c4e0a  LEA R8,[0x1133210]
009c4e11  MOV R9D,0x1
009c4e17  MOV R10,qword ptr [RSP + 0x378]
009c4e1f  MOV R11,qword ptr [RSP + 0x380]
009c4e27  CALL 0x0046b340
009c4e2c  MOV RCX,RAX
009c4e2f  MOV RDI,RBX
009c4e32  MOV RSI,qword ptr [RSP + 0x180]
009c4e3a  MOV R8,qword ptr [RSP + 0x98]
009c4e42  MOV R9,qword ptr [RSP + 0xa0]
009c4e4a  MOV RAX,qword ptr [RSP + 0x388]
009c4e52  MOV RBX,qword ptr [RSP + 0x390]
009c4e5a  CALL 0x009e4b60
009c4e5f  MOV qword ptr [RSP + 0x90],RBX
009c4e67  XOR ECX,ECX
009c4e69  MOV RDX,qword ptr [RSP + 0x80]
009c4e71  MOV RSI,qword ptr [RSP + 0x100]
009c4e79  MOV RDI,qword ptr [RSP + 0x78]
009c4e7e  NOP
009c4e80  JMP 0x009c4ed3
009c4e82  MOV RAX,qword ptr [RSP + 0x80]
009c4e8a  MOV RCX,qword ptr [RSP + 0x78]
009c4e8f  MOV RDX,qword ptr [RSP + 0x100]
009c4e97  MOV RBX,RAX
009c4e9a  MOV RAX,RCX
009c4e9d  MOV RCX,RBX
009c4ea0  JMP 0x009c4a7c
009c4ea5  MOV R8,qword ptr [RSP + 0x310]
009c4ead  ADD R8,0x28
009c4eb1  MOV R9,qword ptr [RSP + 0xf8]
009c4eb9  INC R9
009c4ebc  MOV RDX,RCX
009c4ebf  MOV RSI,RAX
009c4ec2  MOV RDI,RBX
009c4ec5  MOV RBX,qword ptr [RSP + 0x90]
009c4ecd  MOV RCX,R9
009c4ed0  MOV RAX,R8
009c4ed3  CMP RBX,RCX
009c4ed6  JLE 0x009c517a
009c4edc  MOV qword ptr [RSP + 0xc0],RDX
009c4ee4  MOV qword ptr [RSP + 0xf8],RCX
009c4eec  MOV qword ptr [RSP + 0xb8],RDI
009c4ef4  MOV qword ptr [RSP + 0x2d8],RSI
009c4efc  MOV qword ptr [RSP + 0x310],RAX
009c4f04  LEA RDX,[RSP + 0x110]
009c4f0c  MOVUPS XMM14,xmmword ptr [RAX]
009c4f10  MOVUPS xmmword ptr [RDX],XMM14
009c4f14  MOVUPS XMM14,xmmword ptr [RAX + 0x10]
009c4f19  MOVUPS xmmword ptr [RDX + 0x10],XMM14
009c4f1e  MOVUPS XMM14,xmmword ptr [RAX + 0x18]
009c4f23  MOVUPS xmmword ptr [RDX + 0x18],XMM14
009c4f28  MOV RCX,qword ptr [RSP + 0x120]
009c4f30  MOV RDI,qword ptr [RSP + 0x128]
009c4f38  LEA RAX,[0xe16280]
009c4f3f  LEA RBX,[RSP + 0x2a0]
009c4f47  CALL 0x00412ee0
009c4f4c  CMP byte ptr [RAX],0x0
009c4f4f  JZ 0x009c4f6e
009c4f51  MOV RBX,qword ptr [RSP + 0xb8]
009c4f59  MOV RCX,qword ptr [RSP + 0xc0]
009c4f61  MOV RAX,qword ptr [RSP + 0x2d8]
009c4f69  JMP 0x009c4ea5
009c4f6e  MOV RCX,qword ptr [RSP + 0x120]
009c4f76  MOV RDI,qword ptr [RSP + 0x128]
009c4f7e  LEA RAX,[0xe16280]
009c4f85  LEA RBX,[RSP + 0x2a0]
009c4f8d  CALL 0x00413460
009c4f92  MOV byte ptr [RAX],0x1
009c4f95  MOV RSI,qword ptr [RSP + 0x120]
009c4f9d  MOV R8,qword ptr [RSP + 0x128]
009c4fa5  MOV RAX,qword ptr [RSP + 0x358]
009c4fad  MOV RBX,qword ptr [RSP + 0x360]
009c4fb5  MOV RCX,qword ptr [RSP + 0x368]
009c4fbd  MOV RDI,qword ptr [RSP + 0x370]
009c4fc5  MOV R9,qword ptr [RSP + 0x340]
009c4fcd  MOV R10,qword ptr [RSP + 0x348]
009c4fd5  CALL 0x009c3260
009c4fda  TEST RSI,RSI
009c4fdd  JNZ 0x009c4fe5
009c4fdf  NOP
009c4fe0  TEST RBX,RBX
009c4fe3  JNZ 0x009c5040
009c4fe5  MOV RSI,qword ptr [RSP + 0x120]
009c4fed  MOV R8,qword ptr [RSP + 0x128]
009c4ff5  MOVUPS xmmword ptr [RSP],XMM15
009c4ffa  MOV qword ptr [RSP + 0x10],0x0
009c5003  MOV RAX,qword ptr [RSP + 0x358]
009c500b  MOV RBX,qword ptr [RSP + 0x360]
009c5013  MOV RCX,qword ptr [RSP + 0x368]
009c501b  MOV RDI,qword ptr [RSP + 0x370]
009c5023  MOV R9,qword ptr [RSP + 0x340]
009c502b  MOV R10,qword ptr [RSP + 0x348]
009c5033  CALL 0x009c1f20
009c5038  NOP dword ptr [RAX + RAX*0x1]
009c5040  TEST RBX,RBX
009c5043  JZ 0x009c515d
009c5049  TEST RDI,RDI
009c504c  JNZ 0x009c505e
009c504e  MOV RCX,qword ptr [RSP + 0x110]
009c5056  MOV RDI,qword ptr [RSP + 0x118]
009c505e  MOV qword ptr [RSP + 0x110],RCX
009c5066  MOV qword ptr [RSP + 0x118],RDI
009c506e  MOV qword ptr [RSP + 0x120],RAX
009c5076  MOV qword ptr [RSP + 0x128],RBX
009c507e  MOV qword ptr [RSP + 0x130],0x64
009c508a  MOV RBX,qword ptr [RSP + 0xb8]
009c5092  INC RBX
009c5095  MOV RCX,qword ptr [RSP + 0xc0]
009c509d  NOP dword ptr [RAX]
009c50a0  CMP RCX,RBX
009c50a3  JC 0x009c50af
009c50a5  MOV RAX,qword ptr [RSP + 0x2d8]
009c50ad  JMP 0x009c50c8
009c50af  MOV RAX,qword ptr [RSP + 0x2d8]
009c50b7  MOV EDI,0x1
009c50bc  LEA RSI,[0xe698a0]
009c50c3  CALL 0x00486be0
009c50c8  LEA RDX,[RBX + RBX*0x4]
009c50cc  LEA RDX,[RAX + RDX*0x8]
009c50d0  LEA RDX,[RDX + -0x28]
009c50d4  CMP dword ptr [0x019b5f00],0x0
009c50db  JZ 0x009c5134
009c50dd  MOV qword ptr [RSP + 0x2d0],RAX
009c50e5  MOV qword ptr [RSP + 0xb0],RBX
009c50ed  MOV qword ptr [RSP + 0xa8],RCX
009c50f5  MOV qword ptr [RSP + 0x2f8],RDX
009c50fd  LEA RAX,[0xe698a0]
009c5104  MOV RBX,RDX
009c5107  LEA RCX,[RSP + 0x110]
009c510f  CALL 0x004226a0
009c5114  MOV RAX,qword ptr [RSP + 0x2d0]
009c511c  MOV RCX,qword ptr [RSP + 0xa8]
009c5124  MOV RDX,qword ptr [RSP + 0x2f8]
009c512c  MOV RBX,qword ptr [RSP + 0xb0]
009c5134  LEA R8,[RSP + 0x110]
009c513c  MOVUPS XMM14,xmmword ptr [R8]
009c5140  MOVUPS xmmword ptr [RDX],XMM14
009c5144  MOVUPS XMM14,xmmword ptr [R8 + 0x10]
009c5149  MOVUPS xmmword ptr [RDX + 0x10],XMM14
009c514e  MOVUPS XMM14,xmmword ptr [R8 + 0x18]
009c5153  MOVUPS xmmword ptr [RDX + 0x18],XMM14
009c5158  JMP 0x009c4ea5
009c515d  MOV RCX,qword ptr [RSP + 0xc0]
009c5165  MOV RBX,qword ptr [RSP + 0xb8]
009c516d  MOV RAX,qword ptr [RSP + 0x2d8]
009c5175  JMP 0x009c4ea5
009c517a  MOV RAX,RDX
009c517d  MOV RCX,RDI
009c5180  MOV RDX,RSI
009c5183  JMP 0x009c4e97
009c5188  MOV qword ptr [RSP + 0x30],RAX
009c518d  MOV qword ptr [RSP + 0x38],RBX
009c5192  MOV qword ptr [RSP + 0x40],RCX
009c5197  MOV qword ptr [RSP + 0x48],RDI
009c519c  MOV qword ptr [RSP + 0x50],RSI
009c51a1  MOV qword ptr [RSP + 0x58],R8
009c51a6  MOV qword ptr [RSP + 0x60],R9
009c51ab  MOV qword ptr [RSP + 0x68],R10
009c51b0  MOV qword ptr [RSP + 0x70],R11
009c51b5  CALL 0x0048a280
009c51ba  MOV RAX,qword ptr [RSP + 0x30]
009c51bf  MOV RBX,qword ptr [RSP + 0x38]
009c51c4  MOV RCX,qword ptr [RSP + 0x40]
009c51c9  MOV RDI,qword ptr [RSP + 0x48]
009c51ce  MOV RSI,qword ptr [RSP + 0x50]
009c51d3  MOV R8,qword ptr [RSP + 0x58]
009c51d8  MOV R9,qword ptr [RSP + 0x60]
009c51dd  MOV R10,qword ptr [RSP + 0x68]
009c51e2  MOV R11,qword ptr [RSP + 0x70]
009c51e7  JMP 0x009c45a0
