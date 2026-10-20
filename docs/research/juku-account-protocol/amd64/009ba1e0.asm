; mv-daemon/provider.(*Cloud115Provider).PollQrLogin
009ba1e0  LEA R12,[RSP + -0x698]
009ba1e8  CMP R12,qword ptr [R14 + 0x10]
009ba1ec  JBE 0x009bbf05
009ba1f2  PUSH RBP
009ba1f3  MOV RBP,RSP
009ba1f6  SUB RSP,0x710
009ba1fd  MOV qword ptr [RSP + 0x728],RBX
009ba205  MOV qword ptr [RSP + 0x1b8],0x0
009ba211  MOVUPS xmmword ptr [RSP + 0x190],XMM15
009ba21a  NOP
009ba21b  MOV RAX,RBX
009ba21e  MOV RBX,RCX
009ba221  LEA RCX,[0x1133218]
009ba228  MOV EDI,0x1
009ba22d  XOR ESI,ESI
009ba22f  MOV R8,-0x1
009ba236  CALL 0x004adc40
009ba23b  NOP dword ptr [RAX + RAX*0x1]
009ba240  CMP RBX,0x4
009ba244  JL 0x009ba708
009ba24a  MOV RDX,qword ptr [RAX + 0x8]
009ba24e  MOV qword ptr [RSP + 0x60],RDX
009ba253  MOV RSI,qword ptr [RAX]
009ba256  MOV qword ptr [RSP + 0x1d0],RSI
009ba25e  MOV RDI,qword ptr [RAX + 0x18]
009ba262  MOV qword ptr [RSP + 0x88],RDI
009ba26a  MOV R8,qword ptr [RAX + 0x10]
009ba26e  MOV qword ptr [RSP + 0x1f8],R8
009ba276  MOV R9,qword ptr [RAX + 0x28]
009ba27a  MOV qword ptr [RSP + 0x68],R9
009ba27f  MOV R10,qword ptr [RAX + 0x20]
009ba283  MOV qword ptr [RSP + 0x1d8],R10
009ba28b  MOV R11,qword ptr [RAX + 0x38]
009ba28f  MOV qword ptr [RSP + 0x50],R11
009ba294  MOV R12,qword ptr [RAX + 0x30]
009ba298  MOV qword ptr [RSP + 0x1c0],R12
009ba2a0  CMP RBX,0x5
009ba2a4  JL 0x009ba2c4
009ba2a6  MOV R13,qword ptr [RAX + 0x48]
009ba2aa  TEST R13,R13
009ba2ad  JZ 0x009ba2b5
009ba2af  MOV R15,qword ptr [RAX + 0x40]
009ba2b3  JMP 0x009ba2d1
009ba2b5  LEA R15,[0xefac72]
009ba2bc  MOV R13D,0x3
009ba2c2  JMP 0x009ba2d1
009ba2c4  LEA R15,[0xefac72]
009ba2cb  MOV R13D,0x3
009ba2d1  MOV qword ptr [RSP + 0xe0],R13
009ba2d9  MOV qword ptr [RSP + 0x278],R15
009ba2e1  LEA RAX,[0x113fde8]
009ba2e8  LEA RBX,[0x19b5220]
009ba2ef  MOV RCX,0x6fc23ac00
009ba2f9  CALL 0x00552580
009ba2fe  MOV qword ptr [RSP + 0xb0],RAX
009ba306  MOV qword ptr [RSP + 0x250],RBX
009ba30e  MOV qword ptr [RSP + 0x178],RCX
009ba316  LEA RAX,[RSP + 0x160]
009ba31e  NOP
009ba320  CALL 0x0044ac40
009ba325  LEA RBX,[RSP + 0x690]
009ba32d  MOVUPS xmmword ptr [RBX],XMM15
009ba331  MOVUPS xmmword ptr [RBX + 0x10],XMM15
009ba336  MOVUPS xmmword ptr [RBX + 0x20],XMM15
009ba33b  MOVUPS xmmword ptr [RBX + 0x30],XMM15
009ba340  MOVUPS xmmword ptr [RBX + 0x40],XMM15
009ba345  MOVUPS xmmword ptr [RBX + 0x50],XMM15
009ba34a  MOVUPS xmmword ptr [RBX + 0x60],XMM15
009ba34f  MOV RDX,qword ptr [0x0196ddb0]
009ba356  MOV RSI,qword ptr [0x0196ddb8]
009ba35d  MOV qword ptr [RSP + 0x698],RSI
009ba365  MOV qword ptr [RSP + 0x690],RDX
009ba36d  MOV qword ptr [RSP + 0x6a8],0x11
009ba379  LEA RDX,[0xf1b45b]
009ba380  MOV qword ptr [RSP + 0x6a0],RDX
009ba388  MOV RDX,qword ptr [RSP + 0x60]
009ba38d  MOV qword ptr [RSP + 0x6b8],RDX
009ba395  MOV RDX,qword ptr [RSP + 0x1d0]
009ba39d  MOV qword ptr [RSP + 0x6b0],RDX
009ba3a5  MOV qword ptr [RSP + 0x6c8],0x6
009ba3b1  LEA RDX,[0xefe6ef]
009ba3b8  MOV qword ptr [RSP + 0x6c0],RDX
009ba3c0  MOV RDX,qword ptr [RSP + 0x88]
009ba3c8  MOV qword ptr [RSP + 0x6d8],RDX
009ba3d0  MOV RDX,qword ptr [RSP + 0x1f8]
009ba3d8  MOV qword ptr [RSP + 0x6d0],RDX
009ba3e0  MOV qword ptr [RSP + 0x6e8],0x6
009ba3ec  LEA RDX,[0xefe6f5]
009ba3f3  MOV qword ptr [RSP + 0x6e0],RDX
009ba3fb  MOV RDX,qword ptr [RSP + 0x68]
009ba400  MOV qword ptr [RSP + 0x6f8],RDX
009ba408  MOV RDX,qword ptr [RSP + 0x1d8]
009ba410  MOV qword ptr [RSP + 0x6f0],RDX
009ba418  XOR EAX,EAX
009ba41a  MOV ECX,0x7
009ba41f  MOV RDI,RCX
009ba422  CALL 0x0046afe0
009ba427  LEA RCX,[0xefaba3]
009ba42e  MOV EDI,0x3
009ba433  MOV RSI,RAX
009ba436  MOV R8,RBX
009ba439  XOR R9D,R9D
009ba43c  XOR R10D,R10D
009ba43f  MOV RAX,qword ptr [RSP + 0xb0]
009ba447  MOV RBX,qword ptr [RSP + 0x250]
009ba44f  CALL 0x006acc00
009ba454  TEST RBX,RBX
009ba457  JNZ 0x009ba6c6
009ba45d  MOV qword ptr [RSP + 0x218],RAX
009ba465  MOV RCX,qword ptr [RAX + 0x38]
009ba469  MOV qword ptr [RSP + 0x240],RCX
009ba471  NOP
009ba472  LEA RAX,[0xf0a13f]
009ba479  MOV EBX,0xa
009ba47e  NOP
009ba480  CALL 0x00640c00
009ba485  MOV qword ptr [RSP + 0x298],RAX
009ba48d  MOV qword ptr [RSP + 0xf8],RBX
009ba495  LEA RAX,[0xddc380]
009ba49c  NOP dword ptr [RAX]
009ba4a0  CALL 0x00421f00
009ba4a5  MOV qword ptr [RSP + 0x290],RAX
009ba4ad  MOV qword ptr [RAX + 0x8],0xc
009ba4b5  LEA RCX,[0xf11043]
009ba4bc  MOV qword ptr [RAX],RCX
009ba4bf  LEA RAX,[0xe91b20]
009ba4c6  MOV RBX,qword ptr [RSP + 0x240]
009ba4ce  MOV RCX,qword ptr [RSP + 0x298]
009ba4d6  MOV RDI,qword ptr [RSP + 0xf8]
009ba4de  NOP
009ba4e0  CALL 0x00413460
009ba4e5  MOV qword ptr [RAX + 0x8],0x1
009ba4ed  MOV qword ptr [RAX + 0x10],0x1
009ba4f5  CMP dword ptr [0x019b5f00],0x0
009ba4fc  JNZ 0x009ba508
009ba4fe  MOV RDX,qword ptr [RSP + 0x290]
009ba506  JMP 0x009ba51f
009ba508  MOV RCX,qword ptr [RAX]
009ba50b  CALL 0x0048bc00
009ba510  MOV RDX,qword ptr [RSP + 0x290]
009ba518  MOV qword ptr [R11],RDX
009ba51b  MOV qword ptr [R11 + 0x8],RCX
009ba51f  MOV qword ptr [RAX],RDX
009ba522  MOV RAX,qword ptr [0x0196ccc0]
009ba529  MOV RBX,qword ptr [RSP + 0x218]
009ba531  CALL 0x0066f720
009ba536  TEST RBX,RBX
009ba539  JNZ 0x009ba5df
009ba53f  MOV qword ptr [RSP + 0x1b0],RAX
009ba547  MOV RCX,qword ptr [RAX + 0x40]
009ba54b  TEST byte ptr [RCX],AL
009ba54d  MOV RDX,qword ptr [RAX + 0x48]
009ba551  LEA RBX,[0x9bc0a0]
009ba558  MOV qword ptr [RSP + 0x5d8],RBX
009ba560  MOV qword ptr [RSP + 0x5e0],RCX
009ba568  MOV qword ptr [RSP + 0x5e8],RDX
009ba570  LEA RCX,[RSP + 0x5d8]
009ba578  MOV qword ptr [RSP + 0x148],RCX
009ba580  LEA RAX,[RSP + 0x130]
009ba588  CALL 0x0044ac40
009ba58d  LEA RAX,[0xe0fd80]
009ba594  CALL 0x00421f00
009ba599  MOV qword ptr [RSP + 0x700],RAX
009ba5a1  MOV RCX,qword ptr [RSP + 0x1b0]
009ba5a9  MOV RDX,qword ptr [RCX + 0x40]
009ba5ad  MOV RCX,qword ptr [RCX + 0x48]
009ba5b1  MOV qword ptr [RSP + 0x220],RCX
009ba5b9  NOP dword ptr [RAX]
009ba5c0  TEST RDX,RDX
009ba5c3  JZ 0x009ba795
009ba5c9  MOV RBX,qword ptr [RDX + 0x8]
009ba5cd  MOV RSI,qword ptr [0x019765e0]
009ba5d4  MOV RDI,qword ptr [RSI]
009ba5d7  MOV EDX,dword ptr [RDX + 0x10]
009ba5da  JMP 0x009bbec7
009ba5df  MOV qword ptr [RSP + 0x248],RCX
009ba5e7  MOV qword ptr [RSP + 0xa8],RBX
009ba5ef  MOV RCX,qword ptr [RSP + 0xb0]
009ba5f7  MOV RCX,qword ptr [RCX + 0x28]
009ba5fb  MOV RAX,qword ptr [RSP + 0x250]
009ba603  CALL RCX
009ba605  MOV RCX,qword ptr [0x0196ed90]
009ba60c  MOV RDI,qword ptr [0x0196ed98]
009ba613  CALL 0x00492700
009ba618  TEST AL,AL
009ba61a  JZ 0x009ba671
009ba61c  LEA RAX,[0xe836e0]
009ba623  CALL 0x00421f00
009ba628  MOV qword ptr [RAX + 0x8],0x7
009ba630  LEA RCX,[0xeffe11]
009ba637  MOV qword ptr [RAX],RCX
009ba63a  MOV qword ptr [RSP + 0x1b8],RAX
009ba642  MOVUPS xmmword ptr [RSP + 0x190],XMM15
009ba64b  CALL 0x0044b160
009ba650  MOV RBX,qword ptr [RSP + 0x190]
009ba658  MOV RCX,qword ptr [RSP + 0x198]
009ba660  MOV RAX,qword ptr [RSP + 0x1b8]
009ba668  ADD RSP,0x710
009ba66f  POP RBP
009ba670  RET
009ba671  MOV qword ptr [RSP + 0x1b8],0x0
009ba67d  MOV RAX,qword ptr [RSP + 0xa8]
009ba685  MOV qword ptr [RSP + 0x190],RAX
009ba68d  MOV RAX,qword ptr [RSP + 0x248]
009ba695  MOV qword ptr [RSP + 0x198],RAX
009ba69d  NOP dword ptr [RAX]
009ba6a0  CALL 0x0044b160
009ba6a5  MOV RBX,qword ptr [RSP + 0x190]
009ba6ad  MOV RCX,qword ptr [RSP + 0x198]
009ba6b5  MOV RAX,qword ptr [RSP + 0x1b8]
009ba6bd  ADD RSP,0x710
009ba6c4  POP RBP
009ba6c5  RET
009ba6c6  MOV qword ptr [RSP + 0x1b8],0x0
009ba6d2  MOV qword ptr [RSP + 0x190],RBX
009ba6da  MOV qword ptr [RSP + 0x198],RCX
009ba6e2  CALL 0x0044b160
009ba6e7  MOV RBX,qword ptr [RSP + 0x190]
009ba6ef  MOV RCX,qword ptr [RSP + 0x198]
009ba6f7  MOV RAX,qword ptr [RSP + 0x1b8]
009ba6ff  ADD RSP,0x710
009ba706  POP RBP
009ba707  RET
009ba708  LEA RAX,[0xe21740]
009ba70f  CALL 0x00421f00
009ba714  MOV qword ptr [RAX + 0x8],0x10
009ba71c  LEA RCX,[0xf197ec]
009ba723  MOV qword ptr [RAX],RCX
009ba726  MOV qword ptr [RSP + 0x1b8],0x0
009ba732  LEA RCX,[0x1139800]
009ba739  MOV qword ptr [RSP + 0x190],RCX
009ba741  MOV qword ptr [RSP + 0x198],RAX
009ba749  CALL 0x0044b160
009ba74e  MOV RBX,qword ptr [RSP + 0x190]
009ba756  MOV RCX,qword ptr [RSP + 0x198]
009ba75e  MOV RAX,qword ptr [RSP + 0x1b8]
009ba766  ADD RSP,0x710
009ba76d  POP RBP
009ba76e  RET
009ba795  MOV qword ptr [RSP + 0x298],RDX
009ba79d  LEA RAX,[0xeba560]
009ba7a4  CALL 0x00421f00
009ba7a9  MOV RCX,qword ptr [RSP + 0x298]
009ba7b1  MOV qword ptr [RAX],RCX
009ba7b4  CMP dword ptr [0x019b5f00],0x0
009ba7bb  JNZ 0x009ba7c7
009ba7bd  MOV RDX,qword ptr [RSP + 0x220]
009ba7c5  JMP 0x009ba7d7
009ba7c7  CALL 0x0048bbe0
009ba7cc  MOV RDX,qword ptr [RSP + 0x220]
009ba7d4  MOV qword ptr [R11],RDX
009ba7d7  MOV qword ptr [RAX + 0x8],RDX
009ba7db  LEA RBX,[0xdc4ae0]
009ba7e2  MOV RCX,qword ptr [RSP + 0x700]
009ba7ea  CALL 0x0053f680
009ba7ef  TEST RAX,RAX
009ba7f2  JNZ 0x009bafef
009ba7f8  MOV RCX,qword ptr [RSP + 0x700]
009ba800  MOV RCX,qword ptr [RCX]
009ba803  CMP RCX,0x1
009ba807  JNZ 0x009ba817
009ba809  MOV ECX,0x7
009ba80e  LEA RAX,[0xf0010c]
009ba815  JMP 0x009ba846
009ba817  CMP RCX,0x2
009ba81b  JNZ 0x009ba82b
009ba81d  MOV ECX,0x9
009ba822  LEA RAX,[0xf059ff]
009ba829  JMP 0x009ba846
009ba82b  CMP RCX,-0x1
009ba82f  JNZ 0x009ba83a
009ba831  LEA RAX,[0xf00113]
009ba838  JMP 0x009ba841
009ba83a  LEA RAX,[0xeffe11]
009ba841  MOV ECX,0x7
009ba846  MOV qword ptr [RSP + 0x80],RCX
009ba84e  MOV qword ptr [RSP + 0x1f0],RAX
009ba856  LEA RAX,[0xe836e0]
009ba85d  NOP dword ptr [RAX]
009ba860  CALL 0x00421f00
009ba865  MOV RCX,qword ptr [RSP + 0x80]
009ba86d  MOV qword ptr [RAX + 0x8],RCX
009ba871  CMP dword ptr [0x019b5f00],0x0
009ba878  JNZ 0x009ba884
009ba87a  MOV RDX,qword ptr [RSP + 0x1f0]
009ba882  JMP 0x009ba894
009ba884  CALL 0x0048bbe0
009ba889  MOV RDX,qword ptr [RSP + 0x1f0]
009ba891  MOV qword ptr [R11],RDX
009ba894  MOV qword ptr [RAX],RDX
009ba897  NOP word ptr [RAX + RAX*0x1]
009ba8a0  CMP RCX,0x9
009ba8a4  JNZ 0x009bb031
009ba8aa  MOV RCX,0x656d7269666e6f63
009ba8b4  CMP qword ptr [RDX],RCX
009ba8b7  JNZ 0x009bb031
009ba8bd  CMP byte ptr [RDX + 0x8],0x64
009ba8c1  JNZ 0x009bb031
009ba8c7  MOV qword ptr [RSP + 0x208],RAX
009ba8cf  MOVUPS xmmword ptr [RSP + 0x680],XMM15
009ba8d8  MOV RAX,qword ptr [RSP + 0x278]
009ba8e0  MOV RBX,qword ptr [RSP + 0xe0]
009ba8e8  CALL 0x00481ee0
009ba8ed  LEA RCX,[0xdd29c0]
009ba8f4  MOV qword ptr [RSP + 0x680],RCX
009ba8fc  MOV qword ptr [RSP + 0x688],RAX
009ba904  LEA RAX,[0xf4aa63]
009ba90b  MOV EBX,0x37
009ba910  LEA RCX,[RSP + 0x680]
009ba918  MOV EDI,0x1
009ba91d  MOV RSI,RDI
009ba920  CALL 0x005055a0
009ba925  MOV qword ptr [RSP + 0x268],RAX
009ba92d  MOV qword ptr [RSP + 0xc8],RBX
009ba935  LEA RCX,[RSP + 0x5a8]
009ba93d  MOVUPS xmmword ptr [RCX],XMM15
009ba941  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009ba946  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009ba94b  LEA RCX,[RSP + 0x460]
009ba953  MOV EDX,0x5
009ba958  MOVUPS xmmword ptr [RCX],XMM15
009ba95c  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009ba961  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009ba966  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009ba96b  ADD RCX,0x40
009ba96f  DEC EDX
009ba971  JNZ 0x009ba958
009ba973  MOVUPS xmmword ptr [RCX + -0x8],XMM15
009ba978  MOV RCX,-0x7f7f7f7f7f7f7f80
009ba982  MOV qword ptr [RSP + 0x460],RCX
009ba98a  LEA RCX,[RSP + 0x460]
009ba992  MOV qword ptr [RSP + 0x5b8],RCX
009ba99a  CALL 0x00485080
009ba99f  MOV qword ptr [RSP + 0x5b0],RAX
009ba9a7  NOP
009ba9a8  LEA RAX,[0xddc380]
009ba9af  CALL 0x00421f00
009ba9b4  MOV RCX,qword ptr [RSP + 0x60]
009ba9b9  MOV qword ptr [RAX + 0x8],RCX
009ba9bd  CMP dword ptr [0x019b5f00],0x0
009ba9c4  JNZ 0x009ba9d0
009ba9c6  MOV RDX,qword ptr [RSP + 0x1d0]
009ba9ce  JMP 0x009ba9e0
009ba9d0  CALL 0x0048bbe0
009ba9d5  MOV RDX,qword ptr [RSP + 0x1d0]
009ba9dd  MOV qword ptr [R11],RDX
009ba9e0  MOV qword ptr [RSP + 0x290],RAX
009ba9e8  MOV qword ptr [RAX],RDX
009ba9eb  LEA RAX,[0xe9bd40]
009ba9f2  LEA RBX,[RSP + 0x5a8]
009ba9fa  LEA RCX,[0xf00144]
009baa01  MOV EDI,0x7
009baa06  CALL 0x00413460
009baa0b  MOV qword ptr [RAX + 0x8],0x1
009baa13  MOV qword ptr [RAX + 0x10],0x1
009baa1b  CMP dword ptr [0x019b5f00],0x0
009baa22  JNZ 0x009baa2e
009baa24  MOV RDX,qword ptr [RSP + 0x290]
009baa2c  JMP 0x009baa45
009baa2e  MOV RCX,qword ptr [RAX]
009baa31  CALL 0x0048bc00
009baa36  MOV RDX,qword ptr [RSP + 0x290]
009baa3e  MOV qword ptr [R11],RDX
009baa41  MOV qword ptr [R11 + 0x8],RCX
009baa45  MOV qword ptr [RAX],RDX
009baa48  NOP
009baa49  LEA RAX,[0xddc380]
009baa50  CALL 0x00421f00
009baa55  MOV RCX,qword ptr [RSP + 0xe0]
009baa5d  MOV qword ptr [RAX + 0x8],RCX
009baa61  CMP dword ptr [0x019b5f00],0x0
009baa68  JNZ 0x009baa74
009baa6a  MOV RDX,qword ptr [RSP + 0x278]
009baa72  JMP 0x009baa84
009baa74  CALL 0x0048bbe0
009baa79  MOV RDX,qword ptr [RSP + 0x278]
009baa81  MOV qword ptr [R11],RDX
009baa84  MOV qword ptr [RSP + 0x290],RAX
009baa8c  MOV qword ptr [RAX],RDX
009baa8f  LEA RAX,[0xe9bd40]
009baa96  LEA RBX,[RSP + 0x5a8]
009baa9e  LEA RCX,[0xefacc3]
009baaa5  MOV EDI,0x3
009baaaa  CALL 0x00413460
009baaaf  MOV qword ptr [RAX + 0x8],0x1
009baab7  MOV qword ptr [RAX + 0x10],0x1
009baabf  CMP dword ptr [0x019b5f00],0x0
009baac6  JNZ 0x009baad2
009baac8  MOV RDX,qword ptr [RSP + 0x290]
009baad0  JMP 0x009baae9
009baad2  MOV RCX,qword ptr [RAX]
009baad5  CALL 0x0048bc00
009baada  MOV RDX,qword ptr [RSP + 0x290]
009baae2  MOV qword ptr [R11],RDX
009baae5  MOV qword ptr [R11 + 0x8],RCX
009baae9  MOV qword ptr [RAX],RDX
009baaec  MOV RCX,qword ptr [RSP + 0xe0]
009baaf4  CMP RCX,0x3
009baaf8  JNZ 0x009bac68
009baafe  MOV RDX,qword ptr [RSP + 0x278]
009bab06  CMP word ptr [RDX],0x6577
009bab0b  JNZ 0x009bac70
009bab11  CMP byte ptr [RDX + 0x2],0x62
009bab15  JNZ 0x009bac70
009bab1b  NOP
009bab1c  LEA RAX,[0xddc380]
009bab23  CALL 0x00421f00
009bab28  MOV RCX,qword ptr [RSP + 0x88]
009bab30  MOV qword ptr [RAX + 0x8],RCX
009bab34  CMP dword ptr [0x019b5f00],0x0
009bab3b  JNZ 0x009bab47
009bab3d  MOV RDX,qword ptr [RSP + 0x1f8]
009bab45  JMP 0x009bab57
009bab47  CALL 0x0048bbe0
009bab4c  MOV RDX,qword ptr [RSP + 0x1f8]
009bab54  MOV qword ptr [R11],RDX
009bab57  MOV qword ptr [RSP + 0x290],RAX
009bab5f  MOV qword ptr [RAX],RDX
009bab62  LEA RAX,[0xe9bd40]
009bab69  LEA RBX,[RSP + 0x5a8]
009bab71  LEA RCX,[0xefb6ef]
009bab78  MOV EDI,0x4
009bab7d  NOP dword ptr [RAX]
009bab80  CALL 0x00413460
009bab85  MOV qword ptr [RAX + 0x8],0x1
009bab8d  MOV qword ptr [RAX + 0x10],0x1
009bab95  CMP dword ptr [0x019b5f00],0x0
009bab9c  JNZ 0x009baba8
009bab9e  MOV RDX,qword ptr [RSP + 0x290]
009baba6  JMP 0x009babbf
009baba8  MOV RCX,qword ptr [RAX]
009babab  CALL 0x0048bc00
009babb0  MOV RDX,qword ptr [RSP + 0x290]
009babb8  MOV qword ptr [R11],RDX
009babbb  MOV qword ptr [R11 + 0x8],RCX
009babbf  MOV qword ptr [RAX],RDX
009babc2  LEA RAX,[0xddc380]
009babc9  CALL 0x00421f00
009babce  MOV RCX,qword ptr [RSP + 0x68]
009babd3  MOV qword ptr [RAX + 0x8],RCX
009babd7  CMP dword ptr [0x019b5f00],0x0
009babde  NOP
009babe0  JNZ 0x009babec
009babe2  MOV RDX,qword ptr [RSP + 0x1d8]
009babea  JMP 0x009babfc
009babec  CALL 0x0048bbe0
009babf1  MOV RDX,qword ptr [RSP + 0x1d8]
009babf9  MOV qword ptr [R11],RDX
009babfc  MOV qword ptr [RSP + 0x290],RAX
009bac04  MOV qword ptr [RAX],RDX
009bac07  LEA RAX,[0xe9bd40]
009bac0e  LEA RBX,[RSP + 0x5a8]
009bac16  LEA RCX,[0xefb6c7]
009bac1d  MOV EDI,0x4
009bac22  CALL 0x00413460
009bac27  MOV qword ptr [RAX + 0x8],0x1
009bac2f  MOV qword ptr [RAX + 0x10],0x1
009bac37  CMP dword ptr [0x019b5f00],0x0
009bac3e  NOP
009bac40  JNZ 0x009bac4c
009bac42  MOV RDX,qword ptr [RSP + 0x290]
009bac4a  JMP 0x009bac63
009bac4c  MOV RCX,qword ptr [RAX]
009bac4f  CALL 0x0048bc00
009bac54  MOV RDX,qword ptr [RSP + 0x290]
009bac5c  MOV qword ptr [R11],RDX
009bac5f  MOV qword ptr [R11 + 0x8],RCX
009bac63  MOV qword ptr [RAX],RDX
009bac66  JMP 0x009bac70
009bac68  MOV RDX,qword ptr [RSP + 0x278]
009bac70  LEA RAX,[RSP + 0x5a8]
009bac78  CALL 0x005b9f20
009bac7d  MOV qword ptr [RSP + 0x90],RBX
009bac85  MOV qword ptr [RSP + 0x200],RAX
009bac8d  LEA RAX,[0xe694e0]
009bac94  CALL 0x00421f00
009bac99  MOV RCX,qword ptr [RSP + 0x90]
009baca1  MOV qword ptr [RAX + 0x8],RCX
009baca5  CMP dword ptr [0x019b5f00],0x0
009bacac  JNZ 0x009bacb8
009bacae  MOV RDX,qword ptr [RSP + 0x200]
009bacb6  JMP 0x009bacc8
009bacb8  CALL 0x0048bbe0
009bacbd  MOV RDX,qword ptr [RSP + 0x200]
009bacc5  MOV qword ptr [R11],RDX
009bacc8  MOV qword ptr [RAX],RDX
009baccb  MOV qword ptr [RAX + 0x10],0x0
009bacd3  MOV qword ptr [RAX + 0x18],-0x1
009bacdb  LEA RBX,[0x19b5220]
009bace2  LEA RCX,[0xefb573]
009bace9  MOV EDI,0x4
009bacee  MOV RSI,qword ptr [RSP + 0x268]
009bacf6  MOV R8,qword ptr [RSP + 0xc8]
009bacfe  LEA R9,[0x1139720]
009bad05  MOV R10,RAX
009bad08  LEA RAX,[0x113fde8]
009bad0f  CALL 0x006acc00
009bad14  TEST RBX,RBX
009bad17  JNZ 0x009bafad
009bad1d  MOV qword ptr [RSP + 0x210],RAX
009bad25  MOV RCX,qword ptr [RAX + 0x38]
009bad29  MOV qword ptr [RSP + 0x238],RCX
009bad31  NOP
009bad32  LEA RAX,[0xf10b4b]
009bad39  MOV EBX,0xc
009bad3e  NOP
009bad40  CALL 0x00640c00
009bad45  MOV qword ptr [RSP + 0x298],RAX
009bad4d  MOV qword ptr [RSP + 0xf8],RBX
009bad55  LEA RAX,[0xddc380]
009bad5c  NOP dword ptr [RAX]
009bad60  CALL 0x00421f00
009bad65  MOV qword ptr [RSP + 0x290],RAX
009bad6d  MOV qword ptr [RAX + 0x8],0x21
009bad75  LEA RCX,[0xf326ad]
009bad7c  MOV qword ptr [RAX],RCX
009bad7f  LEA RAX,[0xe91b20]
009bad86  MOV RBX,qword ptr [RSP + 0x238]
009bad8e  MOV RCX,qword ptr [RSP + 0x298]
009bad96  MOV RDI,qword ptr [RSP + 0xf8]
009bad9e  NOP
009bada0  CALL 0x00413460
009bada5  MOV qword ptr [RAX + 0x8],0x1
009badad  MOV qword ptr [RAX + 0x10],0x1
009badb5  CMP dword ptr [0x019b5f00],0x0
009badbc  JNZ 0x009badc8
009badbe  MOV RDX,qword ptr [RSP + 0x290]
009badc6  JMP 0x009baddf
009badc8  MOV RCX,qword ptr [RAX]
009badcb  CALL 0x0048bc00
009badd0  MOV RDX,qword ptr [RSP + 0x290]
009badd8  MOV qword ptr [R11],RDX
009baddb  MOV qword ptr [R11 + 0x8],RCX
009baddf  MOV qword ptr [RAX],RDX
009bade2  LEA RAX,[RSP + 0x430]
009badea  MOVUPS xmmword ptr [RAX],XMM15
009badee  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009badf3  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009badf8  LEA RAX,[RSP + 0x328]
009bae00  MOV ECX,0x4
009bae05  MOVUPS xmmword ptr [RAX],XMM15
009bae09  MOVUPS xmmword ptr [RAX + 0x10],XMM15
009bae0e  MOVUPS xmmword ptr [RAX + 0x20],XMM15
009bae13  MOVUPS xmmword ptr [RAX + 0x30],XMM15
009bae18  ADD RAX,0x40
009bae1c  NOP dword ptr [RAX]
009bae20  DEC ECX
009bae22  JNZ 0x009bae05
009bae24  MOVUPS xmmword ptr [RAX + -0x8],XMM15
009bae29  MOV RAX,-0x7f7f7f7f7f7f7f80
009bae33  MOV qword ptr [RSP + 0x328],RAX
009bae3b  LEA RAX,[RSP + 0x328]
009bae43  MOV qword ptr [RSP + 0x440],RAX
009bae4b  CALL 0x00485080
009bae50  MOV qword ptr [RSP + 0x438],RAX
009bae58  LEA RAX,[0xe16200]
009bae5f  LEA RBX,[RSP + 0x430]
009bae67  LEA RCX,[0xefe659]
009bae6e  MOV EDI,0x6
009bae73  CALL 0x00413460
009bae78  MOV qword ptr [RAX + 0x8],0x12
009bae80  CMP dword ptr [0x019b5f00],0x0
009bae87  JZ 0x009bae94
009bae89  MOV RDX,qword ptr [RAX]
009bae8c  CALL 0x0048bbe0
009bae91  MOV qword ptr [R11],RDX
009bae94  LEA RDX,[0xf1d949]
009bae9b  MOV qword ptr [RAX],RDX
009bae9e  LEA RAX,[0xe16200]
009baea5  LEA RBX,[RSP + 0x430]
009baead  LEA RCX,[0xeffe26]
009baeb4  MOV EDI,0x7
009baeb9  CALL 0x00413460
009baebe  MOV qword ptr [RAX + 0x8],0x13
009baec6  CMP dword ptr [0x019b5f00],0x0
009baecd  JZ 0x009baeda
009baecf  MOV RDX,qword ptr [RAX]
009baed2  CALL 0x0048bbe0
009baed7  MOV qword ptr [R11],RDX
009baeda  LEA RDX,[0xf1f31d]
009baee1  MOV qword ptr [RAX],RDX
009baee4  MOV RAX,qword ptr [RSP + 0x278]
009baeec  MOV RBX,qword ptr [RSP + 0xe0]
009baef4  MOV RCX,qword ptr [RSP + 0x1c0]
009baefc  MOV RDI,qword ptr [RSP + 0x50]
009baf01  CALL 0x009b8fc0
009baf06  MOV qword ptr [RSP + 0xf8],RBX
009baf0e  MOV qword ptr [RSP + 0x298],RAX
009baf16  LEA RAX,[0xe16200]
009baf1d  LEA RBX,[RSP + 0x430]
009baf25  LEA RCX,[0xf0a13f]
009baf2c  MOV EDI,0xa
009baf31  CALL 0x00413460
009baf36  MOV RDX,qword ptr [RSP + 0xf8]
009baf3e  MOV qword ptr [RAX + 0x8],RDX
009baf42  CMP dword ptr [0x019b5f00],0x0
009baf49  JNZ 0x009baf55
009baf4b  MOV RSI,qword ptr [RSP + 0x298]
009baf53  JMP 0x009baf6c
009baf55  MOV RDX,qword ptr [RAX]
009baf58  CALL 0x0048bc00
009baf5d  MOV RSI,qword ptr [RSP + 0x298]
009baf65  MOV qword ptr [R11],RSI
009baf68  MOV qword ptr [R11 + 0x8],RDX
009baf6c  MOV qword ptr [RAX],RSI
009baf6f  LEA RCX,[RSP + 0x620]
009baf77  MOVUPS xmmword ptr [RCX],XMM15
009baf7b  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009baf80  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009baf85  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009baf8a  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009baf8f  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009baf94  LEA RAX,[0xe16200]
009baf9b  LEA RBX,[RSP + 0x430]
009bafa3  CALL 0x004225e0
009bafa8  JMP 0x009bb078
009bafad  MOV qword ptr [RSP + 0x1b8],0x0
009bafb9  MOV qword ptr [RSP + 0x190],RBX
009bafc1  MOV qword ptr [RSP + 0x198],RCX
009bafc9  CALL 0x0044b160
009bafce  MOV RBX,qword ptr [RSP + 0x190]
009bafd6  MOV RCX,qword ptr [RSP + 0x198]
009bafde  MOV RAX,qword ptr [RSP + 0x1b8]
009bafe6  ADD RSP,0x710
009bafed  POP RBP
009bafee  RET
009bafef  MOV qword ptr [RSP + 0x1b8],0x0
009baffb  MOV qword ptr [RSP + 0x190],RAX
009bb003  MOV qword ptr [RSP + 0x198],RBX
009bb00b  CALL 0x0044b160
009bb010  MOV RBX,qword ptr [RSP + 0x190]
009bb018  MOV RCX,qword ptr [RSP + 0x198]
009bb020  MOV RAX,qword ptr [RSP + 0x1b8]
009bb028  ADD RSP,0x710
009bb02f  POP RBP
009bb030  RET
009bb031  MOV qword ptr [RSP + 0x1b8],RAX
009bb039  MOVUPS xmmword ptr [RSP + 0x190],XMM15
009bb042  CALL 0x0044b160
009bb047  MOV RBX,qword ptr [RSP + 0x190]
009bb04f  MOV RCX,qword ptr [RSP + 0x198]
009bb057  MOV RAX,qword ptr [RSP + 0x1b8]
009bb05f  ADD RSP,0x710
009bb066  POP RBP
009bb067  RET
009bb068  MOV qword ptr [RAX],RDX
009bb06b  LEA RAX,[RSP + 0x620]
009bb073  CALL 0x00422640
009bb078  MOV RCX,qword ptr [RSP + 0x620]
009bb080  TEST RCX,RCX
009bb083  JZ 0x009bb187
009bb089  MOV RAX,qword ptr [RCX]
009bb08c  MOV RBX,qword ptr [RCX + 0x8]
009bb090  MOV RCX,qword ptr [RSP + 0x628]
009bb098  MOV RDX,qword ptr [RCX + 0x8]
009bb09c  MOV qword ptr [RSP + 0x58],RDX
009bb0a1  MOV RCX,qword ptr [RCX]
009bb0a4  MOV qword ptr [RSP + 0x1c8],RCX
009bb0ac  MOV RCX,qword ptr [RSP + 0x210]
009bb0b4  MOV RCX,qword ptr [RCX + 0x38]
009bb0b8  MOV qword ptr [RSP + 0x288],RCX
009bb0c0  NOP
009bb0c1  CALL 0x00640c00
009bb0c6  MOV qword ptr [RSP + 0x298],RAX
009bb0ce  MOV qword ptr [RSP + 0xf8],RBX
009bb0d6  LEA RAX,[0xddc380]
009bb0dd  NOP dword ptr [RAX]
009bb0e0  CALL 0x00421f00
009bb0e5  MOV RCX,qword ptr [RSP + 0x58]
009bb0ea  MOV qword ptr [RAX + 0x8],RCX
009bb0ee  CMP dword ptr [0x019b5f00],0x0
009bb0f5  JNZ 0x009bb102
009bb0f7  MOV RDX,qword ptr [RSP + 0x1c8]
009bb0ff  NOP
009bb100  JMP 0x009bb112
009bb102  CALL 0x0048bbe0
009bb107  MOV RDX,qword ptr [RSP + 0x1c8]
009bb10f  MOV qword ptr [R11],RDX
009bb112  MOV qword ptr [RSP + 0x290],RAX
009bb11a  MOV qword ptr [RAX],RDX
009bb11d  LEA RAX,[0xe91b20]
009bb124  MOV RBX,qword ptr [RSP + 0x288]
009bb12c  MOV RCX,qword ptr [RSP + 0x298]
009bb134  MOV RDI,qword ptr [RSP + 0xf8]
009bb13c  NOP dword ptr [RAX]
009bb140  CALL 0x00413460
009bb145  MOV qword ptr [RAX + 0x8],0x1
009bb14d  MOV qword ptr [RAX + 0x10],0x1
009bb155  CMP dword ptr [0x019b5f00],0x0
009bb15c  JNZ 0x009bb16b
009bb15e  MOV RDX,qword ptr [RSP + 0x290]
009bb166  JMP 0x009bb068
009bb16b  MOV RCX,qword ptr [RAX]
009bb16e  CALL 0x0048bc00
009bb173  MOV RDX,qword ptr [RSP + 0x290]
009bb17b  MOV qword ptr [R11],RDX
009bb17e  MOV qword ptr [R11 + 0x8],RCX
009bb182  JMP 0x009bb068
009bb187  MOV RAX,qword ptr [0x0196ccc0]
009bb18e  MOV RBX,qword ptr [RSP + 0x210]
009bb196  CALL 0x0066f720
009bb19b  NOP dword ptr [RAX + RAX*0x1]
009bb1a0  TEST RBX,RBX
009bb1a3  JNZ 0x009bb21e
009bb1a5  MOV qword ptr [RSP + 0x1a8],RAX
009bb1ad  MOV RCX,qword ptr [RAX + 0x40]
009bb1b1  TEST byte ptr [RCX],AL
009bb1b3  MOV RDX,qword ptr [RAX + 0x48]
009bb1b7  LEA RBX,[0x9bc060]
009bb1be  MOV qword ptr [RSP + 0x310],RBX
009bb1c6  MOV qword ptr [RSP + 0x318],RCX
009bb1ce  MOV qword ptr [RSP + 0x320],RDX
009bb1d6  LEA RCX,[RSP + 0x310]
009bb1de  MOV qword ptr [RSP + 0x118],RCX
009bb1e6  LEA RAX,[RSP + 0x100]
009bb1ee  CALL 0x0044ac40
009bb1f3  MOV RCX,qword ptr [RSP + 0x1a8]
009bb1fb  MOV RDX,qword ptr [RCX + 0x40]
009bb1ff  MOV RBX,qword ptr [RCX + 0x48]
009bb203  TEST RDX,RDX
009bb206  JZ 0x009bb261
009bb208  MOV RSI,qword ptr [RDX + 0x8]
009bb20c  MOV RDI,qword ptr [0x01976600]
009bb213  MOV R8,qword ptr [RDI]
009bb216  MOV EDX,dword ptr [RDX + 0x10]
009bb219  JMP 0x009bbe79
009bb21e  MOV qword ptr [RSP + 0x1b8],0x0
009bb22a  MOV qword ptr [RSP + 0x190],RBX
009bb232  MOV qword ptr [RSP + 0x198],RCX
009bb23a  CALL 0x0044b160
009bb23f  MOV RBX,qword ptr [RSP + 0x190]
009bb247  MOV RCX,qword ptr [RSP + 0x198]
009bb24f  MOV RAX,qword ptr [RSP + 0x1b8]
009bb257  ADD RSP,0x710
009bb25e  POP RBP
009bb25f  NOP
009bb260  RET
009bb261  MOV RAX,RDX
009bb264  CALL 0x004991a0
009bb269  TEST RDI,RDI
009bb26c  JNZ 0x009bb476
009bb272  MOV qword ptr [RSP + 0xd8],RCX
009bb27a  MOV qword ptr [RSP + 0xd0],RBX
009bb282  MOV qword ptr [RSP + 0x270],RAX
009bb28a  LEA RAX,[0xe7aa80]
009bb291  CALL 0x00421f00
009bb296  MOV qword ptr [RSP + 0x708],RAX
009bb29e  MOV RBX,qword ptr [RSP + 0xd0]
009bb2a6  MOV RCX,qword ptr [RSP + 0xd8]
009bb2ae  LEA RDI,[0xdc6420]
009bb2b5  MOV RSI,RAX
009bb2b8  MOV RAX,qword ptr [RSP + 0x270]
009bb2c0  CALL 0x0052c3c0
009bb2c5  TEST RAX,RAX
009bb2c8  JZ 0x009bb396
009bb2ce  LEA RDX,[RSP + 0x2f0]
009bb2d6  MOVUPS xmmword ptr [RDX],XMM15
009bb2da  MOVUPS xmmword ptr [RDX + 0x10],XMM15
009bb2df  NOP
009bb2e0  JZ 0x009bb2e6
009bb2e2  MOV RAX,qword ptr [RAX + 0x8]
009bb2e6  MOV qword ptr [RSP + 0x2f0],RAX
009bb2ee  MOV qword ptr [RSP + 0x2f8],RBX
009bb2f6  XOR EAX,EAX
009bb2f8  MOV RBX,qword ptr [RSP + 0x270]
009bb300  MOV RCX,qword ptr [RSP + 0xd0]
009bb308  CALL 0x0046b920
009bb30d  CALL 0x00481ee0
009bb312  LEA RDX,[0xdd29c0]
009bb319  MOV qword ptr [RSP + 0x300],RDX
009bb321  MOV qword ptr [RSP + 0x308],RAX
009bb329  LEA RDX,[0x9bc000]
009bb330  MOV qword ptr [RSP + 0x5f0],RDX
009bb338  MOV qword ptr [RSP + 0x600],0x42
009bb344  LEA RDX,[0xf51f05]
009bb34b  MOV qword ptr [RSP + 0x5f8],RDX
009bb353  MOV qword ptr [RSP + 0x610],0x2
009bb35f  MOV qword ptr [RSP + 0x618],0x2
009bb36b  LEA RDX,[RSP + 0x2f0]
009bb373  MOV qword ptr [RSP + 0x608],RDX
009bb37b  MOV RAX,qword ptr [0x01990148]
009bb382  XOR EBX,EBX
009bb384  MOV ECX,0x2
009bb389  LEA RDI,[RSP + 0x5f0]
009bb391  CALL 0x0054d540
009bb396  MOV RCX,qword ptr [RSP + 0x708]
009bb39e  CMP qword ptr [RCX + 0x20],0x0
009bb3a3  JZ 0x009bb445
009bb3a9  MOVUPS xmmword ptr [RSP + 0x2e0],XMM15
009bb3b2  MOV RAX,qword ptr [RCX + 0x18]
009bb3b6  MOV RBX,qword ptr [RCX + 0x20]
009bb3ba  CALL 0x00481ee0
009bb3bf  LEA RCX,[0xdd29c0]
009bb3c6  MOV qword ptr [RSP + 0x2e0],RCX
009bb3ce  MOV qword ptr [RSP + 0x2e8],RAX
009bb3d6  LEA RCX,[0x9bbfa0]
009bb3dd  MOV qword ptr [RSP + 0x5f0],RCX
009bb3e5  MOV qword ptr [RSP + 0x600],0x34
009bb3f1  LEA RCX,[0xf481d0]
009bb3f8  MOV qword ptr [RSP + 0x5f8],RCX
009bb400  MOV qword ptr [RSP + 0x610],0x1
009bb40c  MOV qword ptr [RSP + 0x618],0x1
009bb418  LEA RCX,[RSP + 0x2e0]
009bb420  MOV qword ptr [RSP + 0x608],RCX
009bb428  MOV RAX,qword ptr [0x01990148]
009bb42f  XOR EBX,EBX
009bb431  MOV ECX,0x2
009bb436  LEA RDI,[RSP + 0x5f0]
009bb43e  NOP
009bb440  CALL 0x0054d540
009bb445  CALL 0x004825c0
009bb44a  MOV qword ptr [RSP + 0x260],RAX
009bb452  MOV RAX,qword ptr [RSP + 0x1a8]
009bb45a  MOV RAX,qword ptr [RAX + 0x38]
009bb45e  NOP
009bb460  CALL 0x006727e0
009bb465  MOV qword ptr [RSP + 0x1a0],RAX
009bb46d  MOV qword ptr [RSP + 0x48],RBX
009bb472  XOR ECX,ECX
009bb474  JMP 0x009bb4c0
009bb476  MOV qword ptr [RSP + 0x1b8],0x0
009bb482  MOV qword ptr [RSP + 0x190],RDI
009bb48a  MOV qword ptr [RSP + 0x198],RSI
009bb492  CALL 0x0044b160
009bb497  MOV RBX,qword ptr [RSP + 0x190]
009bb49f  MOV RCX,qword ptr [RSP + 0x198]
009bb4a7  MOV RAX,qword ptr [RSP + 0x1b8]
009bb4af  ADD RSP,0x710
009bb4b6  POP RBP
009bb4b7  RET
009bb4b8  INC RCX
009bb4bb  NOP dword ptr [RAX + RAX*0x1]
009bb4c0  CMP RBX,RCX
009bb4c3  JLE 0x009bb565
009bb4c9  MOV RDX,qword ptr [RAX + RCX*0x8]
009bb4cd  MOV RDI,qword ptr [RDX + 0x8]
009bb4d1  TEST RDI,RDI
009bb4d4  JZ 0x009bb4b8
009bb4d6  MOV RSI,qword ptr [RDX + 0x18]
009bb4da  TEST RSI,RSI
009bb4dd  JZ 0x009bb4b8
009bb4df  MOV qword ptr [RSP + 0xf8],RSI
009bb4e7  MOV qword ptr [RSP + 0xf0],RCX
009bb4ef  MOV RCX,qword ptr [RDX]
009bb4f2  MOV RDX,qword ptr [RDX + 0x10]
009bb4f6  MOV qword ptr [RSP + 0x298],RDX
009bb4fe  LEA RAX,[0xe16200]
009bb505  MOV RBX,qword ptr [RSP + 0x260]
009bb50d  CALL 0x00413460
009bb512  MOV RDX,qword ptr [RSP + 0xf8]
009bb51a  MOV qword ptr [RAX + 0x8],RDX
009bb51e  CMP dword ptr [0x019b5f00],0x0
009bb525  JNZ 0x009bb531
009bb527  MOV RSI,qword ptr [RSP + 0x298]
009bb52f  JMP 0x009bb548
009bb531  MOV RDX,qword ptr [RAX]
009bb534  CALL 0x0048bc00
009bb539  MOV RSI,qword ptr [RSP + 0x298]
009bb541  MOV qword ptr [R11],RSI
009bb544  MOV qword ptr [R11 + 0x8],RDX
009bb548  MOV qword ptr [RAX],RSI
009bb54b  MOV RAX,qword ptr [RSP + 0x1a0]
009bb553  MOV RCX,qword ptr [RSP + 0xf0]
009bb55b  MOV RBX,qword ptr [RSP + 0x48]
009bb560  JMP 0x009bb4b8
009bb565  MOV RDX,qword ptr [RSP + 0x708]
009bb56d  MOV RBX,qword ptr [RDX + 0x28]
009bb571  TEST RBX,RBX
009bb574  JZ 0x009bb9ca
009bb57a  LEA RAX,[0xe16300]
009bb581  LEA RCX,[0xefe407]
009bb588  MOV EDI,0x6
009bb58d  CALL 0x00412ee0
009bb592  LEA RDX,[0xe16300]
009bb599  CMP qword ptr [RAX],RDX
009bb59c  JNZ 0x009bb5a4
009bb59e  MOV RSI,qword ptr [RAX + 0x8]
009bb5a2  JMP 0x009bb5a9
009bb5a4  MOV ESI,0x0
009bb5a9  JNZ 0x009bb7b1
009bb5af  LEA RCX,[RSP + 0x620]
009bb5b7  MOVUPS xmmword ptr [RCX],XMM15
009bb5bb  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009bb5c0  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009bb5c5  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009bb5ca  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009bb5cf  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009bb5d4  MOV RAX,RDX
009bb5d7  MOV RBX,RSI
009bb5da  CALL 0x004225e0
009bb5df  NOP
009bb5e0  JMP 0x009bb5ef
009bb5e2  LEA RAX,[RSP + 0x620]
009bb5ea  CALL 0x00422640
009bb5ef  MOV RDX,qword ptr [RSP + 0x620]
009bb5f7  NOP word ptr [RAX + RAX*0x1]
009bb600  TEST RDX,RDX
009bb603  JZ 0x009bb7aa
009bb609  MOV RSI,qword ptr [RSP + 0x628]
009bb611  MOV R8,qword ptr [RSI]
009bb614  MOV RSI,qword ptr [RSI + 0x8]
009bb618  LEA R9,[0xdd29c0]
009bb61f  NOP
009bb620  CMP R8,R9
009bb623  JNZ 0x009bb62e
009bb625  MOV R10,qword ptr [RSI]
009bb628  MOV R11,qword ptr [RSI + 0x8]
009bb62c  JMP 0x009bb63a
009bb62e  MOV R11D,0x0
009bb634  MOV R10D,0x0
009bb63a  MOV RCX,qword ptr [RDX]
009bb63d  MOV RDI,qword ptr [RDX + 0x8]
009bb641  JNZ 0x009bb6a5
009bb643  TEST R11,R11
009bb646  JZ 0x009bb6a5
009bb648  MOV qword ptr [RSP + 0x78],R11
009bb64d  MOV qword ptr [RSP + 0x1e8],R10
009bb655  LEA RAX,[0xe16200]
009bb65c  MOV RBX,qword ptr [RSP + 0x260]
009bb664  CALL 0x00413460
009bb669  MOV RDX,qword ptr [RSP + 0x78]
009bb66e  MOV qword ptr [RAX + 0x8],RDX
009bb672  CMP dword ptr [0x019b5f00],0x0
009bb679  JNZ 0x009bb685
009bb67b  MOV RDX,qword ptr [RSP + 0x1e8]
009bb683  JMP 0x009bb69c
009bb685  MOV RCX,qword ptr [RAX]
009bb688  CALL 0x0048bc00
009bb68d  MOV RDX,qword ptr [RSP + 0x1e8]
009bb695  MOV qword ptr [R11],RDX
009bb698  MOV qword ptr [R11 + 0x8],RCX
009bb69c  MOV qword ptr [RAX],RDX
009bb69f  NOP
009bb6a0  JMP 0x009bb5e2
009bb6a5  LEA RDX,[0xdd2d80]
009bb6ac  CMP R8,RDX
009bb6af  JNZ 0x009bb6b7
009bb6b1  MOVSD XMM0,qword ptr [RSI]
009bb6b5  JMP 0x009bb6c0
009bb6b7  XORPS XMM0,XMM0
009bb6ba  NOP word ptr [RAX + RAX*0x1]
009bb6c0  JNZ 0x009bb5e2
009bb6c6  MOV qword ptr [RSP + 0xa0],RDI
009bb6ce  MOV qword ptr [RSP + 0x230],RCX
009bb6d6  MOVUPS xmmword ptr [RSP + 0x680],XMM15
009bb6df  MOVQ RAX,XMM0
009bb6e4  CALL 0x00481e60
009bb6e9  LEA RCX,[0xdd2d80]
009bb6f0  MOV qword ptr [RSP + 0x680],RCX
009bb6f8  MOV qword ptr [RSP + 0x688],RAX
009bb700  LEA RAX,[0xefb6ab]
009bb707  MOV EBX,0x4
009bb70c  LEA RCX,[RSP + 0x680]
009bb714  MOV EDI,0x1
009bb719  MOV RSI,RDI
009bb71c  NOP dword ptr [RAX]
009bb720  CALL 0x005055a0
009bb725  MOV qword ptr [RSP + 0xf8],RBX
009bb72d  MOV qword ptr [RSP + 0x298],RAX
009bb735  LEA RAX,[0xe16200]
009bb73c  MOV RBX,qword ptr [RSP + 0x260]
009bb744  MOV RCX,qword ptr [RSP + 0x230]
009bb74c  MOV RDI,qword ptr [RSP + 0xa0]
009bb754  CALL 0x00413460
009bb759  MOV RCX,qword ptr [RSP + 0xf8]
009bb761  MOV qword ptr [RAX + 0x8],RCX
009bb765  CMP dword ptr [0x019b5f00],0x0
009bb76c  JNZ 0x009bb778
009bb76e  MOV RDX,qword ptr [RSP + 0x298]
009bb776  JMP 0x009bb794
009bb778  MOV RCX,qword ptr [RAX]
009bb77b  NOP dword ptr [RAX + RAX*0x1]
009bb780  CALL 0x0048bc00
009bb785  MOV RDX,qword ptr [RSP + 0x298]
009bb78d  MOV qword ptr [R11],RDX
009bb790  MOV qword ptr [R11 + 0x8],RCX
009bb794  MOV qword ptr [RAX],RDX
009bb797  LEA RDX,[0xdd2d80]
009bb79e  LEA R9,[0xdd29c0]
009bb7a5  JMP 0x009bb5e2
009bb7aa  LEA RDX,[0xe16300]
009bb7b1  MOV RSI,qword ptr [RSP + 0x708]
009bb7b9  MOV RBX,qword ptr [RSI + 0x28]
009bb7bd  LEA RCX,[RSP + 0x620]
009bb7c5  MOVUPS xmmword ptr [RCX],XMM15
009bb7c9  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009bb7ce  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009bb7d3  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009bb7d8  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009bb7dd  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009bb7e2  MOV RAX,RDX
009bb7e5  CALL 0x004225e0
009bb7ea  JMP 0x009bb7f9
009bb7ec  LEA RAX,[RSP + 0x620]
009bb7f4  CALL 0x00422640
009bb7f9  MOV RDX,qword ptr [RSP + 0x620]
009bb801  TEST RDX,RDX
009bb804  JZ 0x009bb9ca
009bb80a  MOV RDI,qword ptr [RDX + 0x8]
009bb80e  MOV RSI,qword ptr [RSP + 0x628]
009bb816  TEST byte ptr [RSI],AL
009bb818  MOV RCX,qword ptr [RDX]
009bb81b  NOP dword ptr [RAX + RAX*0x1]
009bb820  CMP RDI,0x6
009bb824  JNZ 0x009bb836
009bb826  CMP dword ptr [RCX],0x6b6f6f63
009bb82c  JNZ 0x009bb836
009bb82e  CMP word ptr [RCX + 0x4],0x6569
009bb834  JZ 0x009bb7ec
009bb836  MOV RDX,qword ptr [RSI]
009bb839  MOV RSI,qword ptr [RSI + 0x8]
009bb83d  LEA R8,[0xdd29c0]
009bb844  CMP RDX,R8
009bb847  JNZ 0x009bb852
009bb849  MOV R9,qword ptr [RSI]
009bb84c  MOV R10,qword ptr [RSI + 0x8]
009bb850  JMP 0x009bb860
009bb852  MOV R10D,0x0
009bb858  MOV R9D,0x0
009bb85e  NOP
009bb860  JNZ 0x009bb8c5
009bb862  TEST R10,R10
009bb865  JZ 0x009bb8c5
009bb867  MOV qword ptr [RSP + 0x1e0],R9
009bb86f  MOV qword ptr [RSP + 0x70],R10
009bb874  LEA RAX,[0xe16200]
009bb87b  MOV RBX,qword ptr [RSP + 0x260]
009bb883  CALL 0x00413460
009bb888  MOV RDX,qword ptr [RSP + 0x70]
009bb88d  MOV qword ptr [RAX + 0x8],RDX
009bb891  CMP dword ptr [0x019b5f00],0x0
009bb898  JNZ 0x009bb8a4
009bb89a  MOV RDX,qword ptr [RSP + 0x1e0]
009bb8a2  JMP 0x009bb8bb
009bb8a4  MOV RCX,qword ptr [RAX]
009bb8a7  CALL 0x0048bc00
009bb8ac  MOV RDX,qword ptr [RSP + 0x1e0]
009bb8b4  MOV qword ptr [R11],RDX
009bb8b7  MOV qword ptr [R11 + 0x8],RCX
009bb8bb  MOV qword ptr [RAX],RDX
009bb8be  NOP
009bb8c0  JMP 0x009bb7ec
009bb8c5  LEA RBX,[0xdd2d80]
009bb8cc  CMP RDX,RBX
009bb8cf  JNZ 0x009bb8d7
009bb8d1  MOVSD XMM0,qword ptr [RSI]
009bb8d5  JMP 0x009bb8e0
009bb8d7  XORPS XMM0,XMM0
009bb8da  NOP word ptr [RAX + RAX*0x1]
009bb8e0  JNZ 0x009bb7ec
009bb8e6  MOV qword ptr [RSP + 0x98],RDI
009bb8ee  MOV qword ptr [RSP + 0x228],RCX
009bb8f6  MOVUPS xmmword ptr [RSP + 0x680],XMM15
009bb8ff  MOVQ RAX,XMM0
009bb904  CALL 0x00481e60
009bb909  LEA RCX,[0xdd2d80]
009bb910  MOV qword ptr [RSP + 0x680],RCX
009bb918  MOV qword ptr [RSP + 0x688],RAX
009bb920  LEA RAX,[0xefb6ab]
009bb927  MOV EBX,0x4
009bb92c  LEA RCX,[RSP + 0x680]
009bb934  MOV EDI,0x1
009bb939  MOV RSI,RDI
009bb93c  NOP dword ptr [RAX]
009bb940  CALL 0x005055a0
009bb945  MOV qword ptr [RSP + 0xf8],RBX
009bb94d  MOV qword ptr [RSP + 0x298],RAX
009bb955  LEA RAX,[0xe16200]
009bb95c  MOV RBX,qword ptr [RSP + 0x260]
009bb964  MOV RCX,qword ptr [RSP + 0x228]
009bb96c  MOV RDI,qword ptr [RSP + 0x98]
009bb974  CALL 0x00413460
009bb979  MOV RCX,qword ptr [RSP + 0xf8]
009bb981  MOV qword ptr [RAX + 0x8],RCX
009bb985  CMP dword ptr [0x019b5f00],0x0
009bb98c  JNZ 0x009bb998
009bb98e  MOV RDX,qword ptr [RSP + 0x298]
009bb996  JMP 0x009bb9b4
009bb998  MOV RCX,qword ptr [RAX]
009bb99b  NOP dword ptr [RAX + RAX*0x1]
009bb9a0  CALL 0x0048bc00
009bb9a5  MOV RDX,qword ptr [RSP + 0x298]
009bb9ad  MOV qword ptr [R11],RDX
009bb9b0  MOV qword ptr [R11 + 0x8],RCX
009bb9b4  MOV qword ptr [RAX],RDX
009bb9b7  LEA RBX,[0xdd2d80]
009bb9be  LEA R8,[0xdd29c0]
009bb9c5  JMP 0x009bb7ec
009bb9ca  LEA RCX,[RSP + 0x620]
009bb9d2  MOVUPS xmmword ptr [RCX],XMM15
009bb9d6  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009bb9db  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009bb9e0  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009bb9e5  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009bb9ea  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009bb9ef  LEA RAX,[0xe16200]
009bb9f6  MOV RBX,qword ptr [RSP + 0x260]
009bb9fe  NOP
009bba00  CALL 0x004225e0
009bba05  JMP 0x009bba14
009bba07  LEA RAX,[RSP + 0x620]
009bba0f  CALL 0x00422640
009bba14  MOV RDX,qword ptr [RSP + 0x620]
009bba1c  NOP dword ptr [RAX]
009bba20  TEST RDX,RDX
009bba23  JZ 0x009bbb14
009bba29  MOV qword ptr [RSP + 0x280],RDX
009bba31  MOV RAX,qword ptr [RDX]
009bba34  MOV RBX,qword ptr [RDX + 0x8]
009bba38  MOV RCX,qword ptr [RSP + 0x628]
009bba40  MOV RCX,qword ptr [RCX + 0x8]
009bba44  MOV qword ptr [RSP + 0xe8],RCX
009bba4c  TEST RCX,RCX
009bba4f  CALL 0x004af2e0
009bba54  CMP RBX,0x3
009bba58  JNZ 0x009bbaa2
009bba5a  CMP word ptr [RAX],0x4955
009bba5f  NOP
009bba60  JNZ 0x009bba80
009bba62  CMP byte ptr [RAX + 0x2],0x44
009bba66  JNZ 0x009bba78
009bba68  MOV RDX,qword ptr [RSP + 0xe8]
009bba70  TEST RDX,RDX
009bba73  JMP 0x009bbb03
009bba78  CMP RBX,0x3
009bba7c  JMP 0x009bba84
009bba80  CMP RBX,0x3
009bba84  JNZ 0x009bbaa2
009bba86  CMP word ptr [RAX],0x4943
009bba8b  JNZ 0x009bbaa2
009bba8d  CMP byte ptr [RAX + 0x2],0x44
009bba91  JNZ 0x009bbaa2
009bba93  MOV RDX,qword ptr [RSP + 0xe8]
009bba9b  TEST RDX,RDX
009bba9e  NOP
009bbaa0  JMP 0x009bbb03
009bbaa2  CMP RBX,0x4
009bbaa6  JNZ 0x009bbac0
009bbaa8  CMP dword ptr [RAX],0x44494553
009bbaae  JNZ 0x009bbac0
009bbab0  MOV RDX,qword ptr [RSP + 0xe8]
009bbab8  TEST RDX,RDX
009bbabb  JMP 0x009bbb03
009bbac0  CMP RBX,0xb
009bbac4  JNZ 0x009bba07
009bbaca  MOV RDX,0x524553555f353131
009bbad4  CMP qword ptr [RAX],RDX
009bbad7  JNZ 0x009bba07
009bbadd  CMP word ptr [RAX + 0x8],0x495f
009bbae3  JNZ 0x009bba07
009bbae9  CMP byte ptr [RAX + 0xa],0x44
009bbaed  JNZ 0x009bba07
009bbaf3  MOV RDX,qword ptr [RSP + 0xe8]
009bbafb  NOP dword ptr [RAX + RAX*0x1]
009bbb00  TEST RDX,RDX
009bbb03  JZ 0x009bba07
009bbb09  MOV RDX,qword ptr [RSP + 0x280]
009bbb11  TEST RDX,RDX
009bbb14  JZ 0x009bbb5c
009bbb16  LEA RCX,[RSP + 0x620]
009bbb1e  MOVUPS xmmword ptr [RCX],XMM15
009bbb22  MOVUPS xmmword ptr [RCX + 0x10],XMM15
009bbb27  MOVUPS xmmword ptr [RCX + 0x20],XMM15
009bbb2c  MOVUPS xmmword ptr [RCX + 0x30],XMM15
009bbb31  MOVUPS xmmword ptr [RCX + 0x40],XMM15
009bbb36  MOVUPS xmmword ptr [RCX + 0x50],XMM15
009bbb3b  LEA RAX,[0xe16200]
009bbb42  MOV RBX,qword ptr [RSP + 0x260]
009bbb4a  CALL 0x004225e0
009bbb4f  XOR EAX,EAX
009bbb51  XOR ECX,ECX
009bbb53  XOR EDX,EDX
009bbb55  XOR EBX,EBX
009bbb57  JMP 0x009bbcec
009bbb5c  LEA RDX,[RSP + 0x2c0]
009bbb64  MOVUPS xmmword ptr [RDX],XMM15
009bbb68  MOVUPS xmmword ptr [RDX + 0x10],XMM15
009bbb6d  LEA RDX,[0xe16200]
009bbb74  MOV qword ptr [RSP + 0x2c0],RDX
009bbb7c  MOV RDX,qword ptr [RSP + 0x260]
009bbb84  MOV qword ptr [RSP + 0x2c8],RDX
009bbb8c  XOR EAX,EAX
009bbb8e  MOV RBX,qword ptr [RSP + 0x270]
009bbb96  MOV RCX,qword ptr [RSP + 0xd0]
009bbb9e  NOP
009bbba0  CALL 0x0046b920
009bbba5  CALL 0x00481ee0
009bbbaa  LEA RDX,[0xdd29c0]
009bbbb1  MOV qword ptr [RSP + 0x2d0],RDX
009bbbb9  MOV qword ptr [RSP + 0x2d8],RAX
009bbbc1  LEA RDX,[0x9bbf40]
009bbbc8  MOV qword ptr [RSP + 0x5f0],RDX
009bbbd0  MOV qword ptr [RSP + 0x600],0x66
009bbbdc  LEA RDX,[0xf6024a]
009bbbe3  MOV qword ptr [RSP + 0x5f8],RDX
009bbbeb  MOV qword ptr [RSP + 0x610],0x2
009bbbf7  MOV qword ptr [RSP + 0x618],0x2
009bbc03  LEA RDX,[RSP + 0x2c0]
009bbc0b  MOV qword ptr [RSP + 0x608],RDX
009bbc13  MOV RAX,qword ptr [0x01990148]
009bbc1a  XOR EBX,EBX
009bbc1c  MOV ECX,0x2
009bbc21  LEA RDI,[RSP + 0x5f0]
009bbc29  CALL 0x0054d540
009bbc2e  LEA RAX,[0xf57aa1]
009bbc35  MOV EBX,0x4d
009bbc3a  XOR ECX,ECX
009bbc3c  XOR EDI,EDI
009bbc3e  MOV RSI,RDI
009bbc41  CALL 0x005025c0
009bbc46  TEST RAX,RAX
009bbc49  JNZ 0x009bbc74
009bbc4b  NOP
009bbc4c  LEA RAX,[0xe21740]
009bbc53  CALL 0x00421f00
009bbc58  MOV qword ptr [RAX + 0x8],0x4d
009bbc60  LEA RCX,[0xf57aa1]
009bbc67  MOV qword ptr [RAX],RCX
009bbc6a  MOV RBX,RAX
009bbc6d  LEA RAX,[0x1139800]
009bbc74  MOV qword ptr [RSP + 0x1b8],0x0
009bbc80  MOV qword ptr [RSP + 0x190],RAX
009bbc88  MOV qword ptr [RSP + 0x198],RBX
009bbc90  CALL 0x0044b160
009bbc95  MOV RBX,qword ptr [RSP + 0x190]
009bbc9d  MOV RCX,qword ptr [RSP + 0x198]
009bbca5  MOV RAX,qword ptr [RSP + 0x1b8]
009bbcad  ADD RSP,0x710
009bbcb4  POP RBP
009bbcb5  RET
009bbcb6  MOV qword ptr [RSP + 0x258],RDX
009bbcbe  MOV qword ptr [RDX + RDI*0x1],RAX
009bbcc2  LEA RAX,[RSP + 0x620]
009bbcca  CALL 0x00422640
009bbccf  MOVZX EAX,byte ptr [RSP + 0x47]
009bbcd4  MOV RCX,qword ptr [RSP + 0xc0]
009bbcdc  MOV RDX,qword ptr [RSP + 0xb8]
009bbce4  MOV RBX,qword ptr [RSP + 0x258]
009bbcec  MOV R10,qword ptr [RSP + 0x620]
009bbcf4  TEST R10,R10
009bbcf7  JZ 0x009bbe31
009bbcfd  MOV qword ptr [RSP + 0xc0],RCX
009bbd05  MOV qword ptr [RSP + 0xb8],RDX
009bbd0d  MOV qword ptr [RSP + 0x258],RBX
009bbd15  MOV byte ptr [RSP + 0x47],AL
009bbd19  MOV RBX,qword ptr [R10]
009bbd1c  MOV RCX,qword ptr [R10 + 0x8]
009bbd20  MOV RDX,qword ptr [RSP + 0x628]
009bbd28  MOV R8,qword ptr [RDX]
009bbd2b  MOV R9,qword ptr [RDX + 0x8]
009bbd2f  XOR EAX,EAX
009bbd31  LEA RDI,[0x11331e0]
009bbd38  MOV ESI,0x1
009bbd3d  NOP dword ptr [RAX]
009bbd40  CALL 0x0046b280
009bbd45  MOV RDX,qword ptr [RSP + 0xb8]
009bbd4d  LEA R10,[RDX + 0x1]
009bbd51  MOV RCX,qword ptr [RSP + 0xc0]
009bbd59  CMP RCX,R10
009bbd5c  JC 0x009bbd6d
009bbd5e  MOV RDX,qword ptr [RSP + 0x258]
009bbd66  MOVZX ESI,byte ptr [RSP + 0x47]
009bbd6b  JMP 0x009bbdea
009bbd6d  MOV qword ptr [RSP + 0xf8],RBX
009bbd75  MOV qword ptr [RSP + 0x298],RAX
009bbd7d  NOP dword ptr [RAX]
009bbd80  CMP R10,0x2
009bbd84  JG 0x009bbdb3
009bbd86  MOVZX R8D,byte ptr [RSP + 0x47]
009bbd8c  TEST R8B,R8B
009bbd8f  JNZ 0x009bbdb3
009bbd91  TEST RDX,RDX
009bbd94  JNZ 0x009bbdb3
009bbd96  LEA RDX,[RSP + 0x2a0]
009bbd9e  MOVUPS xmmword ptr [RDX],XMM15
009bbda2  MOVUPS xmmword ptr [RDX + 0x10],XMM15
009bbda7  MOV ECX,0x2
009bbdac  MOV ESI,0x1
009bbdb1  JMP 0x009bbdea
009bbdb3  MOV RAX,qword ptr [RSP + 0x258]
009bbdbb  MOV RBX,R10
009bbdbe  MOV EDI,0x1
009bbdc3  LEA RSI,[0xdd29c0]
009bbdca  CALL 0x00486be0
009bbdcf  MOV RDX,RAX
009bbdd2  MOV R10,RBX
009bbdd5  MOVZX ESI,byte ptr [RSP + 0x47]
009bbdda  MOV RAX,qword ptr [RSP + 0x298]
009bbde2  MOV RBX,qword ptr [RSP + 0xf8]
009bbdea  MOV qword ptr [RSP + 0xb8],R10
009bbdf2  MOV qword ptr [RSP + 0xc0],RCX
009bbdfa  MOV byte ptr [RSP + 0x47],SIL
009bbdff  LEA RDI,[R10 + -0x1]
009bbe03  SHL RDI,0x4
009bbe07  MOV qword ptr [RDX + RDI*0x1 + 0x8],RBX
009bbe0c  CMP dword ptr [0x019b5f00],0x0
009bbe13  JZ 0x009bbcb6
009bbe19  MOV RBX,qword ptr [RDX + RDI*0x1]
009bbe1d  NOP dword ptr [RAX]
009bbe20  CALL 0x0048bc00
009bbe25  MOV qword ptr [R11],RAX
009bbe28  MOV qword ptr [R11 + 0x8],RBX
009bbe2c  JMP 0x009bbcb6
009bbe31  MOV RAX,RBX
009bbe34  MOV RBX,RDX
009bbe37  LEA RDI,[0xefa6fc]
009bbe3e  MOV ESI,0x2
009bbe43  CALL 0x004ae3e0
009bbe48  MOV RDX,qword ptr [RSP + 0x208]
009bbe50  MOV qword ptr [RDX + 0x18],RBX
009bbe54  CMP dword ptr [0x019b5f00],0x0
009bbe5b  JZ 0x009bbe6d
009bbe5d  MOV RCX,qword ptr [RDX + 0x10]
009bbe61  CALL 0x0048bc00
009bbe66  MOV qword ptr [R11],RAX
009bbe69  MOV qword ptr [R11 + 0x8],RCX
009bbe6d  MOV qword ptr [RDX + 0x10],RAX
009bbe71  MOV RAX,RDX
009bbe74  JMP 0x009bb031
009bbe79  MOV R9,RDX
009bbe7c  AND RDX,R8
009bbe7f  SHL RDX,0x4
009bbe83  MOV R10,qword ptr [RDI + RDX*0x1 + 0x8]
009bbe88  CMP R10,RSI
009bbe8b  JZ 0x009bbebd
009bbe8d  LEA RDX,[R9 + 0x1]
009bbe91  TEST R10,R10
009bbe94  JNZ 0x009bbe79
009bbe96  MOV qword ptr [RSP + 0x298],RBX
009bbe9e  LEA RAX,[0x1976600]
009bbea5  MOV RBX,RSI
009bbea8  CALL 0x0041e320
009bbead  MOV RBX,qword ptr [RSP + 0x298]
009bbeb5  MOV RDX,RAX
009bbeb8  JMP 0x009bb261
009bbebd  MOV RDX,qword ptr [RDI + RDX*0x1 + 0x10]
009bbec2  JMP 0x009bb261
009bbec7  MOV R8,RDX
009bbeca  AND RDX,RDI
009bbecd  SHL RDX,0x4
009bbed1  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
009bbed6  CMP R9,RBX
009bbed9  JZ 0x009bbef9
009bbedb  LEA RDX,[R8 + 0x1]
009bbedf  NOP
009bbee0  TEST R9,R9
009bbee3  JNZ 0x009bbec7
009bbee5  LEA RAX,[0x19765e0]
009bbeec  CALL 0x0041e320
009bbef1  MOV RDX,RAX
009bbef4  JMP 0x009ba795
009bbef9  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
009bbefe  NOP
009bbf00  JMP 0x009ba795
009bbf05  MOV qword ptr [RSP + 0x8],RAX
009bbf0a  MOV qword ptr [RSP + 0x10],RBX
009bbf0f  MOV qword ptr [RSP + 0x18],RCX
009bbf14  CALL 0x0048a280
009bbf19  MOV RAX,qword ptr [RSP + 0x8]
009bbf1e  MOV RBX,qword ptr [RSP + 0x10]
009bbf23  MOV RCX,qword ptr [RSP + 0x18]
009bbf28  JMP 0x009ba1e0
