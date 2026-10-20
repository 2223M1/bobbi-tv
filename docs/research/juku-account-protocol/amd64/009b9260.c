/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).StartQrLoginWithType */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__StartQrLoginWithType
          (undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  code *pcVar1;
  int iVar2;
  undefined1 auVar3 [24];
  undefined1 auVar4 [24];
  bool bVar5;
  undefined1 auVar6 [16];
  undefined1 auVar7 [16];
  undefined1 auVar8 [16];
  undefined1 auVar9 [16];
  int extraout_RAX;
  undefined8 *puVar10;
  int *piVar11;
  int extraout_RAX_00;
  undefined8 *puVar12;
  char *extraout_RAX_01;
  undefined8 uVar13;
  undefined8 uVar14;
  sdword sVar18;
  undefined8 extraout_RCX;
  int extraout_RCX_00;
  undefined8 extraout_RCX_01;
  int extraout_RCX_02;
  uint uVar19;
  undefined8 extraout_RCX_03;
  undefined1 auVar15 [24];
  undefined1 auVar16 [24];
  undefined1 auVar17 [24];
  int iVar20;
  undefined8 uVar22;
  int extraout_RBX;
  int extraout_RBX_00;
  int extraout_RBX_01;
  int extraout_RSI;
  int iVar23;
  int extraout_RDI;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  int *extraout_R11_03;
  undefined8 *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  undefined8 *extraout_R11_07;
  int *extraout_R11_08;
  int *extraout_R11_09;
  undefined8 *extraout_R11_10;
  int *extraout_R11_11;
  int unaff_R14;
  undefined8 *in_XMM15_Qa;
  code **in_XMM15_Qb;
  undefined1 auVar24 [16];
  undefined1 auVar25 [16];
  undefined8 uStack0000000000000010;
  undefined1 local_440 [16];
  int local_430;
  int local_428;
  int *local_420;
  undefined8 local_418;
  code *local_410;
  code *local_408;
  int local_400;
  undefined8 local_3f8;
  int local_3f0;
  int local_3e8;
  undefined8 local_3e0;
  undefined *local_3d8;
  undefined8 uStack_3d0;
  undefined *local_3c8;
  undefined8 uStack_3c0;
  undefined *local_3b8;
  undefined8 uStack_3b0;
  undefined8 *local_3a8;
  code **ppcStack_3a0;
  undefined *local_348;
  undefined8 uStack_340;
  undefined *local_338;
  undefined8 uStack_330;
  undefined8 *local_328;
  undefined8 local_320;
  undefined8 local_318;
  code *local_310;
  undefined8 local_308;
  undefined8 local_300;
  undefined8 local_2f8 [33];
  undefined1 local_1f0 [8];
  undefined8 uStack_1e8;
  undefined8 *local_1e0;
  code *local_1c0;
  undefined8 local_1b8;
  undefined8 local_1b0;
  undefined8 local_1a8 [33];
  undefined1 local_a0 [8];
  undefined8 uStack_98;
  undefined8 *local_90;
  undefined *local_70;
  undefined8 uStack_68;
  undefined *local_60;
  undefined8 uStack_58;
  undefined *local_50;
  undefined8 uStack_48;
  undefined *local_40;
  undefined8 uStack_38;
  undefined *local_30;
  undefined8 uStack_28;
  int *local_20;
  code **local_18;
  code **ppcStack_10;
  undefined8 uVar21;
  
  uStack0000000000000010 = param_2;
  while (local_440 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_420 = (int *)0x0;
  ppcStack_10 = in_XMM15_Qb;
  auVar24 = mv_daemon_provider_NormalizeCloud115ClientType(uStack0000000000000010,param_3);
  uVar21 = auVar24._8_8_;
  local_3e0 = auVar24._0_8_;
  auVar24 = mv_daemon_provider_get115BrowserVersion();
  uVar22 = auVar24._8_8_;
  local_418 = auVar24._0_8_;
  uStack_340 = runtime_convTstring(mv_daemon_provider_Cloud115ApiBase.str,
                                   mv_daemon_provider_Cloud115ApiBase.len);
  local_348 = &DAT_00dd29c0;
  uStack_330 = runtime_convTstring(local_3e0,uVar21);
  local_338 = &DAT_00dd29c0;
  auVar24 = fmt_Sprintf(&DAT_00f25343,0x17,&local_348,2,2);
  net_http_NewRequestWithContext
            (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_00efaba3,3,
             auVar24._0_8_,auVar24._8_8_,0,0);
  if (extraout_RBX != 0) {
    auVar3._8_8_ = extraout_RCX;
    auVar3._0_8_ = extraout_RBX;
    auVar3._16_8_ = 0;
    return auVar3 << 0x40;
  }
  sVar18 = 4;
  puVar10 = local_1a8;
  do {
    puVar12 = puVar10;
    *puVar12 = in_XMM15_Qa;
    puVar12[1] = in_XMM15_Qb;
    puVar12[2] = in_XMM15_Qa;
    puVar12[3] = in_XMM15_Qb;
    puVar12[4] = in_XMM15_Qa;
    puVar12[5] = in_XMM15_Qb;
    puVar12[6] = in_XMM15_Qa;
    puVar12[7] = in_XMM15_Qb;
    sVar18 = sVar18 + -1;
    puVar10 = puVar12 + 8;
  } while (sVar18 != 0);
  puVar12[7] = in_XMM15_Qa;
  puVar12[8] = in_XMM15_Qb;
  local_1a8[0] = 0x8080808080808080;
  local_90 = local_1a8;
  local_400 = extraout_RAX;
  uStack_98 = runtime_rand();
  puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_a0,&DAT_00efe659,6);
  puVar10[1] = 0x12;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar14 = *puVar10;
    puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11 = uVar14;
  }
  *puVar10 = &DAT_00f1d949;
  puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_a0,&DAT_00effe26,7);
  puVar10[1] = 0x13;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar14 = *puVar10;
    puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar14;
  }
  *puVar10 = &DAT_00f1f31d;
  auVar24 = mv_daemon_provider_get115QrUserAgent(local_3e0,uVar21,local_418,uVar22);
  local_318 = auVar24._0_8_;
  puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_a0,&DAT_00f0a13f,10);
  puVar10[1] = auVar24._8_8_;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar14 = *puVar10;
    puVar10 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_01 = local_318;
    extraout_R11_01[1] = uVar14;
  }
  *puVar10 = local_318;
  local_3a8 = in_XMM15_Qa;
  ppcStack_3a0 = in_XMM15_Qb;
  runtime_mapIterStart(&DAT_00e16200,local_a0);
  while (local_3a8 != (undefined8 *)0x0) {
    pcVar1 = ppcStack_3a0[1];
    local_408 = *ppcStack_3a0;
    local_320 = *(undefined8 *)(local_400 + 0x38);
    auVar24 = net_textproto_CanonicalMIMEHeaderKey(*local_3a8,local_3a8[1]);
    local_318 = auVar24._0_8_;
    puVar10 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
    puVar10[1] = pcVar1;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_02 = local_408;
    }
    *puVar10 = local_408;
    local_328 = puVar10;
    auVar24 = runtime_mapassign_faststr(&DAT_00e91b20,local_320,local_318,auVar24._8_8_);
    piVar11 = auVar24._0_8_;
    piVar11[1] = 1;
    piVar11[2] = 1;
    if (runtime_writeBarrier._0_4_ != 0) {
      piVar11 = (int *)runtime_gcWriteBarrier2(piVar11,auVar24._8_8_,*piVar11);
      *extraout_R11_03 = (int)local_328;
      extraout_R11_03[1] = extraout_RCX_00;
    }
    *piVar11 = (int)local_328;
    runtime_mapIterNext(&local_3a8);
  }
  net_http___Client__do(net_http_DefaultClient,local_400);
  if (extraout_RBX_00 != 0) {
    auVar4._8_8_ = extraout_RCX_01;
    auVar4._0_8_ = extraout_RBX_00;
    auVar4._16_8_ = 0;
    return auVar4 << 0x40;
  }
  local_1b8 = *(undefined8 *)(extraout_RAX_00 + 0x40);
  local_1b0 = *(undefined8 *)(extraout_RAX_00 + 0x48);
  local_1c0 = mv_daemon_provider___Cloud115Provider__StartQrLoginWithType_deferwrap1;
  local_18 = &local_1c0;
  local_428 = extraout_RAX_00;
  local_20 = (int *)runtime_newobject(&DAT_00e32d00);
  iVar23 = *(int *)(local_428 + 0x40);
  local_3f8 = *(undefined8 *)(local_428 + 0x48);
  uVar14 = 0;
  if (iVar23 != 0) {
    uVar19 = (uint)*(dword *)(iVar23 + 0x10);
    do {
      iVar20 = (uVar19 & *(uint *)mv_daemon_provider__typeAssert_69) * 0x10;
      if (*(int *)(mv_daemon_provider__typeAssert_69 + iVar20 + 8) == *(int *)(iVar23 + 8)) {
        uVar14 = *(undefined8 *)(mv_daemon_provider__typeAssert_69 + iVar20 + 0x10);
        goto LAB_009b9788;
      }
      uVar19 = uVar19 + 1;
    } while (*(int *)(mv_daemon_provider__typeAssert_69 + iVar20 + 8) != 0);
    uVar14 = runtime_typeAssert(&mv_daemon_provider__typeAssert_69);
  }
