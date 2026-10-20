/* Reconstructed pseudocode, not original Go source: main.handle115OfflineResolve */

void main_handle115OfflineResolve(int param_1,undefined8 param_2,int param_3)

{
  byte bVar1;
  undefined1 auVar2 [16];
  undefined8 uVar3;
  int *piVar4;
  undefined8 uVar5;
  byte *extraout_RAX;
  undefined8 *puVar6;
  undefined8 extraout_RCX;
  undefined8 uVar7;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 extraout_RCX_05;
  undefined8 uVar8;
  char extraout_BL;
  int extraout_RBX;
  uint uVar9;
  int iVar10;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  undefined8 *extraout_R11_03;
  undefined8 *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  undefined8 *extraout_R11_07;
  undefined8 *extraout_R11_08;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar11 [16];
  undefined1 auVar12 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_110;
  undefined8 local_108;
  byte *local_100;
  undefined8 local_f8;
  int local_f0;
  undefined8 local_e8;
  undefined8 local_e0;
  undefined8 local_d8;
  undefined8 uStack_d0;
  undefined1 local_b8;
  undefined7 uStack_b7;
  undefined *local_78;
  undefined8 uStack_70;
  code *local_68;
  undefined *local_60;
  undefined8 local_58;
  undefined **local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  undefined8 local_30;
  undefined8 local_28;
  undefined8 local_20;
  undefined8 *local_18;
  undefined8 local_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_110 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_e0 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar11 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_10 = auVar11._0_8_;
  local_18 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_18[1] = 0x10;
  *local_18 = &DAT_00f195fc;
  auVar11 = runtime_mapassign_faststr(&DAT_00e91b20,local_e0,local_10,auVar11._8_8_);
  puVar6 = auVar11._0_8_;
  puVar6[1] = 1;
  puVar6[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,*puVar6);
    *extraout_R11 = local_18;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar6 = local_18;
  auVar11 = main_getRequestUserAgent(iStack0000000000000018);
  local_110 = auVar11._0_8_;
  uVar3 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar4 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar3,&DAT_00efc947,5);
  if (piVar4[1] == 0) {
    iVar10 = 0;
    uVar3 = 0;
  }
  else {
    iVar10 = ((undefined8 *)*piVar4)[1];
    uVar3 = *(undefined8 *)*piVar4;
  }
  auVar2._8_8_ = iVar10;
  auVar2._0_8_ = uVar3;
  auVar12._8_8_ = iVar10;
  auVar12._0_8_ = uVar3;
  if ((iVar10 == 0) && (auVar12 = auVar2, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar12 = mv_daemon_provider___TokenStore__Get(main_tokenStore,&DAT_00f02951,8);
  }
  local_108 = auVar12._0_8_;
  if (auVar12._8_8_ == 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3daf3,0x2a,0x191);
    return;
  }
  piVar4 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,&DAT_00f02951,8);
  local_f0 = piVar4[1];
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d163,0x1d,500);
    return;
  }
  if ((undefined1 *)*piVar4 !=
      go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3a315,0x27,500);
    return;
  }
  uVar3 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar4 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar3,&DAT_00effe2d,7);
  if (piVar4[1] == 0) {
    uVar3 = 0;
    uVar7 = 0;
  }
  else {
    uVar3 = ((undefined8 *)*piVar4)[1];
    uVar7 = *(undefined8 *)*piVar4;
  }
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar4 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f05a3e,9);
  if (piVar4[1] == 0) {
    uVar5 = 0;
    uVar8 = 0;
  }
  else {
    uVar5 = ((undefined8 *)*piVar4)[1];
    uVar8 = *(undefined8 *)*piVar4;
  }
  local_38 = local_110;
  local_30 = auVar11._8_8_;
  mv_daemon_provider___Cloud115Provider__Resolve115OfflineToPlay
            (local_f0,uVar7,uVar3,uVar8,uVar5,local_108,auVar12._8_8_,uVar5,&local_38,&local_38,1,1)
  ;
  if (extraout_RBX != 0) {
    auVar11 = (**(code **)(extraout_RBX + 0x18))(extraout_RCX_00);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar11._0_8_,auVar11._8_8_,
                        500);
    return;
  }
  local_f8 = *(undefined8 *)(extraout_RAX + 8);
  uVar3 = *(undefined8 *)(extraout_RAX + 0x10);
  local_e8 = *(undefined8 *)(extraout_RAX + 0x18);
  local_100 = extraout_RAX;
  uStack_70 = runtime_convTstring(local_f8);
  local_78 = &DAT_00dd29c0;
  local_68 = main_handle115OfflineResolve_Printf_func1;
  local_58 = 0x46;
  local_60 = &DAT_00f54168;
  local_48 = 1;
  local_40 = 1;
  local_50 = &local_78;
  log___Logger__output(log_std,0,2,&local_68);
  local_d8 = 0;
  if (iStack0000000000000008 != 0) {
    uVar9 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar10 = (uVar9 & *(uint *)main__typeAssert_59) * 0x10;
      if (*(int *)(main__typeAssert_59 + iVar10 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_d8 = *(undefined8 *)(main__typeAssert_59 + iVar10 + 0x10);
        goto LAB_00c5819f;
      }
      uVar9 = uVar9 + 1;
    } while (*(int *)(main__typeAssert_59 + iVar10 + 8) != 0);
    local_d8 = runtime_typeAssert(&main__typeAssert_59);
  }
