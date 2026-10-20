/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).PollQrLogin */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__PollQrLogin
          (undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  undefined8 uVar1;
  sdword *psVar2;
  undefined1 auVar3 [16];
  char cVar4;
  int extraout_RAX;
  int extraout_RAX_00;
  int extraout_RAX_01;
  undefined8 *puVar5;
  int *piVar6;
  int extraout_RAX_02;
  undefined8 *puVar7;
  int extraout_RAX_03;
  undefined8 extraout_RAX_04;
  undefined8 extraout_RAX_05;
  undefined8 **extraout_RAX_06;
  undefined8 uVar8;
  undefined8 uVar9;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  uint uVar20;
  uint extraout_RCX_17;
  undefined8 extraout_RCX_18;
  sdword sVar21;
  undefined1 auVar10 [24];
  undefined1 auVar11 [24];
  undefined1 auVar12 [24];
  undefined1 auVar13 [24];
  int extraout_RCX_03;
  int extraout_RCX_04;
  undefined8 extraout_RCX_05;
  int extraout_RCX_06;
  undefined8 extraout_RCX_07;
  undefined8 extraout_RCX_08;
  undefined8 extraout_RCX_09;
  undefined1 auVar14 [24];
  undefined1 auVar15 [24];
  undefined1 auVar16 [24];
  undefined8 extraout_RCX_10;
  undefined8 extraout_RCX_11;
  undefined1 auVar17 [24];
  undefined8 extraout_RCX_12;
  undefined1 auVar18 [24];
  undefined8 extraout_RCX_13;
  undefined8 extraout_RCX_14;
  undefined8 extraout_RCX_15;
  undefined8 extraout_RCX_16;
  undefined1 auVar19 [24];
  uint uVar22;
  undefined8 **ppuVar23;
  int iVar24;
  undefined8 extraout_RBX;
  int extraout_RBX_00;
  int extraout_RBX_01;
  int extraout_RBX_02;
  int extraout_RBX_03;
  undefined8 extraout_RBX_04;
  undefined *extraout_RBX_05;
  undefined *extraout_RBX_06;
  undefined8 extraout_RBX_07;
  undefined *puVar25;
  uint extraout_RBX_08;
  undefined8 extraout_RSI;
  int extraout_RDI;
  int extraout_RDI_00;
  undefined8 uVar26;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  int *extraout_R11_03;
  undefined8 *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  int *extraout_R11_07;
  undefined8 *extraout_R11_08;
  undefined8 *extraout_R11_09;
  undefined8 *extraout_R11_10;
  undefined8 *extraout_R11_11;
  undefined8 *extraout_R11_12;
  undefined8 *extraout_R11_13;
  undefined8 *extraout_R11_14;
  undefined8 *extraout_R11_15;
  undefined8 *extraout_R11_16;
  undefined8 *extraout_R11_17;
  int iVar27;
  undefined8 *extraout_R11_18;
  undefined8 *extraout_R11_19;
  undefined8 *extraout_R11_20;
  undefined8 *extraout_R11_21;
  undefined1 (*extraout_R11_22) [16];
  undefined8 *extraout_R11_23;
  int unaff_R14;
  bool bVar28;
  undefined8 *in_XMM15_Qa;
  undefined8 *in_XMM15_Qb;
  undefined1 auVar29 [16];
  undefined1 auVar30 [16];
  undefined8 uStack0000000000000010;
  int local_698;
  undefined8 local_690;
  undefined8 local_688;
  int local_680;
  undefined8 local_678;
  int local_670;
  int local_668;
  uint local_660;
  uint local_658;
  undefined8 local_650;
  undefined8 local_648;
  undefined8 local_640;
  int local_638;
  int local_630;
  int local_628;
  int local_620;
  undefined1 local_618 [24];
  code **local_600;
  undefined1 local_5e8 [24];
  code **local_5d0;
  undefined1 local_5b8 [24];
  undefined8 local_5a0;
  undefined1 local_588 [16];
  int local_578;
  int local_570;
  int local_568;
  undefined8 *local_560;
  undefined8 local_558;
  undefined8 local_550;
  undefined8 local_548;
  undefined8 local_540;
  undefined8 local_538;
  undefined8 local_530;
  int *local_528;
  undefined8 local_520;
  undefined8 local_518;
  undefined8 *local_510;
  int local_508;
  int local_500;
  undefined8 local_4f8;
  sdword *local_4f0;
  undefined8 local_4e8;
  undefined8 local_4e0;
  undefined8 local_4d8;
  undefined8 local_4d0;
  undefined8 local_4c8;
  undefined8 **local_4c0;
  undefined8 local_4b8;
  undefined8 local_4b0;
  undefined8 local_4a8;
  short *local_4a0;
  undefined8 *local_498;
  undefined8 local_490;
  undefined8 *local_488;
  undefined8 local_480;
  undefined8 *local_478;
  undefined8 *puStack_470;
  undefined8 *local_468;
  undefined8 *puStack_460;
  undefined *local_458;
  undefined8 uStack_450;
  undefined *local_448;
  undefined8 uStack_440;
  undefined *local_438;
  undefined8 uStack_430;
  undefined *local_428;
  undefined8 uStack_420;
  undefined *local_418;
  undefined8 uStack_410;
  code *local_408;
  undefined8 local_400;
  undefined8 local_3f8;
  undefined8 local_3f0 [33];
  undefined1 local_2e8 [8];
  undefined8 uStack_2e0;
  undefined8 *local_2d8;
  undefined8 local_2b8 [41];
  undefined1 local_170 [8];
  undefined8 uStack_168;
  undefined8 *local_160;
  code *local_140;
  undefined8 local_138;
  undefined8 local_130;
  code *local_128;
  undefined *local_120;
  undefined8 local_118;
  undefined **local_110;
  undefined8 local_108;
  undefined8 local_100;
  undefined8 *local_f8;
  undefined8 *puStack_f0;
  undefined *local_98;
  undefined8 uStack_90;
  uint8 *local_88;
  int iStack_80;
  undefined *local_78;
  undefined8 uStack_70;
  undefined8 local_68;
  undefined8 uStack_60;
  undefined *local_58;
  undefined8 uStack_50;
  undefined8 local_48;
  undefined8 uStack_40;
  undefined *local_38;
  undefined8 uStack_30;
  undefined8 local_28;
  undefined8 uStack_20;
  int *local_18;
  int local_10;
  
  uStack0000000000000010 = param_2;
  while (&local_698 <= *(int **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_560 = (undefined8 *)0x0;
  auVar29 = strings_genSplit(uStack0000000000000010,param_3,&DAT_01133218,1,0,0xffffffffffffffff);
  puVar5 = auVar29._0_8_;
  if (auVar29._8_8_ < 4) {
    local_588._8_8_ = runtime_newobject(&DAT_00e21740);
    *(undefined8 *)(local_588._8_8_ + 8) = 0x10;
    *(undefined **)local_588._8_8_ = &DAT_00f197ec;
    local_560 = (undefined8 *)0x0;
    local_588._0_8_ = go_itab__errors_errorString_error;
    runtime_deferreturn();
    auVar13._8_8_ = local_588._0_8_;
    auVar13._0_8_ = local_560;
    auVar13._16_8_ = local_588._8_8_;
    return auVar13;
  }
  uVar26 = puVar5[1];
  local_548 = *puVar5;
  local_690 = puVar5[3];
  local_520 = puVar5[2];
  uVar8 = puVar5[5];
  local_540 = puVar5[4];
  uVar1 = puVar5[7];
  local_558 = puVar5[6];
  if (auVar29._8_8_ < 5) {
    local_4a0 = (short *)&DAT_00efac72;
    local_638 = 3;
  }
  else {
    local_638 = puVar5[9];
    if (local_638 == 0) {
      local_4a0 = (short *)&DAT_00efac72;
      local_638 = 3;
    }
    else {
      local_4a0 = (short *)puVar5[8];
    }
  }
  context_WithTimeout(go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,30000000000);
  local_668 = extraout_RAX;
  local_5a0 = extraout_RCX;
  local_4c8 = extraout_RBX;
  runtime_deferprocStack(local_5b8);
  iStack_80 = mv_daemon_provider_Cloud115ApiBase.len;
  local_88 = mv_daemon_provider_Cloud115ApiBase.str;
  uStack_70 = 0x11;
  local_78 = &DAT_00f1b45b;
  local_68 = local_548;
  uStack_50 = 6;
  local_58 = &DAT_00efe6ef;
  uStack_40 = local_690;
  local_48 = local_520;
  uStack_30 = 6;
  local_38 = &DAT_00efe6f5;
  local_28 = local_540;
  uStack_60 = uVar26;
  uStack_20 = uVar8;
  auVar29 = runtime_concatstrings(0,&local_88,7,7);
  net_http_NewRequestWithContext
            (local_668,local_4c8,&DAT_00efaba3,3,auVar29._0_8_,auVar29._8_8_,0,0);
  if (extraout_RBX_00 != 0) {
    local_560 = (undefined8 *)0x0;
    local_588._0_8_ = extraout_RBX_00;
    local_588._8_8_ = extraout_RCX_00;
    runtime_deferreturn();
    auVar12._8_8_ = local_588._0_8_;
    auVar12._0_8_ = local_560;
    auVar12._16_8_ = local_588._8_8_;
    return auVar12;
  }
  local_4d8 = *(undefined8 *)(extraout_RAX_00 + 0x38);
  local_500 = extraout_RAX_00;
  auVar29 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f0a13f,10);
  local_620 = auVar29._8_8_;
  local_480 = auVar29._0_8_;
  local_488 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_488[1] = 0xc;
  *local_488 = &DAT_00f11043;
  auVar29 = runtime_mapassign_faststr(&DAT_00e91b20,local_4d8,local_480,local_620);
  puVar5 = auVar29._0_8_;
  puVar5[1] = 1;
  puVar5[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
    *extraout_R11 = local_488;
    extraout_R11[1] = extraout_RCX_01;
  }
  *puVar5 = local_488;
  net_http___Client__do(net_http_DefaultClient,local_500);
  if (extraout_RBX_01 != 0) {
    local_670 = extraout_RBX_01;
    local_4d0 = extraout_RCX_02;
    auVar29 = (**(code **)(local_668 + 0x28))(local_4c8);
    cVar4 = errors_Is(auVar29._0_8_,auVar29._8_8_,context_DeadlineExceeded.tab,
                      context_DeadlineExceeded.data);
    if (cVar4 == '\0') {
      local_560 = (undefined8 *)0x0;
      local_588._0_8_ = local_670;
      local_588._8_8_ = local_4d0;
      runtime_deferreturn();
      auVar11._8_8_ = local_588._0_8_;
      auVar11._0_8_ = local_560;
      auVar11._16_8_ = local_588._8_8_;
      return auVar11;
    }
    local_560 = (undefined8 *)runtime_newobject(&DAT_00e836e0);
    local_560[1] = 7;
    *local_560 = &DAT_00effe11;
    local_588._0_8_ = in_XMM15_Qa;
    local_588._8_8_ = in_XMM15_Qb;
    runtime_deferreturn();
    auVar10._8_8_ = local_588._0_8_;
    auVar10._0_8_ = local_560;
    auVar10._16_8_ = local_588._8_8_;
    return auVar10;
  }
  local_138 = *(undefined8 *)(extraout_RAX_01 + 0x40);
  local_130 = *(undefined8 *)(extraout_RAX_01 + 0x48);
  local_140 = mv_daemon_provider___Cloud115Provider__PollQrLogin_deferwrap1;
  local_5d0 = &local_140;
  local_568 = extraout_RAX_01;
  runtime_deferprocStack(local_5e8);
  local_18 = (int *)runtime_newobject(&DAT_00e0fd80);
  iVar27 = *(int *)(local_568 + 0x40);
  local_4f8 = *(undefined8 *)(local_568 + 0x48);
  uVar9 = 0;
  if (iVar27 != 0) {
    uVar20 = (uint)*(dword *)(iVar27 + 0x10);
    do {
      iVar24 = (uVar20 & *(uint *)mv_daemon_provider__typeAssert_71) * 0x10;
      if (*(int *)(mv_daemon_provider__typeAssert_71 + iVar24 + 8) == *(int *)(iVar27 + 8)) {
        uVar9 = *(undefined8 *)(mv_daemon_provider__typeAssert_71 + iVar24 + 0x10);
        goto LAB_009ba795;
      }
      uVar20 = uVar20 + 1;
    } while (*(int *)(mv_daemon_provider__typeAssert_71 + iVar24 + 8) != 0);
    uVar9 = runtime_typeAssert(&mv_daemon_provider__typeAssert_71);
  }
LAB_009ba795:
  local_480 = uVar9;
  puVar5 = (undefined8 *)runtime_newobject(&DAT_00eba560);
  *puVar5 = local_480;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = local_4f8;
  }
  puVar5[1] = local_4f8;
  local_588 = encoding_json___Decoder__Decode(puVar5,&DAT_00dc4ae0,local_18);
  if (local_588._0_8_ != 0) {
    local_560 = (undefined8 *)0x0;
    runtime_deferreturn();
    auVar15._8_8_ = local_588._0_8_;
    auVar15._0_8_ = local_560;
    auVar15._16_8_ = local_588._8_8_;
    return auVar15;
  }
  iVar27 = *local_18;
  if (iVar27 == 1) {
    local_698 = 7;
    local_528 = &DAT_00f0010c;
  }
  else if (iVar27 == 2) {
    local_698 = 9;
    local_528 = &DAT_00f059ff;
  }
  else {
    if (iVar27 == -1) {
      local_528 = (int *)((int)&DAT_00f0010c + 7);
    }
    else {
      local_528 = &DAT_00effe11;
    }
    local_698 = 7;
  }
  puVar5 = (undefined8 *)runtime_newobject(&DAT_00e836e0);
  puVar5[1] = local_698;
  iVar27 = local_698;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_01 = local_528;
    iVar27 = extraout_RCX_03;
  }
  *puVar5 = local_528;
  if (((iVar27 == 9) && (*local_528 == 0x656d7269666e6f63)) && ((char)local_528[1] == 'd')) {
    local_510 = puVar5;
    uStack_90 = runtime_convTstring(local_4a0,local_638);
    local_98 = &DAT_00dd29c0;
    auVar29 = fmt_Sprintf(&DAT_00f4aa63,0x37,&local_98,1,1);
    local_650 = auVar29._8_8_;
    local_4b0 = auVar29._0_8_;
    sVar21 = 5;
    puVar5 = local_2b8;
    do {
      puVar7 = puVar5;
      *puVar7 = in_XMM15_Qa;
      puVar7[1] = in_XMM15_Qb;
      puVar7[2] = in_XMM15_Qa;
      puVar7[3] = in_XMM15_Qb;
      puVar7[4] = in_XMM15_Qa;
      puVar7[5] = in_XMM15_Qb;
      puVar7[6] = in_XMM15_Qa;
      puVar7[7] = in_XMM15_Qb;
      sVar21 = sVar21 + -1;
      puVar5 = puVar7 + 8;
    } while (sVar21 != 0);
    puVar7[7] = in_XMM15_Qa;
    puVar7[8] = in_XMM15_Qb;
    local_2b8[0] = 0x8080808080808080;
    local_160 = local_2b8;
    uStack_168 = runtime_rand();
    puVar5 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
    puVar5[1] = uVar26;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_02 = local_548;
    }
    *puVar5 = local_548;
    local_488 = puVar5;
    auVar29 = runtime_mapassign_faststr(&DAT_00e9bd40,local_170,&DAT_00f00144,7);
    piVar6 = auVar29._0_8_;
    piVar6[1] = 1;
    piVar6[2] = 1;
    if (runtime_writeBarrier._0_4_ != 0) {
      piVar6 = (int *)runtime_gcWriteBarrier2(piVar6,auVar29._8_8_,*piVar6);
      *extraout_R11_03 = (int)local_488;
      extraout_R11_03[1] = extraout_RCX_04;
    }
    *piVar6 = (int)local_488;
    puVar5 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
    puVar5[1] = local_638;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_04 = local_4a0;
    }
    *puVar5 = local_4a0;
    local_488 = puVar5;
    auVar29 = runtime_mapassign_faststr(&DAT_00e9bd40,local_170,&DAT_00efacc3,3);
    puVar5 = auVar29._0_8_;
    puVar5[1] = 1;
    puVar5[2] = 1;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
      *extraout_R11_05 = local_488;
      extraout_R11_05[1] = extraout_RCX_05;
    }
    *puVar5 = local_488;
    if (((local_638 == 3) && (*local_4a0 == 0x6577)) && ((char)local_4a0[1] == 'b')) {
      puVar5 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
      puVar5[1] = local_690;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_06 = local_520;
      }
      *puVar5 = local_520;
      local_488 = puVar5;
      auVar29 = runtime_mapassign_faststr(&DAT_00e9bd40,local_170,&DAT_00efb6ef,4);
      piVar6 = auVar29._0_8_;
      piVar6[1] = 1;
      piVar6[2] = 1;
      if (runtime_writeBarrier._0_4_ != 0) {
        piVar6 = (int *)runtime_gcWriteBarrier2(piVar6,auVar29._8_8_,*piVar6);
        *extraout_R11_07 = (int)local_488;
        extraout_R11_07[1] = extraout_RCX_06;
      }
      *piVar6 = (int)local_488;
      puVar5 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
      puVar5[1] = uVar8;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_08 = local_540;
      }
      *puVar5 = local_540;
      local_488 = puVar5;
      auVar29 = runtime_mapassign_faststr(&DAT_00e9bd40,local_170,&DAT_00efb6c7,4);
      puVar5 = auVar29._0_8_;
      puVar5[1] = 1;
      puVar5[2] = 1;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
        *extraout_R11_09 = local_488;
        extraout_R11_09[1] = extraout_RCX_07;
      }
      *puVar5 = local_488;
    }
    auVar29 = net_url_Values_Encode(local_170);
    local_688 = auVar29._8_8_;
    local_518 = auVar29._0_8_;
    puVar5 = (undefined8 *)runtime_newobject(&DAT_00e694e0);
    puVar5[1] = local_688;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_10 = local_518;
    }
    *puVar5 = local_518;
    puVar5[2] = 0;
    puVar5[3] = 0xffffffffffffffff;
    net_http_NewRequestWithContext
              (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_00efb573,4,
               local_4b0,local_650,go_itab__strings_Reader_io_Reader,puVar5);
    if (extraout_RBX_02 != 0) {
      local_560 = (undefined8 *)0x0;
      local_588._0_8_ = extraout_RBX_02;
      local_588._8_8_ = extraout_RCX_08;
      runtime_deferreturn();
      auVar14._8_8_ = local_588._0_8_;
      auVar14._0_8_ = local_560;
      auVar14._16_8_ = local_588._8_8_;
      return auVar14;
    }
    local_4e0 = *(undefined8 *)(extraout_RAX_02 + 0x38);
    local_508 = extraout_RAX_02;
    auVar29 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
    local_620 = auVar29._8_8_;
    local_480 = auVar29._0_8_;
    local_488 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
    local_488[1] = 0x21;
    *local_488 = &DAT_00f326ad;
    auVar29 = runtime_mapassign_faststr(&DAT_00e91b20,local_4e0,local_480,local_620);
    puVar5 = auVar29._0_8_;
    puVar5[1] = 1;
    puVar5[2] = 1;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
      *extraout_R11_11 = local_488;
      extraout_R11_11[1] = extraout_RCX_09;
    }
    *puVar5 = local_488;
    sVar21 = 4;
    puVar5 = local_3f0;
    do {
      puVar7 = puVar5;
      *puVar7 = in_XMM15_Qa;
      puVar7[1] = in_XMM15_Qb;
      puVar7[2] = in_XMM15_Qa;
      puVar7[3] = in_XMM15_Qb;
      puVar7[4] = in_XMM15_Qa;
      puVar7[5] = in_XMM15_Qb;
      puVar7[6] = in_XMM15_Qa;
      puVar7[7] = in_XMM15_Qb;
      sVar21 = sVar21 + -1;
      puVar5 = puVar7 + 8;
    } while (sVar21 != 0);
    puVar7[7] = in_XMM15_Qa;
    puVar7[8] = in_XMM15_Qb;
    local_3f0[0] = 0x8080808080808080;
    local_2d8 = local_3f0;
    uStack_2e0 = runtime_rand();
    puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_2e8,&DAT_00efe659,6);
    puVar5[1] = 0x12;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar26 = *puVar5;
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_12 = uVar26;
    }
    *puVar5 = &DAT_00f1d949;
    puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_2e8,&DAT_00effe26,7);
    puVar5[1] = 0x13;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar26 = *puVar5;
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_13 = uVar26;
    }
    *puVar5 = &DAT_00f1f31d;
    auVar29 = mv_daemon_provider_get115QrUserAgent(local_4a0,local_638,local_558,uVar1);
    local_620 = auVar29._8_8_;
    local_480 = auVar29._0_8_;
    puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_2e8,&DAT_00f0a13f,10);
    puVar5[1] = local_620;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar26 = *puVar5;
      puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_14 = local_480;
      extraout_R11_14[1] = uVar26;
    }
    *puVar5 = local_480;
    local_f8 = in_XMM15_Qa;
    puStack_f0 = in_XMM15_Qb;
    runtime_mapIterStart(&DAT_00e16200,local_2e8);
    while (local_f8 != (undefined8 *)0x0) {
      uVar26 = puStack_f0[1];
      local_550 = *puStack_f0;
      local_490 = *(undefined8 *)(local_508 + 0x38);
      auVar29 = net_textproto_CanonicalMIMEHeaderKey(*local_f8,local_f8[1]);
      local_620 = auVar29._8_8_;
      local_480 = auVar29._0_8_;
      puVar5 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
      puVar5[1] = uVar26;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_15 = local_550;
      }
      *puVar5 = local_550;
      local_488 = puVar5;
      auVar29 = runtime_mapassign_faststr(&DAT_00e91b20,local_490,local_480,local_620);
      puVar5 = auVar29._0_8_;
      puVar5[1] = 1;
      puVar5[2] = 1;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
        *extraout_R11_16 = local_488;
        extraout_R11_16[1] = extraout_RCX_10;
      }
      *puVar5 = local_488;
      runtime_mapIterNext(&local_f8);
    }
    net_http___Client__do(net_http_DefaultClient,local_508);
    if (extraout_RBX_03 != 0) {
      local_560 = (undefined8 *)0x0;
      local_588._0_8_ = extraout_RBX_03;
      local_588._8_8_ = extraout_RCX_11;
      runtime_deferreturn();
      auVar17._8_8_ = local_588._0_8_;
      auVar17._0_8_ = local_560;
      auVar17._16_8_ = local_588._8_8_;
      return auVar17;
    }
    local_400 = *(undefined8 *)(extraout_RAX_03 + 0x40);
    local_3f8 = *(undefined8 *)(extraout_RAX_03 + 0x48);
    local_408 = mv_daemon_provider___Cloud115Provider__PollQrLogin_deferwrap2;
    local_600 = &local_408;
    local_570 = extraout_RAX_03;
    runtime_deferprocStack(local_618);
    iVar27 = *(int *)(local_570 + 0x40);
    uVar26 = *(undefined8 *)(local_570 + 0x48);
    uVar8 = 0;
    if (iVar27 != 0) {
      uVar20 = (uint)*(dword *)(iVar27 + 0x10);
      do {
        iVar24 = (uVar20 & *(uint *)mv_daemon_provider__typeAssert_72) * 0x10;
        if (*(int *)(mv_daemon_provider__typeAssert_72 + iVar24 + 8) == *(int *)(iVar27 + 8)) {
          uVar8 = *(undefined8 *)(mv_daemon_provider__typeAssert_72 + iVar24 + 0x10);
          goto LAB_009bb261;
        }
        uVar20 = uVar20 + 1;
      } while (*(int *)(mv_daemon_provider__typeAssert_72 + iVar24 + 8) != 0);
      local_480 = uVar26;
      uVar8 = runtime_typeAssert(&mv_daemon_provider__typeAssert_72,*(int *)(iVar27 + 8));
      uVar26 = local_480;
    }