LAB_009b9788:
  local_318 = uVar14;
  puVar10 = (undefined8 *)runtime_newobject(&DAT_00eba560);
  *puVar10 = local_318;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_04 = local_3f8;
  }
  puVar10[1] = local_3f8;
  local_440 = encoding_json___Decoder__Decode(puVar10,&DAT_00dc63e0,local_20);
  if (local_440._0_8_ != 0) {
    local_420 = (int *)0x0;
    (**local_18)();
    auVar16._8_8_ = local_440._0_8_;
    auVar16._0_8_ = local_420;
    auVar16._16_8_ = local_440._8_8_;
    return auVar16;
  }
  if (*local_20 != 1) {
    local_440._8_8_ = runtime_newobject(&DAT_00e21740);
    *(undefined8 *)(local_440._8_8_ + 8) = 0x1a;
    *(undefined **)local_440._8_8_ = &DAT_00f294c2;
    local_420 = (int *)0x0;
    local_440._0_8_ = go_itab__errors_errorString_error;
    (**local_18)();
    auVar15._8_8_ = local_440._0_8_;
    auVar15._0_8_ = local_420;
    auVar15._16_8_ = local_440._8_8_;
    return auVar15;
  }
  local_3f0 = local_20[6];
  iVar23 = local_20[7];
  uStack_3d0 = runtime_convTstring(mv_daemon_provider_Cloud115ApiBase.str,
                                   mv_daemon_provider_Cloud115ApiBase.len);
  local_3d8 = &DAT_00dd29c0;
  uStack_3c0 = runtime_convTstring(local_3e0,uVar21);
  local_3c8 = &DAT_00dd29c0;
  uStack_3b0 = runtime_convTstring(local_20[1],local_20[2]);
  local_3b8 = &DAT_00dd29c0;
  auVar24 = fmt_Sprintf(&DAT_00f2fde5,0x1f,&local_3d8,3,3);
  auVar25 = net_http_NewRequestWithContext
                      (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_00efaba3
                       ,3,auVar24._0_8_,auVar24._8_8_,0,0);
  auVar24._8_8_ = iVar23;
  auVar24._0_8_ = local_3f0;
  if (auVar25._8_8_ == 0) {
    sVar18 = 4;
    puVar10 = local_2f8;
    do {
      puVar12 = puVar10;
      *puVar12 = in_XMM15_Qa;
      puVar12[1] = in_XMM15_Qb;
      puVar12[2] = in_XMM15_Qa;
      puVar12[3] = in_XMM15_Qb;
      puVar12[4] = in_XMM15_Qa;
      puVar12[5] = in_XMM15_Qb;
      puVar12[6] = in_XMM15_Qa;
      puVar12[7] = in_XMM15_Qb;
      sVar18 = sVar18 + -1;
      puVar10 = puVar12 + 8;
    } while (sVar18 != 0);
    puVar12[7] = in_XMM15_Qa;
    puVar12[8] = in_XMM15_Qb;
    local_2f8[0] = 0x8080808080808080;
    local_1e0 = local_2f8;
    local_430 = auVar25._0_8_;
    uStack_1e8 = runtime_rand();
    puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_1f0,&DAT_00efe659,6);
    puVar10[1] = 0x12;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar14 = *puVar10;
      puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_05 = uVar14;
    }
    *puVar10 = &DAT_00f1d949;
    puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_1f0,&DAT_00effe26,7);
    puVar10[1] = 0x13;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar14 = *puVar10;
      puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_06 = uVar14;
    }
    *puVar10 = &DAT_00f1f31d;
    auVar24 = mv_daemon_provider_get115QrUserAgent(local_3e0,uVar21,local_418,uVar22);
    local_318 = auVar24._0_8_;
    puVar10 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_1f0,&DAT_00f0a13f,10);
    puVar10[1] = auVar24._8_8_;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar14 = *puVar10;
      puVar10 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_07 = local_318;
      extraout_R11_07[1] = uVar14;
    }
    *puVar10 = local_318;
    local_3a8 = in_XMM15_Qa;
    ppcStack_3a0 = in_XMM15_Qb;
    runtime_mapIterStart(&DAT_00e16200,local_1f0);
    while (local_3a8 != (undefined8 *)0x0) {
      pcVar1 = ppcStack_3a0[1];
      local_410 = *ppcStack_3a0;
      local_320 = *(undefined8 *)(local_430 + 0x38);
      auVar24 = net_textproto_CanonicalMIMEHeaderKey(*local_3a8,local_3a8[1]);
      local_318 = auVar24._0_8_;
      puVar10 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
      puVar10[1] = pcVar1;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar10 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_10 = local_410;
      }
      *puVar10 = local_410;
      local_328 = puVar10;
      auVar24 = runtime_mapassign_faststr(&DAT_00e91b20,local_320,local_318,auVar24._8_8_);
      piVar11 = auVar24._0_8_;
      piVar11[1] = 1;
      piVar11[2] = 1;
      if (runtime_writeBarrier._0_4_ != 0) {
        piVar11 = (int *)runtime_gcWriteBarrier2(piVar11,auVar24._8_8_,*piVar11);
        *extraout_R11_11 = (int)local_328;
        extraout_R11_11[1] = extraout_RCX_02;
      }
      *piVar11 = (int)local_328;
      runtime_mapIterNext(&local_3a8);
    }
    auVar25 = net_http___Client__do(net_http_DefaultClient,local_430);
    auVar24._0_8_ = local_3f0;
    iVar20 = auVar25._0_8_;
    if (auVar25._8_8_ == 0) {
      local_308 = *(undefined8 *)(iVar20 + 0x40);
      local_300 = *(undefined8 *)(iVar20 + 0x48);
      local_310 = mv_daemon_provider___Cloud115Provider__StartQrLoginWithType_deferwrap2;
      ppcStack_10 = &local_310;
      iVar2 = *(int *)(iVar20 + 0x40);
      uVar14 = *(undefined8 *)(iVar20 + 0x48);
      uVar13 = 0;
      if (iVar2 != 0) {
        uVar19 = (uint)*(dword *)(iVar2 + 0x10);
        do {
          iVar20 = (uVar19 & *(uint *)mv_daemon_provider__typeAssert_70) * 0x10;
          if (*(int *)(mv_daemon_provider__typeAssert_70 + iVar20 + 8) == *(int *)(iVar2 + 8)) {
            uVar13 = *(undefined8 *)(mv_daemon_provider__typeAssert_70 + iVar20 + 0x10);
            goto LAB_009b9f9f;
          }
          uVar19 = uVar19 + 1;
        } while (*(int *)(mv_daemon_provider__typeAssert_70 + iVar20 + 8) != 0);
        local_318 = uVar14;
        uVar13 = runtime_typeAssert(&mv_daemon_provider__typeAssert_70,*(int *)(iVar2 + 8));
        uVar14 = local_318;
      }
LAB_009b9f9f:
      io_ReadAll(uVar13,uVar14);
      auVar24._0_8_ = local_3f0;
      auVar9._8_8_ = iVar23;
      auVar9._0_8_ = local_3f0;
      auVar8._8_8_ = iVar23;
      auVar8._0_8_ = local_3f0;
      auVar7._8_8_ = iVar23;
      auVar7._0_8_ = local_3f0;
      auVar6._8_8_ = iVar23;
      auVar6._0_8_ = local_3f0;
      auVar25._8_8_ = iVar23;
      auVar25._0_8_ = local_3f0;
      if ((((extraout_RDI == 0) && (auVar24 = auVar25, 8 < extraout_RBX_01)) &&
          (auVar24 = auVar6, *extraout_RAX_01 == -0x77)) &&
         (((auVar24 = auVar7, extraout_RAX_01[1] == 'P' &&
           (auVar24 = auVar8, extraout_RAX_01[2] == 'N')) &&
          (auVar24 = auVar9, extraout_RAX_01[3] == 'G')))) {
        auVar24 = encoding_base64___Encoding__EncodeToString
                            (encoding_base64_StdEncoding,extraout_RAX_01,extraout_RBX_01,
                             extraout_RCX_03);
        auVar24 = runtime_concatstring2(0,&DAT_00f23a5a,0x16,auVar24._0_8_,auVar24._8_8_);
      }
      bVar5 = true;
    }
    else {
      bVar5 = false;
    }
  }
  else {
    bVar5 = false;
  }
  local_3f0 = auVar24._0_8_;
  uStack_68 = runtime_convTstring(local_20[1],local_20[2]);
  local_70 = &DAT_00dd29c0;
  uStack_58 = runtime_convTstring(local_20[4],local_20[5]);
  local_60 = &DAT_00dd29c0;
  uStack_48 = runtime_convT64(local_20[3]);
  local_50 = &DAT_00dd2b80;
  uStack_38 = runtime_convTstring(local_418,uVar22);
  local_40 = &DAT_00dd29c0;
  uStack_28 = runtime_convTstring(local_3e0,uVar21);
  local_30 = &DAT_00dd29c0;
  auVar25 = fmt_Sprintf(&DAT_00f1577b,0xe,&local_70,5,5);
  local_3e8 = auVar25._0_8_;
  piVar11 = (int *)runtime_newobject(&DAT_00e69960);
  piVar11[5] = auVar25._8_8_;
  if (runtime_writeBarrier._0_4_ != 0) {
    piVar11 = (int *)runtime_gcWriteBarrier2();
    *extraout_R11_08 = local_3e8;
    extraout_R11_08[1] = local_3f0;
  }
  piVar11[4] = local_3e8;
  piVar11[3] = auVar24._8_8_;
  piVar11[2] = local_3f0;
  iVar23 = local_20[6];
  piVar11[1] = local_20[7];
  if (runtime_writeBarrier._0_4_ != 0) {
    piVar11 = (int *)runtime_gcWriteBarrier1();
    *extraout_R11_09 = extraout_RSI;
    iVar23 = extraout_RSI;
  }
  *piVar11 = iVar23;
  local_440._0_8_ = in_XMM15_Qa;
  local_440._8_8_ = in_XMM15_Qb;
  local_420 = piVar11;
  if (bVar5) {
    (**ppcStack_10)();
  }
  (**local_18)();
  auVar17._8_8_ = local_440._0_8_;
  auVar17._0_8_ = local_420;
  auVar17._16_8_ = local_440._8_8_;
  return auVar17;
}