LAB_00c5819f:
  uStack_d0 = uStack0000000000000010;
  _local_b8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_20 = runtime_makemap(&DAT_00e16300,9,0);
  puVar6 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00effdf5,7);
  *puVar6 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar7 = puVar6[1];
    puVar6 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar7;
  }
  puVar6[1] = 0x115e2c8;
  bVar1 = *local_100;
  auVar11 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00efe2c3,6);
  puVar6 = auVar11._0_8_;
  *puVar6 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier1(puVar6,auVar11._8_8_,puVar6[1]);
    *extraout_R11_01 = extraout_RCX_01;
  }
  puVar6[1] = runtime_staticuint64s + (uint)bVar1 * 8;
  local_28 = runtime_convTstring(local_f8,uVar3);
  puVar6 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f02a69,8);
  *puVar6 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar3 = puVar6[1];
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_02 = local_28;
    extraout_R11_02[1] = uVar3;
  }
  puVar6[1] = local_28;
  auVar11 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00effe49,7);
  puVar6 = auVar11._0_8_;
  *puVar6 = &DAT_00e16200;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,puVar6[1]);
    *extraout_R11_03 = local_e8;
    extraout_R11_03[1] = extraout_RCX_02;
  }
  puVar6[1] = local_e8;
  local_28 = runtime_convTstring(*(undefined8 *)(local_100 + 0x20),*(undefined8 *)(local_100 + 0x28)
                                );
  auVar11 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00effe2d,7);
  puVar6 = auVar11._0_8_;
  *puVar6 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,puVar6[1]);
    *extraout_R11_04 = local_28;
    extraout_R11_04[1] = extraout_RCX_03;
  }
  puVar6[1] = local_28;
  local_28 = runtime_convTstring(*(undefined8 *)(local_100 + 0x30),*(undefined8 *)(local_100 + 0x38)
                                );
  auVar11 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f05a3e,9);
  puVar6 = auVar11._0_8_;
  *puVar6 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,puVar6[1]);
    *extraout_R11_05 = local_28;
    extraout_R11_05[1] = extraout_RCX_04;
  }
  puVar6[1] = local_28;
  local_28 = runtime_convTstring(*(undefined8 *)(local_100 + 0x40),*(undefined8 *)(local_100 + 0x48)
                                );
  auVar11 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f05a11,9);
  puVar6 = auVar11._0_8_;
  *puVar6 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,puVar6[1]);
    *extraout_R11_06 = local_28;
    extraout_R11_06[1] = extraout_RCX_05;
  }
  puVar6[1] = local_28;
  local_28 = runtime_convT64(*(undefined8 *)(local_100 + 0x50));
  puVar6 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f05a1a,9);
  *puVar6 = &DAT_00dd2b80;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar3 = puVar6[1];
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_07 = local_28;
    extraout_R11_07[1] = uVar3;
  }
  puVar6[1] = local_28;
  local_28 = runtime_convTslice(*(undefined8 *)(local_100 + 0x58),*(undefined8 *)(local_100 + 0x60),
                                *(undefined8 *)(local_100 + 0x68));
  puVar6 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f05a47,9);
  *puVar6 = &DAT_00dc15a0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar3 = puVar6[1];
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_08 = local_28;
    extraout_R11_08[1] = uVar3;
  }
  puVar6[1] = local_28;
  encoding_json___Encoder__Encode(&local_d8,&DAT_00e16300,local_20);
  return;
}

