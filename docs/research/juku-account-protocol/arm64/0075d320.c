/* Reconstructed pseudocode, not original Go source: main.handleManualInputUrl */

void main_handleManualInputUrl(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined1 *puVar1;
  undefined1 *puVar2;
  undefined1 *puVar3;
  undefined1 *puVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  int *piVar7;
  undefined8 extraout_x0;
  int iVar8;
  uint extraout_x1;
  undefined8 extraout_x1_00;
  int iVar9;
  undefined8 extraout_x2;
  undefined8 uVar10;
  int extraout_x3;
  undefined8 extraout_x3_00;
  undefined8 extraout_x4;
  undefined8 extraout_x4_00;
  undefined8 extraout_x4_01;
  uint uVar11;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar12 [16];
  undefined8 local_138 [14];
  undefined8 local_c8 [25];
  
  for (; (undefined1 *)((int)register0x00000008 + -0xb0) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75d774;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x138) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x130) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar5 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -0xa8) = uVar5;
  auVar12 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)((int)register0x00000008 + -0x80) = auVar12._0_8_;
  *(int *)((int)register0x00000008 + -200) = auVar12._8_8_;
  puVar6 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -0x80) = puVar6;
  *puVar6 = &DAT_009f0b73;
  puVar6[1] = 0x10;
  puVar6 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -0x98),
                      *(undefined8 *)((int)register0x00000008 + -0x78),
                      *(undefined8 *)((int)register0x00000008 + -0xc0));
  puVar1 = (undefined1 *)((int)register0x00000008 + -0x110);
  puVar6[1] = 1;
  puVar6[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar5 = *(undefined8 *)((int)register0x00000008 + -0x78);
  }
  else {
    auVar12 = runtime_gcWriteBarrier2(puVar6,*puVar6);
    puVar6 = auVar12._0_8_;
    puVar1 = (undefined1 *)((int)register0x00000008 + -0x108);
    uVar5 = *(undefined8 *)((int)register0x00000008 + -0x70);
    *in_x25 = uVar5;
    in_x25[1] = auVar12._8_8_;
  }
  *puVar6 = uVar5;
  uVar5 = net_url___URL__Query(*(undefined8 *)(*(int *)(puVar1 + 0x148) + 0x10));
  piVar7 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar5,&DAT_009d9f87,8);
  if (piVar7[1] == 0) {
    uVar10 = 0;
    uVar5 = 0;
  }
  else {
    uVar5 = *(undefined8 *)*piVar7;
    uVar10 = ((undefined8 *)*piVar7)[1];
  }
  auVar12 = main_getRealProvider(uVar5,uVar10);
  *(int *)(puVar1 + 0x80) = auVar12._0_8_;
  *(int *)(puVar1 + 0x48) = auVar12._8_8_;
  runtime_mapaccess2_faststr(&DAT_008edb60,main_providers,auVar12._0_8_,auVar12._8_8_);
  if ((extraout_x1 & 1) == 0) {
    main_writeJsonError(*(undefined8 *)(puVar1 + 0x158),*(undefined8 *)(puVar1 + 0x160),
                        &DAT_009f0ba3,0x10,400);
    return;
  }
  auVar12 = main_getLocalIP();
  *(int *)(puVar1 + 0xa0) = auVar12._0_8_;
  *(int *)(puVar1 + 0x68) = auVar12._8_8_;
  uVar5 = net_url___URL__Query(*(undefined8 *)(*(int *)(puVar1 + 0x170) + 0x10));
  piVar7 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar5,&DAT_009d9f87,8);
  if (piVar7[1] == 0) {
    uVar10 = 0;
    uVar5 = 0;
  }
  else {
    uVar5 = *(undefined8 *)*piVar7;
    uVar10 = ((undefined8 *)*piVar7)[1];
  }
  auVar12 = strings_TrimSpace(uVar5,uVar10);
  *(int *)(puVar1 + 0xd0) = auVar12._0_8_;
  *(int *)(puVar1 + 0x90) = auVar12._8_8_;
  *(undefined8 *)(puVar1 + 0x148) = 0;
  *(undefined8 *)(puVar1 + 0x150) = 0;
  *(undefined8 *)(puVar1 + 0x158) = 0;
  *(undefined8 *)(puVar1 + 0x160) = 0;
  uVar5 = runtime_convTstring(*(undefined8 *)(puVar1 + 0xb8),*(undefined8 *)(puVar1 + 0x80));
  *(undefined8 **)(puVar1 + 0x150) = &DAT_008a6880;
  *(undefined8 *)(puVar1 + 0x158) = uVar5;
  iVar9 = *(int *)(puVar1 + 0x98);
  iVar8 = *(int *)(puVar1 + 0x78);
  if (iVar9 != 0) {
    iVar8 = iVar9;
  }
  uVar5 = *(undefined8 *)(puVar1 + 0xb0);
  if (iVar9 != 0) {
    uVar5 = *(undefined8 *)(puVar1 + 0xd8);
  }
  uVar5 = runtime_convTstring(uVar5,iVar8);
  *(undefined8 **)(puVar1 + 0x168) = &DAT_008a6880;
  *(undefined8 *)(puVar1 + 0x170) = uVar5;
  auVar12 = fmt_Sprintf(&DAT_009fafc2,0x16,puVar1 + 0x158,2,2);
  *(int *)(puVar1 + 200) = auVar12._0_8_;
  *(int *)(puVar1 + 0x90) = auVar12._8_8_;
  mv_daemon_provider_EncodeQRCodeRGBA(auVar12._0_8_,auVar12._8_8_,1,300);
  if (extraout_x3 != 0) {
    auVar12 = (**(code **)(extraout_x3 + 0x18))(extraout_x4);
    main_writeJsonError(*(undefined8 *)(puVar1 + 0x1a0),*(undefined8 *)(puVar1 + 0x1a8),
                        auVar12._0_8_,auVar12._8_8_,500);
    return;
  }
  auVar12 = encoding_base64___Encoding__EncodeToString
                      (encoding_base64_StdEncoding,extraout_x0,extraout_x1_00,extraout_x2);
  auVar12 = runtime_concatstring2(0,&DAT_009fafac,0x16,auVar12._0_8_,auVar12._8_8_);
  *(int *)(puVar1 + 0xf8) = auVar12._0_8_;
  *(int *)(puVar1 + 0xb8) = auVar12._8_8_;
  uVar5 = runtime_makemap_small();
  *(undefined8 *)(puVar1 + 0xd8) = uVar5;
  puVar6 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,uVar5,&DAT_009d210d,3);
  puVar2 = puVar1 + 0x80;
  puVar6[1] = 6;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar2 = puVar1 + 0x88;
    *in_x25 = extraout_x4_00;
  }
  *puVar6 = &DAT_009d582f;
  puVar6 = (undefined8 *)
           runtime_mapassign_faststr(&DAT_008ecae0,*(undefined8 *)(puVar2 + 0x60),&DAT_009d2104,3);
  puVar3 = puVar2 + 8;
  puVar6[1] = *(undefined8 *)(puVar2 + 0x40);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar5 = *(undefined8 *)(puVar2 + 0x78);
  }
  else {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar3 = puVar2 + 0x10;
    uVar5 = *(undefined8 *)(puVar2 + 0x80);
    *in_x25 = uVar5;
    in_x25[1] = extraout_x4_01;
  }
  *puVar6 = uVar5;
  puVar6 = (undefined8 *)
           runtime_mapassign_faststr(&DAT_008ecae0,*(undefined8 *)(puVar3 + 0x60),&DAT_009d5835,6);
  puVar4 = puVar3 + 8;
  puVar6[1] = *(undefined8 *)(puVar3 + 0x50);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar5 = *(undefined8 *)(puVar3 + 0x90);
  }
  else {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar4 = puVar3 + 0x10;
    uVar5 = *(undefined8 *)(puVar3 + 0x98);
    *in_x25 = uVar5;
    in_x25[1] = extraout_x3_00;
  }
  *puVar6 = uVar5;
  iVar8 = *(int *)(puVar4 + 0x138);
  uVar5 = 0;
  if (iVar8 != 0) {
    uVar11 = (uint)*(dword *)(iVar8 + 0x10);
    do {
      iVar9 = (uVar11 & *(uint *)main__typeAssert_34) * 0x10;
      if (*(int *)(main__typeAssert_34 + iVar9 + 8) == *(int *)(iVar8 + 8)) {
        uVar5 = *(undefined8 *)(main__typeAssert_34 + iVar9 + 0x10);
        goto LAB_0075d6e0;
      }
      uVar11 = uVar11 + 1;
    } while (*(int *)(main__typeAssert_34 + iVar9 + 8) != 0);
    uVar5 = runtime_typeAssert(&main__typeAssert_34);
    puVar4 = puVar4 + 8;
  }
LAB_0075d6e0:
  *(undefined8 *)(puVar4 + 0xa8) = 0;
  *(undefined8 *)(puVar4 + 0xb0) = 0;
  *(undefined8 *)(puVar4 + 0xb8) = 0;
  *(undefined8 *)(puVar4 + 0xc0) = 0;
  *(undefined8 *)(puVar4 + 200) = 0;
  *(undefined8 *)(puVar4 + 0xd0) = 0;
  *(undefined8 *)(puVar4 + 0xd8) = 0;
  *(undefined8 *)(puVar4 + 0xe0) = 0;
  *(undefined8 *)(puVar4 + 0xe8) = 0;
  *(undefined8 *)(puVar4 + 0xf0) = 0;
  *(undefined8 *)(puVar4 + 0xf8) = 0;
  *(undefined8 *)(puVar4 + 0x100) = 0;
  *(undefined8 *)(puVar4 + 0xa8) = uVar5;
  *(undefined8 *)(puVar4 + 0xb0) = *(undefined8 *)(puVar4 + 0x140);
  puVar4[200] = 1;
  encoding_json___Encoder__Encode(puVar4 + 0xa8,&DAT_008ecae0,*(undefined8 *)(puVar4 + 0x60));
  return;
}

