/* Reconstructed pseudocode, not original Go source: main.handlePlay */

void main_handlePlay(int param_1,undefined8 param_2,int param_3)

{
  undefined1 auVar1 [16];
  undefined8 uVar2;
  int *piVar3;
  undefined8 uVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  int iVar7;
  undefined8 extraout_RAX;
  undefined8 extraout_RAX_00;
  undefined8 *extraout_RAX_01;
  undefined8 *extraout_RAX_02;
  undefined8 extraout_RAX_03;
  int iVar8;
  int extraout_RAX_04;
  char extraout_CL;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 *extraout_RCX_05;
  undefined8 extraout_RCX_06;
  undefined8 *extraout_RCX_07;
  uint uVar9;
  undefined8 extraout_RBX;
  int extraout_RBX_00;
  int extraout_RBX_01;
  int extraout_RBX_02;
  undefined8 extraout_RBX_03;
  int extraout_RBX_04;
  undefined8 extraout_RSI;
  undefined8 extraout_RSI_00;
  undefined8 extraout_RDI;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  undefined8 *extraout_R11_03;
  undefined8 *extraout_R11_04;
  int unaff_R14;
  bool bVar10;
  bool bVar11;
  undefined8 in_XMM15_Qa;
  undefined **in_XMM15_Qb;
  undefined1 auVar12 [16];
  undefined1 auVar13 [16];
  undefined1 auVar14 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_2e0;
  undefined8 local_2d8;
  undefined8 local_2d0;
  undefined8 local_2c8;
  int local_2c0;
  undefined8 local_2b8;
  undefined1 *local_2b0;
  int local_2a8;
  undefined8 local_2a0;
  undefined8 local_298;
  int local_290;
  undefined8 local_288;
  int local_280;
  int local_278;
  int local_270;
  undefined8 local_268;
  undefined8 local_260;
  int local_258;
  undefined8 local_250;
  int local_248;
  undefined8 local_240;
  undefined8 local_238;
  undefined8 local_230;
  uint local_228;
  undefined8 local_220;
  undefined8 local_218;
  undefined8 local_210;
  undefined8 local_208;
  undefined8 local_200;
  undefined8 *local_1f8;
  undefined8 local_1f0;
  undefined8 local_1e8;
  undefined8 local_1e0;
  undefined8 local_1d8;
  undefined8 local_1d0;
  undefined8 local_1c8;
  undefined8 local_1c0;
  sdword *local_1b8;
  undefined8 local_1b0;
  undefined8 local_1a8;
  undefined8 local_1a0;
  undefined8 local_198;
  undefined8 *local_190;
  undefined8 *local_188;
  undefined8 local_180;
  undefined8 local_178;
  undefined8 uStack_170;
  undefined1 local_158;
  undefined7 uStack_157;
  undefined *local_118;
  undefined8 uStack_110;
  undefined *local_108;
  undefined8 uStack_100;
  undefined8 local_f8;
  undefined8 uStack_f0;
  undefined *local_e8;
  undefined8 uStack_e0;
  undefined *local_d8;
  undefined8 uStack_d0;
  undefined *local_c8;
  undefined8 uStack_c0;
  undefined8 local_b8;
  undefined8 uStack_b0;
  undefined *local_a8;
  int *local_a0;
  undefined *local_98;
  undefined8 uStack_90;
  undefined *local_88;
  undefined8 uStack_80;
  code *local_78;
  undefined *puStack_70;
  undefined8 local_68;
  undefined **ppuStack_60;
  undefined8 local_58;
  undefined **ppuStack_50;
  undefined8 local_48;
  undefined8 uStack_40;
  undefined8 local_38;
  int iStack_30;
  undefined8 local_28;
  undefined8 uStack_20;
  int *local_18;
  undefined8 *local_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_2e0 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_1d0 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar12 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_240 = auVar12._8_8_;
  local_180 = auVar12._0_8_;
  local_188 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_188[1] = 0x10;
  *local_188 = &DAT_00f195fc;
  auVar12 = runtime_mapassign_faststr(&DAT_00e91b20,local_1d0,local_180,local_240);
  puVar6 = auVar12._0_8_;
  puVar6[1] = 1;
  puVar6[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar12._8_8_,*puVar6);
    *extraout_R11 = local_188;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar6 = local_188;
  auVar12 = main_getRequestUserAgent(iStack0000000000000018);
  local_2d0 = auVar12._8_8_;
  local_210 = auVar12._0_8_;
  mv_daemon_pkg_proxy___ProxyManager__CloseAll(mv_daemon_pkg_proxy_DefaultProxyManager);
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f05a08,9);
  if (piVar3[1] == 0) {
    local_2e0 = 0;
    local_218 = 0;
  }
  else {
    local_2e0 = ((undefined8 *)*piVar3)[1];
    local_218 = *(undefined8 *)*piVar3;
  }
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00efb56f,4);
  if (piVar3[1] == 0) {
    uVar2 = 0;
    local_220 = 0;
  }
  else {
    uVar2 = ((undefined8 *)*piVar3)[1];
    local_220 = *(undefined8 *)*piVar3;
  }
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00effe2d,7);
  if (piVar3[1] == 0) {
    uVar9 = 0;
    local_228 = 0;
  }
  else {
    uVar9 = ((uint *)*piVar3)[1];
    local_228 = *(uint *)*piVar3;
  }
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00efc947,5);
  if (piVar3[1] == 0) {
    iVar8 = 0;
    local_230 = 0;
  }
  else {
    iVar8 = ((undefined8 *)*piVar3)[1];
    local_230 = *(undefined8 *)*piVar3;
  }
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00f05a11,9);
  if (piVar3[1] == 0) {
    uVar4 = 0;
    local_238 = 0;
  }
  else {
    uVar4 = ((undefined8 *)*piVar3)[1];
    local_238 = *(undefined8 *)*piVar3;
  }
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f05a1a,9);
  if (piVar3[1] == 0) {
    local_290 = 0;
    local_1c8 = 0;
  }
  else {
    local_290 = ((undefined8 *)*piVar3)[1];
    local_1c8 = *(undefined8 *)*piVar3;
  }
  if (local_290 == 0) {
    uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
    piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efb5a3,4);
    if (piVar3[1] == 0) {
      local_290 = 0;
      local_1c8 = 0;
    }
    else {
      local_290 = ((undefined8 *)*piVar3)[1];
      local_1c8 = *(undefined8 *)*piVar3;
    }
  }
  local_18 = (int *)runtime_newobject(&DAT_00dd2b80);
  if (local_290 != 0) {
    puVar6 = (undefined8 *)runtime_newobject(&DAT_00dd29c0);
    local_a8 = &DAT_00db4420;
    local_a0 = local_18;
    puVar6[1] = local_290;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = *puVar6;
      puVar6 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_00 = local_1c8;
      extraout_R11_00[1] = uVar5;
    }
    *puVar6 = local_1c8;
    fmt_Fscanf(go_itab__fmt_stringReader_io_Reader,puVar6,&DAT_00efa6de,2,&local_a8,1,1);
  }
  if (*local_18 < 1) {
    iVar7 = mv_daemon_provider_ExtractFileSizeFromUrl(local_218,local_2e0);
    *local_18 = iVar7;
  }
  if ((*local_18 < 1) && (uVar9 != 0)) {
    iVar7 = mv_daemon_provider_ExtractFileSizeFromUrl(local_228);
    *local_18 = iVar7;
  }
  auVar12._8_8_ = uVar9;
  auVar12._0_8_ = local_228;
  if (uVar9 == 0) {
    auVar13 = mv_daemon_provider_ExtractSubIdsFromUrl(local_218,local_2e0);
    auVar12._8_8_ = 0;
    auVar12._0_8_ = local_228;
    if (auVar13._8_8_ != 0) {
      auVar12 = auVar13;
    }
  }
  local_288 = auVar12._8_8_;
  local_1c0 = auVar12._0_8_;
  mv_daemon_provider_CleanShareUrlAndExtractCode(local_218,local_2e0,local_220,uVar2);
  local_2b8 = extraout_RBX;
  local_260 = extraout_RDI;
  local_200 = extraout_RAX;
  local_1a0 = extraout_RCX_00;
  iVar7 = internal_stringslite_Index(local_1c0,local_288,&DAT_00efabb5,3);
  if (iVar7 < 0) {
    local_2a8 = 0;
    local_1e8 = 0;
  }
  else {
    mv_daemon_provider_DecodeBase64Flexible(local_1c0,local_288);
    if (extraout_RBX_00 == 0) {
      local_2a8 = 0;
      local_1e8 = 0;
    }
    else {
      local_258 = extraout_RBX_00;
      local_250 = extraout_RCX_01;
      local_198 = extraout_RAX_00;
      local_10 = (undefined8 *)runtime_newobject(&DAT_00e2dd00);
      iVar7 = encoding_json_Unmarshal(local_198,local_258,local_250,&DAT_00dc0060,local_10);
      if (iVar7 == 0) {
        local_2a8 = local_10[1];
        if (local_2a8 == 0) {
          iVar7 = local_10[3];
          local_2a8 = 0;
          if (iVar7 != 0) {
            local_2a8 = iVar7;
          }
          local_1e8 = 0;
          if (iVar7 != 0) {
            local_1e8 = local_10[2];
          }
        }
        else {
          local_1e8 = *local_10;
        }
      }
      else {
        local_2a8 = 0;
        local_1e8 = 0;
      }
    }
  }
  local_48 = local_238;
  uStack_20 = local_288;
  local_28 = local_1c0;
  uStack_40 = uVar4;
  local_38 = local_1e8;
  iStack_30 = local_2a8;
  auVar12 = main_extractSafeVideoExt(&local_48,3,3);
  local_280 = auVar12._8_8_;
  local_1b8 = auVar12._0_8_;
  auVar13 = main_getProviderByShareUrl(local_200,local_2b8);
  auVar14._8_8_ = iVar8;
  auVar14._0_8_ = local_230;
  local_1f0 = auVar13._8_8_;
  local_2b0 = auVar13._0_8_;
  if (local_2b0 == (undefined1 *)0x0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f21faa,0x15,400);
    return;
  }
  if (iVar8 == 0) {
    auVar12 = (**(code **)((int)local_2b0 + 0x28))(local_1f0);
    auVar14 = mv_daemon_provider___TokenStore__Get(main_tokenStore,auVar12._0_8_,auVar12._8_8_);
    auVar13._8_8_ = local_1f0;
    auVar13._0_8_ = local_2b0;
  }
  local_2c8 = auVar14._8_8_;
  local_208 = auVar14._0_8_;
  local_1f0 = auVar13._8_8_;
  local_2b0 = auVar13._0_8_;
  if (local_2b0 == go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    mv_daemon_provider___Cloud115Provider__ResolvePlayWithUA
              (local_1f0,local_200,local_2b8,local_1a0,local_260,local_1c0,local_288,local_208,
               local_2c8,local_210,local_2d0);
    puVar6 = extraout_RAX_01;
    local_1a8 = extraout_RCX_02;
    local_270 = extraout_RBX_01;
  }
  else {
    (**(code **)(local_2b0 + 0x38))
              (local_1f0,local_200,local_2b8,local_1a0,local_260,local_1c0,local_288,local_208,
               local_2c8);
    puVar6 = extraout_RAX_02;
    local_1a8 = extraout_RCX_03;
    local_270 = extraout_RBX_02;
  }
  if (local_270 != 0) {
    (**(code **)(local_2b0 + 0x28))(local_1f0);
    uStack_c0 = runtime_convTstring();
    local_c8 = &DAT_00dd29c0;
    if (local_270 == 0) {
      local_b8 = 0;
    }
    else {
      local_b8 = *(undefined8 *)(local_270 + 8);
    }
    uStack_b0 = local_1a8;
    local_78 = main_handlePlay_Printf_func2;
    local_68 = 0x29;
    puStack_70 = &DAT_00f3ca4a;
    local_58 = 2;
    ppuStack_50 = (undefined **)0x2;
    ppuStack_60 = &local_c8;
    log___Logger__output(log_std,0,2,&local_78);
    auVar12 = (**(code **)(local_270 + 0x18))(local_1a8);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar12._0_8_,auVar12._8_8_,
                        500);
    return;
  }
  local_1f8 = puVar6;
  if (puVar6[4] != 0) {
    main_proxySubtitles(puVar6[3],puVar6[4],puVar6[5],puVar6[2]);
    puVar6 = local_1f8;
    local_1f8[4] = extraout_RBX_03;
    local_1f8[5] = extraout_RCX_04;
    uVar2 = extraout_RAX_03;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar2 = runtime_gcWriteBarrier2();
      *extraout_R11_01 = uVar2;
      extraout_R11_01[1] = extraout_RSI;
    }
    puVar6[3] = uVar2;
  }
  if (puVar6[1] == 0) goto LAB_00c4d04f;
  auVar12 = strings_ToLower(*puVar6);
  local_2a0 = auVar12._8_8_;
  local_1e0 = auVar12._0_8_;
  auVar12 = main_hasSafeVideoExt(local_1f8[7],local_1f8[8]);
  if (extraout_CL == '\0') {
    local_48 = *local_1f8;
    uStack_40 = local_1f8[1];
    iStack_30 = local_2a8;
    local_38 = local_1e8;
    local_28 = local_238;
    uStack_20 = uVar4;
    auVar12 = main_extractSafeVideoExt(&local_48,3,3);
    auVar1._8_8_ = local_280;
    auVar1._0_8_ = local_1b8;
    if ((auVar12._8_8_ == 4) && (*auVar12._0_8_ == 0x34706d2e)) {
      auVar12 = auVar1;
    }
  }
  local_280 = auVar12._8_8_;
  local_1b8 = auVar12._0_8_;
  auVar12 = (**(code **)(local_2b0 + 0x28))(local_1f0);
  if (auVar12._8_8_ == 8) {
    bVar10 = *auVar12._0_8_ == 0x35313144554f4c43;
  }
  else {
    bVar10 = false;
  }
  iVar8 = internal_stringslite_Index(local_1e0,local_2a0,&DAT_00efc93d,5);
  if (iVar8 < 0) {
    iVar8 = internal_stringslite_Index(local_1e0,local_2a0,&DAT_00efb52f,4);
    bVar11 = -1 < iVar8;
  }
  else {
    bVar11 = true;
  }
  if ((bVar10) || (bVar11)) {
    local_78 = main_handlePlay_Printf_func3;
    local_68 = 0x5e;
    puStack_70 = &DAT_00f5de62;
    ppuStack_60 = in_XMM15_Qb;
    local_58 = in_XMM15_Qa;
    ppuStack_50 = in_XMM15_Qb;
    log___Logger__output(log_std,0,2);
    puVar6 = local_1f8;
    if (bVar11) {
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = local_1f8[2];
        runtime_gcWriteBarrier1();
        *extraout_R11_02 = uVar2;
        puVar6 = extraout_RCX_05;
      }
      puVar6[2] = 0;
    }
    goto LAB_00c4d04f;
  }
  if ((int)local_1f8[6] < 1) {
    if (*local_18 < 1) {
      mv_daemon_pkg_proxy_GetRemoteFileSize(*local_1f8,local_1f8[1],local_1f8[2]);
      local_2c0 = extraout_RAX_04;
      local_1b0 = extraout_RCX_06;
      local_278 = extraout_RBX_04;
    }
    else {
      local_248 = *local_18;
      uStack_e0 = runtime_convT64();
      local_e8 = &DAT_00dd2b80;
      local_78 = main_handlePlay_Printf_func5;
      local_68 = 0x28;
      puStack_70 = &DAT_00f3b70f;
      local_58 = 1;
      ppuStack_50 = (undefined **)0x1;
      ppuStack_60 = &local_e8;
      log___Logger__output(log_std,0,2,&local_78);
      local_278 = 0;
      local_1b0 = 0;
      local_2c0 = local_248;
    }
  }
  else {
    local_248 = local_1f8[6];
    uStack_d0 = runtime_convT64();
    local_d8 = &DAT_00dd2b80;
    local_78 = main_handlePlay_Printf_func4;
    local_68 = 0x31;
    puStack_70 = &DAT_00f453b1;
    local_58 = 1;
    ppuStack_50 = (undefined **)0x1;
    ppuStack_60 = &local_d8;
    log___Logger__output(log_std,0,2,&local_78);
    local_278 = 0;
    local_1b0 = 0;
    local_2c0 = local_248;
  }
  if ((local_278 != 0) || (local_2c0 < 1)) {
    uStack_100 = runtime_convT64();
    local_108 = &DAT_00dd2b80;
    if (local_278 == 0) {
      local_f8 = 0;
    }
    else {
      local_f8 = *(undefined8 *)(local_278 + 8);
    }
    uStack_f0 = local_1b0;
    local_78 = main_handlePlay_Printf_func6;
    local_68 = 0x5c;
    puStack_70 = &DAT_00f5d780;
    local_58 = 2;
    ppuStack_50 = (undefined **)0x2;
    ppuStack_60 = &local_108;
    log___Logger__output(log_std,0,2,&local_78);
    local_2c0 = 0x80000000;
  }
  auVar12 = (**(code **)(local_2b0 + 0x28))(local_1f0);
  if (((auVar12._8_8_ == 6) && (*auVar12._0_8_ == 0x59494c41)) &&
     ((short)auVar12._0_8_[1] == 0x4e55)) {
    local_268 = 0x20;
  }
  else {
    auVar12 = (**(code **)(local_2b0 + 0x28))(local_1f0);
    if (((auVar12._8_8_ == 6) && (*auVar12._0_8_ == 0x4c4e5558)) &&
       ((short)auVar12._0_8_[1] == 0x4945)) {
      local_268 = 0x10;
    }
    else {
      local_268 = 8;
    }
  }
  if (main_concurrencyStore != (mv_daemon_provider_ConcurrencyStore *)0x0) {
    auVar12 = (**(code **)(local_2b0 + 0x28))(local_1f0);
    local_268 = mv_daemon_provider___ConcurrencyStore__Get
                          (main_concurrencyStore,auVar12._0_8_,auVar12._8_8_);
  }
  if (mv_daemon_provider_GlobalChunkSizeStore == (mv_daemon_provider_ChunkSizeStore *)0x0) {
    local_2d8 = 0;
  }
  else {
    auVar12 = (**(code **)(local_2b0 + 0x28))(local_1f0);
    local_2d8 = mv_daemon_provider___ChunkSizeStore__Get
                          (mv_daemon_provider_GlobalChunkSizeStore,auVar12._0_8_,auVar12._8_8_);
  }
  local_190 = (undefined8 *)runtime_newobject(&DAT_00e9c520);
  *local_190 = main_handlePlay_func1;
  local_190[2] = local_2c8;
  if (runtime_writeBarrier._0_4_ != 0) {
    local_190 = (undefined8 *)runtime_gcWriteBarrier5();
    *extraout_R11_03 = local_208;
    extraout_R11_03[1] = local_1f0;
    extraout_R11_03[2] = local_200;
    extraout_R11_03[3] = local_1a0;
    extraout_R11_03[4] = local_1c0;
  }
  local_190[1] = local_208;
  local_190[3] = local_2b0;
  local_190[4] = local_1f0;
  local_190[6] = local_2b8;
  local_190[5] = local_200;
  local_190[8] = local_260;
  local_190[7] = local_1a0;
  local_190[10] = local_288;
  local_190[9] = local_1c0;
  uStack_110 = runtime_convTstring(*local_1f8,local_1f8[1]);
  local_118 = &DAT_00dd29c0;
  local_78 = main_handlePlay_Printf_func7;
  local_68 = 0x1c;
  puStack_70 = &DAT_00f2bdce;
  local_58 = 1;
  ppuStack_50 = (undefined **)0x1;
  ppuStack_60 = &local_118;
  log___Logger__output(log_std,0,2,&local_78);
  if (local_280 == 4) {
    if (*local_1b8 == 0x6f73692e) {
      bVar10 = true;
    }
    else if (*local_1b8 == 0x676d692e) {
      bVar10 = true;
    }
    else {
      if (*local_1b8 != 0x67726e2e) goto LAB_00c4ce38;
      bVar10 = true;
    }
  }
  else {
LAB_00c4ce38:
    auVar12 = strings_ToLower(local_1c0,local_288);
    iVar8 = internal_stringslite_Index(auVar12._0_8_,auVar12._8_8_,&DAT_00efb5a7,4);
    if (iVar8 < 0) {
      auVar12 = strings_ToLower(local_1f8[7],local_1f8[8]);
      iVar8 = internal_stringslite_Index(auVar12._0_8_,auVar12._8_8_,&DAT_00efb5a7,4);
      bVar10 = -1 < iVar8;
    }
    else {
      bVar10 = true;
    }
  }
  if (bVar10) {
LAB_00c4ceec:
    auVar12 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull
                        (mv_daemon_pkg_proxy_DefaultProxyManager,*local_1f8,local_1f8[1],
                         local_1f8[2],local_2c0,0,0,1,local_190);
  }
  else {
    auVar12 = strings_ToLower(local_238,uVar4,local_280);
    iVar8 = internal_stringslite_Index(auVar12._0_8_,auVar12._8_8_,&DAT_00efb5a7,4);
    if (-1 < iVar8) goto LAB_00c4ceec;
    auVar12 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull
                        (mv_daemon_pkg_proxy_DefaultProxyManager,*local_1f8,local_1f8[1],
                         local_1f8[2],local_2c0,local_268,local_2d8,0,local_190);
  }
  local_298 = auVar12._8_8_;
  local_1d8 = auVar12._0_8_;
  uStack_90 = runtime_convTstring(local_1b8,local_280);
  local_98 = &DAT_00dd29c0;
  uStack_80 = runtime_convTstring(local_1d8,local_298);
  local_88 = &DAT_00dd29c0;
  auVar12 = fmt_Sprintf(&DAT_00f3ed29,0x2b,&local_98,2,2);
  uVar2 = auVar12._0_8_;
  local_1f8[1] = auVar12._8_8_;
  puVar6 = local_1f8;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar4 = *local_1f8;
    uVar2 = runtime_gcWriteBarrier3();
    *extraout_R11_04 = uVar2;
    extraout_R11_04[1] = uVar4;
    extraout_R11_04[2] = extraout_RSI_00;
    puVar6 = extraout_RCX_07;
  }
  *puVar6 = uVar2;
  puVar6[2] = 0;
  puVar6[6] = local_2c0;
LAB_00c4d04f:
  local_178 = 0;
  if (iStack0000000000000008 != 0) {
    uVar9 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar8 = (uVar9 & *(uint *)main__typeAssert_40) * 0x10;
      if (*(int *)(main__typeAssert_40 + iVar8 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_178 = *(undefined8 *)(main__typeAssert_40 + iVar8 + 0x10);
        goto LAB_00c4d1dd;
      }
      uVar9 = uVar9 + 1;
    } while (*(int *)(main__typeAssert_40 + iVar8 + 8) != 0);
    local_178 = runtime_typeAssert(&main__typeAssert_40);
    puVar6 = local_1f8;
  }
LAB_00c4d1dd:
  uStack_170 = uStack0000000000000010;
  _local_158 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_178,&DAT_00db1aa0,puVar6);
  return;
}

