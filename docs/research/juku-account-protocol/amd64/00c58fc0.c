/* Reconstructed pseudocode, not original Go source: main.handlePanLogout */

void main_handlePanLogout(int param_1,undefined8 param_2,int param_3)

{
  undefined8 uVar1;
  undefined8 *puVar2;
  undefined8 *puVar3;
  int *piVar4;
  undefined8 extraout_RCX;
  uint uVar5;
  int iVar6;
  undefined8 uVar7;
  char extraout_BL;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar8 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_68;
  undefined8 uStack_60;
  undefined1 local_48;
  undefined7 uStack_47;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_48 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar1 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar8 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  puVar2 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  puVar2[1] = 0x10;
  *puVar2 = &DAT_00f195fc;
  auVar8 = runtime_mapassign_faststr(&DAT_00e91b20,uVar1,auVar8._0_8_,auVar8._8_8_);
  puVar3 = auVar8._0_8_;
  puVar3[1] = 1;
  puVar3[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar3 = (undefined8 *)runtime_gcWriteBarrier2(puVar3,auVar8._8_8_,*puVar3);
    *extraout_R11 = puVar2;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar3 = puVar2;
  uVar1 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar4 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar1,&DAT_00f02a51,8);
  if (piVar4[1] == 0) {
    uVar1 = 0;
    uVar7 = 0;
  }
  else {
    uVar1 = ((undefined8 *)*piVar4)[1];
    uVar7 = *(undefined8 *)*piVar4;
  }
  runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,uVar7,uVar1);
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1962c,0x10,400);
    return;
  }
  if (main_tokenStore != (mv_daemon_provider_TokenStore *)0x0) {
    mv_daemon_provider___TokenStore__Save(main_tokenStore,uVar7,uVar1,0,0);
  }
  local_68 = 0;
  if (iStack0000000000000008 != 0) {
    uVar5 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar6 = (uVar5 & *(uint *)main__typeAssert_61) * 0x10;
      if (*(int *)(main__typeAssert_61 + iVar6 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_68 = *(undefined8 *)(main__typeAssert_61 + iVar6 + 0x10);
        goto LAB_00c59177;
      }
      uVar5 = uVar5 + 1;
    } while (*(int *)(main__typeAssert_61 + iVar6 + 8) != 0);
    local_68 = runtime_typeAssert(&main__typeAssert_61);
  }
LAB_00c59177:
  uStack_60 = uStack0000000000000010;
  _local_48 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  uVar1 = runtime_makemap_small();
  puVar2 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar1,&DAT_00effdf5,7);
  *puVar2 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar7 = puVar2[1];
    puVar2 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar7;
  }
  puVar2[1] = 0x115e2c8;
  encoding_json___Encoder__Encode(&local_68,&DAT_00e16300,uVar1);
  return;
}

