/* Reconstructed pseudocode, not original Go source: main.handleUserPlay */

void main_handleUserPlay(int param_1,undefined8 param_2,int param_3)

{
  undefined1 auVar1 [16];
  undefined8 uVar2;
  int *piVar3;
  undefined8 uVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  undefined8 *extraout_RAX;
  undefined8 extraout_RAX_00;
  int iVar7;
  int extraout_RAX_01;
  char extraout_CL;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 *extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 *extraout_RCX_04;
  uint uVar8;
  char extraout_BL;
  int extraout_RBX;
  undefined8 extraout_RBX_00;
  int extraout_RBX_01;
  undefined8 extraout_RSI;
  undefined8 extraout_RSI_00;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  undefined8 *extraout_R11_03;
  undefined8 *extraout_R11_04;
  int unaff_R14;
  bool bVar9;
  bool bVar10;
  undefined8 in_XMM15_Qa;
  undefined **in_XMM15_Qb;
  undefined1 auVar11 [16];
  undefined1 auVar12 [16];
  undefined1 auVar13 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  int local_250;
  undefined8 local_248;
  int local_240;
  undefined8 local_238;
  undefined8 local_230;
  int local_228;
  int local_220;
  int local_218;
  int local_210;
  undefined8 local_208;
  int local_200;
  undefined8 local_1f8;
  undefined8 local_1f0;
  undefined8 local_1e8;
  undefined8 local_1e0;
  undefined8 local_1d8;
  undefined8 local_1d0;
  undefined8 local_1c8;
  undefined8 *local_1c0;
  undefined8 local_1b8;
  int local_1b0;
  undefined8 local_1a8;
  undefined8 local_1a0;
  undefined8 local_198;
  undefined8 local_190;
  sdword *local_188;
  undefined8 local_180;
  undefined8 *local_178;
  undefined8 *local_170;
  undefined8 local_168;
  undefined8 local_160;
  undefined8 uStack_158;
  undefined1 local_140;
  undefined7 uStack_13f;
  undefined *local_100;
  undefined8 uStack_f8;
  undefined8 local_f0;
  undefined8 uStack_e8;
  undefined *local_e0;
  undefined8 uStack_d8;
  undefined *local_d0;
  undefined8 uStack_c8;
  undefined *local_c0;
  undefined8 uStack_b8;
  undefined8 local_b0;
  undefined8 uStack_a8;
  undefined *local_a0;
  int *local_98;
  undefined *local_90;
  undefined8 uStack_88;
  undefined *local_80;
  undefined8 uStack_78;
  undefined8 local_70;
  undefined8 uStack_68;
  undefined8 local_60;
  undefined8 uStack_58;
  undefined8 local_50;
  undefined8 uStack_48;
  code *local_40;
  undefined *puStack_38;
  undefined8 local_30;
  undefined **ppuStack_28;
  undefined8 local_20;
  undefined **ppuStack_18;
  int *local_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_250 <= *(int **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_198 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar11 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_1f8 = auVar11._8_8_;
  local_168 = auVar11._0_8_;
  local_170 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_170[1] = 0x10;
  *local_170 = &DAT_00f195fc;
  auVar11 = runtime_mapassign_faststr(&DAT_00e91b20,local_198,local_168,local_1f8);
  puVar6 = auVar11._0_8_;
  puVar6[1] = 1;
  puVar6[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar11._8_8_,*puVar6);
    *extraout_R11 = local_170;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar6 = local_170;
  auVar11 = main_getRequestUserAgent(iStack0000000000000018);
  local_1d8 = auVar11._0_8_;
  mv_daemon_pkg_proxy___ProxyManager__CloseAll(mv_daemon_pkg_proxy_DefaultProxyManager);
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f02a51,8);
  if (piVar3[1] == 0) {
    uVar2 = 0;
    uVar4 = 0;
  }
  else {
    uVar2 = ((undefined8 *)*piVar3)[1];
    uVar4 = *(undefined8 *)*piVar3;
  }
  auVar12 = main_getRealProvider(uVar4,uVar2);
  local_248 = auVar12._8_8_;
  local_1b8 = auVar12._0_8_;
  piVar3 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,local_1b8,local_248);
  local_240 = *piVar3;
  local_1b0 = piVar3[1];
  if (extraout_BL == '\0') {
    auVar11 = runtime_concatstring2(0,&DAT_00f1d559,0x12,local_1b8,local_248);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar11._0_8_,auVar11._8_8_,
                        400);
    return;
  }
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00effe2d,7);
  if (piVar3[1] == 0) {
    local_1e0 = 0;
    uVar2 = 0;
  }
  else {
    uVar2 = ((undefined8 *)*piVar3)[1];
    local_1e0 = *(undefined8 *)*piVar3;
  }
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00efc947,5);
  if (piVar3[1] == 0) {
    iVar7 = 0;
    local_1e8 = 0;
  }
  else {
    iVar7 = ((undefined8 *)*piVar3)[1];
    local_1e8 = *(undefined8 *)*piVar3;
  }
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00f05a11,9);
  if (piVar3[1] == 0) {
    uVar4 = 0;
    local_1f0 = 0;
  }
  else {
    uVar4 = ((undefined8 *)*piVar3)[1];
    local_1f0 = *(undefined8 *)*piVar3;
  }
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f05a1a,9);
  if (piVar3[1] == 0) {
    local_228 = 0;
    local_190 = 0;
  }
  else {
    local_228 = ((undefined8 *)*piVar3)[1];
    local_190 = *(undefined8 *)*piVar3;
  }
  if (local_228 == 0) {
    uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
    piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efb5a3,4);
    if (piVar3[1] == 0) {
      local_228 = 0;
      local_190 = 0;
    }
    else {
      local_228 = ((undefined8 *)*piVar3)[1];
      local_190 = *(undefined8 *)*piVar3;
    }
  }
  local_10 = (int *)runtime_newobject(&DAT_00dd2b80);
  if (local_228 != 0) {
    puVar6 = (undefined8 *)runtime_newobject(&DAT_00dd29c0);
    local_a0 = &DAT_00db4420;
    local_98 = local_10;
    puVar6[1] = local_228;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = *puVar6;
      puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_00 = local_190;
      extraout_R11_00[1] = uVar5;
    }
    *puVar6 = local_190;
    fmt_Fscanf(go_itab__fmt_stringReader_io_Reader,puVar6,&DAT_00efa6de,2,&local_a0,1,1);
  }
  auVar13._8_8_ = iVar7;
  auVar13._0_8_ = local_1e8;
  auVar12._8_8_ = iVar7;
  auVar12._0_8_ = local_1e8;
  if ((iVar7 == 0) && (auVar12 = auVar13, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar12 = (**(code **)(local_240 + 0x28))(local_1b0);
    auVar12 = mv_daemon_provider___TokenStore__Get(main_tokenStore,auVar12._0_8_,auVar12._8_8_);
  }
  local_1d0 = auVar12._0_8_;
  (**(code **)(local_240 + 0x40))
            (local_1b0,local_1e0,uVar2,local_1d0,auVar12._8_8_,local_1d8,auVar11._8_8_);
  if (extraout_RBX != 0) {
    local_210 = extraout_RBX;
    local_180 = extraout_RCX_00;
    (**(code **)(local_240 + 0x28))(local_1b0);
    uStack_b8 = runtime_convTstring();
    local_c0 = &DAT_00dd29c0;
    if (local_210 == 0) {
      local_b0 = 0;
    }
    else {
      local_b0 = *(undefined8 *)(local_210 + 8);
    }
    uStack_a8 = local_180;
    local_40 = main_handleUserPlay_Printf_func2;
    local_30 = 0x31;
    puStack_38 = &DAT_00f453e2;
    local_20 = 2;
    ppuStack_18 = (undefined **)0x2;
    ppuStack_28 = &local_c0;
    log___Logger__output(log_std,0,2,&local_40);
    auVar11 = (**(code **)(local_210 + 0x18))(local_180);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar11._0_8_,auVar11._8_8_,
                        500);
    return;
  }
  puVar6 = extraout_RAX;
  local_1c0 = extraout_RAX;
  if (extraout_RAX[4] != 0) {
    main_proxySubtitles(extraout_RAX[3],extraout_RAX[4],extraout_RAX[5],extraout_RAX[2]);
    puVar6 = local_1c0;
    local_1c0[4] = extraout_RBX_00;
    local_1c0[5] = extraout_RCX_01;
    uVar5 = extraout_RAX_00;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = runtime_gcWriteBarrier2();
      *extraout_R11_01 = uVar5;
      extraout_R11_01[1] = extraout_RSI;
    }
    puVar6[3] = uVar5;
  }
  if (puVar6[1] == 0) goto LAB_00c507d3;
  auVar13 = strings_ToLower(*puVar6);
  local_238 = auVar13._8_8_;
  local_1a8 = auVar13._0_8_;
  local_70 = *local_1c0;
  uStack_68 = local_1c0[1];
  local_60 = local_1f0;
  local_50 = local_1e0;
  uStack_58 = uVar4;
  uStack_48 = uVar2;
  auVar13 = main_extractSafeVideoExt(&local_70,3,3);
  local_218 = auVar13._8_8_;
  local_188 = auVar13._0_8_;
  auVar13 = main_hasSafeVideoExt(local_1c0[7],local_1c0[8]);
  auVar1._8_8_ = local_218;
  auVar1._0_8_ = local_188;
  if (extraout_CL == '\0') {
    auVar13 = auVar1;
  }
  local_218 = auVar13._8_8_;
  local_188 = auVar13._0_8_;
  auVar13 = (**(code **)(local_240 + 0x28))(local_1b0);
  if (auVar13._8_8_ == 8) {
    bVar9 = *auVar13._0_8_ == 0x35313144554f4c43;
  }
  else {
    bVar9 = false;
  }
  iVar7 = internal_stringslite_Index(local_1a8,local_238,&DAT_00efc93d,5);
  if (iVar7 < 0) {
    iVar7 = internal_stringslite_Index(local_1a8,local_238,&DAT_00efb52f,4);
    bVar10 = -1 < iVar7;
  }
  else {
    bVar10 = true;
  }
  if ((bVar9) || (bVar10)) {
    local_40 = main_handleUserPlay_Printf_func3;
    local_30 = 0x68;
    puStack_38 = &DAT_00f60983;
    ppuStack_28 = in_XMM15_Qb;
    local_20 = in_XMM15_Qa;
    ppuStack_18 = in_XMM15_Qb;
    log___Logger__output(log_std,0,2);
    puVar6 = local_1c0;
    if (bVar10) {
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = local_1c0[2];
        runtime_gcWriteBarrier1();
        *extraout_R11_02 = uVar2;
        puVar6 = extraout_RCX_02;
      }
      puVar6[2] = 0;
    }
    goto LAB_00c507d3;
  }
  if ((int)local_1c0[6] < 1) {
    if (*local_10 < 1) {
      mv_daemon_pkg_proxy_GetRemoteFileSize(*local_1c0,local_1c0[1],local_1c0[2]);
      local_1c8 = extraout_RCX_03;
      local_250 = extraout_RBX_01;
      local_220 = extraout_RAX_01;
    }
    else {
      local_200 = *local_10;
      uStack_c8 = runtime_convT64();
      local_d0 = &DAT_00dd2b80;
      local_40 = main_handleUserPlay_Printf_func4;
      local_30 = 0x2e;
      puStack_38 = &DAT_00f41e70;
      local_20 = 1;
      ppuStack_18 = (undefined **)0x1;
      ppuStack_28 = &local_d0;
      log___Logger__output(log_std,0,2,&local_40);
      local_250 = 0;
      local_1c8 = 0;
      local_220 = local_200;
    }
  }
  else {
    local_250 = 0;
    local_1c8 = 0;
    local_220 = local_1c0[6];
  }
  if ((local_250 != 0) || (local_220 < 1)) {
    uStack_f8 = runtime_convT64(local_220);
    local_100 = &DAT_00dd2b80;
    if (local_250 == 0) {
      local_f0 = 0;
    }
    else {
      local_f0 = *(undefined8 *)(local_250 + 8);
    }
    uStack_e8 = local_1c8;
    uStack_d8 = runtime_convTstring(local_1e0,uVar2);
    local_e0 = &DAT_00dd29c0;
    local_40 = main_handleUserPlay_Printf_func5;
    local_30 = 0x6d;
    puStack_38 = &DAT_00f61fdc;
    local_20 = 3;
    ppuStack_18 = (undefined **)0x3;
    ppuStack_28 = &local_100;
    log___Logger__output(log_std,0,2,&local_40);
    local_220 = 0x80000000;
  }
  auVar13 = (**(code **)(local_240 + 0x28))(local_1b0);
  if (((auVar13._8_8_ == 6) && (*auVar13._0_8_ == 0x59494c41)) &&
     ((short)auVar13._0_8_[1] == 0x4e55)) {
    local_208 = 0x20;
  }
  else {
    auVar13 = (**(code **)(local_240 + 0x28))(local_1b0);
    if (((auVar13._8_8_ == 6) && (*auVar13._0_8_ == 0x4c4e5558)) &&
       ((short)auVar13._0_8_[1] == 0x4945)) {
      local_208 = 0x10;
    }
    else {
      local_208 = 8;
    }
  }
  if (main_concurrencyStore != (mv_daemon_provider_ConcurrencyStore *)0x0) {
    auVar13 = (**(code **)(local_240 + 0x28))(local_1b0);
    local_208 = mv_daemon_provider___ConcurrencyStore__Get
                          (main_concurrencyStore,auVar13._0_8_,auVar13._8_8_);
  }
  if (mv_daemon_provider_GlobalChunkSizeStore == (mv_daemon_provider_ChunkSizeStore *)0x0) {
    uVar5 = 0;
  }
  else {
    auVar13 = (**(code **)(local_240 + 0x28))(local_1b0);
    uVar5 = mv_daemon_provider___ChunkSizeStore__Get
                      (mv_daemon_provider_GlobalChunkSizeStore,auVar13._0_8_,auVar13._8_8_);
  }
  local_178 = (undefined8 *)runtime_newobject(&DAT_00e8d700);
  *local_178 = main_handleUserPlay_func1;
  local_178[2] = auVar12._8_8_;
  if (runtime_writeBarrier._0_4_ != 0) {
    local_178 = (undefined8 *)runtime_gcWriteBarrier4();
    *extraout_R11_03 = local_1d0;
    extraout_R11_03[1] = local_1b0;
    extraout_R11_03[2] = local_1e0;
    extraout_R11_03[3] = local_1d8;
  }
  local_178[1] = local_1d0;
  local_178[3] = local_240;
  local_178[4] = local_1b0;
  local_178[6] = uVar2;
  local_178[5] = local_1e0;
  local_178[8] = auVar11._8_8_;
  local_178[7] = local_1d8;
  if (local_218 == 4) {
    if (*local_188 == 0x6f73692e) {
      bVar9 = true;
    }
    else if (*local_188 == 0x676d692e) {
      bVar9 = true;
    }
    else {
      if (*local_188 != 0x67726e2e) goto LAB_00c505a5;
      bVar9 = true;
    }
  }
  else {
LAB_00c505a5:
    auVar11 = strings_ToLower(local_1f0,uVar4);
    iVar7 = internal_stringslite_Index(auVar11._0_8_,auVar11._8_8_,&DAT_00efb5a7,4);
    if (iVar7 < 0) {
      auVar11 = strings_ToLower(local_1c0[7],local_1c0[8]);
      iVar7 = internal_stringslite_Index(auVar11._0_8_,auVar11._8_8_,&DAT_00efb5a7,4);
      bVar9 = -1 < iVar7;
    }
    else {
      bVar9 = true;
    }
  }
  if (bVar9) {
LAB_00c50674:
    auVar11 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull
                        (mv_daemon_pkg_proxy_DefaultProxyManager,*local_1c0,local_1c0[1],
                         local_1c0[2],local_220,0,0,1,local_178);
  }
  else {
    auVar11 = strings_ToLower(local_1e0,uVar2);
    iVar7 = internal_stringslite_Index(auVar11._0_8_,auVar11._8_8_,&DAT_00efb5a7,4);
    if (-1 < iVar7) goto LAB_00c50674;
    auVar11 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull
                        (mv_daemon_pkg_proxy_DefaultProxyManager,*local_1c0,local_1c0[1],
                         local_1c0[2],local_220,local_208,uVar5,0,local_178);
  }
  local_230 = auVar11._8_8_;
  local_1a0 = auVar11._0_8_;
  uStack_88 = runtime_convTstring(local_188,local_218);
  local_90 = &DAT_00dd29c0;
  uStack_78 = runtime_convTstring(local_1a0,local_230);
  local_80 = &DAT_00dd29c0;
  auVar11 = fmt_Sprintf(&DAT_00f3ed29,0x2b,&local_90,2,2);
  uVar2 = auVar11._0_8_;
  local_1c0[1] = auVar11._8_8_;
  puVar6 = local_1c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar4 = *local_1c0;
    uVar2 = runtime_gcWriteBarrier3();
    *extraout_R11_04 = uVar2;
    extraout_R11_04[1] = uVar4;
    extraout_R11_04[2] = extraout_RSI_00;
    puVar6 = extraout_RCX_04;
  }
  *puVar6 = uVar2;
  puVar6[2] = 0;
  puVar6[6] = local_220;
LAB_00c507d3:
  local_160 = 0;
  if (iStack0000000000000008 != 0) {
    uVar8 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar7 = (uVar8 & *(uint *)main__typeAssert_47) * 0x10;
      if (*(int *)(main__typeAssert_47 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_160 = *(undefined8 *)(main__typeAssert_47 + iVar7 + 0x10);
        goto LAB_00c5097a;
      }
      uVar8 = uVar8 + 1;
    } while (*(int *)(main__typeAssert_47 + iVar7 + 8) != 0);
    local_160 = runtime_typeAssert(&main__typeAssert_47);
    puVar6 = local_1c0;
  }
LAB_00c5097a:
  uStack_158 = uStack0000000000000010;
  _local_140 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_160,&DAT_00db1aa0,puVar6);
  return;
}

