/* Reconstructed pseudocode, not original Go source: main.handlePanLogout */

void main_handlePanLogout(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined1 *puVar1;
  undefined1 *puVar2;
  undefined1 *puVar3;
  undefined8 uVar4;
  undefined8 *puVar5;
  int *piVar6;
  int iVar7;
  uint extraout_x1;
  undefined8 extraout_x3;
  uint uVar8;
  undefined8 uVar9;
  int iVar10;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar11 [16];
  undefined8 local_d8 [10];
  undefined8 local_88 [15];
  undefined1 local_10 [16];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x50) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x769728;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0xd0) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0xd8) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar4 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -0x80) = uVar4;
  auVar11 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)((int)register0x00000008 + -0x60) = auVar11._0_8_;
  *(int *)((int)register0x00000008 + -0x88) = auVar11._8_8_;
  puVar5 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -0x60) = puVar5;
  *puVar5 = &DAT_009f0b73;
  puVar5[1] = 0x10;
  puVar5 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -0x70),
                      *(undefined8 *)((int)register0x00000008 + -0x58),
                      *(undefined8 *)((int)register0x00000008 + -0x80));
  puVar1 = (undefined1 *)((int)register0x00000008 + -0xb0);
  puVar5[1] = 1;
  puVar5[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar4 = *(undefined8 *)((int)register0x00000008 + -0x58);
  }
  else {
    auVar11 = runtime_gcWriteBarrier2(puVar5,*puVar5);
    puVar5 = auVar11._0_8_;
    puVar1 = (undefined1 *)((int)register0x00000008 + -0xa8);
    uVar4 = *(undefined8 *)((int)register0x00000008 + -0x50);
    *in_x25 = uVar4;
    in_x25[1] = auVar11._8_8_;
  }
  *puVar5 = uVar4;
  uVar4 = net_url___URL__Query(*(undefined8 *)(*(int *)(puVar1 + 0xe8) + 0x10));
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar4,&DAT_009d9f87,8);
  if (piVar6[1] == 0) {
    uVar9 = 0;
    uVar4 = 0;
  }
  else {
    uVar4 = *(undefined8 *)*piVar6;
    uVar9 = ((undefined8 *)*piVar6)[1];
  }
  *(undefined8 *)(puVar1 + 0x50) = uVar4;
  *(undefined8 *)(puVar1 + 0x40) = uVar9;
  runtime_mapaccess2_faststr(&DAT_008edb60,main_providers,uVar4,uVar9);
  puVar2 = puVar1 + 0x18;
  if ((extraout_x1 & 1) == 0) {
    main_writeJsonError(*(undefined8 *)(puVar1 + 0xf0),*(undefined8 *)(puVar1 + 0xf8),&DAT_009f0ba3,
                        0x10,400);
    return;
  }
  if (main_tokenStore != (mv_daemon_provider_TokenStore *)0x0) {
    mv_daemon_provider___TokenStore__Save
              (main_tokenStore,*(undefined8 *)(puVar1 + 0x58),*(undefined8 *)(puVar1 + 0x48),0,0);
    puVar2 = puVar1 + 0x20;
  }
  iVar7 = *(int *)(puVar2 + 0xd8);
  uVar4 = 0;
  if (iVar7 != 0) {
    uVar8 = (uint)*(dword *)(iVar7 + 0x10);
    do {
      iVar10 = (uVar8 & *(uint *)main__typeAssert_61) * 0x10;
      if (*(int *)(main__typeAssert_61 + iVar10 + 8) == *(int *)(iVar7 + 8)) {
        uVar4 = *(undefined8 *)(main__typeAssert_61 + iVar10 + 0x10);
        goto LAB_00769640;
      }
      uVar8 = uVar8 + 1;
    } while (*(int *)(main__typeAssert_61 + iVar10 + 8) != 0);
    uVar4 = runtime_typeAssert(&main__typeAssert_61);
    puVar2 = puVar2 + 8;
  }
LAB_00769640:
  *(undefined8 *)(puVar2 + 0x68) = 0;
  *(undefined8 *)(puVar2 + 0x70) = 0;
  *(undefined8 *)(puVar2 + 0x78) = 0;
  *(undefined8 *)(puVar2 + 0x80) = 0;
  *(undefined8 *)(puVar2 + 0x88) = 0;
  *(undefined8 *)(puVar2 + 0x90) = 0;
  *(undefined8 *)(puVar2 + 0x98) = 0;
  *(undefined8 *)(puVar2 + 0xa0) = 0;
  *(undefined8 *)(puVar2 + 0xa8) = 0;
  *(undefined8 *)(puVar2 + 0xb0) = 0;
  *(undefined8 *)(puVar2 + 0xb8) = 0;
  *(undefined8 *)(puVar2 + 0xc0) = 0;
  *(undefined8 *)(puVar2 + 0x68) = uVar4;
  *(undefined8 *)(puVar2 + 0x70) = *(undefined8 *)(puVar2 + 0xe0);
  puVar2[0x88] = 1;
  uVar4 = runtime_makemap_small();
  *(undefined8 *)(puVar2 + 0x58) = uVar4;
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecbe0,uVar4,&DAT_009d739b,7);
  puVar3 = puVar2 + 0x10;
  *puVar5 = &DAT_008a6c80;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar3 = puVar2 + 0x18;
    *in_x25 = extraout_x3;
  }
  puVar5[1] = 0xc327c8;
  encoding_json___Encoder__Encode(puVar3 + 0x68,&DAT_008ecbe0,*(undefined8 *)(puVar3 + 0x50));
  return;
}

