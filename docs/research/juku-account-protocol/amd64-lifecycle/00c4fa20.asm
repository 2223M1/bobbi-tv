; main.handleUserPlay
00c4fa20  LEA R12,[RSP + -0x250]
00c4fa28  CMP R12,qword ptr [R14 + 0x10]
00c4fa2c  JBE 0x00c50a1f
00c4fa32  PUSH RBP
00c4fa33  MOV RBP,RSP
00c4fa36  SUB RSP,0x2c8
00c4fa3d  MOV qword ptr [RSP + 0x2e8],RCX
00c4fa45  MOV qword ptr [RSP + 0x2e0],RBX
00c4fa4d  MOV qword ptr [RSP + 0x2d8],RAX
00c4fa55  MOV RCX,qword ptr [RAX + 0x18]
00c4fa59  MOV RAX,RBX
00c4fa5c  CALL RCX
00c4fa5e  MOV qword ptr [RSP + 0x138],RAX
00c4fa66  NOP
00c4fa67  LEA RAX,[0xf10b4b]
00c4fa6e  MOV EBX,0xc
00c4fa73  CALL 0x00640c00
00c4fa78  MOV qword ptr [RSP + 0x168],RAX
00c4fa80  MOV qword ptr [RSP + 0xd8],RBX
00c4fa88  LEA RAX,[0xddc380]
00c4fa8f  CALL 0x00421f00
00c4fa94  MOV qword ptr [RSP + 0x160],RAX
00c4fa9c  MOV qword ptr [RAX + 0x8],0x10
00c4faa4  LEA RCX,[0xf195fc]
00c4faab  MOV qword ptr [RAX],RCX
00c4faae  LEA RAX,[0xe91b20]
00c4fab5  MOV RBX,qword ptr [RSP + 0x138]
00c4fabd  MOV RCX,qword ptr [RSP + 0x168]
00c4fac5  MOV RDI,qword ptr [RSP + 0xd8]
00c4facd  CALL 0x00413460
00c4fad2  MOV qword ptr [RAX + 0x8],0x1
00c4fada  MOV qword ptr [RAX + 0x10],0x1
00c4fae2  CMP dword ptr [0x019b5f00],0x0
00c4fae9  JNZ 0x00c4faf5
00c4faeb  MOV RDX,qword ptr [RSP + 0x160]
00c4faf3  JMP 0x00c4fb0c
00c4faf5  MOV RCX,qword ptr [RAX]
00c4faf8  CALL 0x0048bc00
00c4fafd  MOV RDX,qword ptr [RSP + 0x160]
00c4fb05  MOV qword ptr [R11],RDX
00c4fb08  MOV qword ptr [R11 + 0x8],RCX
00c4fb0c  MOV qword ptr [RAX],RDX
00c4fb0f  MOV RAX,qword ptr [RSP + 0x2e8]
00c4fb17  CALL 0x00c4bd40
00c4fb1c  MOV qword ptr [RSP + 0xf8],RAX
00c4fb24  MOV qword ptr [RSP + 0x70],RBX
00c4fb29  MOV RAX,qword ptr [0x0196cdc0]
00c4fb30  CALL 0x00aa6620
00c4fb35  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fb3d  MOV RAX,qword ptr [RCX + 0x10]
00c4fb41  CALL 0x005bb0e0
00c4fb46  MOV RBX,RAX
00c4fb49  LEA RCX,[0xf02a51]
00c4fb50  MOV EDI,0x8
00c4fb55  LEA RAX,[0xe9bd40]
00c4fb5c  NOP dword ptr [RAX]
00c4fb60  CALL 0x00412ee0
00c4fb65  CMP qword ptr [RAX + 0x8],0x0
00c4fb6a  JNZ 0x00c4fb72
00c4fb6c  XOR EDX,EDX
00c4fb6e  XOR ECX,ECX
00c4fb70  JMP 0x00c4fb7c
00c4fb72  MOV RCX,qword ptr [RAX]
00c4fb75  MOV RDX,qword ptr [RCX + 0x8]
00c4fb79  MOV RCX,qword ptr [RCX]
00c4fb7c  MOV RAX,RCX
00c4fb7f  MOV RBX,RDX
00c4fb82  CALL 0x00c47f20
00c4fb87  MOV qword ptr [RSP + 0x118],RAX
00c4fb8f  MOV qword ptr [RSP + 0x88],RBX
00c4fb97  MOV RCX,qword ptr [0x019900d0]
00c4fb9e  MOV RDI,RBX
00c4fba1  MOV RBX,RCX
00c4fba4  MOV RCX,RAX
00c4fba7  LEA RAX,[0xe17280]
00c4fbae  CALL 0x004131a0
00c4fbb3  MOV RCX,qword ptr [RAX]
00c4fbb6  MOV RDX,qword ptr [RAX + 0x8]
00c4fbba  NOP word ptr [RAX + RAX*0x1]
00c4fbc0  TEST BL,BL
00c4fbc2  JZ 0x00c5092e
00c4fbc8  MOV qword ptr [RSP + 0x90],RCX
00c4fbd0  MOV qword ptr [RSP + 0x120],RDX
00c4fbd8  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fbe0  MOV RAX,qword ptr [RCX + 0x10]
00c4fbe4  CALL 0x005bb0e0
00c4fbe9  MOV RBX,RAX
00c4fbec  LEA RCX,[0xeffe2d]
00c4fbf3  MOV EDI,0x7
00c4fbf8  LEA RAX,[0xe9bd40]
00c4fbff  NOP
00c4fc00  CALL 0x00412ee0
00c4fc05  CMP qword ptr [RAX + 0x8],0x0
00c4fc0a  JNZ 0x00c4fc12
00c4fc0c  XOR ECX,ECX
00c4fc0e  XOR EDX,EDX
00c4fc10  JMP 0x00c4fc1c
00c4fc12  MOV RCX,qword ptr [RAX]
00c4fc15  MOV RDX,qword ptr [RCX + 0x8]
00c4fc19  MOV RCX,qword ptr [RCX]
00c4fc1c  MOV qword ptr [RSP + 0x60],RDX
00c4fc21  MOV qword ptr [RSP + 0xf0],RCX
00c4fc29  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fc31  MOV RAX,qword ptr [RCX + 0x10]
00c4fc35  CALL 0x005bb0e0
00c4fc3a  MOV RBX,RAX
00c4fc3d  LEA RCX,[0xefc947]
00c4fc44  MOV EDI,0x5
00c4fc49  LEA RAX,[0xe9bd40]
00c4fc50  CALL 0x00412ee0
00c4fc55  CMP qword ptr [RAX + 0x8],0x0
00c4fc5a  JNZ 0x00c4fc62
00c4fc5c  XOR EDX,EDX
00c4fc5e  XOR ECX,ECX
00c4fc60  JMP 0x00c4fc6c
00c4fc62  MOV RCX,qword ptr [RAX]
00c4fc65  MOV RDX,qword ptr [RCX + 0x8]
00c4fc69  MOV RCX,qword ptr [RCX]
00c4fc6c  MOV qword ptr [RSP + 0x58],RDX
00c4fc71  MOV qword ptr [RSP + 0xe8],RCX
00c4fc79  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fc81  MOV RAX,qword ptr [RCX + 0x10]
00c4fc85  CALL 0x005bb0e0
00c4fc8a  MOV RBX,RAX
00c4fc8d  LEA RCX,[0xf05a11]
00c4fc94  MOV EDI,0x9
00c4fc99  LEA RAX,[0xe9bd40]
00c4fca0  CALL 0x00412ee0
00c4fca5  CMP qword ptr [RAX + 0x8],0x0
00c4fcaa  JNZ 0x00c4fcb2
00c4fcac  XOR EDX,EDX
00c4fcae  XOR ECX,ECX
00c4fcb0  JMP 0x00c4fcbc
00c4fcb2  MOV RCX,qword ptr [RAX]
00c4fcb5  MOV RDX,qword ptr [RCX + 0x8]
00c4fcb9  MOV RCX,qword ptr [RCX]
00c4fcbc  MOV qword ptr [RSP + 0x50],RDX
00c4fcc1  MOV qword ptr [RSP + 0xe0],RCX
00c4fcc9  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fcd1  MOV RAX,qword ptr [RCX + 0x10]
00c4fcd5  CALL 0x005bb0e0
00c4fcda  MOV RBX,RAX
00c4fcdd  LEA RCX,[0xf05a1a]
00c4fce4  MOV EDI,0x9
00c4fce9  LEA RAX,[0xe9bd40]
00c4fcf0  CALL 0x00412ee0
00c4fcf5  CMP qword ptr [RAX + 0x8],0x0
00c4fcfa  JNZ 0x00c4fd02
00c4fcfc  XOR EDX,EDX
00c4fcfe  XOR ECX,ECX
00c4fd00  JMP 0x00c4fd0c
00c4fd02  MOV RCX,qword ptr [RAX]
00c4fd05  MOV RDX,qword ptr [RCX + 0x8]
00c4fd09  MOV RCX,qword ptr [RCX]
00c4fd0c  TEST RDX,RDX
00c4fd0f  JNZ 0x00c4fd5c
00c4fd11  MOV RCX,qword ptr [RSP + 0x2e8]
00c4fd19  MOV RAX,qword ptr [RCX + 0x10]
00c4fd1d  NOP dword ptr [RAX]
00c4fd20  CALL 0x005bb0e0
00c4fd25  MOV RBX,RAX
00c4fd28  LEA RCX,[0xefb5a3]
00c4fd2f  MOV EDI,0x4
00c4fd34  LEA RAX,[0xe9bd40]
00c4fd3b  NOP dword ptr [RAX + RAX*0x1]
00c4fd40  CALL 0x00412ee0
00c4fd45  CMP qword ptr [RAX + 0x8],0x0
00c4fd4a  JNZ 0x00c4fd52
00c4fd4c  XOR EDX,EDX
00c4fd4e  XOR ECX,ECX
00c4fd50  JMP 0x00c4fd5c
00c4fd52  MOV RCX,qword ptr [RAX]
00c4fd55  MOV RDX,qword ptr [RCX + 0x8]
00c4fd59  MOV RCX,qword ptr [RCX]
00c4fd5c  MOV qword ptr [RSP + 0xa8],RDX
00c4fd64  MOV qword ptr [RSP + 0x140],RCX
00c4fd6c  LEA RAX,[0xdd2b80]
00c4fd73  CALL 0x00421f00
00c4fd78  MOV qword ptr [RSP + 0x2c0],RAX
00c4fd80  MOV RCX,qword ptr [RSP + 0xa8]
00c4fd88  TEST RCX,RCX
00c4fd8b  JZ 0x00c4fe2d
00c4fd91  LEA RAX,[0xdd29c0]
00c4fd98  CALL 0x00421f00
00c4fd9d  LEA RCX,[0xdb4420]
00c4fda4  MOV qword ptr [RSP + 0x230],RCX
00c4fdac  MOV RCX,qword ptr [RSP + 0x2c0]
00c4fdb4  MOV qword ptr [RSP + 0x238],RCX
00c4fdbc  MOV RDX,qword ptr [RSP + 0xa8]
00c4fdc4  MOV qword ptr [RAX + 0x8],RDX
00c4fdc8  CMP dword ptr [0x019b5f00],0x0
00c4fdcf  JNZ 0x00c4fddb
00c4fdd1  MOV R10,qword ptr [RSP + 0x140]
00c4fdd9  JMP 0x00c4fdf4
00c4fddb  MOV RDX,qword ptr [RAX]
00c4fdde  NOP
00c4fde0  CALL 0x0048bc00
00c4fde5  MOV R10,qword ptr [RSP + 0x140]
00c4fded  MOV qword ptr [R11],R10
00c4fdf0  MOV qword ptr [R11 + 0x8],RDX
00c4fdf4  MOV qword ptr [RAX],R10
00c4fdf7  MOV RBX,RAX
00c4fdfa  LEA RCX,[0xefa6de]
00c4fe01  MOV EDI,0x2
00c4fe06  LEA RSI,[RSP + 0x230]
00c4fe0e  MOV R8D,0x1
00c4fe14  MOV R9,R8
00c4fe17  LEA RAX,[0x1139840]
00c4fe1e  NOP
00c4fe20  CALL 0x0050c620
00c4fe25  MOV RAX,qword ptr [RSP + 0x2c0]
00c4fe2d  MOV RDX,qword ptr [RSP + 0x58]
00c4fe32  TEST RDX,RDX
00c4fe35  JNZ 0x00c4fe85
00c4fe37  CMP qword ptr [0x019900b0],0x0
00c4fe3f  NOP
00c4fe40  JNZ 0x00c4fe4c
00c4fe42  MOV RCX,qword ptr [RSP + 0xe8]
00c4fe4a  JMP 0x00c4fe8d
00c4fe4c  MOV RCX,qword ptr [RSP + 0x90]
00c4fe54  MOV RCX,qword ptr [RCX + 0x28]
00c4fe58  MOV RAX,qword ptr [RSP + 0x120]
00c4fe60  CALL RCX
00c4fe62  MOV RCX,qword ptr [0x019900b0]
00c4fe69  MOV RDX,RAX
00c4fe6c  MOV RAX,RCX
00c4fe6f  MOV RSI,RBX
00c4fe72  MOV RBX,RDX
00c4fe75  MOV RCX,RSI
00c4fe78  CALL 0x00a63de0
00c4fe7d  MOV RCX,RAX
00c4fe80  MOV RDX,RBX
00c4fe83  JMP 0x00c4fe8d
00c4fe85  MOV RCX,qword ptr [RSP + 0xe8]
00c4fe8d  MOV qword ptr [RSP + 0x78],RDX
00c4fe92  MOV qword ptr [RSP + 0x100],RCX
00c4fe9a  MOV R10,qword ptr [RSP + 0x90]
00c4fea2  MOV R10,qword ptr [R10 + 0x40]
00c4fea6  MOV RAX,qword ptr [RSP + 0x120]
00c4feae  MOV RBX,qword ptr [RSP + 0xf0]
00c4feb6  MOV RDI,RCX
00c4feb9  MOV RSI,RDX
00c4febc  MOV R8,qword ptr [RSP + 0xf8]
00c4fec4  MOV R9,qword ptr [RSP + 0x70]
00c4fec9  MOV RCX,qword ptr [RSP + 0x60]
00c4fece  CALL R10
00c4fed1  TEST RBX,RBX
00c4fed4  JNZ 0x00c507ff
00c4feda  MOV qword ptr [RSP + 0x110],RAX
00c4fee2  MOV RBX,qword ptr [RAX + 0x20]
00c4fee6  TEST RBX,RBX
00c4fee9  JZ 0x00c4ff33
00c4feeb  MOV RDX,qword ptr [RAX + 0x18]
00c4feef  MOV RCX,qword ptr [RAX + 0x28]
00c4fef3  MOV RDI,qword ptr [RAX + 0x10]
00c4fef7  MOV RAX,RDX
00c4fefa  CALL 0x00c487e0
00c4feff  MOV RDX,qword ptr [RSP + 0x110]
00c4ff07  MOV qword ptr [RDX + 0x20],RBX
00c4ff0b  MOV qword ptr [RDX + 0x28],RCX
00c4ff0f  CMP dword ptr [0x019b5f00],0x0
00c4ff16  JZ 0x00c4ff2c
00c4ff18  MOV RSI,qword ptr [RDX + 0x18]
00c4ff1c  NOP dword ptr [RAX]
00c4ff20  CALL 0x0048bc00
00c4ff25  MOV qword ptr [R11],RAX
00c4ff28  MOV qword ptr [R11 + 0x8],RSI
00c4ff2c  MOV qword ptr [RDX + 0x18],RAX
00c4ff30  MOV RAX,RDX
00c4ff33  MOV RBX,qword ptr [RAX + 0x8]
00c4ff37  NOP word ptr [RAX + RAX*0x1]
00c4ff40  TEST RBX,RBX
00c4ff43  JZ 0x00c507d3
00c4ff49  MOV RAX,qword ptr [RAX]
00c4ff4c  CALL 0x004af740
00c4ff51  MOV qword ptr [RSP + 0x128],RAX
00c4ff59  MOV qword ptr [RSP + 0x98],RBX
00c4ff61  LEA RAX,[RSP + 0x260]
00c4ff69  MOVUPS xmmword ptr [RAX],XMM15
00c4ff6d  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c4ff72  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c4ff77  MOV RCX,qword ptr [RSP + 0x110]
00c4ff7f  MOV RDX,qword ptr [RCX]
00c4ff82  MOV RCX,qword ptr [RCX + 0x8]
00c4ff86  MOV qword ptr [RSP + 0x268],RCX
00c4ff8e  MOV qword ptr [RSP + 0x260],RDX
00c4ff96  MOV RCX,qword ptr [RSP + 0x50]
00c4ff9b  MOV qword ptr [RSP + 0x278],RCX
00c4ffa3  MOV RCX,qword ptr [RSP + 0xe0]
00c4ffab  MOV qword ptr [RSP + 0x270],RCX
00c4ffb3  MOV RCX,qword ptr [RSP + 0x60]
00c4ffb8  MOV qword ptr [RSP + 0x288],RCX
00c4ffc0  MOV RCX,qword ptr [RSP + 0xf0]
00c4ffc8  MOV qword ptr [RSP + 0x280],RCX
00c4ffd0  MOV EBX,0x3
00c4ffd5  MOV RCX,RBX
00c4ffd8  CALL 0x00c4b580
00c4ffdd  MOV qword ptr [RSP + 0x148],RAX
00c4ffe5  MOV qword ptr [RSP + 0xb8],RBX
00c4ffed  MOV RCX,qword ptr [RSP + 0x110]
00c4fff5  MOV RAX,qword ptr [RCX + 0x38]
00c4fff9  MOV RBX,qword ptr [RCX + 0x40]
00c4fffd  NOP dword ptr [RAX]
00c50000  CALL 0x00c4b980
00c50005  TEST CL,CL
00c50007  JNZ 0x00c50019
00c50009  MOV RAX,qword ptr [RSP + 0x148]
00c50011  MOV RBX,qword ptr [RSP + 0xb8]
00c50019  MOV qword ptr [RSP + 0xb8],RBX
00c50021  MOV qword ptr [RSP + 0x148],RAX
00c50029  MOV RCX,qword ptr [RSP + 0x90]
00c50031  MOV RCX,qword ptr [RCX + 0x28]
00c50035  MOV RAX,qword ptr [RSP + 0x120]
00c5003d  CALL RCX
00c5003f  NOP
00c50040  CMP RBX,0x8
00c50044  JNZ 0x00c50058
00c50046  MOV RDX,0x35313144554f4c43
00c50050  CMP qword ptr [RAX],RDX
00c50053  SETZ DL
00c50056  JMP 0x00c5005a
00c50058  XOR EDX,EDX
00c5005a  MOV byte ptr [RSP + 0x4f],DL
00c5005e  MOV RAX,qword ptr [RSP + 0x128]
00c50066  MOV RBX,qword ptr [RSP + 0x98]
00c5006e  LEA RCX,[0xefc93d]
00c50075  MOV EDI,0x5
00c5007a  CALL 0x00414f60
00c5007f  NOP
00c50080  TEST RAX,RAX
00c50083  JL 0x00c5008c
00c50085  MOV EDX,0x1
00c5008a  JMP 0x00c500b3
00c5008c  MOV RAX,qword ptr [RSP + 0x128]
00c50094  MOV RBX,qword ptr [RSP + 0x98]
00c5009c  LEA RCX,[0xefb52f]
00c500a3  MOV EDI,0x4
00c500a8  CALL 0x00414f60
00c500ad  TEST RAX,RAX
00c500b0  SETGE DL
00c500b3  MOV byte ptr [RSP + 0x4e],DL
00c500b7  MOVZX ESI,byte ptr [RSP + 0x4f]
00c500bc  NOP dword ptr [RAX]
00c500c0  TEST SIL,SIL
00c500c3  JNZ 0x00c500cd
00c500c5  TEST DL,DL
00c500c7  JZ 0x00c50172
00c500cd  NOP
00c500ce  LEA RDI,[RSP + 0x290]
00c500d6  MOVUPS xmmword ptr [RDI],XMM15
00c500da  MOVUPS xmmword ptr [RDI + 0x10],XMM15
00c500df  MOVUPS xmmword ptr [RDI + 0x20],XMM15
00c500e4  LEA RDX,[0xc50c20]
00c500eb  MOV qword ptr [RSP + 0x290],RDX
00c500f3  MOV qword ptr [RSP + 0x2a0],0x68
00c500ff  LEA RDX,[0xf60983]
00c50106  MOV qword ptr [RSP + 0x298],RDX
00c5010e  MOV RAX,qword ptr [0x01990148]
00c50115  XOR EBX,EBX
00c50117  MOV ECX,0x2
00c5011c  NOP dword ptr [RAX]
00c50120  CALL 0x0054d540
00c50125  MOVZX EDX,byte ptr [RSP + 0x4e]
00c5012a  TEST DL,DL
00c5012c  JZ 0x00c50165
00c5012e  CMP dword ptr [0x019b5f00],0x0
00c50135  JNZ 0x00c50142
00c50137  MOV RCX,qword ptr [RSP + 0x110]
00c5013f  NOP
00c50140  JMP 0x00c50156
00c50142  MOV RCX,qword ptr [RSP + 0x110]
00c5014a  MOV RDX,qword ptr [RCX + 0x10]
00c5014e  CALL 0x0048bbe0
00c50153  MOV qword ptr [R11],RDX
00c50156  MOV qword ptr [RCX + 0x10],0x0
00c5015e  NOP
00c50160  JMP 0x00c507d0
00c50165  MOV RCX,qword ptr [RSP + 0x110]
00c5016d  JMP 0x00c507d0
00c50172  MOV RDX,qword ptr [RSP + 0x110]
00c5017a  MOV RSI,qword ptr [RDX + 0x30]
00c5017e  NOP
00c50180  TEST RSI,RSI
00c50183  JG 0x00c50262
00c50189  MOV RSI,qword ptr [RSP + 0x2c0]
00c50191  MOV RAX,qword ptr [RSI]
00c50194  TEST RAX,RAX
00c50197  JLE 0x00c50245
00c5019d  MOV qword ptr [RSP + 0xd0],RAX
00c501a5  MOVUPS xmmword ptr [RSP + 0x200],XMM15
00c501ae  CALL 0x00481e60
00c501b3  LEA RCX,[0xdd2b80]
00c501ba  MOV qword ptr [RSP + 0x200],RCX
00c501c2  MOV qword ptr [RSP + 0x208],RAX
00c501ca  LEA RCX,[0xc50bc0]
00c501d1  MOV qword ptr [RSP + 0x290],RCX
00c501d9  MOV qword ptr [RSP + 0x2a0],0x2e
00c501e5  LEA RCX,[0xf41e70]
00c501ec  MOV qword ptr [RSP + 0x298],RCX
00c501f4  MOV qword ptr [RSP + 0x2b0],0x1
00c50200  MOV qword ptr [RSP + 0x2b8],0x1
00c5020c  LEA RCX,[RSP + 0x200]
00c50214  MOV qword ptr [RSP + 0x2a8],RCX
00c5021c  MOV RAX,qword ptr [0x01990148]
00c50223  XOR EBX,EBX
00c50225  MOV ECX,0x2
00c5022a  LEA RDI,[RSP + 0x290]
00c50232  CALL 0x0054d540
00c50237  MOV RAX,qword ptr [RSP + 0xd0]
00c5023f  XOR EBX,EBX
00c50241  XOR ECX,ECX
00c50243  JMP 0x00c50255
00c50245  MOV RBX,qword ptr [RDX + 0x8]
00c50249  MOV RAX,qword ptr [RDX]
00c5024c  MOV RCX,qword ptr [RDX + 0x10]
00c50250  CALL 0x00a9f520
00c50255  MOV RDX,qword ptr [RSP + 0x110]
00c5025d  MOV RSI,RAX
00c50260  JMP 0x00c50266
00c50262  XOR EBX,EBX
00c50264  XOR ECX,ECX
00c50266  MOV qword ptr [RSP + 0x108],RCX
00c5026e  MOV qword ptr [RSP + 0x80],RBX
00c50276  TEST RBX,RBX
00c50279  JNZ 0x00c50289
00c5027b  NOP dword ptr [RAX + RAX*0x1]
00c50280  TEST RSI,RSI
00c50283  JG 0x00c5038a
00c50289  LEA RCX,[RSP + 0x1d0]
00c50291  MOVUPS xmmword ptr [RCX],XMM15
00c50295  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c5029a  MOVUPS xmmword ptr [RCX + 0x20],XMM15
00c5029f  MOV RAX,RSI
00c502a2  CALL 0x00481e60
00c502a7  LEA RCX,[0xdd2b80]
00c502ae  MOV qword ptr [RSP + 0x1d0],RCX
00c502b6  MOV qword ptr [RSP + 0x1d8],RAX
00c502be  MOV RCX,qword ptr [RSP + 0x80]
00c502c6  TEST RCX,RCX
00c502c9  JZ 0x00c502d1
00c502cb  MOV RBX,qword ptr [RCX + 0x8]
00c502cf  JMP 0x00c502d4
00c502d1  MOV RBX,RCX
00c502d4  MOV qword ptr [RSP + 0x1e0],RBX
00c502dc  MOV RCX,qword ptr [RSP + 0x108]
00c502e4  MOV qword ptr [RSP + 0x1e8],RCX
00c502ec  MOV RAX,qword ptr [RSP + 0xf0]
00c502f4  MOV RBX,qword ptr [RSP + 0x60]
00c502f9  CALL 0x00481ee0
00c502fe  LEA RCX,[0xdd29c0]
00c50305  MOV qword ptr [RSP + 0x1f0],RCX
00c5030d  MOV qword ptr [RSP + 0x1f8],RAX
00c50315  LEA RCX,[0xc50b60]
00c5031c  MOV qword ptr [RSP + 0x290],RCX
00c50324  MOV qword ptr [RSP + 0x2a0],0x6d
00c50330  LEA RCX,[0xf61fdc]
00c50337  MOV qword ptr [RSP + 0x298],RCX
00c5033f  MOV qword ptr [RSP + 0x2b0],0x3
00c5034b  MOV qword ptr [RSP + 0x2b8],0x3
00c50357  LEA RCX,[RSP + 0x1d0]
00c5035f  MOV qword ptr [RSP + 0x2a8],RCX
00c50367  MOV RAX,qword ptr [0x01990148]
00c5036e  XOR EBX,EBX
00c50370  MOV ECX,0x2
00c50375  LEA RDI,[RSP + 0x290]
00c5037d  NOP dword ptr [RAX]
00c50380  CALL 0x0054d540
00c50385  MOV ESI,0x80000000
00c5038a  MOV qword ptr [RSP + 0xb0],RSI
00c50392  MOV RCX,qword ptr [RSP + 0x90]
00c5039a  MOV RCX,qword ptr [RCX + 0x28]
00c5039e  MOV RAX,qword ptr [RSP + 0x120]
00c503a6  CALL RCX
00c503a8  CMP RBX,0x6
00c503ac  JNZ 0x00c503c5
00c503ae  CMP dword ptr [RAX],0x59494c41
00c503b4  JNZ 0x00c503c5
00c503b6  CMP word ptr [RAX + 0x4],0x4e55
00c503bc  JNZ 0x00c503c5
00c503be  MOV EAX,0x20
00c503c3  JMP 0x00c50402
00c503c5  MOV RCX,qword ptr [RSP + 0x90]
00c503cd  MOV RCX,qword ptr [RCX + 0x28]
00c503d1  MOV RAX,qword ptr [RSP + 0x120]
00c503d9  CALL RCX
00c503db  NOP dword ptr [RAX + RAX*0x1]
00c503e0  CMP RBX,0x6
00c503e4  JNZ 0x00c503fd
00c503e6  CMP dword ptr [RAX],0x4c4e5558
00c503ec  JNZ 0x00c503fd
00c503ee  CMP word ptr [RAX + 0x4],0x4945
00c503f4  JNZ 0x00c503fd
00c503f6  MOV EAX,0x10
00c503fb  JMP 0x00c50402
00c503fd  MOV EAX,0x8
00c50402  CMP qword ptr [0x019900b8],0x0
00c5040a  JZ 0x00c5043d
00c5040c  MOV RCX,qword ptr [RSP + 0x90]
00c50414  MOV RCX,qword ptr [RCX + 0x28]
00c50418  MOV RAX,qword ptr [RSP + 0x120]
00c50420  CALL RCX
00c50422  MOV RCX,qword ptr [0x019900b8]
00c50429  MOV RDX,RAX
00c5042c  MOV RAX,RCX
00c5042f  MOV RSI,RBX
00c50432  MOV RBX,RDX
00c50435  MOV RCX,RSI
00c50438  CALL 0x009e7e60
00c5043d  MOV qword ptr [RSP + 0xc8],RAX
00c50445  CMP qword ptr [0x01990188],0x0
00c5044d  JNZ 0x00c50453
00c5044f  XOR ECX,ECX
00c50451  JMP 0x00c50488
00c50453  MOV RCX,qword ptr [RSP + 0x90]
00c5045b  MOV RCX,qword ptr [RCX + 0x28]
00c5045f  MOV RAX,qword ptr [RSP + 0x120]
00c50467  CALL RCX
00c50469  MOV RCX,qword ptr [0x01990188]
00c50470  MOV RDX,RAX
00c50473  MOV RAX,RCX
00c50476  MOV RSI,RBX
00c50479  MOV RBX,RDX
00c5047c  MOV RCX,RSI
00c5047f  NOP
00c50480  CALL 0x009b86c0
00c50485  MOV RCX,RAX
00c50488  MOV qword ptr [RSP + 0x68],RCX
00c5048d  LEA RAX,[0xe8d700]
00c50494  CALL 0x00421f00
00c50499  LEA RCX,[0xc50a60]
00c504a0  MOV qword ptr [RAX],RCX
00c504a3  MOV RCX,qword ptr [RSP + 0x78]
00c504a8  MOV qword ptr [RAX + 0x10],RCX
00c504ac  CMP dword ptr [0x019b5f00],0x0
00c504b3  JNZ 0x00c504d7
00c504b5  MOV RDX,qword ptr [RSP + 0x100]
00c504bd  MOV R12,qword ptr [RSP + 0x120]
00c504c5  MOV R13,qword ptr [RSP + 0xf0]
00c504cd  MOV R15,qword ptr [RSP + 0xf8]
00c504d5  JMP 0x00c5050b
00c504d7  CALL 0x0048bc40
00c504dc  MOV RDX,qword ptr [RSP + 0x100]
00c504e4  MOV qword ptr [R11],RDX
00c504e7  MOV R12,qword ptr [RSP + 0x120]
00c504ef  MOV qword ptr [R11 + 0x8],R12
00c504f3  MOV R13,qword ptr [RSP + 0xf0]
00c504fb  MOV qword ptr [R11 + 0x10],R13
00c504ff  MOV R15,qword ptr [RSP + 0xf8]
00c50507  MOV qword ptr [R11 + 0x18],R15
00c5050b  MOV qword ptr [RSP + 0x158],RAX
00c50513  MOV qword ptr [RAX + 0x8],RDX
00c50517  MOV RDX,qword ptr [RSP + 0x90]
00c5051f  MOV qword ptr [RAX + 0x18],RDX
00c50523  MOV qword ptr [RAX + 0x20],R12
00c50527  MOV RBX,qword ptr [RSP + 0x60]
00c5052c  MOV qword ptr [RAX + 0x30],RBX
00c50530  MOV qword ptr [RAX + 0x28],R13
00c50534  MOV RDX,qword ptr [RSP + 0x70]
00c50539  MOV qword ptr [RAX + 0x40],RDX
00c5053d  MOV qword ptr [RAX + 0x38],R15
00c50541  MOV RDX,qword ptr [RSP + 0xb8]
00c50549  CMP RDX,0x4
00c5054d  JNZ 0x00c505a5
00c5054f  MOV R12,qword ptr [RSP + 0x148]
00c50557  CMP dword ptr [R12],0x6f73692e
00c5055f  NOP
00c50560  JNZ 0x00c5056c
00c50562  MOV ECX,0x1
00c50567  JMP 0x00c5064a
00c5056c  CMP RDX,0x4
00c50570  JNZ 0x00c505a5
00c50572  CMP dword ptr [R12],0x676d692e
00c5057a  JNZ 0x00c50586
00c5057c  MOV ECX,0x1
00c50581  JMP 0x00c5064a
00c50586  CMP RDX,0x4
00c5058a  JNZ 0x00c505a5
00c5058c  CMP dword ptr [R12],0x67726e2e
00c50594  JNZ 0x00c505a5
00c50596  MOV ECX,0x1
00c5059b  NOP dword ptr [RAX + RAX*0x1]
00c505a0  JMP 0x00c5064a
00c505a5  MOV RAX,qword ptr [RSP + 0xe0]
00c505ad  MOV RBX,qword ptr [RSP + 0x50]
00c505b2  CALL 0x004af740
00c505b7  LEA RCX,[0xefb5a7]
00c505be  MOV EDI,0x4
00c505c3  CALL 0x00414f60
00c505c8  TEST RAX,RAX
00c505cb  JL 0x00c505f9
00c505cd  MOV RAX,qword ptr [RSP + 0x158]
00c505d5  MOV RDX,qword ptr [RSP + 0xb8]
00c505dd  MOV RBX,qword ptr [RSP + 0x60]
00c505e2  MOV R12,qword ptr [RSP + 0x148]
00c505ea  MOV R13,qword ptr [RSP + 0xf0]
00c505f2  MOV ECX,0x1
00c505f7  JMP 0x00c5064a
00c505f9  MOV RCX,qword ptr [RSP + 0x110]
00c50601  MOV RAX,qword ptr [RCX + 0x38]
00c50605  MOV RBX,qword ptr [RCX + 0x40]
00c50609  CALL 0x004af740
00c5060e  LEA RCX,[0xefb5a7]
00c50615  MOV EDI,0x4
00c5061a  CALL 0x00414f60
00c5061f  TEST RAX,RAX
00c50622  SETGE CL
00c50625  MOV RAX,qword ptr [RSP + 0x158]
00c5062d  MOV RDX,qword ptr [RSP + 0xb8]
00c50635  MOV RBX,qword ptr [RSP + 0x60]
00c5063a  MOV R12,qword ptr [RSP + 0x148]
00c50642  MOV R13,qword ptr [RSP + 0xf0]
00c5064a  TEST CL,CL
00c5064c  JNZ 0x00c50674
00c5064e  MOV RAX,R13
00c50651  CALL 0x004af740
00c50656  LEA RCX,[0xefb5a7]
00c5065d  MOV EDI,0x4
00c50662  CALL 0x00414f60
00c50667  TEST RAX,RAX
00c5066a  JL 0x00c506b2
00c5066c  MOV RAX,qword ptr [RSP + 0x158]
00c50674  MOV RDX,qword ptr [0x0196cdc0]
00c5067b  MOV R12,qword ptr [RSP + 0x110]
00c50683  MOV RBX,qword ptr [R12]
00c50687  MOV RCX,qword ptr [R12 + 0x8]
00c5068c  MOV RDI,qword ptr [R12 + 0x10]
00c50691  MOV RSI,qword ptr [RSP + 0xb0]
00c50699  XOR R8D,R8D
00c5069c  MOV R9,R8
00c5069f  MOV R10D,0x1
00c506a5  MOV R11,RAX
00c506a8  MOV RAX,RDX
00c506ab  CALL 0x00aa4980
00c506b0  JMP 0x00c506f1
00c506b2  MOV RAX,qword ptr [0x0196cdc0]
00c506b9  MOV RDX,qword ptr [RSP + 0x110]
00c506c1  MOV RBX,qword ptr [RDX]
00c506c4  MOV RCX,qword ptr [RDX + 0x8]
00c506c8  MOV RDI,qword ptr [RDX + 0x10]
00c506cc  MOV RSI,qword ptr [RSP + 0xb0]
00c506d4  MOV R8,qword ptr [RSP + 0xc8]
00c506dc  MOV R9,qword ptr [RSP + 0x68]
00c506e1  XOR R10D,R10D
00c506e4  MOV R11,qword ptr [RSP + 0x158]
00c506ec  CALL 0x00aa4980
00c506f1  MOV qword ptr [RSP + 0xa0],RBX
00c506f9  MOV qword ptr [RSP + 0x130],RAX
00c50701  LEA RCX,[RSP + 0x240]
00c50709  MOVUPS xmmword ptr [RCX],XMM15
00c5070d  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c50712  MOV RAX,qword ptr [RSP + 0x148]
00c5071a  MOV RBX,qword ptr [RSP + 0xb8]
00c50722  CALL 0x00481ee0
00c50727  LEA RCX,[0xdd29c0]
00c5072e  MOV qword ptr [RSP + 0x240],RCX
00c50736  MOV qword ptr [RSP + 0x248],RAX
00c5073e  MOV RAX,qword ptr [RSP + 0x130]
00c50746  MOV RBX,qword ptr [RSP + 0xa0]
00c5074e  CALL 0x00481ee0
00c50753  LEA RCX,[0xdd29c0]
00c5075a  MOV qword ptr [RSP + 0x250],RCX
00c50762  MOV qword ptr [RSP + 0x258],RAX
00c5076a  LEA RAX,[0xf3ed29]
00c50771  MOV EBX,0x2b
00c50776  LEA RCX,[RSP + 0x240]
00c5077e  MOV EDI,0x2
00c50783  MOV RSI,RDI
00c50786  CALL 0x005055a0
00c5078b  MOV RCX,qword ptr [RSP + 0x110]
00c50793  MOV qword ptr [RCX + 0x8],RBX
00c50797  CMP dword ptr [0x019b5f00],0x0
00c5079e  NOP
00c507a0  JZ 0x00c507b9
00c507a2  MOV RDX,qword ptr [RCX]
00c507a5  MOV RSI,qword ptr [RCX + 0x10]
00c507a9  CALL 0x0048bc20
00c507ae  MOV qword ptr [R11],RAX
00c507b1  MOV qword ptr [R11 + 0x8],RDX
00c507b5  MOV qword ptr [R11 + 0x10],RSI
00c507b9  MOV qword ptr [RCX],RAX
00c507bc  MOV qword ptr [RCX + 0x10],0x0
00c507c4  MOV RDX,qword ptr [RSP + 0xb0]
00c507cc  MOV qword ptr [RCX + 0x30],RDX
00c507d0  MOV RAX,RCX
00c507d3  MOV RDX,qword ptr [RSP + 0x2d8]
00c507db  NOP dword ptr [RAX + RAX*0x1]
00c507e0  TEST RDX,RDX
00c507e3  JZ 0x00c5097a
00c507e9  MOV RBX,qword ptr [RDX + 0x8]
00c507ed  MOV RSI,qword ptr [0x01974000]
00c507f4  MOV RDI,qword ptr [RSI]
00c507f7  MOV EDX,dword ptr [RDX + 0x10]
00c507fa  JMP 0x00c509da
00c507ff  MOV qword ptr [RSP + 0x150],RCX
00c50807  MOV qword ptr [RSP + 0xc0],RBX
00c5080f  MOV RCX,qword ptr [RSP + 0x90]
00c50817  MOV RCX,qword ptr [RCX + 0x28]
00c5081b  MOV RAX,qword ptr [RSP + 0x120]
00c50823  CALL RCX
00c50825  LEA RCX,[RSP + 0x210]
00c5082d  MOVUPS xmmword ptr [RCX],XMM15
00c50831  MOVUPS xmmword ptr [RCX + 0x10],XMM15
00c50836  CALL 0x00481ee0
00c5083b  LEA RCX,[0xdd29c0]
00c50842  MOV qword ptr [RSP + 0x210],RCX
00c5084a  MOV qword ptr [RSP + 0x218],RAX
00c50852  MOV RCX,qword ptr [RSP + 0xc0]
00c5085a  TEST RCX,RCX
00c5085d  JZ 0x00c50865
00c5085f  MOV RBX,qword ptr [RCX + 0x8]
00c50863  JMP 0x00c50868
00c50865  MOV RBX,RCX
00c50868  MOV qword ptr [RSP + 0x220],RBX
00c50870  MOV RDX,qword ptr [RSP + 0x150]
00c50878  MOV qword ptr [RSP + 0x228],RDX
00c50880  LEA RDX,[0xc50c80]
00c50887  MOV qword ptr [RSP + 0x290],RDX
00c5088f  MOV qword ptr [RSP + 0x2a0],0x31
00c5089b  LEA RDX,[0xf453e2]
00c508a2  MOV qword ptr [RSP + 0x298],RDX
00c508aa  MOV qword ptr [RSP + 0x2b0],0x2
00c508b6  MOV qword ptr [RSP + 0x2b8],0x2
00c508c2  LEA RDX,[RSP + 0x210]
00c508ca  MOV qword ptr [RSP + 0x2a8],RDX
00c508d2  MOV RAX,qword ptr [0x01990148]
00c508d9  XOR EBX,EBX
00c508db  MOV ECX,0x2
00c508e0  LEA RDI,[RSP + 0x290]
00c508e8  CALL 0x0054d540
00c508ed  MOV RDX,qword ptr [RSP + 0xc0]
00c508f5  MOV RDX,qword ptr [RDX + 0x18]
00c508f9  MOV RAX,qword ptr [RSP + 0x150]
00c50901  CALL RDX
00c50903  MOV RCX,RAX
00c50906  MOV RDI,RBX
00c50909  MOV ESI,0x1f4
00c5090e  MOV RAX,qword ptr [RSP + 0x2d8]
00c50916  MOV RBX,qword ptr [RSP + 0x2e0]
00c5091e  NOP
00c50920  CALL 0x00c484c0
00c50925  ADD RSP,0x2c8
00c5092c  POP RBP
00c5092d  RET
00c5092e  XOR EAX,EAX
00c50930  LEA RBX,[0xf1d559]
00c50937  MOV ECX,0x12
00c5093c  MOV RDI,qword ptr [RSP + 0x118]
00c50944  MOV RSI,qword ptr [RSP + 0x88]
00c5094c  CALL 0x0046b1e0
00c50951  MOV RCX,RAX
00c50954  MOV RDI,RBX
00c50957  MOV ESI,0x190
00c5095c  MOV RAX,qword ptr [RSP + 0x2d8]
00c50964  MOV RBX,qword ptr [RSP + 0x2e0]
00c5096c  CALL 0x00c484c0
00c50971  ADD RSP,0x2c8
00c50978  POP RBP
00c50979  RET
00c5097a  LEA RSI,[RSP + 0x170]
00c50982  MOVUPS xmmword ptr [RSI],XMM15
00c50986  MOVUPS xmmword ptr [RSI + 0x10],XMM15
00c5098b  MOVUPS xmmword ptr [RSI + 0x20],XMM15
00c50990  MOVUPS xmmword ptr [RSI + 0x30],XMM15
00c50995  MOVUPS xmmword ptr [RSI + 0x40],XMM15
00c5099a  MOVUPS xmmword ptr [RSI + 0x50],XMM15
00c5099f  MOV qword ptr [RSP + 0x170],RDX
00c509a7  MOV RDX,qword ptr [RSP + 0x2e0]
00c509af  MOV qword ptr [RSP + 0x178],RDX
00c509b7  MOV byte ptr [RSP + 0x190],0x1
00c509bf  LEA RBX,[0xdb1aa0]
00c509c6  MOV RCX,RAX
00c509c9  MOV RAX,RSI
00c509cc  CALL 0x0053fda0
00c509d1  ADD RSP,0x2c8
00c509d8  POP RBP
00c509d9  RET
00c509da  MOV R8,RDX
00c509dd  AND RDX,RDI
00c509e0  SHL RDX,0x4
00c509e4  MOV R9,qword ptr [RDX + RSI*0x1 + 0x8]
00c509e9  CMP R9,RBX
00c509ec  JZ 0x00c50a15
00c509ee  LEA RDX,[R8 + 0x1]
00c509f2  TEST R9,R9
00c509f5  JNZ 0x00c509da
00c509f7  LEA RAX,[0x1974000]
00c509fe  NOP
00c50a00  CALL 0x0041e320
00c50a05  MOV RDX,RAX
00c50a08  MOV RAX,qword ptr [RSP + 0x110]
00c50a10  JMP 0x00c5097a
00c50a15  MOV RDX,qword ptr [RDX + RSI*0x1 + 0x10]
00c50a1a  JMP 0x00c5097a
00c50a1f  MOV qword ptr [RSP + 0x8],RAX
00c50a24  MOV qword ptr [RSP + 0x10],RBX
00c50a29  MOV qword ptr [RSP + 0x18],RCX
00c50a2e  CALL 0x0048a280
00c50a33  MOV RAX,qword ptr [RSP + 0x8]
00c50a38  MOV RBX,qword ptr [RSP + 0x10]
00c50a3d  MOV RCX,qword ptr [RSP + 0x18]
00c50a42  JMP 0x00c4fa20
