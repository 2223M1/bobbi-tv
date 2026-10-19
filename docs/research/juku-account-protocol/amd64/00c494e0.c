/* Reconstructed pseudocode, not original Go source: main.handleManualInputPage */

void main_handleManualInputPage(int param_1,undefined8 param_2)

{
  undefined8 uVar1;
  undefined8 *puVar2;
  undefined8 *puVar3;
  undefined8 extraout_RAX;
  undefined8 extraout_RCX;
  undefined8 extraout_RBX;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined1 auVar4 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  
  iStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar1 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar4 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  puVar2 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  puVar2[1] = 0x18;
  *puVar2 = &DAT_00f267da;
  puVar3 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e91b20,uVar1,auVar4._0_8_,auVar4._8_8_);
  puVar3[1] = 1;
  puVar3[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar1 = *puVar3;
    puVar3 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11 = puVar2;
    extraout_R11[1] = uVar1;
  }
  *puVar3 = puVar2;
  runtime_stringtoslicebyte(0,main_qrHTML.str,main_qrHTML.len);
  (**(code **)(iStack0000000000000008 + 0x20))
            (uStack0000000000000010,extraout_RAX,extraout_RBX,extraout_RCX);
  return;
}

