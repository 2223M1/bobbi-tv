/* Reconstructed pseudocode, not original Go source: main.handleManualInput */

void main_handleManualInput(int param_1,undefined8 param_2,undefined8 *param_3)

{
  undefined1 (*pauVar1) [16];
  undefined8 uVar2;
  undefined8 *puVar3;
  int iVar4;
  undefined8 extraout_RAX;
  undefined8 uVar5;
  undefined8 *extraout_RCX;
  uint uVar6;
  int iVar7;
  char extraout_BL;
  undefined8 extraout_RBX;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar8 [16];
  undefined1 auVar9 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 *puStack0000000000000018;
  undefined8 local_a0;
  undefined8 uStack_98;
  undefined1 local_80;
  undefined7 uStack_7f;
  undefined1 auStack_78 [56];
  undefined *local_40;
  undefined8 uStack_38;
  undefined8 local_30;
  undefined8 local_28;
  undefined8 *local_20;
  undefined8 local_18;
  undefined8 *local_10;
  
  iStack0000000000000008 = param_1;
  puStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (auStack_78 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar2 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar8 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_18 = auVar8._0_8_;
  local_20 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_20[1] = 0x10;
  *local_20 = &DAT_00f195fc;
  puVar3 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e91b20,uVar2,local_18,auVar8._8_8_);
  puVar3[1] = 1;
  puVar3[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = *puVar3;
    puVar3 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11 = local_20;
    extraout_R11[1] = uVar2;
  }
  *puVar3 = local_20;
  if ((puStack0000000000000018[1] != 4) || (*(sdword *)*puStack0000000000000018 != 0x54534f50)) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1d535,0x12,0x195);
    return;
  }
  local_10 = (undefined8 *)runtime_newobject(&DAT_00e2e100);
  iVar4 = puStack0000000000000018[8];
  uVar2 = puStack0000000000000018[9];
  uVar5 = 0;
  if (iVar4 != 0) {
    uVar6 = (uint)*(dword *)(iVar4 + 0x10);
    do {
      iVar7 = (uVar6 & *(uint *)main__typeAssert_35) * 0x10;
      if (*(int *)(main__typeAssert_35 + iVar7 + 8) == *(int *)(iVar4 + 8)) {
        uVar5 = *(undefined8 *)(main__typeAssert_35 + iVar7 + 0x10);
        goto LAB_00c4aaf4;
      }
      uVar6 = uVar6 + 1;
    } while (*(int *)(main__typeAssert_35 + iVar7 + 8) != 0);
    uVar5 = runtime_typeAssert(&main__typeAssert_35);
  }
LAB_00c4aaf4:
  local_18 = uVar5;
  puVar3 = (undefined8 *)runtime_newobject(&DAT_00eba560);
  *puVar3 = local_18;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar3 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar2;
  }
  puVar3[1] = uVar2;
  iVar4 = encoding_json___Decoder__Decode(puVar3,&DAT_00dc06e0,local_10);
  if (iVar4 != 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f0cd9a,0xb,400);
    return;
  }
  auVar8 = main_getRealProvider(*local_10,local_10[1]);
  local_10[1] = auVar8._8_8_;
  puVar3 = local_10;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = *local_10;
    runtime_gcWriteBarrier2();
    auVar8._8_8_ = extraout_RBX;
    auVar8._0_8_ = extraout_RAX;
    *extraout_R11_01 = extraout_RAX;
    extraout_R11_01[1] = uVar2;
    puVar3 = extraout_RCX;
  }
  *puVar3 = auVar8._0_8_;
  runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,auVar8._0_8_,auVar8._8_8_);
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1962c,0x10,400);
    return;
  }
  pauVar1 = (undefined1 (*) [16])(local_10 + 2);
  uVar2 = *(undefined8 *)*pauVar1;
  uVar5 = local_10[3];
  auVar8 = *pauVar1;
  auVar9 = *pauVar1;
  if ((((local_10[1] == 6) && (auVar9 = *pauVar1, *(sdword *)*local_10 == 0x59494c41)) &&
      (auVar9 = *pauVar1, (short)((sdword *)*local_10)[1] == 0x4e55)) &&
     (iVar4 = internal_stringslite_Index(uVar2,uVar5,&DAT_00f176a8,0xf), auVar9 = auVar8, iVar4 < 0)
     ) {
    uStack_38 = runtime_convTstring(uVar2,uVar5);
    local_40 = &DAT_00dd29c0;
    auVar9 = fmt_Sprintf(&DAT_00f1f05e,0x13,&local_40,1,1);
  }
  uVar2 = auVar9._8_8_;
  if (((local_10[1] == 6) && (*(sdword *)*local_10 == 0x4c4e5558)) &&
     ((short)((sdword *)*local_10)[1] == 0x4945)) {
    local_28 = auVar9._0_8_;
    iVar4 = internal_stringslite_Index(auVar9._0_8_,uVar2,&DAT_00f176a8,0xf);
    auVar9._8_8_ = uVar2;
    auVar9._0_8_ = local_28;
    if (iVar4 < 0) {
      iVar4 = internal_stringslite_Index(local_28,uVar2,&DAT_00f1545d,0xe);
      auVar9._0_8_ = local_28;
      if (iVar4 < 0) {
        uStack_38 = runtime_convTstring(local_28,uVar2);
        local_40 = &DAT_00dd29c0;
        auVar9 = fmt_Sprintf(&DAT_00f1f05e,0x13,&local_40,1,1);
      }
    }
  }
  if (main_tokenStore != (mv_daemon_provider_TokenStore *)0x0) {
    auVar8 = mv_daemon_provider___TokenStore__Save
                       (main_tokenStore,*local_10,local_10[1],auVar9._0_8_,auVar9._8_8_);
    if (auVar8._0_8_ != 0) {
      auVar8 = (**(code **)(auVar8._0_8_ + 0x18))(auVar8._8_8_);
      auVar8 = runtime_concatstring2(0,&DAT_00f23a86,0x16,auVar8._0_8_,auVar8._8_8_);
      main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar8._0_8_,auVar8._8_8_,
                          500);
      return;
    }
  }
  local_a0 = 0;
  if (iStack0000000000000008 != 0) {
    uVar6 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar4 = (uVar6 & *(uint *)main__typeAssert_36) * 0x10;
      if (*(int *)(main__typeAssert_36 + iVar4 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_a0 = *(undefined8 *)(main__typeAssert_36 + iVar4 + 0x10);
        goto LAB_00c4ae55;
      }
      uVar6 = uVar6 + 1;
    } while (*(int *)(main__typeAssert_36 + iVar4 + 8) != 0);
    local_a0 = runtime_typeAssert(&main__typeAssert_36);
  }
LAB_00c4ae55:
  uStack_98 = uStack0000000000000010;
  _local_80 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_30 = runtime_makemap_small();
  puVar3 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_30,&DAT_00effdf5,7);
  *puVar3 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = puVar3[1];
    puVar3 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_02 = uVar2;
  }
  puVar3[1] = 0x115e2c8;
  encoding_json___Encoder__Encode(&local_a0,&DAT_00e16300,local_30);
  return;
}

