/* Reconstructed pseudocode, not original Go source: main.handleManualInputPage */

void main_handleManualInputPage(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined8 *puVar1;
  undefined8 uVar2;
  undefined8 *puVar3;
  undefined8 extraout_x0;
  undefined8 extraout_x1;
  undefined8 extraout_x2;
  undefined8 extraout_x3;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar4 [16];
  undefined8 local_58 [8];
  undefined8 local_18 [3];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75c610;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x50) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x58) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar2 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -8) = uVar2;
  auVar4 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)((int)register0x00000008 + -8) = auVar4._0_8_;
  *(int *)((int)register0x00000008 + -0x18) = auVar4._8_8_;
  puVar3 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -8) = puVar3;
  *puVar3 = &DAT_009fdd42;
  puVar3[1] = 0x18;
  puVar3 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + 8),
                      *(undefined8 *)register0x00000008,
                      *(undefined8 *)((int)register0x00000008 + -0x10));
  puVar1 = (undefined8 *)((int)register0x00000008 + -0x30);
  puVar3[1] = 1;
  puVar3[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar2 = *(undefined8 *)register0x00000008;
  }
  else {
    puVar3 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar1 = (undefined8 *)((int)register0x00000008 + -0x28);
    uVar2 = *(undefined8 *)((int)register0x00000008 + 8);
    *in_x25 = uVar2;
    in_x25[1] = extraout_x3;
  }
  *puVar3 = uVar2;
  runtime_stringtoslicebyte(0,main_qrHTML.str,main_qrHTML.len);
  (**(code **)(*(int *)((int)puVar1 + 0x60) + 0x20))
            (*(undefined8 *)((int)puVar1 + 0x68),extraout_x0,extraout_x1,extraout_x2);
  return;
}

