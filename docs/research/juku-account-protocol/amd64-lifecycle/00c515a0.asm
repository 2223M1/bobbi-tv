; main.handle115OfflineAdd
00c515a0  LEA R12,[RSP + -0x4f0]
00c515a8  CMP R12,qword ptr [R14 + 0x10]
00c515ac  JBE 0x00c5390f
00c515b2  PUSH RBP
00c515b3  MOV RBP,RSP
00c515b6  SUB RSP,0x568
00c515bd  MOV qword ptr [RSP + 0x588],RCX
00c515c5  MOV qword ptr [RSP + 0x580],RBX
00c515cd  MOV qword ptr [RSP + 0x578],RAX
00c515d5  MOV RCX,qword ptr [RAX + 0x18]
00c515d9  MOV RAX,RBX
00c515dc  CALL RCX
00c515de  MOV qword ptr [RSP + 0x1d8],RAX
00c515e6  NOP
00c515e7  LEA RAX,[0xf10b4b]
00c515ee  MOV EBX,0xc
00c515f3  CALL 0x00640c00
00c515f8  MOV qword ptr [RSP + 0x218],RAX
00c51600  MOV qword ptr [RSP + 0x108],RBX
00c51608  LEA RAX,[0xddc380]
00c5160f  CALL 0x00421f00
00c51614  MOV qword ptr [RSP + 0x210],RAX
00c5161c  MOV qword ptr [RAX + 0x8],0x10
00c51624  LEA RCX,[0xf195fc]
00c5162b  MOV qword ptr [RAX],RCX
00c5162e  LEA RAX,[0xe91b20]
00c51635  MOV RBX,qword ptr [RSP + 0x1d8]
00c5163d  MOV RCX,qword ptr [RSP + 0x218]
00c51645  MOV RDI,qword ptr [RSP + 0x108]
00c5164d  CALL 0x00413460
00c51652  MOV qword ptr [RAX + 0x8],0x1
00c5165a  MOV qword ptr [RAX + 0x10],0x1
00c51662  CMP dword ptr [0x019b5f00],0x0
00c51669  JNZ 0x00c51675
00c5166b  MOV RDX,qword ptr [RSP + 0x210]
00c51673  JMP 0x00c5168c
00c51675  MOV RCX,qword ptr [RAX]
00c51678  CALL 0x0048bc00
00c5167d  MOV RDX,qword ptr [RSP + 0x210]
00c51685  MOV qword ptr [R11],RDX
00c51688  MOV qword ptr [R11 + 0x8],RCX
00c5168c  MOV qword ptr [RAX],RDX
00c5168f  MOV RAX,qword ptr [RSP + 0x588]
00c51697  CALL 0x00c4bd40
00c5169c  MOV qword ptr [RSP + 0x150],RAX
00c516a4  MOV qword ptr [RSP + 0x90],RBX
00c516ac  MOV RCX,qword ptr [RSP + 0x588]
00c516b4  MOV RAX,qword ptr [RCX + 0x10]
00c516b8  CALL 0x005bb0e0
00c516bd  MOV RBX,RAX
00c516c0  LEA RCX,[0xefc947]
00c516c7  MOV EDI,0x5
00c516cc  LEA RAX,[0xe9bd40]
00c516d3  CALL 0x00412ee0
00c516d8  CMP qword ptr [RAX + 0x8],0x0
00c516dd  JNZ 0x00c516e6
00c516df  XOR R8D,R8D
00c516e2  XOR EDX,EDX
00c516e4  JMP 0x00c516f0
00c516e6  MOV RDX,qword ptr [RAX]
00c516e9  MOV R8,qword ptr [RDX + 0x8]
00c516ed  MOV RDX,qword ptr [RDX]
00c516f0  TEST R8,R8
00c516f3  JNZ 0x00c51720
00c516f5  MOV RAX,qword ptr [0x019900b0]
00c516fc  NOP dword ptr [RAX]
00c51700  TEST RAX,RAX
00c51703  JZ 0x00c51720
00c51705  LEA RBX,[0xf02951]
00c5170c  MOV ECX,0x8
00c51711  CALL 0x00a63de0
00c51716  MOV R8,RBX
00c51719  MOV RDX,RAX
00c5171c  NOP dword ptr [RAX]
00c51720  TEST R8,R8
00c51723  JZ 0x00c51ac5
00c51729  MOV qword ptr [RSP + 0x98],R8
00c51731  MOV qword ptr [RSP + 0x158],RDX
00c51739  MOV RBX,qword ptr [0x019900d0]
00c51740  LEA RAX,[0xe17280]
00c51747  LEA RCX,[0xf02951]
00c5174e  MOV EDI,0x8
00c51753  CALL 0x004131a0
00c51758  MOV RDX,qword ptr [RAX + 0x8]
00c5175c  NOP dword ptr [RAX]
00c51760  TEST BL,BL
00c51762  JZ 0x00c51a96
00c51768  MOV R8,qword ptr [RAX]
00c5176b  LEA R9,[0x11476d0]
00c51772  CMP R8,R9
00c51775  JNZ 0x00c51a67
00c5177b  MOV qword ptr [RSP + 0x1b8],RDX
00c51783  MOV RCX,qword ptr [RSP + 0x588]
00c5178b  MOV RAX,qword ptr [RCX + 0x10]
00c5178f  CALL 0x005bb0e0
00c51794  MOV RBX,RAX
00c51797  LEA RCX,[0xefaba6]
00c5179e  MOV EDI,0x3
00c517a3  LEA RAX,[0xe9bd40]
00c517aa  CALL 0x00412ee0
00c517af  CMP qword ptr [RAX + 0x8],0x0
00c517b4  JNZ 0x00c517bc
00c517b6  XOR EDX,EDX
00c517b8  XOR ECX,ECX
00c517ba  JMP 0x00c517c6
00c517bc  MOV RCX,qword ptr [RAX]
00c517bf  MOV RDX,qword ptr [RCX + 0x8]
00c517c3  MOV RCX,qword ptr [RCX]
00c517c6  MOV qword ptr [RSP + 0x70],RDX
00c517cb  MOV qword ptr [RSP + 0x130],RCX
00c517d3  MOV RCX,qword ptr [RSP + 0x588]
00c517db  MOV RAX,qword ptr [RCX + 0x10]
00c517df  NOP
00c517e0  CALL 0x005bb0e0
00c517e5  MOV RBX,RAX
00c517e8  LEA RCX,[0xefc938]
00c517ef  MOV EDI,0x5
00c517f4  LEA RAX,[0xe9bd40]
00c517fb  NOP dword ptr [RAX + RAX*0x1]
00c51800  CALL 0x00412ee0
00c51805  CMP qword ptr [RAX + 0x8],0x0
00c5180a  JNZ 0x00c51812
00c5180c  XOR EDX,EDX
00c5180e  XOR ECX,ECX
00c51810  JMP 0x00c5181c
00c51812  MOV RCX,qword ptr [RAX]
00c51815  MOV RDX,qword ptr [RCX + 0x8]
00c51819  MOV RCX,qword ptr [RCX]
00c5181c  MOV qword ptr [RSP + 0x68],RDX
00c51821  MOV qword ptr [RSP + 0x128],RCX
00c51829  MOV RCX,qword ptr [RSP + 0x588]
00c51831  MOV RAX,qword ptr [RCX + 0x10]
00c51835  CALL 0x005bb0e0
00c5183a  MOV RBX,RAX
00c5183d  LEA RCX,[0xf05a2c]
00c51844  MOV EDI,0x9
00c51849  LEA RAX,[0xe9bd40]
00c51850  CALL 0x00412ee0
00c51855  CMP qword ptr [RAX + 0x8],0x0
00c5185a  JNZ 0x00c51862
00c5185c  XOR EDX,EDX
00c5185e  XOR ECX,ECX
00c51860  JMP 0x00c5186c
00c51862  MOV RCX,qword ptr [RAX]
00c51865  MOV RDX,qword ptr [RCX + 0x8]
00c51869  MOV RCX,qword ptr [RCX]
00c5186c  MOV qword ptr [RSP + 0x60],RDX
00c51871  MOV qword ptr [RSP + 0x120],RCX
00c51879  MOV RCX,qword ptr [RSP + 0x588]
00c51881  MOV RAX,qword ptr [RCX + 0x10]
00c51885  CALL 0x005bb0e0
00c5188a  MOV RBX,RAX
00c5188d  LEA RCX,[0xefe2b1]
00c51894  MOV EDI,0x6
00c51899  LEA RAX,[0xe9bd40]
00c518a0  CALL 0x00412ee0
00c518a5  CMP qword ptr [RAX + 0x8],0x0
00c518aa  JNZ 0x00c518b2
00c518ac  XOR EDX,EDX
00c518ae  XOR ECX,ECX
00c518b0  JMP 0x00c518bc
00c518b2  MOV RCX,qword ptr [RAX]
00c518b5  MOV RDX,qword ptr [RCX + 0x8]
00c518b9  MOV RCX,qword ptr [RCX]
00c518bc  MOV qword ptr [RSP + 0x58],RDX
00c518c1  MOV qword ptr [RSP + 0x118],RCX
00c518c9  MOV RCX,qword ptr [RSP + 0x588]
00c518d1  MOV RAX,qword ptr [RCX + 0x10]
00c518d5  CALL 0x005bb0e0
00c518da  MOV RBX,RAX
00c518dd  LEA RCX,[0xf02a61]
00c518e4  MOV EDI,0x8
00c518e9  LEA RAX,[0xe9bd40]
00c518f0  CALL 0x00412ee0
00c518f5  CMP qword ptr [RAX + 0x8],0x0
00c518fa  JNZ 0x00c51902
00c518fc  XOR ESI,ESI
00c518fe  XOR EDX,EDX
00c51900  JMP 0x00c5190c
00c51902  MOV RDX,qword ptr [RAX]
00c51905  MOV RSI,qword ptr [RDX + 0x8]
00c51909  MOV RDX,qword ptr [RDX]
00c5190c  MOV R8,qword ptr [RSP + 0x588]
00c51914  CMP qword ptr [R8 + 0x8],0x4
00c51919  JNZ 0x00c51a1e
00c5191f  MOV R9,qword ptr [R8]
00c51922  CMP dword ptr [R9],0x54534f50
00c51929  JNZ 0x00c519d5
00c5192f  MOV R9,qword ptr [RSP + 0x70]
00c51934  TEST R9,R9
00c51937  JNZ 0x00c51991
00c51939  MOV qword ptr [RSP + 0x50],RSI
00c5193e  MOV qword ptr [RSP + 0x110],RDX
00c51946  LEA RAX,[0xe9c440]
00c5194d  CALL 0x00421f00
00c51952  MOV qword ptr [RSP + 0x560],RAX
00c5195a  MOV RCX,qword ptr [RSP + 0x588]
00c51962  MOV RDX,qword ptr [RCX + 0x40]
00c51966  MOV RCX,qword ptr [RCX + 0x48]
00c5196a  MOV qword ptr [RSP + 0x1a0],RCX
00c51972  TEST RDX,RDX
00c51975  JZ 0x00c5370f
00c5197b  MOV RBX,qword ptr [RDX + 0x8]
00c5197f  MOV RSI,qword ptr [0x01974040]
00c51986  MOV RDI,qword ptr [RSI]
00c51989  MOV EDX,dword ptr [RDX + 0x10]
00c5198c  JMP 0x00c538ce
00c51991  MOV RAX,qword ptr [RSP + 0x68]
00c51996  MOV RCX,qword ptr [RSP + 0x128]
00c5199e  MOV RBX,qword ptr [RSP + 0x130]
00c519a6  MOV RDI,qword ptr [RSP + 0x98]
00c519ae  MOV R8,qword ptr [RSP + 0x158]
00c519b6  MOV R10,qword ptr [RSP + 0x58]
00c519bb  MOV R11,qword ptr [RSP + 0x60]
00c519c0  MOV R12,qword ptr [RSP + 0x118]
00c519c8  MOV R13,qword ptr [RSP + 0x120]
00c519d0  JMP 0x00c51af4
00c519d5  MOV RAX,qword ptr [RSP + 0x68]
00c519da  MOV RCX,qword ptr [RSP + 0x128]
00c519e2  MOV R9,qword ptr [RSP + 0x70]
00c519e7  MOV RBX,qword ptr [RSP + 0x130]
00c519ef  MOV RDI,qword ptr [RSP + 0x98]
00c519f7  MOV R8,qword ptr [RSP + 0x158]
00c519ff  MOV R10,qword ptr [RSP + 0x58]
00c51a04  MOV R11,qword ptr [RSP + 0x60]
00c51a09  MOV R12,qword ptr [RSP + 0x118]
00c51a11  MOV R13,qword ptr [RSP + 0x120]
00c51a19  JMP 0x00c51af4
00c51a1e  MOV RAX,qword ptr [RSP + 0x68]
00c51a23  MOV RCX,qword ptr [RSP + 0x128]
00c51a2b  MOV R9,qword ptr [RSP + 0x70]
00c51a30  MOV RBX,qword ptr [RSP + 0x130]
00c51a38  MOV RDI,qword ptr [RSP + 0x98]
00c51a40  MOV R8,qword ptr [RSP + 0x158]
00c51a48  MOV R10,qword ptr [RSP + 0x58]
00c51a4d  MOV R11,qword ptr [RSP + 0x60]
00c51a52  MOV R12,qword ptr [RSP + 0x118]
00c51a5a  MOV R13,qword ptr [RSP + 0x120]
00c51a62  JMP 0x00c51af4
00c51a67  MOV RAX,qword ptr [RSP + 0x578]
00c51a6f  MOV RBX,qword ptr [RSP + 0x580]
00c51a77  LEA RCX,[0xf3a315]
00c51a7e  MOV EDI,0x27
00c51a83  MOV ESI,0x1f4
00c51a88  CALL 0x00c484c0
00c51a8d  ADD RSP,0x568
00c51a94  POP RBP
00c51a95  RET
00c51a96  MOV RAX,qword ptr [RSP + 0x578]
00c51a9e  MOV RBX,qword ptr [RSP + 0x580]
00c51aa6  LEA RCX,[0xf2d163]
00c51aad  MOV EDI,0x1d
00c51ab2  MOV ESI,0x1f4
00c51ab7  CALL 0x00c484c0
00c51abc  ADD RSP,0x568
00c51ac3  POP RBP
00c51ac4  RET
00c51ac5  MOV RAX,qword ptr [RSP + 0x578]
00c51acd  MOV RBX,qword ptr [RSP + 0x580]
00c51ad5  LEA RCX,[0xf3daf3]
00c51adc  MOV EDI,0x2a
00c51ae1  MOV ESI,0x191
00c51ae6  CALL 0x00c484c0
00c51aeb  ADD RSP,0x568
00c51af2  POP RBP
00c51af3  RET
00c51af4  MOV qword ptr [RSP + 0x80],R10
00c51afc  MOV qword ptr [RSP + 0x140],R12
00c51b04  MOV qword ptr [RSP + 0xa0],RAX
00c51b0c  MOV qword ptr [RSP + 0x160],RCX
00c51b14  MOV qword ptr [RSP + 0x78],R11
00c51b19  MOV qword ptr [RSP + 0x98],RDI
00c51b21  MOV qword ptr [RSP + 0x178],RDX
00c51b29  MOV qword ptr [RSP + 0xb0],RSI
00c51b31  MOV qword ptr [RSP + 0x158],R8
00c51b39  MOV qword ptr [RSP + 0x138],R13
00c51b41  MOV RDI,RAX
00c51b44  MOV RAX,RBX
00c51b47  MOV RBX,R9
00c51b4a  CALL 0x00a09760
00c51b4f  TEST RBX,RBX
00c51b52  JZ 0x00c52606
00c51b58  MOV qword ptr [RSP + 0xe8],R8
00c51b60  MOV qword ptr [RSP + 0x1c0],RSI
00c51b68  MOV qword ptr [RSP + 0x88],RDI
00c51b70  MOV qword ptr [RSP + 0x148],RCX
00c51b78  MOV qword ptr [RSP + 0xf8],RBX
00c51b80  MOV qword ptr [RSP + 0x1e8],RAX
00c51b88  MOV RDX,qword ptr [0x01990200]
00c51b8f  TEST RDX,RDX
00c51b92  JZ 0x00c51f15
00c51b98  MOV RCX,RBX
00c51b9b  MOV RDI,qword ptr [RSP + 0x1b8]
00c51ba3  MOV RSI,qword ptr [RSP + 0x158]
00c51bab  MOV R8,qword ptr [RSP + 0x98]
00c51bb3  MOV RBX,RAX
00c51bb6  MOV RAX,RDX
00c51bb9  CALL 0x00a142e0
00c51bbe  NOP
00c51bc0  TEST RAX,RAX
00c51bc3  JZ 0x00c51bcf
00c51bc5  MOV RCX,qword ptr [RSP + 0xe8]
00c51bcd  JMP 0x00c51c10
00c51bcf  MOV RCX,qword ptr [RSP + 0xe8]
00c51bd7  TEST RCX,RCX
00c51bda  JZ 0x00c51c10
00c51bdc  MOV RAX,qword ptr [0x01990200]
00c51be3  MOV RBX,qword ptr [RSP + 0x1c0]
00c51beb  MOV RDI,qword ptr [RSP + 0x1b8]
00c51bf3  MOV RSI,qword ptr [RSP + 0x158]
00c51bfb  MOV R8,qword ptr [RSP + 0x98]
00c51c03  CALL 0x00a142e0
00c51c08  MOV RCX,qword ptr [RSP + 0xe8]
00c51c10  TEST RAX,RAX
00c51c13  JZ 0x00c51f05
00c51c19  CMP qword ptr [RAX + 0xb8],0x2
00c51c21  JNZ 0x00c51f05
00c51c27  MOV qword ptr [RSP + 0x1f0],RAX
00c51c2f  LEA RCX,[RSP + 0x4e0]
00c51c37  MOVUPS xmmword ptr [RCX],XMM15
00c51c3b  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c51c40  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00c51c45  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00c51c4a  MOV RAX,qword ptr [RSP + 0x1e8]
00c51c52  MOV RBX,qword ptr [RSP + 0xf8]
00c51c5a  CALL 0x00481ee0
00c51c5f  LEA RCX,[0xdd29c0]
00c51c66  MOV qword ptr [RSP + 0x4e0],RCX
00c51c6e  MOV qword ptr [RSP + 0x4e8],RAX
00c51c76  MOV RCX,qword ptr [RSP + 0x1f0]
00c51c7e  MOV RAX,qword ptr [RCX + 0x60]
00c51c82  MOV RBX,qword ptr [RCX + 0x68]
00c51c86  CALL 0x00481ee0
00c51c8b  LEA RCX,[0xdd29c0]
00c51c92  MOV qword ptr [RSP + 0x4f0],RCX
00c51c9a  MOV qword ptr [RSP + 0x4f8],RAX
00c51ca2  MOV RCX,qword ptr [RSP + 0x1f0]
00c51caa  MOV RAX,qword ptr [RCX + 0x70]
00c51cae  MOV RBX,qword ptr [RCX + 0x78]
00c51cb2  CALL 0x00481ee0
00c51cb7  LEA RCX,[0xdd29c0]
00c51cbe  MOV qword ptr [RSP + 0x500],RCX
00c51cc6  MOV qword ptr [RSP + 0x508],RAX
00c51cce  MOV RCX,qword ptr [RSP + 0x1f0]
00c51cd6  MOVZX ECX,byte ptr [RCX + 0x98]
00c51cdd  LEA RDX,[0xdd2dc0]
00c51ce4  MOV qword ptr [RSP + 0x510],RDX
00c51cec  LEA RDX,[0x115e2c0]
00c51cf3  LEA RCX,[RDX + RCX*0x8]
00c51cf7  MOV qword ptr [RSP + 0x518],RCX
00c51cff  LEA RCX,[0xc539a0]
00c51d06  MOV qword ptr [RSP + 0x530],RCX
00c51d0e  MOV qword ptr [RSP + 0x540],0x59
00c51d1a  LEA RCX,[0xf5cbe6]
00c51d21  MOV qword ptr [RSP + 0x538],RCX
00c51d29  MOV qword ptr [RSP + 0x550],0x4
00c51d35  MOV qword ptr [RSP + 0x558],0x4
00c51d41  LEA RCX,[RSP + 0x4e0]
00c51d49  MOV qword ptr [RSP + 0x548],RCX
00c51d51  MOV RAX,qword ptr [0x01990148]
00c51d58  XOR EBX,EBX
00c51d5a  MOV ECX,0x2
00c51d5f  LEA RDI,[RSP + 0x530]
00c51d67  CALL 0x0054d540
00c51d6c  MOV RCX,qword ptr [RSP + 0x1f0]
00c51d74  CMP byte ptr [RCX + 0x98],0x0
00c51d7b  JZ 0x00c51d89
00c51d7d  XOR R11D,R11D
00c51d80  XOR EDX,EDX
00c51d82  XOR ESI,ESI
00c51d84  JMP 0x00c51ec2
00c51d89  CMP qword ptr [RCX + 0x78],0x0
00c51d8e  JNZ 0x00c51da5
00c51d90  CMP qword ptr [RCX + 0x68],0x0
00c51d95  JNZ 0x00c51da5
00c51d97  XOR R11D,R11D
00c51d9a  XOR EDX,EDX
00c51d9c  XOR ESI,ESI
00c51d9e  NOP
00c51da0  JMP 0x00c51ec2
00c51da5  MOV RDX,qword ptr [RSP + 0x90]
00c51dad  MOV qword ptr [RSP + 0x528],RDX
00c51db5  MOV RDX,qword ptr [RSP + 0x150]
00c51dbd  MOV qword ptr [RSP + 0x520],RDX
00c51dc5  MOV RBX,qword ptr [RCX + 0x60]
00c51dc9  MOV RDX,qword ptr [RCX + 0x68]
00c51dcd  MOV RDI,qword ptr [RCX + 0x70]
00c51dd1  MOV RSI,qword ptr [RCX + 0x78]
00c51dd5  LEA R10,[RSP + 0x520]
00c51ddd  MOV qword ptr [RSP],R10
00c51de1  MOV qword ptr [RSP + 0x8],0x1
00c51dea  MOV qword ptr [RSP + 0x10],0x1
00c51df3  MOV RAX,qword ptr [RSP + 0x1b8]
00c51dfb  MOV RCX,RDX
00c51dfe  MOV R8,qword ptr [RSP + 0x158]
00c51e06  MOV R9,qword ptr [RSP + 0x98]
00c51e0e  CALL 0x00a11c60
00c51e13  TEST RAX,RAX
00c51e16  JZ 0x00c51eb0
00c51e1c  MOV RDX,qword ptr [RAX + 0x10]
00c51e20  MOV RSI,qword ptr [RAX + 0x8]
00c51e24  TEST RDX,RDX
00c51e27  JZ 0x00c51e9f
00c51e29  MOV RDI,qword ptr [RSP + 0x1f0]
00c51e31  MOV R8,qword ptr [RDI + 0x88]
00c51e38  MOV R9,qword ptr [RDI + 0x80]
00c51e3f  NOP
00c51e40  TEST R8,R8
00c51e43  JNZ 0x00c51e4d
00c51e45  MOV R8,qword ptr [RAX + 0x48]
00c51e49  MOV R9,qword ptr [RAX + 0x40]
00c51e4d  MOV R10,qword ptr [RDI + 0x90]
00c51e54  TEST R10,R10
00c51e57  JG 0x00c51e5d
00c51e59  MOV R10,qword ptr [RAX + 0x50]
00c51e5d  MOV R11,qword ptr [RAX + 0x18]
00c51e61  MOV qword ptr [RDI + 0x88],R8
00c51e68  CMP dword ptr [0x019b5f00],0x0
00c51e6f  JZ 0x00c51e8f
00c51e71  MOV R8,qword ptr [RDI + 0x80]
00c51e78  MOV RAX,R11
00c51e7b  NOP dword ptr [RAX + RAX*0x1]
00c51e80  CALL 0x0048bc00
00c51e85  MOV qword ptr [R11],R9
00c51e88  MOV qword ptr [R11 + 0x8],R8
00c51e8c  MOV R11,RAX
00c51e8f  MOV qword ptr [RDI + 0x80],R9
00c51e96  MOV qword ptr [RDI + 0x90],R10
00c51e9d  JMP 0x00c51ebf
00c51e9f  MOV RDI,qword ptr [RSP + 0x1f0]
00c51ea7  XOR EDX,EDX
00c51ea9  XOR ESI,ESI
00c51eab  XOR R11D,R11D
00c51eae  JMP 0x00c51ebf
00c51eb0  MOV RDI,qword ptr [RSP + 0x1f0]
00c51eb8  XOR EDX,EDX
00c51eba  XOR ESI,ESI
00c51ebc  XOR R11D,R11D
00c51ebf  MOV RCX,RDI
00c51ec2  MOV qword ptr [RSP + 0x1a8],RSI
00c51eca  MOV qword ptr [RSP + 0xd8],RDX
00c51ed2  MOV qword ptr [RSP + 0x1d0],R11
00c51eda  MOV RDI,qword ptr [RSP + 0x578]
00c51ee2  TEST RDI,RDI
00c51ee5  JZ 0x00c5305d
00c51eeb  MOV RBX,qword ptr [RDI + 0x8]
00c51eef  MOV R8,qword ptr [0x01974060]
00c51ef6  MOV R9,qword ptr [R8]
00c51ef9  MOV EDI,dword ptr [RDI + 0x10]
00c51efc  NOP dword ptr [RAX]
00c51f00  JMP 0x00c536d3
00c51f05  MOV RAX,qword ptr [RSP + 0x1e8]
00c51f0d  MOV RBX,qword ptr [RSP + 0xf8]
00c51f15  MOV RCX,RBX
00c51f18  MOV RDI,qword ptr [RSP + 0x178]
00c51f20  MOV RSI,qword ptr [RSP + 0xb0]
00c51f28  MOV R8,qword ptr [RSP + 0x158]
00c51f30  MOV R9,qword ptr [RSP + 0x98]
00c51f38  MOV RBX,RAX
00c51f3b  MOV RAX,qword ptr [RSP + 0x1b8]
00c51f43  CALL 0x00a0bcc0
00c51f48  TEST RBX,RBX
00c51f4b  JNZ 0x00c52526
00c51f51  MOV qword ptr [RSP + 0x170],RAX
00c51f59  MOV RCX,qword ptr [RAX + 0x8]
00c51f5d  MOV RDX,qword ptr [RAX]
00c51f60  TEST RCX,RCX
00c51f63  MOV RSI,qword ptr [RSP + 0xe8]
00c51f6b  CMOVZ RCX,RSI
00c51f6f  MOV qword ptr [RSP + 0xa8],RCX
00c51f77  MOV RSI,qword ptr [RSP + 0x1c0]
00c51f7f  CMOVZ RDX,RSI
00c51f83  MOV qword ptr [RSP + 0x168],RDX
00c51f8b  CMP qword ptr [0x01990200],0x0
00c51f93  JZ 0x00c52086
00c51f99  LEA RBX,[RSP + 0x3a8]
00c51fa1  MOV ESI,0x3
00c51fa6  MOVUPS xmmword ptr [RBX],XMM15
00c51faa  MOVUPS xmmword ptr [RBX + 0x10],XMM15
00c51faf  MOVUPS xmmword ptr [RBX + 0x20],XMM15
00c51fb4  MOVUPS xmmword ptr [RBX + 0x30],XMM15
00c51fb9  ADD RBX,0x40
00c51fbd  NOP dword ptr [RAX]
00c51fc0  DEC ESI
00c51fc2  JNZ 0x00c51fa6
00c51fc4  MOVUPS xmmword ptr [RBX + -0x8],XMM15
00c51fc9  MOV RSI,qword ptr [RSP + 0xf8]
00c51fd1  MOV qword ptr [RSP + 0x3b0],RSI
00c51fd9  MOV RDI,qword ptr [RSP + 0x1e8]
00c51fe1  MOV qword ptr [RSP + 0x3a8],RDI
00c51fe9  MOV qword ptr [RSP + 0x3c0],RSI
00c51ff1  MOV qword ptr [RSP + 0x3b8],RDI
00c51ff9  MOV qword ptr [RSP + 0x3d0],RCX
00c52001  MOV qword ptr [RSP + 0x3c8],RDX
00c52009  MOV RCX,qword ptr [RSP + 0xa0]
00c52011  MOV qword ptr [RSP + 0x3e0],RCX
00c52019  MOV RCX,qword ptr [RSP + 0x160]
00c52021  MOV qword ptr [RSP + 0x3d8],RCX
00c52029  MOV RCX,qword ptr [RSP + 0x78]
00c5202e  MOV qword ptr [RSP + 0x3f0],RCX
00c52036  MOV RCX,qword ptr [RSP + 0x138]
00c5203e  MOV qword ptr [RSP + 0x3e8],RCX
00c52046  MOV RCX,qword ptr [RSP + 0x80]
00c5204e  MOV qword ptr [RSP + 0x400],RCX
00c52056  MOV RCX,qword ptr [RSP + 0x140]
00c5205e  MOV qword ptr [RSP + 0x3f8],RCX
00c52066  MOV qword ptr [RSP + 0x460],0x0
00c52072  MOV RAX,qword ptr [0x01990200]
00c52079  LEA RBX,[RSP + 0x3a8]
00c52081  CALL 0x00a13b00
00c52086  MOV EAX,0x11e1a300
00c5208b  CALL 0x00488400
00c52090  MOV RAX,qword ptr [RSP + 0x1b8]
00c52098  MOV RBX,qword ptr [RSP + 0x168]
00c520a0  MOV RCX,qword ptr [RSP + 0xa8]
00c520a8  MOV RDI,qword ptr [RSP + 0x1e8]
00c520b0  MOV RSI,qword ptr [RSP + 0xf8]
00c520b8  MOV R8,qword ptr [RSP + 0x158]
00c520c0  MOV R9,qword ptr [RSP + 0x98]
00c520c8  CALL 0x00a10500
00c520cd  TEST RBX,RBX
00c520d0  JZ 0x00c520e0
00c520d2  MOV RAX,qword ptr [RSP + 0x170]
00c520da  JMP 0x00c524f7
00c520e0  TEST RAX,RAX
00c520e3  JZ 0x00c524ef
00c520e9  CMP qword ptr [RAX + 0x40],0x2
00c520ee  JZ 0x00c52109
00c520f0  CMP qword ptr [RAX + 0x70],0x0
00c520f5  JZ 0x00c524f7
00c520fb  CMP qword ptr [RAX + 0x80],0x0
00c52103  JZ 0x00c524f7
00c52109  MOV qword ptr [RSP + 0x208],RAX
00c52111  MOV RDX,qword ptr [RSP + 0x90]
00c52119  MOV qword ptr [RSP + 0x528],RDX
00c52121  MOV RDX,qword ptr [RSP + 0x150]
00c52129  MOV qword ptr [RSP + 0x520],RDX
00c52131  MOV RBX,qword ptr [RAX + 0x68]
00c52135  MOV RCX,qword ptr [RAX + 0x70]
00c52139  MOV RDI,qword ptr [RAX + 0x78]
00c5213d  MOV RSI,qword ptr [RAX + 0x80]
00c52144  LEA RDX,[RSP + 0x520]
00c5214c  MOV qword ptr [RSP],RDX
00c52150  MOV qword ptr [RSP + 0x8],0x1
00c52159  MOV qword ptr [RSP + 0x10],0x1
00c52162  MOV RAX,qword ptr [RSP + 0x1b8]
00c5216a  MOV R8,qword ptr [RSP + 0x158]
00c52172  MOV R9,qword ptr [RSP + 0x98]
00c5217a  CALL 0x00a11c60
00c5217f  NOP
00c52180  TEST RBX,RBX
00c52183  JNZ 0x00c524e5
00c52189  TEST RAX,RAX
00c5218c  JZ 0x00c524e5
00c52192  MOV RDX,qword ptr [RSP + 0x208]
00c5219a  MOV RSI,qword ptr [RDX + 0x68]
00c5219e  MOV RDI,qword ptr [RDX + 0x70]
00c521a2  MOV R8,qword ptr [RDX + 0x80]
00c521a9  MOV R9,qword ptr [RDX + 0x78]
00c521ad  MOV R10,qword ptr [RDX + 0x18]
00c521b1  MOV R11,qword ptr [RDX + 0x10]
00c521b5  MOV RDX,qword ptr [RDX + 0x20]
00c521b9  CMP byte ptr [RAX],0x0
00c521bc  JZ 0x00c521ca
00c521be  XOR R13D,R13D
00c521c1  MOV R12,RDI
00c521c4  XOR ECX,ECX
00c521c6  XOR EDI,EDI
00c521c8  JMP 0x00c5221d
00c521ca  MOV R12,qword ptr [RAX + 0x28]
00c521ce  TEST R12,R12
00c521d1  JZ 0x00c521e2
00c521d3  MOV RSI,qword ptr [RAX + 0x20]
00c521d7  MOV R8,qword ptr [RAX + 0x38]
00c521db  MOV R9,qword ptr [RAX + 0x30]
00c521df  NOP
00c521e0  JMP 0x00c521e5
00c521e2  MOV R12,RDI
00c521e5  MOV RDI,qword ptr [RAX + 0x48]
00c521e9  MOV R13,qword ptr [RAX + 0x40]
00c521ed  MOV R15,qword ptr [RAX + 0x50]
00c521f1  MOV RCX,qword ptr [RAX + 0x10]
00c521f5  TEST RDI,RDI
00c521f8  CMOVNZ R10,RDI
00c521fc  CMOVNZ R11,R13
00c52200  TEST R15,R15
00c52203  CMOVG RDX,R15
00c52207  TEST RCX,RCX
00c5220a  JZ 0x00c52216
00c5220c  MOV RDI,qword ptr [RAX + 0x8]
00c52210  MOV R13,qword ptr [RAX + 0x18]
00c52214  JMP 0x00c5221d
00c52216  XOR ECX,ECX
00c52218  XOR EDI,EDI
00c5221a  XOR R13D,R13D
00c5221d  MOV qword ptr [RSP + 0xc8],R10
00c52225  MOV qword ptr [RSP + 0x190],R11
00c5222d  MOV qword ptr [RSP + 0xe0],RCX
00c52235  MOV qword ptr [RSP + 0x1b0],RDI
00c5223d  MOV qword ptr [RSP + 0x180],RAX
00c52245  MOV qword ptr [RSP + 0x188],R9
00c5224d  MOV qword ptr [RSP + 0xb8],R8
00c52255  MOV qword ptr [RSP + 0x198],RSI
00c5225d  MOV qword ptr [RSP + 0xd0],R12
00c52265  MOV qword ptr [RSP + 0x1c8],R13
00c5226d  MOV qword ptr [RSP + 0xc0],RDX
00c52275  CMP qword ptr [0x01990200],0x0
00c5227d  NOP dword ptr [RAX]
00c52280  JZ 0x00c524b6
00c52286  CALL 0x004c7f40
00c5228b  NOP
00c5228c  BT RAX,0x3f
00c52291  JNC 0x00c522a9
00c52293  LEA RCX,[RAX + RAX*0x1]
00c52297  SHR RCX,0x1f
00c5229b  MOV RDX,0xdd7b17f80
00c522a5  LEA RBX,[RCX + RDX*0x1]
00c522a9  LEA RCX,[RSP + 0x2e0]
00c522b1  MOV EDX,0x3
00c522b6  MOVUPS xmmword ptr [RCX],XMM15
00c522ba  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c522bf  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00c522c4  MOVUPS xmmword ptr [RCX + 0x30],XMM15
00c522c9  ADD RCX,0x40
00c522cd  DEC EDX
00c522cf  JNZ 0x00c522b6
00c522d1  MOVUPS xmmword ptr [RCX + -0x8],XMM15
00c522d6  MOV RCX,qword ptr [RSP + 0xf8]
00c522de  MOV qword ptr [RSP + 0x2e8],RCX
00c522e6  MOV RDX,qword ptr [RSP + 0x1e8]
00c522ee  MOV qword ptr [RSP + 0x2e0],RDX
00c522f6  MOV qword ptr [RSP + 0x2f8],RCX
00c522fe  MOV qword ptr [RSP + 0x2f0],RDX
00c52306  MOV RCX,qword ptr [RSP + 0xa8]
00c5230e  MOV qword ptr [RSP + 0x308],RCX
00c52316  MOV RCX,qword ptr [RSP + 0x168]
00c5231e  MOV qword ptr [RSP + 0x300],RCX
00c52326  MOV RCX,qword ptr [RSP + 0xa0]
00c5232e  MOV qword ptr [RSP + 0x318],RCX
00c52336  MOV RCX,qword ptr [RSP + 0x160]
00c5233e  MOV qword ptr [RSP + 0x310],RCX
00c52346  MOV RCX,qword ptr [RSP + 0x78]
00c5234b  MOV qword ptr [RSP + 0x328],RCX
00c52353  MOV RCX,qword ptr [RSP + 0x138]
00c5235b  MOV qword ptr [RSP + 0x320],RCX
00c52363  MOV RCX,qword ptr [RSP + 0x80]
00c5236b  MOV qword ptr [RSP + 0x338],RCX
00c52373  MOV RCX,qword ptr [RSP + 0x140]
00c5237b  MOV qword ptr [RSP + 0x330],RCX
00c52383  MOV RCX,qword ptr [RSP + 0xd0]
00c5238b  MOV qword ptr [RSP + 0x348],RCX
00c52393  MOV RCX,qword ptr [RSP + 0x198]
00c5239b  MOV qword ptr [RSP + 0x340],RCX
00c523a3  MOV RCX,qword ptr [RSP + 0xb8]
00c523ab  MOV qword ptr [RSP + 0x358],RCX
00c523b3  MOV RCX,qword ptr [RSP + 0x188]
00c523bb  MOV qword ptr [RSP + 0x350],RCX
00c523c3  MOV RCX,qword ptr [RSP + 0xc8]
00c523cb  MOV qword ptr [RSP + 0x368],RCX
00c523d3  MOV RCX,qword ptr [RSP + 0x190]
00c523db  MOV qword ptr [RSP + 0x360],RCX
00c523e3  MOV RCX,qword ptr [RSP + 0xc0]
00c523eb  MOV qword ptr [RSP + 0x370],RCX
00c523f3  MOV RCX,qword ptr [RSP + 0x180]
00c523fb  MOVZX EDX,byte ptr [RCX]
00c523fe  MOV byte ptr [RSP + 0x378],DL
00c52405  MOV RDX,qword ptr [RCX + 0x58]
00c52409  MOV RSI,qword ptr [RCX + 0x60]
00c5240d  MOV RCX,qword ptr [RCX + 0x68]
00c52411  MOV qword ptr [RSP + 0x388],RSI
00c52419  MOV qword ptr [RSP + 0x390],RCX
00c52421  MOV qword ptr [RSP + 0x380],RDX
00c52429  MOV qword ptr [RSP + 0x398],0x2
00c52435  MOV RCX,-0xe7791f700
00c5243f  ADD RCX,RBX
00c52442  MOV qword ptr [RSP + 0x3a0],RCX
00c5244a  MOV RAX,qword ptr [0x01990200]
00c52451  LEA RBX,[RSP + 0x2e0]
00c52459  CALL 0x00a13b00
00c5245e  MOV RAX,qword ptr [RSP + 0x180]
00c52466  MOV RCX,qword ptr [RSP + 0xe0]
00c5246e  MOV RDX,qword ptr [RSP + 0xc0]
00c52476  MOV RSI,qword ptr [RSP + 0x198]
00c5247e  MOV RDI,qword ptr [RSP + 0x1b0]
00c52486  MOV R8,qword ptr [RSP + 0xb8]
00c5248e  MOV R9,qword ptr [RSP + 0x188]
00c52496  MOV R10,qword ptr [RSP + 0xc8]
00c5249e  MOV R11,qword ptr [RSP + 0x190]
00c524a6  MOV R12,qword ptr [RSP + 0xd0]
00c524ae  MOV R13,qword ptr [RSP + 0x1c8]
00c524b6  MOV R15,qword ptr [RSP + 0x578]
00c524be  NOP
00c524c0  TEST R15,R15
00c524c3  JZ 0x00c529b1
00c524c9  MOV RBX,qword ptr [R15 + 0x8]
00c524cd  MOV R13,qword ptr [0x01974080]
00c524d4  MOV RCX,qword ptr [R13]
00c524d8  MOV R15D,dword ptr [R15 + 0x10]
00c524dc  NOP dword ptr [RAX]
00c524e0  JMP 0x00c53016
00c524e5  MOV RAX,qword ptr [RSP + 0x208]
00c524ed  JMP 0x00c524f7
00c524ef  MOV RAX,qword ptr [RSP + 0x170]
00c524f7  MOV qword ptr [RSP + 0x170],RAX
00c524ff  MOV RCX,qword ptr [RSP + 0x578]
00c52507  TEST RCX,RCX
00c5250a  JZ 0x00c52635
00c52510  MOV RBX,qword ptr [RCX + 0x8]
00c52514  MOV RDX,qword ptr [0x019740a0]
00c5251b  MOV RSI,qword ptr [RDX]
00c5251e  MOV ECX,dword ptr [RCX + 0x10]
00c52521  JMP 0x00c52976
00c52526  MOV qword ptr [RSP + 0xf0],RBX
00c5252e  MOVUPS xmmword ptr [RSP + 0x470],XMM15
00c52537  JZ 0x00c5253f
00c52539  MOV RDX,qword ptr [RBX + 0x8]
00c5253d  JMP 0x00c52542
00c5253f  MOV RDX,RBX
00c52542  MOV qword ptr [RSP + 0x1e0],RCX
00c5254a  MOV qword ptr [RSP + 0x470],RDX
00c52552  MOV qword ptr [RSP + 0x478],RCX
00c5255a  LEA RDX,[0xc53940]
00c52561  MOV qword ptr [RSP + 0x530],RDX
00c52569  MOV qword ptr [RSP + 0x540],0x2a
00c52575  LEA RDX,[0xf3db47]
00c5257c  MOV qword ptr [RSP + 0x538],RDX
00c52584  MOV qword ptr [RSP + 0x550],0x1
00c52590  MOV qword ptr [RSP + 0x558],0x1
00c5259c  LEA RDX,[RSP + 0x470]
00c525a4  MOV qword ptr [RSP + 0x548],RDX
00c525ac  MOV RAX,qword ptr [0x01990148]
00c525b3  XOR EBX,EBX
00c525b5  MOV ECX,0x2
00c525ba  LEA RDI,[RSP + 0x530]
00c525c2  CALL 0x0054d540
00c525c7  MOV RDX,qword ptr [RSP + 0xf0]
00c525cf  MOV RDX,qword ptr [RDX + 0x18]
00c525d3  MOV RAX,qword ptr [RSP + 0x1e0]
00c525db  CALL RDX
00c525dd  MOV RCX,RAX
00c525e0  MOV RDI,RBX
00c525e3  MOV ESI,0x1f4
00c525e8  MOV RAX,qword ptr [RSP + 0x578]
00c525f0  MOV RBX,qword ptr [RSP + 0x580]
00c525f8  CALL 0x00c484c0
00c525fd  ADD RSP,0x568
00c52604  POP RBP
00c52605  RET
00c52606  MOV RAX,qword ptr [RSP + 0x578]
00c5260e  MOV RBX,qword ptr [RSP + 0x580]
00c52616  LEA RCX,[0xf2d180]
00c5261d  MOV EDI,0x1d
00c52622  MOV ESI,0x190
00c52627  CALL 0x00c484c0
00c5262c  ADD RSP,0x568
00c52633  POP RBP
00c52634  RET
00c52635  LEA RAX,[RSP + 0x220]
00c5263d  MOVUPS xmmword ptr [RAX],XMM15
00c52641  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c52646  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c5264b  MOVUPS xmmword ptr [RAX + 0x30],XMM15
00c52650  MOVUPS xmmword ptr [RAX + 0x40],XMM15
00c52655  MOVUPS xmmword ptr [RAX + 0x50],XMM15
00c5265a  MOV qword ptr [RSP + 0x220],RCX
00c52662  MOV RAX,qword ptr [RSP + 0x580]
00c5266a  MOV qword ptr [RSP + 0x228],RAX
00c52672  MOV byte ptr [RSP + 0x240],0x1
00c5267a  CALL 0x004825c0
00c5267f  MOV qword ptr [RSP + 0x200],RAX
00c52687  MOV RBX,RAX
00c5268a  LEA RCX,[0xeffdf5]
00c52691  MOV EDI,0x7
00c52696  LEA RAX,[0xe16300]
00c5269d  NOP dword ptr [RAX]
00c526a0  CALL 0x00413460
00c526a5  LEA RCX,[0xdd2dc0]
00c526ac  MOV qword ptr [RAX],RCX
00c526af  CMP dword ptr [0x019b5f00],0x0
00c526b6  JZ 0x00c526c8
00c526b8  MOV RDX,qword ptr [RAX + 0x8]
00c526bc  NOP dword ptr [RAX]
00c526c0  CALL 0x0048bbe0
00c526c5  MOV qword ptr [R11],RDX
00c526c8  LEA RDX,[0x115e2c8]
00c526cf  MOV qword ptr [RAX + 0x8],RDX
00c526d3  LEA RAX,[0xe16300]
00c526da  MOV RBX,qword ptr [RSP + 0x200]
00c526e2  LEA RCX,[0xefe2b7]
00c526e9  MOV EDI,0x6
00c526ee  CALL 0x00413460
00c526f3  LEA RDX,[0xdd2dc0]
00c526fa  MOV qword ptr [RAX],RDX
00c526fd  CMP dword ptr [0x019b5f00],0x0
00c52704  JZ 0x00c52712
00c52706  MOV RCX,qword ptr [RAX + 0x8]
00c5270a  CALL 0x0048bbe0
00c5270f  MOV qword ptr [R11],RCX
00c52712  LEA RCX,[0x115e2c0]
00c52719  MOV qword ptr [RAX + 0x8],RCX
00c5271d  MOV RCX,qword ptr [RSP + 0x170]
00c52725  MOV RAX,qword ptr [RCX + 0x40]
00c52729  CALL 0x00481e60
00c5272e  MOV qword ptr [RSP + 0x1f8],RAX
00c52736  LEA RAX,[0xe16300]
00c5273d  MOV RBX,qword ptr [RSP + 0x200]
00c52745  LEA RCX,[0xefe2bd]
00c5274c  MOV EDI,0x6
00c52751  CALL 0x00413460
00c52756  LEA RCX,[0xdd2c00]
00c5275d  MOV qword ptr [RAX],RCX
00c52760  CMP dword ptr [0x019b5f00],0x0
00c52767  JNZ 0x00c52773
00c52769  MOV RDX,qword ptr [RSP + 0x1f8]
00c52771  JMP 0x00c5278b
00c52773  MOV RCX,qword ptr [RAX + 0x8]
00c52777  CALL 0x0048bc00
00c5277c  MOV RDX,qword ptr [RSP + 0x1f8]
00c52784  MOV qword ptr [R11],RDX
00c52787  MOV qword ptr [R11 + 0x8],RCX
00c5278b  MOV qword ptr [RAX + 0x8],RDX
00c5278f  MOV RAX,qword ptr [RSP + 0x168]
00c52797  MOV RBX,qword ptr [RSP + 0xa8]
00c5279f  NOP
00c527a0  CALL 0x00481ee0
00c527a5  MOV qword ptr [RSP + 0x1f8],RAX
00c527ad  LEA RAX,[0xe16300]
00c527b4  MOV RBX,qword ptr [RSP + 0x200]
00c527bc  LEA RCX,[0xf05a35]
00c527c3  MOV EDI,0x9
00c527c8  CALL 0x00413460
00c527cd  LEA RCX,[0xdd29c0]
00c527d4  MOV qword ptr [RAX],RCX
00c527d7  CMP dword ptr [0x019b5f00],0x0
00c527de  NOP
00c527e0  JNZ 0x00c527ec
00c527e2  MOV RDX,qword ptr [RSP + 0x1f8]
00c527ea  JMP 0x00c52804
00c527ec  MOV RCX,qword ptr [RAX + 0x8]
00c527f0  CALL 0x0048bc00
00c527f5  MOV RDX,qword ptr [RSP + 0x1f8]
00c527fd  MOV qword ptr [R11],RDX
00c52800  MOV qword ptr [R11 + 0x8],RCX
00c52804  MOV qword ptr [RAX + 0x8],RDX
00c52808  MOV RAX,qword ptr [RSP + 0x1e8]
00c52810  MOV RBX,qword ptr [RSP + 0xf8]
00c52818  CALL 0x00481ee0
00c5281d  MOV qword ptr [RSP + 0x1f8],RAX
00c52825  LEA RAX,[0xe16300]
00c5282c  MOV RBX,qword ptr [RSP + 0x200]
00c52834  LEA RCX,[0xefaba6]
00c5283b  MOV EDI,0x3
00c52840  CALL 0x00413460
00c52845  LEA RCX,[0xdd29c0]
00c5284c  MOV qword ptr [RAX],RCX
00c5284f  CMP dword ptr [0x019b5f00],0x0
00c52856  JNZ 0x00c52862
00c52858  MOV RDX,qword ptr [RSP + 0x1f8]
00c52860  JMP 0x00c5287a
00c52862  MOV RCX,qword ptr [RAX + 0x8]
00c52866  CALL 0x0048bc00
00c5286b  MOV RDX,qword ptr [RSP + 0x1f8]
00c52873  MOV qword ptr [R11],RDX
00c52876  MOV qword ptr [R11 + 0x8],RCX
00c5287a  MOV qword ptr [RAX + 0x8],RDX
00c5287e  MOV RAX,qword ptr [RSP + 0x148]
00c52886  MOV RBX,qword ptr [RSP + 0x88]
00c5288e  CALL 0x00481ee0
00c52893  MOV qword ptr [RSP + 0x1f8],RAX
00c5289b  LEA RAX,[0xe16300]
00c528a2  MOV RBX,qword ptr [RSP + 0x200]
00c528aa  LEA RCX,[0xf02a71]
00c528b1  MOV EDI,0x8
00c528b6  CALL 0x00413460
00c528bb  LEA RCX,[0xdd29c0]
00c528c2  MOV qword ptr [RAX],RCX
00c528c5  CMP dword ptr [0x019b5f00],0x0
00c528cc  JNZ 0x00c528d8
00c528ce  MOV RSI,qword ptr [RSP + 0x1f8]
00c528d6  JMP 0x00c528f4
00c528d8  MOV RDX,qword ptr [RAX + 0x8]
00c528dc  NOP dword ptr [RAX]
00c528e0  CALL 0x0048bc00
00c528e5  MOV RSI,qword ptr [RSP + 0x1f8]
00c528ed  MOV qword ptr [R11],RSI
00c528f0  MOV qword ptr [R11 + 0x8],RDX
00c528f4  MOV qword ptr [RAX + 0x8],RSI
00c528f8  LEA RAX,[0xe16300]
00c528ff  MOV RBX,qword ptr [RSP + 0x200]
00c52907  LEA RCX,[0xefb5b7]
00c5290e  MOV EDI,0x4
00c52913  CALL 0x00413460
00c52918  LEA RDX,[0xdb1b20]
00c5291f  MOV qword ptr [RAX],RDX
00c52922  CMP dword ptr [0x019b5f00],0x0
00c52929  JNZ 0x00c52935
00c5292b  MOV RSI,qword ptr [RSP + 0x170]
00c52933  JMP 0x00c5294d
00c52935  MOV RDX,qword ptr [RAX + 0x8]
00c52939  CALL 0x0048bc00
00c5293e  MOV RSI,qword ptr [RSP + 0x170]
00c52946  MOV qword ptr [R11],RSI
00c52949  MOV qword ptr [R11 + 0x8],RDX
00c5294d  MOV qword ptr [RAX + 0x8],RSI
00c52951  LEA RAX,[RSP + 0x220]
00c52959  LEA RBX,[0xe16300]
00c52960  MOV RCX,qword ptr [RSP + 0x200]
00c52968  CALL 0x0053fda0
00c5296d  ADD RSP,0x568
00c52974  POP RBP
00c52975  RET
00c52976  MOV RDI,RCX
00c52979  AND RCX,RSI
00c5297c  SHL RCX,0x4
00c52980  MOV R8,qword ptr [RDX + RCX*0x1 + 0x8]
00c52985  CMP R8,RBX
00c52988  JZ 0x00c529a7
00c5298a  LEA RCX,[RDI + 0x1]
00c5298e  TEST R8,R8
00c52991  JNZ 0x00c52976
00c52993  LEA RAX,[0x19740a0]
00c5299a  CALL 0x0041e320
00c5299f  MOV RCX,RAX
00c529a2  JMP 0x00c52635
00c529a7  MOV RCX,qword ptr [RDX + RCX*0x1 + 0x10]
00c529ac  JMP 0x00c52635
00c529b1  LEA RDX,[RSP + 0x280]
00c529b9  MOVUPS xmmword ptr [RDX],XMM15
00c529bd  MOVUPS xmmword ptr [RDX + 0x10],XMM15
00c529c2  MOVUPS xmmword ptr [RDX + 0x20],XMM15
00c529c7  MOVUPS xmmword ptr [RDX + 0x30],XMM15
00c529cc  MOVUPS xmmword ptr [RDX + 0x40],XMM15
00c529d1  MOVUPS xmmword ptr [RDX + 0x50],XMM15
00c529d6  MOV qword ptr [RSP + 0x280],R15
00c529de  MOV RDX,qword ptr [RSP + 0x580]
00c529e6  MOV qword ptr [RSP + 0x288],RDX
00c529ee  MOV byte ptr [RSP + 0x2a0],0x1
00c529f6  LEA RAX,[0xe16300]
00c529fd  MOV EBX,0xe
00c52a02  XOR ECX,ECX
00c52a04  CALL 0x00482600
00c52a09  MOV qword ptr [RSP + 0x200],RAX
00c52a11  MOV RBX,RAX
00c52a14  LEA RCX,[0xeffdf5]
00c52a1b  MOV EDI,0x7
00c52a20  LEA RAX,[0xe16300]
00c52a27  CALL 0x00413460
00c52a2c  LEA RDX,[0xdd2dc0]
00c52a33  MOV qword ptr [RAX],RDX
00c52a36  CMP dword ptr [0x019b5f00],0x0
00c52a3d  JZ 0x00c52a4b
00c52a3f  MOV RDX,qword ptr [RAX + 0x8]
00c52a43  CALL 0x0048bbe0
00c52a48  MOV qword ptr [R11],RDX
00c52a4b  LEA RDX,[0x115e2c8]
00c52a52  MOV qword ptr [RAX + 0x8],RDX
00c52a56  LEA RAX,[0xe16300]
00c52a5d  MOV RBX,qword ptr [RSP + 0x200]
00c52a65  LEA RCX,[0xefe2b7]
00c52a6c  MOV EDI,0x6
00c52a71  CALL 0x00413460
00c52a76  LEA RDX,[0xdd2dc0]
00c52a7d  MOV qword ptr [RAX],RDX
00c52a80  CMP dword ptr [0x019b5f00],0x0
00c52a87  JZ 0x00c52a95
00c52a89  MOV RDX,qword ptr [RAX + 0x8]
00c52a8d  CALL 0x0048bbe0
00c52a92  MOV qword ptr [R11],RDX
00c52a95  LEA RDX,[0x115e2c0]
00c52a9c  MOV qword ptr [RAX + 0x8],RDX
00c52aa0  LEA RAX,[0xe16300]
00c52aa7  MOV RBX,qword ptr [RSP + 0x200]
00c52aaf  LEA RCX,[0xefe2bd]
00c52ab6  MOV EDI,0x6
00c52abb  NOP dword ptr [RAX + RAX*0x1]
00c52ac0  CALL 0x00413460
00c52ac5  LEA RDX,[0xdd2c00]
00c52acc  MOV qword ptr [RAX],RDX
00c52acf  CMP dword ptr [0x019b5f00],0x0
00c52ad6  JZ 0x00c52ae8
00c52ad8  MOV RCX,qword ptr [RAX + 0x8]
00c52adc  NOP dword ptr [RAX]
00c52ae0  CALL 0x0048bbe0
00c52ae5  MOV qword ptr [R11],RCX
00c52ae8  LEA RCX,[0x1132ee8]
00c52aef  MOV qword ptr [RAX + 0x8],RCX
00c52af3  MOV RAX,qword ptr [RSP + 0x168]
00c52afb  MOV RBX,qword ptr [RSP + 0xa8]
00c52b03  CALL 0x00481ee0
00c52b08  MOV qword ptr [RSP + 0x1f8],RAX
00c52b10  LEA RAX,[0xe16300]
00c52b17  MOV RBX,qword ptr [RSP + 0x200]
00c52b1f  LEA RCX,[0xf05a35]
00c52b26  MOV EDI,0x9
00c52b2b  CALL 0x00413460
00c52b30  LEA RCX,[0xdd29c0]
00c52b37  MOV qword ptr [RAX],RCX
00c52b3a  CMP dword ptr [0x019b5f00],0x0
00c52b41  JNZ 0x00c52b4d
00c52b43  MOV RDX,qword ptr [RSP + 0x1f8]
00c52b4b  JMP 0x00c52b65
00c52b4d  MOV RCX,qword ptr [RAX + 0x8]
00c52b51  CALL 0x0048bc00
00c52b56  MOV RDX,qword ptr [RSP + 0x1f8]
00c52b5e  MOV qword ptr [R11],RDX
00c52b61  MOV qword ptr [R11 + 0x8],RCX
00c52b65  MOV qword ptr [RAX + 0x8],RDX
00c52b69  MOV RAX,qword ptr [RSP + 0x198]
00c52b71  MOV RBX,qword ptr [RSP + 0xd0]
00c52b79  CALL 0x00481ee0
00c52b7e  MOV qword ptr [RSP + 0x1f8],RAX
00c52b86  LEA RAX,[0xe16300]
00c52b8d  MOV RBX,qword ptr [RSP + 0x200]
00c52b95  LEA RCX,[0xeffe2d]
00c52b9c  MOV EDI,0x7
00c52ba1  CALL 0x00413460
00c52ba6  LEA RCX,[0xdd29c0]
00c52bad  MOV qword ptr [RAX],RCX
00c52bb0  CMP dword ptr [0x019b5f00],0x0
00c52bb7  JNZ 0x00c52bc3
00c52bb9  MOV RDX,qword ptr [RSP + 0x1f8]
00c52bc1  JMP 0x00c52bdb
00c52bc3  MOV RCX,qword ptr [RAX + 0x8]
00c52bc7  CALL 0x0048bc00
00c52bcc  MOV RDX,qword ptr [RSP + 0x1f8]
00c52bd4  MOV qword ptr [R11],RDX
00c52bd7  MOV qword ptr [R11 + 0x8],RCX
00c52bdb  MOV qword ptr [RAX + 0x8],RDX
00c52bdf  MOV RAX,qword ptr [RSP + 0x188]
00c52be7  MOV RBX,qword ptr [RSP + 0xb8]
00c52bef  CALL 0x00481ee0
00c52bf4  MOV qword ptr [RSP + 0x1f8],RAX
00c52bfc  LEA RAX,[0xe16300]
00c52c03  MOV RBX,qword ptr [RSP + 0x200]
00c52c0b  LEA RCX,[0xf05a3e]
00c52c12  MOV EDI,0x9
00c52c17  CALL 0x00413460
00c52c1c  LEA RCX,[0xdd29c0]
00c52c23  MOV qword ptr [RAX],RCX
00c52c26  CMP dword ptr [0x019b5f00],0x0
00c52c2d  JNZ 0x00c52c39
00c52c2f  MOV RDX,qword ptr [RSP + 0x1f8]
00c52c37  JMP 0x00c52c54
00c52c39  MOV RCX,qword ptr [RAX + 0x8]
00c52c3d  NOP dword ptr [RAX]
00c52c40  CALL 0x0048bc00
00c52c45  MOV RDX,qword ptr [RSP + 0x1f8]
00c52c4d  MOV qword ptr [R11],RDX
00c52c50  MOV qword ptr [R11 + 0x8],RCX
00c52c54  MOV qword ptr [RAX + 0x8],RDX
00c52c58  MOV RAX,qword ptr [RSP + 0x190]
00c52c60  MOV RBX,qword ptr [RSP + 0xc8]
00c52c68  CALL 0x00481ee0
00c52c6d  MOV qword ptr [RSP + 0x1f8],RAX
00c52c75  LEA RAX,[0xe16300]
00c52c7c  MOV RBX,qword ptr [RSP + 0x200]
00c52c84  LEA RCX,[0xf05a11]
00c52c8b  MOV EDI,0x9
00c52c90  CALL 0x00413460
00c52c95  LEA RCX,[0xdd29c0]
00c52c9c  MOV qword ptr [RAX],RCX
00c52c9f  CMP dword ptr [0x019b5f00],0x0
00c52ca6  JNZ 0x00c52cb2
00c52ca8  MOV RDX,qword ptr [RSP + 0x1f8]
00c52cb0  JMP 0x00c52cca
00c52cb2  MOV RCX,qword ptr [RAX + 0x8]
00c52cb6  CALL 0x0048bc00
00c52cbb  MOV RDX,qword ptr [RSP + 0x1f8]
00c52cc3  MOV qword ptr [R11],RDX
00c52cc6  MOV qword ptr [R11 + 0x8],RCX
00c52cca  MOV qword ptr [RAX + 0x8],RDX
00c52cce  MOV RAX,qword ptr [RSP + 0xc0]
00c52cd6  CALL 0x00481e60
00c52cdb  MOV qword ptr [RSP + 0x1f8],RAX
00c52ce3  LEA RAX,[0xe16300]
00c52cea  MOV RBX,qword ptr [RSP + 0x200]
00c52cf2  LEA RCX,[0xf05a1a]
00c52cf9  MOV EDI,0x9
00c52cfe  NOP
00c52d00  CALL 0x00413460
00c52d05  LEA RCX,[0xdd2b80]
00c52d0c  MOV qword ptr [RAX],RCX
00c52d0f  CMP dword ptr [0x019b5f00],0x0
00c52d16  JNZ 0x00c52d22
00c52d18  MOV RSI,qword ptr [RSP + 0x1f8]
00c52d20  JMP 0x00c52d3a
00c52d22  MOV RDX,qword ptr [RAX + 0x8]
00c52d26  CALL 0x0048bc00
00c52d2b  MOV RSI,qword ptr [RSP + 0x1f8]
00c52d33  MOV qword ptr [R11],RSI
00c52d36  MOV qword ptr [R11 + 0x8],RDX
00c52d3a  MOV qword ptr [RAX + 0x8],RSI
00c52d3e  MOV RDX,qword ptr [RSP + 0x180]
00c52d46  MOVZX EDX,byte ptr [RDX]
00c52d49  MOV qword ptr [RSP + 0x108],RDX
00c52d51  LEA RAX,[0xe16300]
00c52d58  MOV RBX,qword ptr [RSP + 0x200]
00c52d60  LEA RCX,[0xefe2c3]
00c52d67  MOV EDI,0x6
00c52d6c  CALL 0x00413460
00c52d71  LEA RDX,[0xdd2dc0]
00c52d78  MOV qword ptr [RAX],RDX
00c52d7b  MOV RDX,qword ptr [RSP + 0x108]
00c52d83  LEA RSI,[0x115e2c0]
00c52d8a  LEA RDX,[RSI + RDX*0x8]
00c52d8e  CMP dword ptr [0x019b5f00],0x0
00c52d95  JZ 0x00c52da8
00c52d97  MOV RSI,qword ptr [RAX + 0x8]
00c52d9b  NOP dword ptr [RAX + RAX*0x1]
00c52da0  CALL 0x0048bbe0
00c52da5  MOV qword ptr [R11],RSI
00c52da8  MOV qword ptr [RAX + 0x8],RDX
00c52dac  MOV RDX,qword ptr [RSP + 0x180]
00c52db4  MOV RAX,qword ptr [RDX + 0x58]
00c52db8  MOV RBX,qword ptr [RDX + 0x60]
00c52dbc  MOV RCX,qword ptr [RDX + 0x68]
00c52dc0  CALL 0x00481f80
00c52dc5  MOV qword ptr [RSP + 0x1f8],RAX
00c52dcd  LEA RAX,[0xe16300]
00c52dd4  MOV RBX,qword ptr [RSP + 0x200]
00c52ddc  LEA RCX,[0xf05a47]
00c52de3  MOV EDI,0x9
00c52de8  CALL 0x00413460
00c52ded  LEA RDX,[0xdc15a0]
00c52df4  MOV qword ptr [RAX],RDX
00c52df7  CMP dword ptr [0x019b5f00],0x0
00c52dfe  NOP
00c52e00  JNZ 0x00c52e0c
00c52e02  MOV RDX,qword ptr [RSP + 0x1f8]
00c52e0a  JMP 0x00c52e24
00c52e0c  MOV RCX,qword ptr [RAX + 0x8]
00c52e10  CALL 0x0048bc00
00c52e15  MOV RDX,qword ptr [RSP + 0x1f8]
00c52e1d  MOV qword ptr [R11],RDX
00c52e20  MOV qword ptr [R11 + 0x8],RCX
00c52e24  MOV qword ptr [RAX + 0x8],RDX
00c52e28  MOV RAX,qword ptr [RSP + 0x1b0]
00c52e30  MOV RBX,qword ptr [RSP + 0xe0]
00c52e38  CALL 0x00481ee0
00c52e3d  MOV qword ptr [RSP + 0x1f8],RAX
00c52e45  LEA RAX,[0xe16300]
00c52e4c  MOV RBX,qword ptr [RSP + 0x200]
00c52e54  LEA RCX,[0xf02a69]
00c52e5b  MOV EDI,0x8
00c52e60  CALL 0x00413460
00c52e65  LEA RCX,[0xdd29c0]
00c52e6c  MOV qword ptr [RAX],RCX
00c52e6f  CMP dword ptr [0x019b5f00],0x0
00c52e76  JNZ 0x00c52e82
00c52e78  MOV RSI,qword ptr [RSP + 0x1f8]
00c52e80  JMP 0x00c52e9a
00c52e82  MOV RDX,qword ptr [RAX + 0x8]
00c52e86  CALL 0x0048bc00
00c52e8b  MOV RSI,qword ptr [RSP + 0x1f8]
00c52e93  MOV qword ptr [R11],RSI
00c52e96  MOV qword ptr [R11 + 0x8],RDX
00c52e9a  MOV qword ptr [RAX + 0x8],RSI
00c52e9e  LEA RAX,[0xe16300]
00c52ea5  MOV RBX,qword ptr [RSP + 0x200]
00c52ead  LEA RCX,[0xeffe49]
00c52eb4  MOV EDI,0x7
00c52eb9  CALL 0x00413460
00c52ebe  LEA RDX,[0xe16200]
00c52ec5  MOV qword ptr [RAX],RDX
00c52ec8  CMP dword ptr [0x019b5f00],0x0
00c52ecf  JNZ 0x00c52edb
00c52ed1  MOV RDX,qword ptr [RSP + 0x1c8]
00c52ed9  JMP 0x00c52ef4
00c52edb  MOV RCX,qword ptr [RAX + 0x8]
00c52edf  NOP
00c52ee0  CALL 0x0048bc00
00c52ee5  MOV RDX,qword ptr [RSP + 0x1c8]
00c52eed  MOV qword ptr [R11],RDX
00c52ef0  MOV qword ptr [R11 + 0x8],RCX
00c52ef4  MOV qword ptr [RAX + 0x8],RDX
00c52ef8  MOV RAX,qword ptr [RSP + 0x138]
00c52f00  MOV RBX,qword ptr [RSP + 0x78]
00c52f05  CALL 0x00481ee0
00c52f0a  MOV qword ptr [RSP + 0x1f8],RAX
00c52f12  LEA RAX,[0xe16300]
00c52f19  MOV RBX,qword ptr [RSP + 0x200]
00c52f21  LEA RCX,[0xf05a2c]
00c52f28  MOV EDI,0x9
00c52f2d  CALL 0x00413460
00c52f32  LEA RCX,[0xdd29c0]
00c52f39  MOV qword ptr [RAX],RCX
00c52f3c  CMP dword ptr [0x019b5f00],0x0
00c52f43  JNZ 0x00c52f4f
00c52f45  MOV RDX,qword ptr [RSP + 0x1f8]
00c52f4d  JMP 0x00c52f67
00c52f4f  MOV RCX,qword ptr [RAX + 0x8]
00c52f53  CALL 0x0048bc00
00c52f58  MOV RDX,qword ptr [RSP + 0x1f8]
00c52f60  MOV qword ptr [R11],RDX
00c52f63  MOV qword ptr [R11 + 0x8],RCX
00c52f67  MOV qword ptr [RAX + 0x8],RDX
00c52f6b  MOV RAX,qword ptr [RSP + 0x140]
00c52f73  MOV RBX,qword ptr [RSP + 0x80]
00c52f7b  NOP dword ptr [RAX + RAX*0x1]
00c52f80  CALL 0x00481ee0
00c52f85  MOV qword ptr [RSP + 0x1f8],RAX
00c52f8d  LEA RAX,[0xe16300]
00c52f94  MOV RBX,qword ptr [RSP + 0x200]
00c52f9c  LEA RCX,[0xefe2b1]
00c52fa3  MOV EDI,0x6
00c52fa8  CALL 0x00413460
00c52fad  LEA RCX,[0xdd29c0]
00c52fb4  MOV qword ptr [RAX],RCX
00c52fb7  CMP dword ptr [0x019b5f00],0x0
00c52fbe  NOP
00c52fc0  JNZ 0x00c52fcc
00c52fc2  MOV RSI,qword ptr [RSP + 0x1f8]
00c52fca  JMP 0x00c52fe4
00c52fcc  MOV RDX,qword ptr [RAX + 0x8]
00c52fd0  CALL 0x0048bc00
00c52fd5  MOV RSI,qword ptr [RSP + 0x1f8]
00c52fdd  MOV qword ptr [R11],RSI
00c52fe0  MOV qword ptr [R11 + 0x8],RDX
00c52fe4  MOV qword ptr [RAX + 0x8],RSI
00c52fe8  LEA RAX,[RSP + 0x280]
00c52ff0  LEA RBX,[0xe16300]
00c52ff7  MOV RCX,qword ptr [RSP + 0x200]
00c52fff  NOP
00c53000  CALL 0x0053fda0
00c53005  ADD RSP,0x568
00c5300c  POP RBP
00c5300d  RET
00c5300e  MOV RDI,qword ptr [RSP + 0x1b0]
00c53016  MOV qword ptr [RSP + 0x100],R15
00c5301e  AND R15,RCX
00c53021  SHL R15,0x4
00c53025  MOV RDI,qword ptr [R13 + R15*0x1 + 0x8]
00c5302a  CMP RDI,RBX
00c5302d  JZ 0x00c53053
00c5302f  MOV R15,qword ptr [RSP + 0x100]
00c53037  INC R15
00c5303a  TEST RDI,RDI
00c5303d  JNZ 0x00c5300e
00c5303f  LEA RAX,[0x1974080]
00c53046  CALL 0x0041e320
00c5304b  MOV R15,RAX
00c5304e  JMP 0x00c529b1
00c53053  MOV R15,qword ptr [R13 + R15*0x1 + 0x10]
00c53058  JMP 0x00c529b1
00c5305d  LEA RDX,[RSP + 0x480]
00c53065  MOVUPS xmmword ptr [RDX],XMM15
00c53069  MOVUPS xmmword ptr [RDX + 0x10],XMM15
00c5306e  MOVUPS xmmword ptr [RDX + 0x20],XMM15
00c53073  MOVUPS xmmword ptr [RDX + 0x30],XMM15
00c53078  MOVUPS xmmword ptr [RDX + 0x40],XMM15
00c5307d  MOVUPS xmmword ptr [RDX + 0x50],XMM15
00c53082  MOV qword ptr [RSP + 0x480],RDI
00c5308a  MOV RDX,qword ptr [RSP + 0x580]
00c53092  MOV qword ptr [RSP + 0x488],RDX
00c5309a  MOV byte ptr [RSP + 0x4a0],0x1
00c530a2  LEA RAX,[0xe16300]
00c530a9  MOV EBX,0xe
00c530ae  XOR ECX,ECX
00c530b0  CALL 0x00482600
00c530b5  MOV qword ptr [RSP + 0x200],RAX
00c530bd  MOV RBX,RAX
00c530c0  LEA RCX,[0xeffdf5]
00c530c7  MOV EDI,0x7
00c530cc  LEA RAX,[0xe16300]
00c530d3  CALL 0x00413460
00c530d8  LEA RDX,[0xdd2dc0]
00c530df  MOV qword ptr [RAX],RDX
00c530e2  CMP dword ptr [0x019b5f00],0x0
00c530e9  JZ 0x00c530f7
00c530eb  MOV RDX,qword ptr [RAX + 0x8]
00c530ef  CALL 0x0048bbe0
00c530f4  MOV qword ptr [R11],RDX
00c530f7  LEA RDX,[0x115e2c8]
00c530fe  MOV qword ptr [RAX + 0x8],RDX
00c53102  LEA RAX,[0xe16300]
00c53109  MOV RBX,qword ptr [RSP + 0x200]
00c53111  LEA RCX,[0xefe2b7]
00c53118  MOV EDI,0x6
00c5311d  NOP dword ptr [RAX]
00c53120  CALL 0x00413460
00c53125  LEA RDX,[0xdd2dc0]
00c5312c  MOV qword ptr [RAX],RDX
00c5312f  CMP dword ptr [0x019b5f00],0x0
00c53136  JZ 0x00c53148
00c53138  MOV RDX,qword ptr [RAX + 0x8]
00c5313c  NOP dword ptr [RAX]
00c53140  CALL 0x0048bbe0
00c53145  MOV qword ptr [R11],RDX
00c53148  LEA RDX,[0x115e2c8]
00c5314f  MOV qword ptr [RAX + 0x8],RDX
00c53153  LEA RAX,[0xe16300]
00c5315a  MOV RBX,qword ptr [RSP + 0x200]
00c53162  LEA RCX,[0xefe2bd]
00c53169  MOV EDI,0x6
00c5316e  CALL 0x00413460
00c53173  LEA RDX,[0xdd2c00]
00c5317a  MOV qword ptr [RAX],RDX
00c5317d  CMP dword ptr [0x019b5f00],0x0
00c53184  JZ 0x00c53192
00c53186  MOV RCX,qword ptr [RAX + 0x8]
00c5318a  CALL 0x0048bbe0
00c5318f  MOV qword ptr [R11],RCX
00c53192  LEA RCX,[0x1132ee8]
00c53199  MOV qword ptr [RAX + 0x8],RCX
00c5319d  MOV RCX,qword ptr [RSP + 0x1f0]
00c531a5  MOV RAX,qword ptr [RCX + 0x20]
00c531a9  MOV RBX,qword ptr [RCX + 0x28]
00c531ad  CALL 0x00481ee0
00c531b2  MOV qword ptr [RSP + 0x1f8],RAX
00c531ba  LEA RAX,[0xe16300]
00c531c1  MOV RBX,qword ptr [RSP + 0x200]
00c531c9  LEA RCX,[0xf05a35]
00c531d0  MOV EDI,0x9
00c531d5  CALL 0x00413460
00c531da  LEA RCX,[0xdd29c0]
00c531e1  MOV qword ptr [RAX],RCX
00c531e4  CMP dword ptr [0x019b5f00],0x0
00c531eb  JNZ 0x00c531f7
00c531ed  MOV RDX,qword ptr [RSP + 0x1f8]
00c531f5  JMP 0x00c53214
00c531f7  MOV RCX,qword ptr [RAX + 0x8]
00c531fb  NOP dword ptr [RAX + RAX*0x1]
00c53200  CALL 0x0048bc00
00c53205  MOV RDX,qword ptr [RSP + 0x1f8]
00c5320d  MOV qword ptr [R11],RDX
00c53210  MOV qword ptr [R11 + 0x8],RCX
00c53214  MOV qword ptr [RAX + 0x8],RDX
00c53218  MOV RCX,qword ptr [RSP + 0x1f0]
00c53220  MOV RAX,qword ptr [RCX + 0x60]
00c53224  MOV RBX,qword ptr [RCX + 0x68]
00c53228  CALL 0x00481ee0
00c5322d  MOV qword ptr [RSP + 0x1f8],RAX
00c53235  LEA RAX,[0xe16300]
00c5323c  MOV RBX,qword ptr [RSP + 0x200]
00c53244  LEA RCX,[0xeffe2d]
00c5324b  MOV EDI,0x7
00c53250  CALL 0x00413460
00c53255  LEA RCX,[0xdd29c0]
00c5325c  MOV qword ptr [RAX],RCX
00c5325f  CMP dword ptr [0x019b5f00],0x0
00c53266  JNZ 0x00c53272
00c53268  MOV RDX,qword ptr [RSP + 0x1f8]
00c53270  JMP 0x00c5328a
00c53272  MOV RCX,qword ptr [RAX + 0x8]
00c53276  CALL 0x0048bc00
00c5327b  MOV RDX,qword ptr [RSP + 0x1f8]
00c53283  MOV qword ptr [R11],RDX
00c53286  MOV qword ptr [R11 + 0x8],RCX
00c5328a  MOV qword ptr [RAX + 0x8],RDX
00c5328e  MOV RCX,qword ptr [RSP + 0x1f0]
00c53296  MOV RAX,qword ptr [RCX + 0x70]
00c5329a  MOV RBX,qword ptr [RCX + 0x78]
00c5329e  NOP
00c532a0  CALL 0x00481ee0
00c532a5  MOV qword ptr [RSP + 0x1f8],RAX
00c532ad  LEA RAX,[0xe16300]
00c532b4  MOV RBX,qword ptr [RSP + 0x200]
00c532bc  LEA RCX,[0xf05a3e]
00c532c3  MOV EDI,0x9
00c532c8  CALL 0x00413460
00c532cd  LEA RCX,[0xdd29c0]
00c532d4  MOV qword ptr [RAX],RCX
00c532d7  CMP dword ptr [0x019b5f00],0x0
00c532de  NOP
00c532e0  JNZ 0x00c532ec
00c532e2  MOV RDX,qword ptr [RSP + 0x1f8]
00c532ea  JMP 0x00c53304
00c532ec  MOV RCX,qword ptr [RAX + 0x8]
00c532f0  CALL 0x0048bc00
00c532f5  MOV RDX,qword ptr [RSP + 0x1f8]
00c532fd  MOV qword ptr [R11],RDX
00c53300  MOV qword ptr [R11 + 0x8],RCX
00c53304  MOV qword ptr [RAX + 0x8],RDX
00c53308  MOV RCX,qword ptr [RSP + 0x1f0]
00c53310  MOV RAX,qword ptr [RCX + 0x80]
00c53317  MOV RBX,qword ptr [RCX + 0x88]
00c5331e  NOP
00c53320  CALL 0x00481ee0
00c53325  MOV qword ptr [RSP + 0x1f8],RAX
00c5332d  LEA RAX,[0xe16300]
00c53334  MOV RBX,qword ptr [RSP + 0x200]
00c5333c  LEA RCX,[0xf05a11]
00c53343  MOV EDI,0x9
00c53348  CALL 0x00413460
00c5334d  LEA RCX,[0xdd29c0]
00c53354  MOV qword ptr [RAX],RCX
00c53357  CMP dword ptr [0x019b5f00],0x0
00c5335e  NOP
00c53360  JNZ 0x00c5336c
00c53362  MOV RDX,qword ptr [RSP + 0x1f8]
00c5336a  JMP 0x00c53384
00c5336c  MOV RCX,qword ptr [RAX + 0x8]
00c53370  CALL 0x0048bc00
00c53375  MOV RDX,qword ptr [RSP + 0x1f8]
00c5337d  MOV qword ptr [R11],RDX
00c53380  MOV qword ptr [R11 + 0x8],RCX
00c53384  MOV qword ptr [RAX + 0x8],RDX
00c53388  MOV RCX,qword ptr [RSP + 0x1f0]
00c53390  MOV RAX,qword ptr [RCX + 0x90]
00c53397  CALL 0x00481e60
00c5339c  MOV qword ptr [RSP + 0x1f8],RAX
00c533a4  LEA RAX,[0xe16300]
00c533ab  MOV RBX,qword ptr [RSP + 0x200]
00c533b3  LEA RCX,[0xf05a1a]
00c533ba  MOV EDI,0x9
00c533bf  NOP
00c533c0  CALL 0x00413460
00c533c5  LEA RCX,[0xdd2b80]
00c533cc  MOV qword ptr [RAX],RCX
00c533cf  CMP dword ptr [0x019b5f00],0x0
00c533d6  JNZ 0x00c533e2
00c533d8  MOV RSI,qword ptr [RSP + 0x1f8]
00c533e0  JMP 0x00c533fa
00c533e2  MOV RDX,qword ptr [RAX + 0x8]
00c533e6  CALL 0x0048bc00
00c533eb  MOV RSI,qword ptr [RSP + 0x1f8]
00c533f3  MOV qword ptr [R11],RSI
00c533f6  MOV qword ptr [R11 + 0x8],RDX
00c533fa  MOV qword ptr [RAX + 0x8],RSI
00c533fe  MOV RDX,qword ptr [RSP + 0x1f0]
00c53406  MOVZX EDX,byte ptr [RDX + 0x98]
00c5340d  MOV qword ptr [RSP + 0x108],RDX
00c53415  LEA RAX,[0xe16300]
00c5341c  MOV RBX,qword ptr [RSP + 0x200]
00c53424  LEA RCX,[0xefe2c3]
00c5342b  MOV EDI,0x6
00c53430  CALL 0x00413460
00c53435  LEA RDX,[0xdd2dc0]
00c5343c  MOV qword ptr [RAX],RDX
00c5343f  MOV RDX,qword ptr [RSP + 0x108]
00c53447  LEA RSI,[0x115e2c0]
00c5344e  LEA RDX,[RSI + RDX*0x8]
00c53452  CMP dword ptr [0x019b5f00],0x0
00c53459  JZ 0x00c53468
00c5345b  MOV RSI,qword ptr [RAX + 0x8]
00c5345f  NOP
00c53460  CALL 0x0048bbe0
00c53465  MOV qword ptr [R11],RSI
00c53468  MOV qword ptr [RAX + 0x8],RDX
00c5346c  MOV RDX,qword ptr [RSP + 0x1f0]
00c53474  MOV RAX,qword ptr [RDX + 0xa0]
00c5347b  MOV RBX,qword ptr [RDX + 0xa8]
00c53482  MOV RCX,qword ptr [RDX + 0xb0]
00c53489  CALL 0x00481f80
00c5348e  MOV qword ptr [RSP + 0x1f8],RAX
00c53496  LEA RAX,[0xe16300]
00c5349d  MOV RBX,qword ptr [RSP + 0x200]
00c534a5  LEA RCX,[0xf05a47]
00c534ac  MOV EDI,0x9
00c534b1  CALL 0x00413460
00c534b6  LEA RDX,[0xdc15a0]
00c534bd  MOV qword ptr [RAX],RDX
00c534c0  CMP dword ptr [0x019b5f00],0x0
00c534c7  JNZ 0x00c534d3
00c534c9  MOV RDX,qword ptr [RSP + 0x1f8]
00c534d1  JMP 0x00c534eb
00c534d3  MOV RCX,qword ptr [RAX + 0x8]
00c534d7  CALL 0x0048bc00
00c534dc  MOV RDX,qword ptr [RSP + 0x1f8]
00c534e4  MOV qword ptr [R11],RDX
00c534e7  MOV qword ptr [R11 + 0x8],RCX
00c534eb  MOV qword ptr [RAX + 0x8],RDX
00c534ef  MOV RAX,qword ptr [RSP + 0x1a8]
00c534f7  MOV RBX,qword ptr [RSP + 0xd8]
00c534ff  NOP
00c53500  CALL 0x00481ee0
00c53505  MOV qword ptr [RSP + 0x1f8],RAX
00c5350d  LEA RAX,[0xe16300]
00c53514  MOV RBX,qword ptr [RSP + 0x200]
00c5351c  LEA RCX,[0xf02a69]
00c53523  MOV EDI,0x8
00c53528  CALL 0x00413460
00c5352d  LEA RCX,[0xdd29c0]
00c53534  MOV qword ptr [RAX],RCX
00c53537  CMP dword ptr [0x019b5f00],0x0
00c5353e  NOP
00c53540  JNZ 0x00c5354c
00c53542  MOV RSI,qword ptr [RSP + 0x1f8]
00c5354a  JMP 0x00c53564
00c5354c  MOV RDX,qword ptr [RAX + 0x8]
00c53550  CALL 0x0048bc00
00c53555  MOV RSI,qword ptr [RSP + 0x1f8]
00c5355d  MOV qword ptr [R11],RSI
00c53560  MOV qword ptr [R11 + 0x8],RDX
00c53564  MOV qword ptr [RAX + 0x8],RSI
00c53568  LEA RAX,[0xe16300]
00c5356f  MOV RBX,qword ptr [RSP + 0x200]
00c53577  LEA RCX,[0xeffe49]
00c5357e  MOV EDI,0x7
00c53583  CALL 0x00413460
00c53588  LEA RDX,[0xe16200]
00c5358f  MOV qword ptr [RAX],RDX
00c53592  CMP dword ptr [0x019b5f00],0x0
00c53599  JNZ 0x00c535a5
00c5359b  MOV RDX,qword ptr [RSP + 0x1d0]
00c535a3  JMP 0x00c535bd
00c535a5  MOV RCX,qword ptr [RAX + 0x8]
00c535a9  CALL 0x0048bc00
00c535ae  MOV RDX,qword ptr [RSP + 0x1d0]
00c535b6  MOV qword ptr [R11],RDX
00c535b9  MOV qword ptr [R11 + 0x8],RCX
00c535bd  MOV qword ptr [RAX + 0x8],RDX
00c535c1  MOV RCX,qword ptr [RSP + 0x1f0]
00c535c9  MOV RAX,qword ptr [RCX + 0x40]
00c535cd  MOV RBX,qword ptr [RCX + 0x48]
00c535d1  CALL 0x00481ee0
00c535d6  MOV qword ptr [RSP + 0x1f8],RAX
00c535de  LEA RAX,[0xe16300]
00c535e5  MOV RBX,qword ptr [RSP + 0x200]
00c535ed  LEA RCX,[0xf05a2c]
00c535f4  MOV EDI,0x9
00c535f9  CALL 0x00413460
00c535fe  LEA RCX,[0xdd29c0]
00c53605  MOV qword ptr [RAX],RCX
00c53608  CMP dword ptr [0x019b5f00],0x0
00c5360f  JNZ 0x00c5361b
00c53611  MOV RDX,qword ptr [RSP + 0x1f8]
00c53619  JMP 0x00c53634
00c5361b  MOV RCX,qword ptr [RAX + 0x8]
00c5361f  NOP
00c53620  CALL 0x0048bc00
00c53625  MOV RDX,qword ptr [RSP + 0x1f8]
00c5362d  MOV qword ptr [R11],RDX
00c53630  MOV qword ptr [R11 + 0x8],RCX
00c53634  MOV qword ptr [RAX + 0x8],RDX
00c53638  MOV RCX,qword ptr [RSP + 0x1f0]
00c53640  MOV RAX,qword ptr [RCX + 0x50]
00c53644  MOV RBX,qword ptr [RCX + 0x58]
00c53648  CALL 0x00481ee0
00c5364d  MOV qword ptr [RSP + 0x1f8],RAX
00c53655  LEA RAX,[0xe16300]
00c5365c  MOV RBX,qword ptr [RSP + 0x200]
00c53664  LEA RCX,[0xefe2b1]
00c5366b  MOV EDI,0x6
00c53670  CALL 0x00413460
00c53675  LEA RCX,[0xdd29c0]
00c5367c  MOV qword ptr [RAX],RCX
00c5367f  CMP dword ptr [0x019b5f00],0x0
00c53686  JNZ 0x00c53692
00c53688  MOV RSI,qword ptr [RSP + 0x1f8]
00c53690  JMP 0x00c536aa
00c53692  MOV RDX,qword ptr [RAX + 0x8]
00c53696  CALL 0x0048bc00
00c5369b  MOV RSI,qword ptr [RSP + 0x1f8]
00c536a3  MOV qword ptr [R11],RSI
00c536a6  MOV qword ptr [R11 + 0x8],RDX
00c536aa  MOV qword ptr [RAX + 0x8],RSI
00c536ae  LEA RAX,[RSP + 0x480]
00c536b6  LEA RBX,[0xe16300]
00c536bd  MOV RCX,qword ptr [RSP + 0x200]
00c536c5  CALL 0x0053fda0
00c536ca  ADD RSP,0x568
00c536d1  POP RBP
00c536d2  RET
00c536d3  MOV R10,RDI
00c536d6  AND RDI,R9
00c536d9  SHL RDI,0x4
00c536dd  MOV R12,qword ptr [R8 + RDI*0x1 + 0x8]
00c536e2  CMP R12,RBX
00c536e5  JZ 0x00c53705
00c536e7  LEA RDI,[R10 + 0x1]
00c536eb  TEST R12,R12
00c536ee  JNZ 0x00c536d3
00c536f0  LEA RAX,[0x1974060]
00c536f7  CALL 0x0041e320
00c536fc  MOV RDI,RAX
00c536ff  NOP
00c53700  JMP 0x00c5305d
00c53705  MOV RDI,qword ptr [R8 + RDI*0x1 + 0x10]
00c5370a  JMP 0x00c5305d
00c5370f  MOV qword ptr [RSP + 0x218],RDX
00c53717  LEA RAX,[0xeba560]
00c5371e  NOP
00c53720  CALL 0x00421f00
00c53725  MOV RCX,qword ptr [RSP + 0x218]
00c5372d  MOV qword ptr [RAX],RCX
00c53730  CMP dword ptr [0x019b5f00],0x0
00c53737  JNZ 0x00c53743
00c53739  MOV RDX,qword ptr [RSP + 0x1a0]
00c53741  JMP 0x00c53753
00c53743  CALL 0x0048bbe0
00c53748  MOV RDX,qword ptr [RSP + 0x1a0]
00c53750  MOV qword ptr [R11],RDX
00c53753  MOV qword ptr [RAX + 0x8],RDX
00c53757  LEA RBX,[0xdc0fa0]
00c5375e  MOV RCX,qword ptr [RSP + 0x560]
00c53766  CALL 0x0053f680
00c5376b  TEST RAX,RAX
00c5376e  JZ 0x00c537c6
00c53770  MOV RDX,qword ptr [RSP + 0x58]
00c53775  MOV RDI,qword ptr [RSP + 0x98]
00c5377d  MOV RBX,qword ptr [RSP + 0x50]
00c53782  MOV RAX,qword ptr [RSP + 0x70]
00c53787  MOV R11,qword ptr [RSP + 0x68]
00c5378c  MOV R13,qword ptr [RSP + 0x60]
00c53791  MOV RCX,qword ptr [RSP + 0x118]
00c53799  MOV R9,qword ptr [RSP + 0x158]
00c537a1  MOV RSI,qword ptr [RSP + 0x110]
00c537a9  MOV R10,qword ptr [RSP + 0x130]
00c537b1  MOV R12,qword ptr [RSP + 0x128]
00c537b9  MOV R15,qword ptr [RSP + 0x120]
00c537c1  JMP 0x00c538a2
00c537c6  MOV R9,qword ptr [RSP + 0x560]
00c537ce  MOV R10,qword ptr [R9 + 0x8]
00c537d2  MOV R11,qword ptr [R9]
00c537d5  MOV R12,qword ptr [R9 + 0x18]
00c537d9  MOV R13,qword ptr [R9 + 0x10]
00c537dd  MOV R15,qword ptr [R9 + 0x28]
00c537e1  MOV RAX,qword ptr [R9 + 0x20]
00c537e5  MOV RCX,qword ptr [R9 + 0x38]
00c537e9  MOV RDX,qword ptr [R9 + 0x30]
00c537ed  MOV RBX,qword ptr [R9 + 0x48]
00c537f1  MOV RSI,qword ptr [R9 + 0x40]
00c537f5  MOV RDI,qword ptr [R9 + 0x58]
00c537f9  MOV R9,qword ptr [R9 + 0x50]
00c537fd  TEST R10,R10
00c53800  MOV R8,R9
00c53803  MOV R9,qword ptr [RSP + 0x70]
00c53808  CMOVNZ R9,R10
00c5380c  MOV R10,qword ptr [RSP + 0x130]
00c53814  CMOVNZ R10,R11
00c53818  TEST R12,R12
00c5381b  MOV R11,qword ptr [RSP + 0x68]
00c53820  CMOVNZ R11,R12
00c53824  MOV R12,qword ptr [RSP + 0x128]
00c5382c  CMOVNZ R12,R13
00c53830  TEST R15,R15
00c53833  MOV R13,qword ptr [RSP + 0x60]
00c53838  CMOVNZ R13,R15
00c5383c  MOV R15,qword ptr [RSP + 0x120]
00c53844  CMOVNZ R15,RAX
00c53848  TEST RCX,RCX
00c5384b  MOV RAX,R9
00c5384e  MOV R9,qword ptr [RSP + 0x58]
00c53853  CMOVNZ R9,RCX
00c53857  MOV RCX,qword ptr [RSP + 0x118]
00c5385f  CMOVNZ RCX,RDX
00c53863  TEST RBX,RBX
00c53866  MOV RDX,R9
00c53869  MOV R9,qword ptr [RSP + 0x50]
00c5386e  CMOVNZ R9,RBX
00c53872  MOV RBX,R9
00c53875  MOV R9,qword ptr [RSP + 0x110]
00c5387d  CMOVNZ R9,RSI
00c53881  TEST RDI,RDI
00c53884  MOV RSI,R9
00c53887  MOV R9,qword ptr [RSP + 0x98]
00c5388f  CMOVNZ R9,RDI
00c53893  MOV RDI,R9
00c53896  MOV R9,qword ptr [RSP + 0x158]
00c5389e  CMOVNZ R9,R8
00c538a2  MOV R8,R9
00c538a5  MOV R9,RAX
00c538a8  MOV RAX,R11
00c538ab  MOV R11,R13
00c538ae  MOV R13,R15
00c538b1  MOV R15,RCX
00c538b4  MOV RCX,R12
00c538b7  MOV R12,R15
00c538ba  MOV R15,RBX
00c538bd  MOV RBX,R10
00c538c0  MOV R10,RDX
00c538c3  MOV RDX,RSI
00c538c6  MOV RSI,R15
00c538c9  JMP 0x00c51af4
00c538ce  MOV R8,RDX
00c538d1  AND RDX,RDI
00c538d4  SHL RDX,0x4
00c538d8  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
00c538dd  NOP dword ptr [RAX]
00c538e0  CMP R9,RBX
00c538e3  JZ 0x00c53905
00c538e5  LEA RDX,[R8 + 0x1]
00c538e9  TEST R9,R9
00c538ec  JNZ 0x00c538ce
00c538ee  LEA RAX,[0x1974040]
00c538f5  CALL 0x0041e320
00c538fa  MOV RDX,RAX
00c538fd  NOP dword ptr [RAX]
00c53900  JMP 0x00c5370f
00c53905  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
00c5390a  JMP 0x00c5370f
00c5390f  MOV qword ptr [RSP + 0x8],RAX
00c53914  MOV qword ptr [RSP + 0x10],RBX
00c53919  MOV qword ptr [RSP + 0x18],RCX
00c5391e  NOP
00c53920  CALL 0x0048a280
00c53925  MOV RAX,qword ptr [RSP + 0x8]
00c5392a  MOV RBX,qword ptr [RSP + 0x10]
00c5392f  MOV RCX,qword ptr [RSP + 0x18]
00c53934  JMP 0x00c515a0