LAB_009bb261:
    io_ReadAll(uVar8,uVar26);
    if (extraout_RDI != 0) {
      local_560 = (undefined8 *)0x0;
      local_588._0_8_ = extraout_RDI;
      local_588._8_8_ = extraout_RSI;
      runtime_deferreturn();
      auVar18._8_8_ = local_588._0_8_;
      auVar18._0_8_ = local_560;
      auVar18._16_8_ = local_588._8_8_;
      return auVar18;
    }
    local_648 = extraout_RBX_04;
    local_640 = extraout_RCX_12;
    local_4a8 = extraout_RAX_04;
    local_10 = runtime_newobject(&DAT_00e7aa80);
    auVar29 = encoding_json_Unmarshal(local_4a8,local_648,local_640,&DAT_00dc6420,local_10);
    if (auVar29._0_8_ != 0) {
      local_428 = *(undefined **)(auVar29._0_8_ + 8);
      uStack_420 = auVar29._8_8_;
      runtime_slicebytetostring(0,local_4a8,local_648);
      uStack_410 = runtime_convTstring();
      local_418 = &DAT_00dd29c0;
      local_128 = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func1;
      local_118 = 0x42;
      local_120 = &DAT_00f51f05;
      local_108 = 2;
      local_100 = 2;
      local_110 = &local_428;
      log___Logger__output(log_std,0,2,&local_128);
    }
    if (*(int *)(local_10 + 0x20) != 0) {
      uStack_430 = runtime_convTstring(*(undefined8 *)(local_10 + 0x18),
                                       *(undefined8 *)(local_10 + 0x20));
      local_438 = &DAT_00dd29c0;
      local_128 = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func2;
      local_118 = 0x34;
      local_120 = &DAT_00f481d0;
      local_108 = 1;
      local_100 = 1;
      local_110 = &local_438;
      log___Logger__output(log_std,0,2,&local_128);
    }
    local_4b8 = runtime_makemap_small();
    auVar29 = net_http_readSetCookies(*(undefined8 *)(local_570 + 0x38));
    iVar27 = auVar29._0_8_;
    local_578 = iVar27;
    for (iVar24 = 0; iVar24 < auVar29._8_8_; iVar24 = iVar24 + 1) {
      puVar5 = *(undefined8 **)(iVar27 + iVar24 * 8);
      if ((puVar5[1] != 0) && (puVar5[3] != 0)) {
        local_480 = puVar5[2];
        local_628 = iVar24;
        local_620 = puVar5[3];
        puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,local_4b8,*puVar5);
        puVar5[1] = local_620;
        if (runtime_writeBarrier._0_4_ != 0) {
          uVar26 = *puVar5;
          puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
          *extraout_R11_17 = local_480;
          extraout_R11_17[1] = uVar26;
        }
        *puVar5 = local_480;
        iVar27 = local_578;
        iVar24 = local_628;
      }
    }
    if (*(int *)(local_10 + 0x28) != 0) {
      puVar5 = (undefined8 *)
               runtime_mapaccess1_faststr(&DAT_00e16300,*(int *)(local_10 + 0x28),&DAT_00efe407,6);
      if ((undefined *)*puVar5 == &DAT_00e16300) {
        local_f8 = in_XMM15_Qa;
        puStack_f0 = in_XMM15_Qb;
        runtime_mapIterStart(&DAT_00e16300,puVar5[1]);
        while (local_f8 != (undefined8 *)0x0) {
          puVar25 = (undefined *)*puStack_f0;
          puVar5 = (undefined8 *)puStack_f0[1];
          if (puVar25 != &DAT_00dd29c0) {
            iVar27 = 0;
            uVar26 = 0;
          }
          else {
            uVar26 = *puVar5;
            iVar27 = puVar5[1];
          }
          if ((puVar25 != &DAT_00dd29c0) || (iVar27 == 0)) {
            if (puVar25 == &DAT_00dd2d80) {
              local_678 = local_f8[1];
              local_4e8 = *local_f8;
              uStack_90 = runtime_convT64(*puVar5);
              local_98 = &DAT_00dd2d80;
              auVar29 = fmt_Sprintf(&DAT_00efb6ab,4,&local_98,1,1);
              local_620 = auVar29._8_8_;
              local_480 = auVar29._0_8_;
              auVar29 = runtime_mapassign_faststr(&DAT_00e16200,local_4b8,local_4e8,local_678);
              puVar5 = auVar29._0_8_;
              puVar5[1] = local_620;
              if (runtime_writeBarrier._0_4_ != 0) {
                puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
                *extraout_R11_19 = local_480;
                extraout_R11_19[1] = extraout_RCX_14;
              }
              *puVar5 = local_480;
            }
          }
          else {
            local_530 = uVar26;
            auVar29 = runtime_mapassign_faststr(&DAT_00e16200,local_4b8);
            puVar5 = auVar29._0_8_;
            puVar5[1] = iVar27;
            if (runtime_writeBarrier._0_4_ != 0) {
              puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
              *extraout_R11_18 = local_530;
              extraout_R11_18[1] = extraout_RCX_13;
            }
            *puVar5 = local_530;
          }
          runtime_mapIterNext(&local_f8);
        }
      }
      local_f8 = in_XMM15_Qa;
      puStack_f0 = in_XMM15_Qb;
      runtime_mapIterStart(&DAT_00e16300,*(undefined8 *)(local_10 + 0x28));
      puVar25 = extraout_RBX_05;
      while (local_f8 != (undefined8 *)0x0) {
        psVar2 = (sdword *)*local_f8;
        if (((local_f8[1] != 6) || (*psVar2 != 0x6b6f6f63)) || ((short)psVar2[1] != 0x6569)) {
          puVar5 = (undefined8 *)puStack_f0[1];
          if ((undefined *)*puStack_f0 == &DAT_00dd29c0) {
            iVar27 = puVar5[1];
            if (iVar27 != 0) {
              local_538 = *puVar5;
              auVar29 = runtime_mapassign_faststr(&DAT_00e16200,local_4b8);
              puVar5 = auVar29._0_8_;
              puVar5[1] = iVar27;
              if (runtime_writeBarrier._0_4_ != 0) {
                runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
                auVar29._8_8_ = extraout_RBX_07;
                auVar29._0_8_ = extraout_RAX_05;
                *extraout_R11_20 = local_538;
                extraout_R11_20[1] = extraout_RCX_15;
              }
              puVar25 = auVar29._8_8_;
              *auVar29._0_8_ = local_538;
              goto LAB_009bb7ec;
            }
          }
          puVar25 = &DAT_00dd2d80;
          if ((undefined *)*puStack_f0 == &DAT_00dd2d80) {
            local_680 = local_f8[1];
            local_4f0 = psVar2;
            uStack_90 = runtime_convT64(*puVar5);
            local_98 = &DAT_00dd2d80;
            auVar29 = fmt_Sprintf(&DAT_00efb6ab,4,&local_98,1,1);
            local_620 = auVar29._8_8_;
            local_480 = auVar29._0_8_;
            auVar29 = runtime_mapassign_faststr(&DAT_00e16200,local_4b8,local_4f0,local_680);
            puVar5 = auVar29._0_8_;
            puVar5[1] = local_620;
            if (runtime_writeBarrier._0_4_ != 0) {
              puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar29._8_8_,*puVar5);
              *extraout_R11_21 = local_480;
              extraout_R11_21[1] = extraout_RCX_16;
            }
            *puVar5 = local_480;
            puVar25 = &DAT_00dd2d80;
          }
        }
LAB_009bb7ec:
        runtime_mapIterNext(&local_f8,puVar25);
        puVar25 = extraout_RBX_06;
      }
    }
    local_f8 = in_XMM15_Qa;
    puStack_f0 = in_XMM15_Qb;
    runtime_mapIterStart(&DAT_00e16200,local_4b8);
    while (bVar28 = true, local_f8 != (undefined8 *)0x0) {
      local_498 = local_f8;
      local_630 = puStack_f0[1];
      auVar29 = strings_ToUpper(*local_f8,local_f8[1]);
      iVar27 = auVar29._8_8_;
      piVar6 = auVar29._0_8_;
      if (((((iVar27 == 3) &&
            ((((short)*piVar6 == 0x4955 && (*(char *)((int)piVar6 + 2) == 'D')) ||
             (((short)*piVar6 == 0x4943 && (*(char *)((int)piVar6 + 2) == 'D')))))) ||
           ((iVar27 == 4 && ((sdword)*piVar6 == 0x44494553)))) ||
          ((iVar27 == 0xb &&
           (((*piVar6 == 0x524553555f353131 && ((short)piVar6[1] == 0x495f)) &&
            (*(char *)((int)piVar6 + 10) == 'D')))))) && (local_630 != 0)) {
        bVar28 = local_498 == (undefined8 *)0x0;
        break;
      }
      runtime_mapIterNext(&local_f8);
    }
    if (bVar28) {
      local_458 = &DAT_00e16200;
      uStack_450 = local_4b8;
      runtime_slicebytetostring(0,local_4a8,local_648);
      uStack_440 = runtime_convTstring();
      local_448 = &DAT_00dd29c0;
      local_128 = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func3;
      local_118 = 0x66;
      local_120 = &DAT_00f6024a;
      local_108 = 2;
      local_100 = 2;
      local_110 = &local_458;
      log___Logger__output(log_std,0,2,&local_128);
      local_588 = fmt_errorf(&DAT_00f57aa1,0x4d,0,0,0);
      if (local_588._0_8_ == 0) {
        puVar5 = (undefined8 *)runtime_newobject(&DAT_00e21740);
        puVar5[1] = 0x4d;
        *puVar5 = &DAT_00f57aa1;
        local_588._8_8_ = puVar5;
        local_588._0_8_ = go_itab__errors_errorString_error;
      }
      local_560 = (undefined8 *)0x0;
      runtime_deferreturn();
      auVar19._8_8_ = local_588._0_8_;
      auVar19._0_8_ = local_560;
      auVar19._16_8_ = local_588._8_8_;
      return auVar19;
    }
    local_f8 = in_XMM15_Qa;
    puStack_f0 = in_XMM15_Qb;
    runtime_mapIterStart(&DAT_00e16200,local_4b8);
    bVar28 = false;
    uVar20 = 0;
    uVar22 = 0;
    ppuVar23 = (undefined8 **)0x0;
    while (local_f8 != (undefined8 *)0x0) {
      local_660 = uVar22;
      local_658 = uVar20;
      local_4c0 = ppuVar23;
      auVar30 = runtime_concatstring3
                          (0,*local_f8,local_f8[1],&DAT_011331e0,1,*puStack_f0,puStack_f0[1]);
      auVar3._8_8_ = local_620;
      auVar3._0_8_ = local_480;
      local_620 = auVar30._8_8_;
      local_480 = auVar30._0_8_;
      uVar20 = local_660 + 1;
      ppuVar23 = local_4c0;
      if (local_658 < uVar20) {
        if (((2 < (int)uVar20) || (bVar28)) || (local_660 != 0)) {
          runtime_growslice(local_4c0,uVar20,local_658,1,&DAT_00dd29c0);
          auVar30._8_8_ = local_620;
          auVar30._0_8_ = local_480;
          local_658 = extraout_RCX_17;
          ppuVar23 = extraout_RAX_06;
          uVar20 = extraout_RBX_08;
          auVar3 = auVar30;
        }
        else {
          local_478 = in_XMM15_Qa;
          puStack_470 = in_XMM15_Qb;
          local_468 = in_XMM15_Qa;
          puStack_460 = in_XMM15_Qb;
          local_658 = 2;
          bVar28 = true;
          ppuVar23 = &local_478;
          auVar3 = auVar30;
        }
      }
      local_620 = auVar3._8_8_;
      local_480 = auVar3._0_8_;
      uVar26 = auVar30._0_8_;
      iVar27 = uVar20 - 1;
      iVar24 = iVar27 * 0x10;
      ppuVar23[iVar27 * 2 + 1] = auVar30._8_8_;
      local_660 = uVar20;
      if (runtime_writeBarrier._0_4_ != 0) {
        auVar29 = runtime_gcWriteBarrier2(uVar26,ppuVar23[iVar27 * 2]);
        auVar3._8_8_ = local_620;
        auVar3._0_8_ = local_480;
        uVar26 = auVar29._0_8_;
        *extraout_R11_22 = auVar29;
        iVar24 = extraout_RDI_00;
      }
      local_620 = auVar3._8_8_;
      local_480 = auVar3._0_8_;
      *(undefined8 *)((int)ppuVar23 + iVar24) = uVar26;
      local_4c0 = ppuVar23;
      runtime_mapIterNext(&local_f8);
      uVar20 = local_658;
      uVar22 = local_660;
      ppuVar23 = local_4c0;
    }
    auVar29 = strings_Join(ppuVar23,uVar22,uVar20,&DAT_00efa6fc,2);
    puVar5 = local_510;
    uVar26 = auVar29._0_8_;
    local_510[3] = auVar29._8_8_;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar26 = runtime_gcWriteBarrier2(uVar26,auVar29._8_8_,local_510[2]);
      *extraout_R11_23 = uVar26;
      extraout_R11_23[1] = extraout_RCX_18;
    }
    puVar5[2] = uVar26;
  }
  local_588._0_8_ = in_XMM15_Qa;
  local_588._8_8_ = in_XMM15_Qb;
  local_560 = puVar5;
  runtime_deferreturn();
  auVar16._8_8_ = local_588._0_8_;
  auVar16._0_8_ = local_560;
  auVar16._16_8_ = local_588._8_8_;
  return auVar16;
}

