; mv-daemon/provider.(*Cloud115Provider).StartQrLoginWithType
009b9260  LEA R12,[RSP + -0x440]
009b9268  CMP R12,qword ptr [R14 + 0x10]
009b926c  JBE 0x009ba121
009b9272  PUSH RBP
009b9273  MOV RBP,RSP
009b9276  SUB RSP,0x4b8
009b927d  MOV qword ptr [RSP + 0x4d0],RBX
009b9285  MOVUPS xmmword ptr [RSP + 0x4a8],XMM15
009b928e  MOV byte ptr [RSP + 0x47],0x0
009b9293  MOV qword ptr [RSP + 0xa0],0x0
009b929f  MOVUPS xmmword ptr [RSP + 0x80],XMM15
009b92a8  MOV RAX,RBX
009b92ab  MOV RBX,RCX
009b92ae  CALL 0x009b8ca0
009b92b3  MOV qword ptr [RSP + 0xe0],RAX
009b92bb  MOV qword ptr [RSP + 0x70],RBX
009b92c0  CALL 0x009b8920
009b92c5  MOV qword ptr [RSP + 0xa8],RAX
009b92cd  MOV qword ptr [RSP + 0x48],RBX
009b92d2  LEA RCX,[RSP + 0x178]
009b92da  MOVUPS xmmword ptr [RCX],XMM15
009b92de  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009b92e3  MOV RAX,qword ptr [0x0196ddb0]
009b92ea  MOV RBX,qword ptr [0x0196ddb8]
009b92f1  CALL 0x00481ee0
009b92f6  LEA RCX,[0xdd29c0]
009b92fd  MOV qword ptr [RSP + 0x178],RCX
009b9305  MOV qword ptr [RSP + 0x180],RAX
009b930d  MOV RAX,qword ptr [RSP + 0xe0]
009b9315  MOV RBX,qword ptr [RSP + 0x70]
009b931a  CALL 0x00481ee0
009b931f  LEA RCX,[0xdd29c0]
009b9326  MOV qword ptr [RSP + 0x188],RCX
009b932e  MOV qword ptr [RSP + 0x190],RAX
009b9336  LEA RAX,[0xf25343]
009b933d  MOV EBX,0x17
009b9342  LEA RCX,[RSP + 0x178]
009b934a  MOV EDI,0x2
009b934f  MOV RSI,RDI
009b9352  CALL 0x005055a0
009b9357  NOP
009b9358  LEA RCX,[0xefaba3]
009b935f  MOV EDI,0x3
009b9364  MOV RSI,RAX
009b9367  MOV R8,RBX
009b936a  XOR R9D,R9D
009b936d  XOR R10D,R10D
009b9370  LEA RAX,[0x113fde8]
009b9377  LEA RBX,[0x19b5220]
009b937e  NOP
009b9380  CALL 0x006acc00
009b9385  TEST RBX,RBX
009b9388  JNZ 0x009b9557
009b938e  MOV qword ptr [RSP + 0xc0],RAX
009b9396  LEA RAX,[RSP + 0x420]
009b939e  MOVUPS xmmword ptr [RAX],XMM15
009b93a2  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009b93a7  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009b93ac  LEA RAX,[RSP + 0x318]
009b93b4  MOV ECX,0x4
009b93b9  MOVUPS xmmword ptr [RAX],XMM15
009b93bd  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009b93c2  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009b93c7  MOVUPS xmmword ptr [RAX + 0x30],XMM15
009b93cc  ADD RAX,0x40
009b93d0  DEC ECX
009b93d2  JNZ 0x009b93b9
009b93d4  MOVUPS xmmword ptr [RAX + -0x8],XMM15
009b93d9  MOV RAX,-0x7f7f7f7f7f7f7f80
009b93e3  MOV qword ptr [RSP + 0x318],RAX
009b93eb  LEA RAX,[RSP + 0x318]
009b93f3  MOV qword ptr [RSP + 0x430],RAX
009b93fb  NOP dword ptr [RAX + RAX*0x1]
009b9400  CALL 0x00485080
009b9405  MOV qword ptr [RSP + 0x428],RAX
009b940d  LEA RAX,[0xe16200]
009b9414  LEA RBX,[RSP + 0x420]
009b941c  LEA RCX,[0xefe659]
009b9423  MOV EDI,0x6
009b9428  CALL 0x00413460
009b942d  MOV qword ptr [RAX + 0x8],0x12
009b9435  CMP dword ptr [0x019b5f00],0x0
009b943c  JZ 0x009b9449
009b943e  MOV RDX,qword ptr [RAX]
009b9441  CALL 0x0048bbe0
009b9446  MOV qword ptr [R11],RDX
009b9449  LEA RDX,[0xf1d949]
009b9450  MOV qword ptr [RAX],RDX
009b9453  LEA RAX,[0xe16200]
009b945a  LEA RBX,[RSP + 0x420]
009b9462  LEA RCX,[0xeffe26]
009b9469  MOV EDI,0x7
009b946e  CALL 0x00413460
009b9473  MOV qword ptr [RAX + 0x8],0x13
009b947b  CMP dword ptr [0x019b5f00],0x0
009b9482  JZ 0x009b948f
009b9484  MOV RDX,qword ptr [RAX]
009b9487  CALL 0x0048bbe0
009b948c  MOV qword ptr [R11],RDX
009b948f  LEA RDX,[0xf1f31d]
009b9496  MOV qword ptr [RAX],RDX
009b9499  MOV RAX,qword ptr [RSP + 0xe0]
009b94a1  MOV RBX,qword ptr [RSP + 0x70]
009b94a6  MOV RCX,qword ptr [RSP + 0xa8]
009b94ae  MOV RDI,qword ptr [RSP + 0x48]
009b94b3  CALL 0x009b8fc0
009b94b8  MOV qword ptr [RSP + 0x78],RBX
009b94bd  MOV qword ptr [RSP + 0x1a8],RAX
009b94c5  LEA RAX,[0xe16200]
009b94cc  LEA RBX,[RSP + 0x420]
009b94d4  LEA RCX,[0xf0a13f]
009b94db  MOV EDI,0xa
009b94e0  CALL 0x00413460
009b94e5  MOV RDX,qword ptr [RSP + 0x78]
009b94ea  MOV qword ptr [RAX + 0x8],RDX
009b94ee  CMP dword ptr [0x019b5f00],0x0
009b94f5  JNZ 0x009b9502
009b94f7  MOV RSI,qword ptr [RSP + 0x1a8]
009b94ff  NOP
009b9500  JMP 0x009b9519
009b9502  MOV RDX,qword ptr [RAX]
009b9505  CALL 0x0048bc00
009b950a  MOV RSI,qword ptr [RSP + 0x1a8]
009b9512  MOV qword ptr [R11],RSI
009b9515  MOV qword ptr [R11 + 0x8],RDX
009b9519  MOV qword ptr [RAX],RSI
009b951c  LEA RCX,[RSP + 0x118]
009b9524  MOVUPS xmmword ptr [RCX],XMM15
009b9528  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009b952d  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009b9532  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009b9537  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009b953c  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009b9541  LEA RAX,[0xe16200]
009b9548  LEA RBX,[RSP + 0x420]
009b9550  CALL 0x004225e0
009b9555  JMP 0x009b9594
009b9557  MOV qword ptr [RSP + 0xa0],0x0
009b9563  MOV qword ptr [RSP + 0x80],RBX
009b956b  MOV qword ptr [RSP + 0x88],RCX
009b9573  MOV RAX,qword ptr [RSP + 0xa0]
009b957b  ADD RSP,0x4b8
009b9582  POP RBP
009b9583  RET
009b9584  MOV qword ptr [RAX],RDX
009b9587  LEA RAX,[RSP + 0x118]
009b958f  CALL 0x00422640
009b9594  MOV RCX,qword ptr [RSP + 0x118]
009b959c  NOP dword ptr [RAX]
009b95a0  TEST RCX,RCX
009b95a3  JZ 0x009b96a5
009b95a9  MOV RAX,qword ptr [RCX]
009b95ac  MOV RBX,qword ptr [RCX + 0x8]
009b95b0  MOV RCX,qword ptr [RSP + 0x120]
009b95b8  MOV RDX,qword ptr [RCX + 0x8]
009b95bc  MOV qword ptr [RSP + 0x58],RDX
009b95c1  MOV RCX,qword ptr [RCX]
009b95c4  MOV qword ptr [RSP + 0xb8],RCX
009b95cc  MOV RCX,qword ptr [RSP + 0xc0]
009b95d4  MOV RCX,qword ptr [RCX + 0x38]
009b95d8  MOV qword ptr [RSP + 0x1a0],RCX
009b95e0  NOP
009b95e1  CALL 0x00640c00
009b95e6  MOV qword ptr [RSP + 0x1a8],RAX
009b95ee  MOV qword ptr [RSP + 0x78],RBX
009b95f3  LEA RAX,[0xddc380]
009b95fa  CALL 0x00421f00
009b95ff  MOV RCX,qword ptr [RSP + 0x58]
009b9604  MOV qword ptr [RAX + 0x8],RCX
009b9608  CMP dword ptr [0x019b5f00],0x0
009b960f  JNZ 0x009b9620
009b9611  MOV RDX,qword ptr [RSP + 0xb8]
009b9619  JMP 0x009b9630
009b9620  CALL 0x0048bbe0
009b9625  MOV RDX,qword ptr [RSP + 0xb8]
009b962d  MOV qword ptr [R11],RDX
009b9630  MOV qword ptr [RSP + 0x198],RAX
009b9638  MOV qword ptr [RAX],RDX
009b963b  LEA RAX,[0xe91b20]
009b9642  MOV RBX,qword ptr [RSP + 0x1a0]
009b964a  MOV RCX,qword ptr [RSP + 0x1a8]
009b9652  MOV RDI,qword ptr [RSP + 0x78]
009b9657  CALL 0x00413460
009b965c  MOV qword ptr [RAX + 0x8],0x1
009b9664  MOV qword ptr [RAX + 0x10],0x1
009b966c  CMP dword ptr [0x019b5f00],0x0
009b9673  JNZ 0x009b9685
009b9675  MOV RDX,qword ptr [RSP + 0x198]
009b967d  NOP dword ptr [RAX]
009b9680  JMP 0x009b9584
009b9685  MOV RCX,qword ptr [RAX]
009b9688  CALL 0x0048bc00
009b968d  MOV RDX,qword ptr [RSP + 0x198]
009b9695  MOV qword ptr [R11],RDX
009b9698  MOV qword ptr [R11 + 0x8],RCX
009b969c  NOP dword ptr [RAX]
009b96a0  JMP 0x009b9584
009b96a5  MOV RAX,qword ptr [0x0196ccc0]
009b96ac  MOV RBX,qword ptr [RSP + 0xc0]
009b96b4  CALL 0x0066f720
009b96b9  NOP dword ptr [RAX]
009b96c0  TEST RBX,RBX
009b96c3  JNZ 0x009b975b
009b96c9  MOV qword ptr [RSP + 0x98],RAX
009b96d1  MOV RCX,qword ptr [RAX + 0x40]
009b96d5  TEST byte ptr [RCX],AL
009b96d7  MOV RDX,qword ptr [RAX + 0x48]
009b96db  LEA RBX,[0x9ba1a0]
009b96e2  MOV qword ptr [RSP + 0x300],RBX
009b96ea  MOV qword ptr [RSP + 0x308],RCX
009b96f2  MOV qword ptr [RSP + 0x310],RDX
009b96fa  LEA RCX,[RSP + 0x300]
009b9702  MOV qword ptr [RSP + 0x4a8],RCX
009b970a  MOV byte ptr [RSP + 0x47],0x1
009b970f  LEA RAX,[0xe32d00]
009b9716  CALL 0x00421f00
009b971b  MOV qword ptr [RSP + 0x4a0],RAX
009b9723  MOV RCX,qword ptr [RSP + 0x98]
009b972b  MOV RDX,qword ptr [RCX + 0x40]
009b972f  MOV RCX,qword ptr [RCX + 0x48]
009b9733  MOV qword ptr [RSP + 0xc8],RCX
009b973b  NOP dword ptr [RAX + RAX*0x1]
009b9740  TEST RDX,RDX
009b9743  JZ 0x009b9788
009b9745  MOV RBX,qword ptr [RDX + 0x8]
009b9749  MOV RSI,qword ptr [0x019765a0]
009b9750  MOV RDI,qword ptr [RSI]
009b9753  MOV EDX,dword ptr [RDX + 0x10]
009b9756  JMP 0x009ba0bf
009b975b  MOV qword ptr [RSP + 0xa0],0x0
009b9767  MOV qword ptr [RSP + 0x80],RBX
009b976f  MOV qword ptr [RSP + 0x88],RCX
009b9777  MOV RAX,qword ptr [RSP + 0xa0]
009b977f  ADD RSP,0x4b8
009b9786  POP RBP
009b9787  RET
009b9788  MOV qword ptr [RSP + 0x1a8],RDX
009b9790  LEA RAX,[0xeba560]
009b9797  CALL 0x00421f00
009b979c  MOV RCX,qword ptr [RSP + 0x1a8]
009b97a4  MOV qword ptr [RAX],RCX
009b97a7  CMP dword ptr [0x019b5f00],0x0
009b97ae  JNZ 0x009b97ba
009b97b0  MOV RDX,qword ptr [RSP + 0xc8]
009b97b8  JMP 0x009b97ca
009b97ba  CALL 0x0048bbe0
009b97bf  MOV RDX,qword ptr [RSP + 0xc8]
009b97c7  MOV qword ptr [R11],RDX
009b97ca  MOV qword ptr [RAX + 0x8],RDX
009b97ce  LEA RBX,[0xdc63e0]
009b97d5  MOV RCX,qword ptr [RSP + 0x4a0]
009b97dd  NOP dword ptr [RAX]
009b97e0  CALL 0x0053f680
009b97e5  TEST RAX,RAX
009b97e8  JNZ 0x009b9b61
009b97ee  MOV RCX,qword ptr [RSP + 0x4a0]
009b97f6  CMP qword ptr [RCX],0x1
009b97fa  NOP word ptr [RAX + RAX*0x1]
009b9800  JNZ 0x009b9aec
009b9806  MOV RDX,qword ptr [RCX + 0x30]
009b980a  MOV qword ptr [RSP + 0xd0],RDX
009b9812  MOV RCX,qword ptr [RCX + 0x38]
009b9816  MOV qword ptr [RSP + 0x60],RCX
009b981b  LEA RCX,[RSP + 0xe8]
009b9823  MOVUPS xmmword ptr [RCX],XMM15
009b9827  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009b982c  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009b9831  MOV RAX,qword ptr [0x0196ddb0]
009b9838  MOV RBX,qword ptr [0x0196ddb8]
009b983f  NOP
009b9840  CALL 0x00481ee0
009b9845  LEA RCX,[0xdd29c0]
009b984c  MOV qword ptr [RSP + 0xe8],RCX
009b9854  MOV qword ptr [RSP + 0xf0],RAX
009b985c  MOV RAX,qword ptr [RSP + 0xe0]
009b9864  MOV RBX,qword ptr [RSP + 0x70]
009b9869  CALL 0x00481ee0
009b986e  LEA RCX,[0xdd29c0]
009b9875  MOV qword ptr [RSP + 0xf8],RCX
009b987d  MOV qword ptr [RSP + 0x100],RAX
009b9885  MOV RCX,qword ptr [RSP + 0x4a0]
009b988d  MOV RAX,qword ptr [RCX + 0x8]
009b9891  MOV RBX,qword ptr [RCX + 0x10]
009b9895  CALL 0x00481ee0
009b989a  LEA RCX,[0xdd29c0]
009b98a1  MOV qword ptr [RSP + 0x108],RCX
009b98a9  MOV qword ptr [RSP + 0x110],RAX
009b98b1  LEA RAX,[0xf2fde5]
009b98b8  MOV EBX,0x1f
009b98bd  LEA RCX,[RSP + 0xe8]
009b98c5  MOV EDI,0x3
009b98ca  MOV RSI,RDI
009b98cd  CALL 0x005055a0
009b98d2  NOP
009b98d3  LEA RCX,[0xefaba3]
009b98da  MOV EDI,0x3
009b98df  MOV RSI,RAX
009b98e2  MOV R8,RBX
009b98e5  XOR R9D,R9D
009b98e8  XOR R10D,R10D
009b98eb  LEA RAX,[0x113fde8]
009b98f2  LEA RBX,[0x19b5220]
009b98f9  CALL 0x006acc00
009b98fe  NOP
009b9900  TEST RBX,RBX
009b9903  JNZ 0x009b9ad5
009b9909  MOV qword ptr [RSP + 0x90],RAX
009b9911  LEA RAX,[RSP + 0x2d0]
009b9919  MOVUPS xmmword ptr [RAX],XMM15
009b991d  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009b9922  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009b9927  LEA RAX,[RSP + 0x1c8]
009b992f  MOV ECX,0x4
009b9934  MOVUPS xmmword ptr [RAX],XMM15
009b9938  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009b993d  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009b9942  MOVUPS xmmword ptr [RAX + 0x30],XMM15
009b9947  ADD RAX,0x40
009b994b  DEC ECX
009b994d  JNZ 0x009b9934
009b994f  MOVUPS xmmword ptr [RAX + -0x8],XMM15
009b9954  MOV RAX,-0x7f7f7f7f7f7f7f80
009b995e  MOV qword ptr [RSP + 0x1c8],RAX
009b9966  LEA RAX,[RSP + 0x1c8]
009b996e  MOV qword ptr [RSP + 0x2e0],RAX
009b9976  CALL 0x00485080
009b997b  MOV qword ptr [RSP + 0x2d8],RAX
009b9983  LEA RAX,[0xe16200]
009b998a  LEA RBX,[RSP + 0x2d0]
009b9992  LEA RCX,[0xefe659]
009b9999  MOV EDI,0x6
009b999e  NOP
009b99a0  CALL 0x00413460
009b99a5  MOV qword ptr [RAX + 0x8],0x12
009b99ad  CMP dword ptr [0x019b5f00],0x0
009b99b4  JZ 0x009b99c1
009b99b6  MOV RDX,qword ptr [RAX]
009b99b9  CALL 0x0048bbe0
009b99be  MOV qword ptr [R11],RDX
009b99c1  LEA RDX,[0xf1d949]
009b99c8  MOV qword ptr [RAX],RDX
009b99cb  LEA RAX,[0xe16200]
009b99d2  LEA RBX,[RSP + 0x2d0]
009b99da  LEA RCX,[0xeffe26]
009b99e1  MOV EDI,0x7
009b99e6  CALL 0x00413460
009b99eb  MOV qword ptr [RAX + 0x8],0x13
009b99f3  CMP dword ptr [0x019b5f00],0x0
009b99fa  JZ 0x009b9a08
009b99fc  MOV RDX,qword ptr [RAX]
009b99ff  NOP
009b9a00  CALL 0x0048bbe0
009b9a05  MOV qword ptr [R11],RDX
009b9a08  LEA RDX,[0xf1f31d]
009b9a0f  MOV qword ptr [RAX],RDX
009b9a12  MOV RAX,qword ptr [RSP + 0xe0]
009b9a1a  MOV RBX,qword ptr [RSP + 0x70]
009b9a1f  MOV RCX,qword ptr [RSP + 0xa8]
009b9a27  MOV RDI,qword ptr [RSP + 0x48]
009b9a2c  CALL 0x009b8fc0
009b9a31  MOV qword ptr [RSP + 0x78],RBX
009b9a36  MOV qword ptr [RSP + 0x1a8],RAX
009b9a3e  LEA RAX,[0xe16200]
009b9a45  LEA RBX,[RSP + 0x2d0]
009b9a4d  LEA RCX,[0xf0a13f]
009b9a54  MOV EDI,0xa
009b9a59  CALL 0x00413460
009b9a5e  MOV RDX,qword ptr [RSP + 0x78]
009b9a63  MOV qword ptr [RAX + 0x8],RDX
009b9a67  CMP dword ptr [0x019b5f00],0x0
009b9a6e  JNZ 0x009b9a7a
009b9a70  MOV RSI,qword ptr [RSP + 0x1a8]
009b9a78  JMP 0x009b9a94
009b9a7a  MOV RDX,qword ptr [RAX]
009b9a7d  NOP dword ptr [RAX]
009b9a80  CALL 0x0048bc00
009b9a85  MOV RSI,qword ptr [RSP + 0x1a8]
009b9a8d  MOV qword ptr [R11],RSI
009b9a90  MOV qword ptr [R11 + 0x8],RDX
009b9a94  MOV qword ptr [RAX],RSI
009b9a97  LEA RCX,[RSP + 0x118]
009b9a9f  MOVUPS xmmword ptr [RCX],XMM15
009b9aa3  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009b9aa8  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009b9aad  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009b9ab2  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009b9ab7  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009b9abc  LEA RAX,[0xe16200]
009b9ac3  LEA RBX,[RSP + 0x2d0]
009b9acb  CALL 0x004225e0
009b9ad0  JMP 0x009b9df3
009b9ad5  MOV EAX,0x1
009b9ada  MOV RCX,qword ptr [RSP + 0xd0]
009b9ae2  MOV RDX,qword ptr [RSP + 0x60]
009b9ae7  JMP 0x009b9bb0
009b9aec  LEA RAX,[0xe21740]
009b9af3  CALL 0x00421f00
009b9af8  MOV qword ptr [RAX + 0x8],0x1a
009b9b00  LEA RCX,[0xf294c2]
009b9b07  MOV qword ptr [RAX],RCX
009b9b0a  MOV qword ptr [RSP + 0xa0],0x0
009b9b16  LEA RCX,[0x1139800]
009b9b1d  MOV qword ptr [RSP + 0x80],RCX
009b9b25  MOV qword ptr [RSP + 0x88],RAX
009b9b2d  MOV byte ptr [RSP + 0x47],0x0
009b9b32  MOV RDX,qword ptr [RSP + 0x4a8]
009b9b3a  MOV RCX,qword ptr [RDX]
009b9b3d  CALL RCX
009b9b3f  MOV RBX,qword ptr [RSP + 0x80]
009b9b47  MOV RAX,qword ptr [RSP + 0xa0]
009b9b4f  MOV RCX,qword ptr [RSP + 0x88]
009b9b57  ADD RSP,0x4b8
009b9b5e  POP RBP
009b9b5f  NOP
009b9b60  RET
009b9b61  MOV qword ptr [RSP + 0xa0],0x0
009b9b6d  MOV qword ptr [RSP + 0x80],RAX
009b9b75  MOV qword ptr [RSP + 0x88],RBX
009b9b7d  MOV byte ptr [RSP + 0x47],0x0
009b9b82  MOV RDX,qword ptr [RSP + 0x4a8]
009b9b8a  MOV RAX,qword ptr [RDX]
009b9b8d  CALL RAX
009b9b8f  MOV RBX,qword ptr [RSP + 0x80]
009b9b97  MOV RAX,qword ptr [RSP + 0xa0]
009b9b9f  MOV RCX,qword ptr [RSP + 0x88]
009b9ba7  ADD RSP,0x4b8
009b9bae  POP RBP
009b9baf  RET
009b9bb0  MOV byte ptr [RSP + 0x46],AL
009b9bb4  MOV qword ptr [RSP + 0xd0],RCX
009b9bbc  MOV qword ptr [RSP + 0x60],RDX
009b9bc1  LEA RCX,[RSP + 0x450]
009b9bc9  MOVUPS xmmword ptr [RCX],XMM15
009b9bcd  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009b9bd2  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009b9bd7  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009b9bdc  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009b9be1  MOV RCX,qword ptr [RSP + 0x4a0]
009b9be9  MOV RAX,qword ptr [RCX + 0x8]
009b9bed  MOV RBX,qword ptr [RCX + 0x10]
009b9bf1  CALL 0x00481ee0
009b9bf6  LEA RCX,[0xdd29c0]
009b9bfd  MOV qword ptr [RSP + 0x450],RCX
009b9c05  MOV qword ptr [RSP + 0x458],RAX
009b9c0d  MOV RCX,qword ptr [RSP + 0x4a0]
009b9c15  MOV RAX,qword ptr [RCX + 0x20]
009b9c19  MOV RBX,qword ptr [RCX + 0x28]
009b9c1d  NOP dword ptr [RAX]
009b9c20  CALL 0x00481ee0
009b9c25  LEA RCX,[0xdd29c0]
009b9c2c  MOV qword ptr [RSP + 0x460],RCX
009b9c34  MOV qword ptr [RSP + 0x468],RAX
009b9c3c  MOV RCX,qword ptr [RSP + 0x4a0]
009b9c44  MOV RAX,qword ptr [RCX + 0x18]
009b9c48  CALL 0x00481e60
009b9c4d  LEA RCX,[0xdd2b80]
009b9c54  MOV qword ptr [RSP + 0x470],RCX
009b9c5c  MOV qword ptr [RSP + 0x478],RAX
009b9c64  MOV RAX,qword ptr [RSP + 0xa8]
009b9c6c  MOV RBX,qword ptr [RSP + 0x48]
009b9c71  CALL 0x00481ee0
009b9c76  LEA RCX,[0xdd29c0]
009b9c7d  MOV qword ptr [RSP + 0x480],RCX
009b9c85  MOV qword ptr [RSP + 0x488],RAX
009b9c8d  MOV RAX,qword ptr [RSP + 0xe0]
009b9c95  MOV RBX,qword ptr [RSP + 0x70]
009b9c9a  CALL 0x00481ee0
009b9c9f  LEA RCX,[0xdd29c0]
009b9ca6  MOV qword ptr [RSP + 0x490],RCX
009b9cae  MOV qword ptr [RSP + 0x498],RAX
009b9cb6  LEA RAX,[0xf1577b]
009b9cbd  MOV EBX,0xe
009b9cc2  LEA RCX,[RSP + 0x450]
009b9cca  MOV EDI,0x5
009b9ccf  MOV RSI,RDI
009b9cd2  CALL 0x005055a0
009b9cd7  MOV qword ptr [RSP + 0x68],RBX
009b9cdc  MOV qword ptr [RSP + 0xd8],RAX
009b9ce4  LEA RAX,[0xe69960]
009b9ceb  CALL 0x00421f00
009b9cf0  MOV RCX,qword ptr [RSP + 0x68]
009b9cf5  MOV qword ptr [RAX + 0x28],RCX
009b9cf9  CMP dword ptr [0x019b5f00],0x0
009b9d00  JNZ 0x009b9d14
009b9d02  MOV RSI,qword ptr [RSP + 0xd8]
009b9d0a  MOV RDI,qword ptr [RSP + 0xd0]
009b9d12  JMP 0x009b9d30
009b9d14  CALL 0x0048bc00
009b9d19  MOV RSI,qword ptr [RSP + 0xd8]
009b9d21  MOV qword ptr [R11],RSI
009b9d24  MOV RDI,qword ptr [RSP + 0xd0]
009b9d2c  MOV qword ptr [R11 + 0x8],RDI
009b9d30  MOV qword ptr [RAX + 0x20],RSI
009b9d34  MOV RSI,qword ptr [RSP + 0x60]
009b9d39  MOV qword ptr [RAX + 0x18],RSI
009b9d3d  MOV qword ptr [RAX + 0x10],RDI
009b9d41  MOV RSI,qword ptr [RSP + 0x4a0]
009b9d49  MOV RDI,qword ptr [RSI + 0x38]
009b9d4d  MOV RSI,qword ptr [RSI + 0x30]
009b9d51  MOV qword ptr [RAX + 0x8],RDI
009b9d55  CMP dword ptr [0x019b5f00],0x0
009b9d5c  JZ 0x009b9d68
009b9d5e  NOP
009b9d60  CALL 0x0048bbe0
009b9d65  MOV qword ptr [R11],RSI
009b9d68  MOV qword ptr [RAX],RSI
009b9d6b  MOV qword ptr [RSP + 0xa0],RAX
009b9d73  MOVUPS xmmword ptr [RSP + 0x80],XMM15
009b9d7c  MOVZX ESI,byte ptr [RSP + 0x46]
009b9d81  TEST SIL,0x2
009b9d85  JZ 0x009b9da7
009b9d87  AND ESI,0xfffffffd
009b9d8a  MOV byte ptr [RSP + 0x46],SIL
009b9d8f  MOV byte ptr [RSP + 0x47],SIL
009b9d94  MOV RDX,qword ptr [RSP + 0x4b0]
009b9d9c  MOV RAX,qword ptr [RDX]
009b9d9f  NOP
009b9da0  CALL RAX
009b9da2  MOVZX ESI,byte ptr [RSP + 0x46]
009b9da7  TEST SIL,0x1
009b9dab  JZ 0x009b9dc2
009b9dad  AND ESI,0xfffffffe
009b9db0  MOV byte ptr [RSP + 0x47],SIL
009b9db5  MOV RDX,qword ptr [RSP + 0x4a8]
009b9dbd  MOV RAX,qword ptr [RDX]
009b9dc0  CALL RAX
009b9dc2  MOV RBX,qword ptr [RSP + 0x80]
009b9dca  MOV RAX,qword ptr [RSP + 0xa0]
009b9dd2  MOV RCX,qword ptr [RSP + 0x88]
009b9dda  ADD RSP,0x4b8
009b9de1  POP RBP
009b9de2  RET
009b9de3  MOV qword ptr [RAX],RDX
009b9de6  LEA RAX,[RSP + 0x118]
009b9dee  CALL 0x00422640
009b9df3  MOV RCX,qword ptr [RSP + 0x118]
009b9dfb  NOP dword ptr [RAX + RAX*0x1]
009b9e00  TEST RCX,RCX
009b9e03  JZ 0x009b9f05
009b9e09  MOV RAX,qword ptr [RCX]
009b9e0c  MOV RBX,qword ptr [RCX + 0x8]
009b9e10  MOV RCX,qword ptr [RSP + 0x120]
009b9e18  MOV RDX,qword ptr [RCX + 0x8]
009b9e1c  MOV qword ptr [RSP + 0x50],RDX
009b9e21  MOV RCX,qword ptr [RCX]
009b9e24  MOV qword ptr [RSP + 0xb0],RCX
009b9e2c  MOV RCX,qword ptr [RSP + 0x90]
009b9e34  MOV RCX,qword ptr [RCX + 0x38]
009b9e38  MOV qword ptr [RSP + 0x1a0],RCX
009b9e40  NOP
009b9e41  CALL 0x00640c00
009b9e46  MOV qword ptr [RSP + 0x1a8],RAX
009b9e4e  MOV qword ptr [RSP + 0x78],RBX
009b9e53  LEA RAX,[0xddc380]
009b9e5a  CALL 0x00421f00
009b9e5f  MOV RCX,qword ptr [RSP + 0x50]
009b9e64  MOV qword ptr [RAX + 0x8],RCX
009b9e68  CMP dword ptr [0x019b5f00],0x0
009b9e6f  JNZ 0x009b9e80
009b9e71  MOV RDX,qword ptr [RSP + 0xb0]
009b9e79  JMP 0x009b9e90
009b9e80  CALL 0x0048bbe0
009b9e85  MOV RDX,qword ptr [RSP + 0xb0]
009b9e8d  MOV qword ptr [R11],RDX
009b9e90  MOV qword ptr [RSP + 0x198],RAX
009b9e98  MOV qword ptr [RAX],RDX
009b9e9b  LEA RAX,[0xe91b20]
009b9ea2  MOV RBX,qword ptr [RSP + 0x1a0]
009b9eaa  MOV RCX,qword ptr [RSP + 0x1a8]
009b9eb2  MOV RDI,qword ptr [RSP + 0x78]
009b9eb7  CALL 0x00413460
009b9ebc  MOV qword ptr [RAX + 0x8],0x1
009b9ec4  MOV qword ptr [RAX + 0x10],0x1
009b9ecc  CMP dword ptr [0x019b5f00],0x0
009b9ed3  JNZ 0x009b9ee5
009b9ed5  MOV RDX,qword ptr [RSP + 0x198]
009b9edd  NOP dword ptr [RAX]
009b9ee0  JMP 0x009b9de3
009b9ee5  MOV RCX,qword ptr [RAX]
009b9ee8  CALL 0x0048bc00
009b9eed  MOV RDX,qword ptr [RSP + 0x198]
009b9ef5  MOV qword ptr [R11],RDX
009b9ef8  MOV qword ptr [R11 + 0x8],RCX
009b9efc  NOP dword ptr [RAX]
009b9f00  JMP 0x009b9de3
009b9f05  MOV RAX,qword ptr [0x0196ccc0]
009b9f0c  MOV RBX,qword ptr [RSP + 0x90]
009b9f14  CALL 0x0066f720
009b9f19  TEST RBX,RBX
009b9f1c  JNZ 0x009b9f7f
009b9f1e  MOV RCX,qword ptr [RAX + 0x40]
009b9f22  TEST byte ptr [RCX],AL
009b9f24  MOV RDX,qword ptr [RAX + 0x48]
009b9f28  LEA RSI,[0x9ba160]
009b9f2f  MOV qword ptr [RSP + 0x1b0],RSI
009b9f37  MOV qword ptr [RSP + 0x1b8],RCX
009b9f3f  MOV qword ptr [RSP + 0x1c0],RDX
009b9f47  LEA RCX,[RSP + 0x1b0]
009b9f4f  MOV qword ptr [RSP + 0x4b0],RCX
009b9f57  MOV byte ptr [RSP + 0x47],0x3
009b9f5c  MOV RCX,qword ptr [RAX + 0x40]
009b9f60  MOV RBX,qword ptr [RAX + 0x48]
009b9f64  TEST RCX,RCX
009b9f67  JZ 0x009b9f9f
009b9f69  MOV RDX,qword ptr [RCX + 0x8]
009b9f6d  MOV RSI,qword ptr [0x019765c0]
009b9f74  MOV RDI,qword ptr [RSI]
009b9f77  MOV ECX,dword ptr [RCX + 0x10]
009b9f7a  JMP 0x009ba071
009b9f7f  MOV EAX,0x1
009b9f84  MOV RCX,qword ptr [RSP + 0x60]
009b9f89  MOV RDX,qword ptr [RSP + 0xd0]
009b9f91  MOV RBX,RCX
009b9f94  MOV RCX,RDX
009b9f97  MOV RDX,RBX
009b9f9a  JMP 0x009b9bb0
009b9f9f  MOV RAX,RCX
009b9fa2  CALL 0x004991a0
009b9fa7  TEST RDI,RDI
009b9faa  JZ 0x009b9fc0
009b9fac  MOV RBX,qword ptr [RSP + 0x60]
009b9fb1  MOV RAX,qword ptr [RSP + 0xd0]
009b9fb9  JMP 0x009ba061
009b9fc0  CMP RBX,0x8
009b9fc4  JLE 0x009ba054
009b9fca  CMP byte ptr [RAX],0x89
009b9fcd  JNZ 0x009ba045
009b9fcf  CMP byte ptr [RAX + 0x1],0x50
009b9fd3  JNZ 0x009ba036
009b9fd5  CMP byte ptr [RAX + 0x2],0x4e
009b9fd9  JNZ 0x009ba027
009b9fdb  CMP byte ptr [RAX + 0x3],0x47
009b9fdf  NOP
009b9fe0  JZ 0x009b9ff1
009b9fe2  MOV RBX,qword ptr [RSP + 0x60]
009b9fe7  MOV RAX,qword ptr [RSP + 0xd0]
009b9fef  JMP 0x009ba061
009b9ff1  MOV RDX,qword ptr [0x01990430]
009b9ff8  MOV RDI,RCX
009b9ffb  MOV RCX,RBX
009b9ffe  MOV RBX,RAX
009ba001  MOV RAX,RDX
009ba004  CALL 0x0052ad20
009ba009  MOV ECX,0x16
009ba00e  MOV RDI,RAX
009ba011  MOV RSI,RBX
009ba014  XOR EAX,EAX
009ba016  LEA RBX,[0xf23a5a]
009ba01d  NOP dword ptr [RAX]
009ba020  CALL 0x0046b1e0
009ba025  JMP 0x009ba061
009ba027  MOV RBX,qword ptr [RSP + 0x60]
009ba02c  MOV RAX,qword ptr [RSP + 0xd0]
009ba034  JMP 0x009ba061
009ba036  MOV RBX,qword ptr [RSP + 0x60]
009ba03b  MOV RAX,qword ptr [RSP + 0xd0]
009ba043  JMP 0x009ba061
009ba045  MOV RBX,qword ptr [RSP + 0x60]
009ba04a  MOV RAX,qword ptr [RSP + 0xd0]
009ba052  JMP 0x009ba061
009ba054  MOV RBX,qword ptr [RSP + 0x60]
009ba059  MOV RAX,qword ptr [RSP + 0xd0]
009ba061  MOV RCX,RBX
009ba064  MOV RDX,RAX
009ba067  MOV EAX,0x3
009ba06c  JMP 0x009b9f91
009ba071  MOV R8,RCX
009ba074  AND RCX,RDI
009ba077  SHL RCX,0x4
009ba07b  MOV R9,qword ptr [RSI + RCX*0x1 + 0x8]
009ba080  CMP R9,RDX
009ba083  JZ 0x009ba0b5
009ba085  LEA RCX,[R8 + 0x1]
009ba089  TEST R9,R9
009ba08c  JNZ 0x009ba071
009ba08e  MOV qword ptr [RSP + 0x1a8],RBX
009ba096  LEA RAX,[0x19765c0]
009ba09d  MOV RBX,RDX
009ba0a0  CALL 0x0041e320
009ba0a5  MOV RBX,qword ptr [RSP + 0x1a8]
009ba0ad  MOV RCX,RAX
009ba0b0  JMP 0x009b9f9f
009ba0b5  MOV RCX,qword ptr [RSI + RCX*0x1 + 0x10]
009ba0ba  JMP 0x009b9f9f
009ba0bf  MOV R8,RDX
009ba0c2  AND RDX,RDI
009ba0c5  SHL RDX,0x4
009ba0c9  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
009ba0ce  CMP R9,RBX
009ba0d1  JZ 0x009ba0f0
009ba0d3  LEA RDX,[R8 + 0x1]
009ba0d7  TEST R9,R9
009ba0da  JNZ 0x009ba0bf
009ba0dc  LEA RAX,[0x19765a0]
009ba0e3  CALL 0x0041e320
009ba0e8  MOV RDX,RAX
009ba0eb  JMP 0x009b9788
009ba0f0  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
009ba0f5  JMP 0x009b9788
009ba121  MOV qword ptr [RSP + 0x8],RAX
009ba126  MOV qword ptr [RSP + 0x10],RBX
009ba12b  MOV qword ptr [RSP + 0x18],RCX
009ba130  CALL 0x0048a280
009ba135  MOV RAX,qword ptr [RSP + 0x8]
009ba13a  MOV RBX,qword ptr [RSP + 0x10]
009ba13f  MOV RCX,qword ptr [RSP + 0x18]
009ba144  JMP 0x009b9260
