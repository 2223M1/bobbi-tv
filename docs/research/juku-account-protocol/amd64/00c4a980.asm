; main.handleManualInput
00c4a980  LEA R12,[RSP + -0x78]
00c4a985  CMP R12,qword ptr [R14 + 0x10]
00c4a989  JBE 0x00c4af78
00c4a98f  PUSH RBP
00c4a990  MOV RBP,RSP
00c4a993  SUB RSP,0xf0
00c4a99a  MOV qword ptr [RSP + 0x110],RCX
00c4a9a2  MOV qword ptr [RSP + 0x108],RBX
00c4a9aa  MOV qword ptr [RSP + 0x100],RAX
00c4a9b2  MOV RCX,qword ptr [RAX + 0x18]
00c4a9b6  MOV RAX,RBX
00c4a9b9  CALL RCX
00c4a9bb  MOV qword ptr [RSP + 0x50],RAX
00c4a9c0  NOP
00c4a9c1  LEA RAX,[0xf10b4b]
00c4a9c8  MOV EBX,0xc
00c4a9cd  CALL 0x00640c00
00c4a9d2  MOV qword ptr [RSP + 0xe0],RAX
00c4a9da  MOV qword ptr [RSP + 0x38],RBX
00c4a9df  LEA RAX,[0xddc380]
00c4a9e6  CALL 0x00421f00
00c4a9eb  MOV qword ptr [RSP + 0xd8],RAX
00c4a9f3  MOV qword ptr [RAX + 0x8],0x10
00c4a9fb  LEA RCX,[0xf195fc]
00c4aa02  MOV qword ptr [RAX],RCX
00c4aa05  LEA RAX,[0xe91b20]
00c4aa0c  MOV RBX,qword ptr [RSP + 0x50]
00c4aa11  MOV RCX,qword ptr [RSP + 0xe0]
00c4aa19  MOV RDI,qword ptr [RSP + 0x38]
00c4aa1e  NOP
00c4aa20  CALL 0x00413460
00c4aa25  MOV qword ptr [RAX + 0x8],0x1
00c4aa2d  MOV qword ptr [RAX + 0x10],0x1
00c4aa35  CMP dword ptr [0x019b5f00],0x0
00c4aa3c  JNZ 0x00c4aa48
00c4aa3e  MOV R8,qword ptr [RSP + 0xd8]
00c4aa46  JMP 0x00c4aa5f
00c4aa48  MOV RDX,qword ptr [RAX]
00c4aa4b  CALL 0x0048bc00
00c4aa50  MOV R8,qword ptr [RSP + 0xd8]
00c4aa58  MOV qword ptr [R11],R8
00c4aa5b  MOV qword ptr [R11 + 0x8],RDX
00c4aa5f  MOV qword ptr [RAX],R8
00c4aa62  MOV RDX,qword ptr [RSP + 0x110]
00c4aa6a  CMP qword ptr [RDX + 0x8],0x4
00c4aa6f  JNZ 0x00c4aac5
00c4aa71  MOV R8,qword ptr [RDX]
00c4aa74  CMP dword ptr [R8],0x54534f50
00c4aa7b  JNZ 0x00c4aac5
00c4aa7d  LEA RAX,[0xe2e100]
00c4aa84  CALL 0x00421f00
00c4aa89  MOV qword ptr [RSP + 0xe8],RAX
00c4aa91  MOV RCX,qword ptr [RSP + 0x110]
00c4aa99  MOV RDX,qword ptr [RCX + 0x40]
00c4aa9d  MOV RCX,qword ptr [RCX + 0x48]
00c4aaa1  MOV qword ptr [RSP + 0x48],RCX
00c4aaa6  TEST RDX,RDX
00c4aaa9  JZ 0x00c4aaf4
00c4aaab  MOV RBX,qword ptr [RDX + 0x8]
00c4aaaf  MOV RSI,qword ptr [0x01973e80]
00c4aab6  MOV RDI,qword ptr [RSI]
00c4aab9  MOV EDX,dword ptr [RDX + 0x10]
00c4aabc  NOP dword ptr [RAX]
00c4aac0  JMP 0x00c4af3d
00c4aac5  MOV RAX,qword ptr [RSP + 0x100]
00c4aacd  MOV RBX,qword ptr [RSP + 0x108]
00c4aad5  LEA RCX,[0xf1d535]
00c4aadc  MOV EDI,0x12
00c4aae1  MOV ESI,0x195
00c4aae6  CALL 0x00c484c0
00c4aaeb  ADD RSP,0xf0
00c4aaf2  POP RBP
00c4aaf3  RET
00c4aaf4  MOV qword ptr [RSP + 0xe0],RDX
00c4aafc  LEA RAX,[0xeba560]
00c4ab03  CALL 0x00421f00
00c4ab08  MOV RCX,qword ptr [RSP + 0xe0]
00c4ab10  MOV qword ptr [RAX],RCX
00c4ab13  CMP dword ptr [0x019b5f00],0x0
00c4ab1a  JNZ 0x00c4ab23
00c4ab1c  MOV RDX,qword ptr [RSP + 0x48]
00c4ab21  JMP 0x00c4ab30
00c4ab23  CALL 0x0048bbe0
00c4ab28  MOV RDX,qword ptr [RSP + 0x48]
00c4ab2d  MOV qword ptr [R11],RDX
00c4ab30  MOV qword ptr [RAX + 0x8],RDX
00c4ab34  LEA RBX,[0xdc06e0]
00c4ab3b  MOV RCX,qword ptr [RSP + 0xe8]
00c4ab43  CALL 0x0053f680
00c4ab48  TEST RAX,RAX
00c4ab4b  JNZ 0x00c4ae26
00c4ab51  MOV RCX,qword ptr [RSP + 0xe8]
00c4ab59  MOV RAX,qword ptr [RCX]
00c4ab5c  MOV RBX,qword ptr [RCX + 0x8]
00c4ab60  CALL 0x00c47f20
00c4ab65  MOV RCX,qword ptr [RSP + 0xe8]
00c4ab6d  MOV qword ptr [RCX + 0x8],RBX
00c4ab71  CMP dword ptr [0x019b5f00],0x0
00c4ab78  JZ 0x00c4ab8c
00c4ab7a  MOV RDX,qword ptr [RCX]
00c4ab7d  NOP dword ptr [RAX]
00c4ab80  CALL 0x0048bc00
00c4ab85  MOV qword ptr [R11],RAX
00c4ab88  MOV qword ptr [R11 + 0x8],RDX
00c4ab8c  MOV qword ptr [RCX],RAX
00c4ab8f  MOV RDX,qword ptr [0x019900d0]
00c4ab96  MOV RCX,RAX
00c4ab99  MOV RDI,RBX
00c4ab9c  LEA RAX,[0xe17280]
00c4aba3  MOV RBX,RDX
00c4aba6  CALL 0x004131a0
00c4abab  TEST BL,BL
00c4abad  JZ 0x00c4adf7
00c4abb3  MOV RDX,qword ptr [RSP + 0xe8]
00c4abbb  MOV RAX,qword ptr [RDX + 0x10]
00c4abbf  MOV RBX,qword ptr [RDX + 0x18]
00c4abc3  CMP qword ptr [RDX + 0x8],0x6
00c4abc8  JNZ 0x00c4ac6f
00c4abce  MOV R8,qword ptr [RDX]
00c4abd1  CMP dword ptr [R8],0x59494c41
00c4abd8  JNZ 0x00c4ac6f
00c4abde  CMP word ptr [R8 + 0x4],0x4e55
00c4abe5  JNZ 0x00c4ac6f
00c4abeb  MOV qword ptr [RSP + 0x28],RBX
00c4abf0  MOV qword ptr [RSP + 0x40],RAX
00c4abf5  LEA RCX,[0xf176a8]
00c4abfc  MOV EDI,0xf
00c4ac01  CALL 0x00414f60
00c4ac06  TEST RAX,RAX
00c4ac09  JL 0x00c4ac17
00c4ac0b  MOV RBX,qword ptr [RSP + 0x28]
00c4ac10  MOV RAX,qword ptr [RSP + 0x40]
00c4ac15  JMP 0x00c4ac67
00c4ac17  MOVUPS xmmword ptr [RSP + 0xb8],XMM15
00c4ac20  MOV RAX,qword ptr [RSP + 0x40]
00c4ac25  MOV RBX,qword ptr [RSP + 0x28]
00c4ac2a  CALL 0x00481ee0
00c4ac2f  LEA RCX,[0xdd29c0]
00c4ac36  MOV qword ptr [RSP + 0xb8],RCX
00c4ac3e  MOV qword ptr [RSP + 0xc0],RAX
00c4ac46  LEA RAX,[0xf1f05e]
00c4ac4d  MOV EBX,0x13
00c4ac52  LEA RCX,[RSP + 0xb8]
00c4ac5a  MOV EDI,0x1
00c4ac5f  MOV RSI,RDI
00c4ac62  CALL 0x005055a0
00c4ac67  MOV RDX,qword ptr [RSP + 0xe8]
00c4ac6f  CMP qword ptr [RDX + 0x8],0x6
00c4ac74  JNZ 0x00c4ad59
00c4ac7a  MOV R8,qword ptr [RDX]
00c4ac7d  CMP dword ptr [R8],0x4c4e5558
00c4ac84  JNZ 0x00c4ad59
00c4ac8a  CMP word ptr [R8 + 0x4],0x4945
00c4ac91  JNZ 0x00c4ad59
00c4ac97  MOV qword ptr [RSP + 0x30],RBX
00c4ac9c  MOV qword ptr [RSP + 0xd0],RAX
00c4aca4  LEA RCX,[0xf176a8]
00c4acab  MOV EDI,0xf
00c4acb0  CALL 0x00414f60
00c4acb5  TEST RAX,RAX
00c4acb8  JL 0x00c4accc
00c4acba  MOV RBX,qword ptr [RSP + 0x30]
00c4acbf  MOV RAX,qword ptr [RSP + 0xd0]
00c4acc7  JMP 0x00c4ad51
00c4accc  MOV RAX,qword ptr [RSP + 0xd0]
00c4acd4  MOV RBX,qword ptr [RSP + 0x30]
00c4acd9  LEA RCX,[0xf1545d]
00c4ace0  MOV EDI,0xe
00c4ace5  CALL 0x00414f60
00c4acea  TEST RAX,RAX
00c4aced  JL 0x00c4acfe
00c4acef  MOV RBX,qword ptr [RSP + 0x30]
00c4acf4  MOV RAX,qword ptr [RSP + 0xd0]
00c4acfc  JMP 0x00c4ad51
00c4acfe  MOVUPS xmmword ptr [RSP + 0xb8],XMM15
00c4ad07  MOV RAX,qword ptr [RSP + 0xd0]
00c4ad0f  MOV RBX,qword ptr [RSP + 0x30]
00c4ad14  CALL 0x00481ee0
00c4ad19  LEA RCX,[0xdd29c0]
00c4ad20  MOV qword ptr [RSP + 0xb8],RCX
00c4ad28  MOV qword ptr [RSP + 0xc0],RAX
00c4ad30  LEA RAX,[0xf1f05e]
00c4ad37  MOV EBX,0x13
00c4ad3c  LEA RCX,[RSP + 0xb8]
00c4ad44  MOV EDI,0x1
00c4ad49  MOV RSI,RDI
00c4ad4c  CALL 0x005055a0
00c4ad51  MOV RDX,qword ptr [RSP + 0xe8]
00c4ad59  MOV R8,qword ptr [0x019900b0]
00c4ad60  TEST R8,R8
00c4ad63  JZ 0x00c4ad85
00c4ad65  MOV RCX,qword ptr [RDX + 0x8]
00c4ad69  MOV RDX,qword ptr [RDX]
00c4ad6c  MOV RDI,RAX
00c4ad6f  MOV RSI,RBX
00c4ad72  MOV RAX,R8
00c4ad75  MOV RBX,RDX
00c4ad78  CALL 0x00a63a60
00c4ad7d  NOP dword ptr [RAX]
00c4ad80  TEST RAX,RAX
00c4ad83  JNZ 0x00c4adac
00c4ad85  MOV RCX,qword ptr [RSP + 0x100]
00c4ad8d  TEST RCX,RCX
00c4ad90  JZ 0x00c4ae55
00c4ad96  MOV RBX,qword ptr [RCX + 0x8]
00c4ad9a  MOV RDX,qword ptr [0x01973ea0]
00c4ada1  MOV RSI,qword ptr [RDX]
00c4ada4  MOV ECX,dword ptr [RCX + 0x10]
00c4ada7  JMP 0x00c4af02
00c4adac  MOV RCX,qword ptr [RAX + 0x18]
00c4adb0  MOV RAX,RBX
00c4adb3  CALL RCX
00c4adb5  MOV ECX,0x16
00c4adba  MOV RDI,RAX
00c4adbd  MOV RSI,RBX
00c4adc0  XOR EAX,EAX
00c4adc2  LEA RBX,[0xf23a86]
00c4adc9  CALL 0x0046b1e0
00c4adce  MOV RCX,RAX
00c4add1  MOV RDI,RBX
00c4add4  MOV ESI,0x1f4
00c4add9  MOV RAX,qword ptr [RSP + 0x100]
00c4ade1  MOV RBX,qword ptr [RSP + 0x108]
00c4ade9  CALL 0x00c484c0
00c4adee  ADD RSP,0xf0
00c4adf5  POP RBP
00c4adf6  RET
00c4adf7  MOV RAX,qword ptr [RSP + 0x100]
00c4adff  MOV RBX,qword ptr [RSP + 0x108]
00c4ae07  LEA RCX,[0xf1962c]
00c4ae0e  MOV EDI,0x10
00c4ae13  MOV ESI,0x190
00c4ae18  CALL 0x00c484c0
00c4ae1d  ADD RSP,0xf0
00c4ae24  POP RBP
00c4ae25  RET
00c4ae26  MOV RAX,qword ptr [RSP + 0x100]
00c4ae2e  MOV RBX,qword ptr [RSP + 0x108]
00c4ae36  LEA RCX,[0xf0cd9a]
00c4ae3d  MOV EDI,0xb
00c4ae42  MOV ESI,0x190
00c4ae47  CALL 0x00c484c0
00c4ae4c  ADD RSP,0xf0
00c4ae53  POP RBP
00c4ae54  RET
00c4ae55  LEA RAX,[RSP + 0x58]
00c4ae5a  MOVUPS xmmword ptr [RAX],XMM15
00c4ae5e  MOVUPS xmmword ptr [RAX + 0x10],XMM15
00c4ae63  MOVUPS xmmword ptr [RAX + 0x20],XMM15
00c4ae68  MOVUPS xmmword ptr [RAX + 0x30],XMM15
00c4ae6d  MOVUPS xmmword ptr [RAX + 0x40],XMM15
00c4ae72  MOVUPS xmmword ptr [RAX + 0x50],XMM15
00c4ae77  MOV qword ptr [RSP + 0x58],RCX
00c4ae7c  MOV RAX,qword ptr [RSP + 0x108]
00c4ae84  MOV qword ptr [RSP + 0x60],RAX
00c4ae89  MOV byte ptr [RSP + 0x78],0x1
00c4ae8e  CALL 0x004825c0
00c4ae93  MOV qword ptr [RSP + 0xc8],RAX
00c4ae9b  MOV RBX,RAX
00c4ae9e  LEA RCX,[0xeffdf5]
00c4aea5  MOV EDI,0x7
00c4aeaa  LEA RAX,[0xe16300]
00c4aeb1  CALL 0x00413460
00c4aeb6  LEA RCX,[0xdd2dc0]
00c4aebd  MOV qword ptr [RAX],RCX
00c4aec0  CMP dword ptr [0x019b5f00],0x0
00c4aec7  JZ 0x00c4aed5
00c4aec9  MOV RDX,qword ptr [RAX + 0x8]
00c4aecd  CALL 0x0048bbe0
00c4aed2  MOV qword ptr [R11],RDX
00c4aed5  LEA RDX,[0x115e2c8]
00c4aedc  MOV qword ptr [RAX + 0x8],RDX
00c4aee0  LEA RAX,[RSP + 0x58]
00c4aee5  LEA RBX,[0xe16300]
00c4aeec  MOV RCX,qword ptr [RSP + 0xc8]
00c4aef4  CALL 0x0053fda0
00c4aef9  ADD RSP,0xf0
00c4af00  POP RBP
00c4af01  RET
00c4af02  MOV RDI,RCX
00c4af05  AND RCX,RSI
00c4af08  SHL RCX,0x4
00c4af0c  MOV R8,qword ptr [RDX + RCX*0x1 + 0x8]
00c4af11  CMP R8,RBX
00c4af14  JZ 0x00c4af33
00c4af16  LEA RCX,[RDI + 0x1]
00c4af1a  TEST R8,R8
00c4af1d  JNZ 0x00c4af02
00c4af1f  LEA RAX,[0x1973ea0]
00c4af26  CALL 0x0041e320
00c4af2b  MOV RCX,RAX
00c4af2e  JMP 0x00c4ae55
00c4af33  MOV RCX,qword ptr [RDX + RCX*0x1 + 0x10]
00c4af38  JMP 0x00c4ae55
00c4af3d  MOV R8,RDX
00c4af40  AND RDX,RDI
00c4af43  SHL RDX,0x4
00c4af47  MOV R9,qword ptr [RSI + RDX*0x1 + 0x8]
00c4af4c  CMP R9,RBX
00c4af4f  JZ 0x00c4af6e
00c4af51  LEA RDX,[R8 + 0x1]
00c4af55  TEST R9,R9
00c4af58  JNZ 0x00c4af3d
00c4af5a  LEA RAX,[0x1973e80]
00c4af61  CALL 0x0041e320
00c4af66  MOV RDX,RAX
00c4af69  JMP 0x00c4aaf4
00c4af6e  MOV RDX,qword ptr [RSI + RDX*0x1 + 0x10]
00c4af73  JMP 0x00c4aaf4
00c4af78  MOV qword ptr [RSP + 0x8],RAX
00c4af7d  MOV qword ptr [RSP + 0x10],RBX
00c4af82  MOV qword ptr [RSP + 0x18],RCX
00c4af87  CALL 0x0048a280
00c4af8c  MOV RAX,qword ptr [RSP + 0x8]
00c4af91  MOV RBX,qword ptr [RSP + 0x10]
00c4af96  MOV RCX,qword ptr [RSP + 0x18]
00c4af9b  NOP dword ptr [RAX + RAX*0x1]
00c4afa0  JMP 0x00c4a980
