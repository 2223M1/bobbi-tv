/* Reconstructed pseudocode, not original Go source: main.handle115OfflineStatus */

void main_handle115OfflineStatus(int param_1,undefined8 param_2,int param_3)

{
  byte bVar1;
  undefined1 auVar2 [16];
  undefined1 auVar3 [16];
  uint uVar4;
  undefined8 uVar5;
  int *piVar6;
  undefined8 uVar7;
  undefined8 *extraout_RAX;
  byte *pbVar8;
  undefined8 *puVar9;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 *puVar10;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 extraout_RCX_05;
  undefined8 extraout_RCX_06;
  undefined8 extraout_RCX_07;
  undefined8 extraout_RCX_08;
  undefined8 extraout_RCX_09;
  undefined8 extraout_RCX_10;
  undefined8 extraout_RCX_11;
  undefined8 extraout_RCX_12;
  undefined8 extraout_RCX_13;
  undefined8 extraout_RCX_14;
  undefined8 extraout_RCX_15;
  undefined8 extraout_RCX_16;
  undefined8 extraout_RCX_17;
  undefined8 extraout_RCX_18;
  undefined8 extraout_RCX_19;
  undefined8 extraout_RCX_20;
  undefined8 extraout_RCX_21;
  undefined8 extraout_RCX_22;
  sdword sVar11;
  uint uVar12;
  char extraout_BL;
  int extraout_RBX;
  undefined8 extraout_RSI;
  undefined8 extraout_RSI_00;
  undefined8 extraout_RSI_01;
  int extraout_RSI_02;
  undefined8 extraout_RSI_03;
  int extraout_RDI;
  int iVar13;
  int extraout_R8;
  int iVar14;
  undefined8 extraout_R8_00;
  int iVar15;
  undefined8 extraout_R9;
  uint uVar16;
  uint extraout_R9_00;
  undefined8 extraout_R10;
  undefined8 extraout_R10_00;
  int extraout_R10_01;
  int iVar17;
  undefined8 extraout_R10_02;
  undefined8 *extraout_R11;
  undefined8 extraout_R11_00;
  undefined8 extraout_R11_01;
  undefined8 uVar18;
  undefined8 *extraout_R11_02;
  undefined8 extraout_R11_03;
  undefined8 *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  undefined8 *extraout_R11_07;
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
  undefined8 *extraout_R11_18;
  undefined8 *extraout_R11_19;
  undefined8 *extraout_R11_20;
  undefined8 *extraout_R11_21;
  undefined8 *extraout_R11_22;
  undefined8 *extraout_R11_23;
  undefined8 *extraout_R11_24;
  undefined8 *extraout_R11_25;
  undefined8 *extraout_R11_26;
  undefined8 *extraout_R11_27;
  undefined8 *extraout_R11_28;
  undefined8 *extraout_R11_29;
  undefined8 *extraout_R11_30;
  undefined8 *extraout_R11_31;
  undefined8 *extraout_R11_32;
  undefined8 *extraout_R11_33;
  undefined8 *extraout_R11_34;
  undefined8 *extraout_R11_35;
  undefined8 *extraout_R11_36;
  undefined8 *extraout_R11_37;
  undefined8 *extraout_R11_38;
  undefined8 *extraout_R11_39;
  undefined8 *extraout_R11_40;
  undefined8 *extraout_R11_41;
  undefined8 *extraout_R11_42;
  undefined8 *extraout_R11_43;
  undefined8 *extraout_R11_44;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar19 [16];
  undefined1 auVar20 [16];
  undefined1 auVar21 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_308;
  undefined8 local_300;
  int local_2f8;
  int local_2f0;
  int local_2e8;
  int local_2e0;
  int local_2d8;
  int local_2d0;
  undefined8 local_2c8;
  uint local_2c0;
  uint local_2b8;
  undefined8 local_2b0;
  undefined8 local_2a8;
  undefined8 local_2a0;
  undefined8 local_298;
  undefined8 *local_290;
  uint local_288;
  undefined8 local_280;
  undefined8 local_278;
  undefined8 local_270;
  undefined8 local_268;
  undefined8 local_260;
  int local_258;
  undefined8 local_250;
  undefined8 local_248;
  undefined8 local_240;
  undefined8 local_238;
  undefined8 local_230;
  int local_228;
  undefined8 local_220;
  undefined8 local_218;
  undefined8 local_210;
  undefined8 local_208;
  undefined8 *local_200;
  undefined1 *local_1f8;
  undefined8 local_1f0;
  undefined8 uStack_1e8;
  undefined1 local_1d0;
  undefined7 uStack_1cf;
  undefined8 local_190;
  undefined8 uStack_188;
  undefined1 local_170;
  undefined7 uStack_16f;
  undefined8 local_130;
  undefined8 uStack_128;
  undefined8 local_120;
  undefined8 uStack_118;
  undefined8 local_110;
  undefined8 uStack_108;
  undefined8 local_100;
  undefined8 uStack_f8;
  undefined8 local_d0;
  int local_c8;
  undefined8 local_c0;
  undefined8 local_b8;
  undefined8 uStack_b0;
  int local_a8;
  int local_a0;
  undefined1 local_98;
  uint local_90;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  int local_70;
  undefined8 local_68;
  undefined8 uStack_60;
  undefined1 local_48;
  undefined7 uStack_47;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_308 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_238 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar19 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_2b8 = auVar19._8_8_;
  local_1f8 = auVar19._0_8_;
  local_200 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_200[1] = 0x10;
  *local_200 = &DAT_00f195fc;
  auVar19 = runtime_mapassign_faststr(&DAT_00e91b20,local_238,local_1f8,local_2b8);
  puVar9 = auVar19._0_8_;
  puVar9[1] = 1;
  puVar9[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,*puVar9);
    *extraout_R11 = local_200;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar9 = local_200;
  auVar19 = main_getRequestUserAgent(iStack0000000000000018);
  local_2a0 = auVar19._0_8_;
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efc947,5);
  if (piVar6[1] == 0) {
    iVar13 = 0;
    uVar5 = 0;
  }
  else {
    iVar13 = ((undefined8 *)*piVar6)[1];
    uVar5 = *(undefined8 *)*piVar6;
  }
  auVar2._8_8_ = iVar13;
  auVar2._0_8_ = uVar5;
  auVar20._8_8_ = iVar13;
  auVar20._0_8_ = uVar5;
  if ((iVar13 == 0) && (auVar20 = auVar2, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar20 = mv_daemon_provider___TokenStore__Get(main_tokenStore,&DAT_00f02951,8);
  }
  iVar13 = auVar20._8_8_;
  local_298 = auVar20._0_8_;
  if (iVar13 == 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3daf3,0x2a,0x191);
    return;
  }
  piVar6 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,&DAT_00f02951,8);
  local_258 = piVar6[1];
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d163,0x1d,500);
    return;
  }
  if ((undefined1 *)*piVar6 !=
      go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3a315,0x27,500);
    return;
  }
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efaba6,3);
  if (piVar6[1] == 0) {
    uVar5 = 0;
    local_2a8 = 0;
  }
  else {
    uVar5 = ((undefined8 *)*piVar6)[1];
    local_2a8 = *(undefined8 *)*piVar6;
  }
  uVar7 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar7,&DAT_00f05a35,9);
  if (piVar6[1] == 0) {
    iVar15 = 0;
    local_2b0 = 0;
  }
  else {
    iVar15 = ((undefined8 *)*piVar6)[1];
    local_2b0 = *(undefined8 *)*piVar6;
  }
  auVar21 = mv_daemon_provider_NormalizeDownloadUrl(local_2a8,uVar5,0,0);
  local_2c8 = auVar21._8_8_;
  local_230 = auVar21._0_8_;
  uVar5 = local_2b0;
  if (iVar15 == 0) {
    uVar5 = extraout_RSI;
    iVar15 = extraout_R8;
  }
  if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
    local_2d0 = iVar15;
    local_250 = uVar5;
    local_228 = mv_daemon_provider___OfflineCacheStore__GetValid
                          (mv_daemon_provider_GlobalOfflineCacheStore,local_230,local_2c8,local_258,
                           local_298,iVar13);
    uVar7 = extraout_R10;
    uVar18 = extraout_R11_00;
    if ((local_228 == 0) && (local_2d0 != 0)) {
      local_228 = mv_daemon_provider___OfflineCacheStore__GetValid
                            (mv_daemon_provider_GlobalOfflineCacheStore,local_250,local_2d0,
                             local_258,local_298,iVar13);
      uVar7 = extraout_R10_00;
      uVar18 = extraout_R11_01;
    }
    auVar3._8_8_ = local_2c8;
    auVar3._0_8_ = local_230;
    auVar21._8_8_ = local_2c8;
    auVar21._0_8_ = local_230;
    iVar15 = local_2d0;
    uVar5 = local_250;
    if ((local_228 != 0) && (auVar21 = auVar3, *(int *)(local_228 + 0xb8) == 2)) {
      if (*(char *)(local_228 + 0x98) == '\0') {
        if ((*(int *)(local_228 + 0x78) == 0) && (*(int *)(local_228 + 0x68) == 0)) {
          uVar5 = 0;
          iVar15 = 0;
          local_260 = 0;
        }
        else {
          local_220 = local_2a0;
          local_218 = auVar19._8_8_;
          iVar13 = mv_daemon_provider___Cloud115Provider__Resolve115OfflineToPlay
                             (local_258,*(undefined8 *)(local_228 + 0x60),
                              *(undefined8 *)(local_228 + 0x68),*(undefined8 *)(local_228 + 0x70),
                              *(undefined8 *)(local_228 + 0x78),local_298,iVar13,uVar7,uVar18,
                              &local_220,1,1);
          if (iVar13 == 0) {
            iVar15 = 0;
            local_260 = 0;
            uVar5 = 0;
          }
          else {
            iVar15 = *(int *)(iVar13 + 0x10);
            local_260 = *(undefined8 *)(iVar13 + 8);
            if (iVar15 == 0) {
              iVar15 = 0;
              local_260 = 0;
              uVar5 = 0;
            }
            else {
              iVar14 = *(int *)(local_228 + 0x88);
              uVar7 = *(undefined8 *)(local_228 + 0x80);
              if (iVar14 == 0) {
                iVar14 = *(int *)(iVar13 + 0x48);
                uVar7 = *(undefined8 *)(iVar13 + 0x40);
              }
              iVar17 = *(int *)(local_228 + 0x90);
              if (iVar17 < 1) {
                iVar17 = *(int *)(iVar13 + 0x50);
              }
              uVar5 = *(undefined8 *)(iVar13 + 0x18);
              *(int *)(local_228 + 0x88) = iVar14;
              iVar13 = local_228;
              if (runtime_writeBarrier._0_4_ != 0) {
                uVar5 = runtime_gcWriteBarrier2(uVar5);
                *extraout_R11_02 = extraout_R9;
                extraout_R11_02[1] = extraout_R8_00;
                local_260 = extraout_RSI_00;
                iVar13 = extraout_RDI;
                uVar7 = extraout_R9;
                iVar17 = extraout_R10_01;
              }
              *(undefined8 *)(iVar13 + 0x80) = uVar7;
              *(int *)(iVar13 + 0x90) = iVar17;
            }
          }
        }
      }
      else {
        uVar5 = 0;
        iVar15 = 0;
        local_260 = 0;
      }
      local_68 = 0;
      local_2d8 = iVar15;
      local_240 = uVar5;
      if (iStack0000000000000008 != 0) {
        uVar12 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
        do {
          iVar13 = (uVar12 & *(uint *)main__typeAssert_53) * 0x10;
          if (*(int *)(main__typeAssert_53 + iVar13 + 8) == *(int *)(iStack0000000000000008 + 8)) {
            local_68 = *(undefined8 *)(main__typeAssert_53 + iVar13 + 0x10);
            goto LAB_00c5512f;
          }
          uVar12 = uVar12 + 1;
        } while (*(int *)(main__typeAssert_53 + iVar13 + 8) != 0);
        local_68 = runtime_typeAssert(&main__typeAssert_53);
      }
LAB_00c5512f:
      uStack_60 = uStack0000000000000010;
      _local_48 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
      local_208 = runtime_makemap(&DAT_00e16300,0xe,0);
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effdf5,7);
      *puVar9 = &DAT_00dd2dc0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_31 = uVar5;
      }
      puVar9[1] = 0x115e2c8;
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efe2bd,6);
      *puVar9 = &DAT_00dd2c00;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_32 = uVar5;
      }
      puVar9[1] = &DAT_01132ee8;
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f10bff,0xc);
      *puVar9 = &DAT_00dd2d80;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_33 = uVar5;
      }
      puVar9[1] = &DAT_011352d8;
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f176b7,0xf);
      *puVar9 = &DAT_00dd2c00;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_34 = uVar5;
      }
      puVar9[1] = &DAT_011352e0;
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f0cda5,0xb);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_35 = extraout_RCX_17;
      }
      puVar9[1] = &PTR_DAT_011359a0;
      local_210 = runtime_convTstring(*(undefined8 *)(local_228 + 0x20),
                                      *(undefined8 *)(local_228 + 0x28));
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a35,9);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_36 = local_210;
        extraout_R11_36[1] = extraout_RCX_18;
      }
      puVar9[1] = local_210;
      local_210 = runtime_convTstring(*(undefined8 *)(local_228 + 0x60),
                                      *(undefined8 *)(local_228 + 0x68));
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effe2d,7);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_37 = local_210;
        extraout_R11_37[1] = extraout_RCX_19;
      }
      puVar9[1] = local_210;
      local_210 = runtime_convTstring(*(undefined8 *)(local_228 + 0x70),
                                      *(undefined8 *)(local_228 + 0x78));
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a3e,9);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_38 = local_210;
        extraout_R11_38[1] = extraout_RCX_20;
      }
      puVar9[1] = local_210;
      local_210 = runtime_convTstring(*(undefined8 *)(local_228 + 0x80),
                                      *(undefined8 *)(local_228 + 0x88));
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a11,9);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_39 = local_210;
        extraout_R11_39[1] = extraout_RCX_21;
      }
      puVar9[1] = local_210;
      local_210 = runtime_convT64(*(undefined8 *)(local_228 + 0x90));
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a1a,9);
      *puVar9 = &DAT_00dd2b80;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_40 = local_210;
        extraout_R11_40[1] = uVar5;
      }
      puVar9[1] = local_210;
      local_2b8 = (uint)*(byte *)(local_228 + 0x98);
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efe2c3,6);
      *puVar9 = &DAT_00dd2dc0;
      iVar13 = local_2b8 * 8;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_41 = extraout_RSI_03;
      }
      puVar9[1] = runtime_staticuint64s + iVar13;
      local_210 = runtime_convTslice(*(undefined8 *)(local_228 + 0xa0),
                                     *(undefined8 *)(local_228 + 0xa8),
                                     *(undefined8 *)(local_228 + 0xb0));
      auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a47,9);
      puVar9 = auVar19._0_8_;
      *puVar9 = &DAT_00dc15a0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
        *extraout_R11_42 = local_210;
        extraout_R11_42[1] = extraout_RCX_22;
      }
      puVar9[1] = local_210;
      local_210 = runtime_convTstring(local_260,local_2d8);
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f02a69,8);
      *puVar9 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_43 = local_210;
        extraout_R11_43[1] = uVar5;
      }
      puVar9[1] = local_210;
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effe49,7);
      *puVar9 = &DAT_00e16200;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar5 = puVar9[1];
        puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_44 = local_240;
        extraout_R11_44[1] = uVar5;
      }
      puVar9[1] = local_240;
      encoding_json___Encoder__Encode(&local_68,&DAT_00e16300,local_208);
      return;
    }
  }
  local_2c8 = auVar21._8_8_;
  local_230 = auVar21._0_8_;
  mv_daemon_provider___Cloud115Provider__Get115OfflineTaskStatus
            (local_258,uVar5,iVar15,local_230,local_2c8,local_298,iVar13);
  if (extraout_RBX != 0) {
    auVar19 = (**(code **)(extraout_RBX + 0x18))(extraout_RCX_00);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar19._0_8_,auVar19._8_8_,
                        500);
    return;
  }
  local_290 = extraout_RAX;
  if ((extraout_RAX[8] == 2) || ((extraout_RAX[0xe] != 0 && (extraout_RAX[0x10] != 0)))) {
    local_220 = local_2a0;
    local_218 = auVar19._8_8_;
    auVar19 = mv_daemon_provider___Cloud115Provider__Resolve115OfflineToPlay
                        (local_258,extraout_RAX[0xd],extraout_RAX[0xe],extraout_RAX[0xf],
                         extraout_RAX[0x10],local_298,iVar13,extraout_R10_02,extraout_R11_03,
                         &local_220,1,1);
    pbVar8 = auVar19._0_8_;
    local_2e8 = local_290[0xe];
    local_270 = local_290[0xd];
    local_300 = local_290[0x10];
    local_280 = local_290[0xf];
    local_2f0 = local_290[3];
    local_278 = local_290[2];
    local_2f8 = local_290[4];
    if (auVar19._8_8_ == 0) {
      if (pbVar8 == (byte *)0x0) {
        uVar12 = 0;
        local_248 = 0;
        local_308 = 0;
        local_288 = 0;
        local_2e0 = 0;
        local_268 = 0;
        uVar5 = 0;
      }
      else {
        bVar1 = *pbVar8;
        uVar12 = (uint)bVar1;
        if ((bVar1 == 0) && (iVar13 = *(int *)(pbVar8 + 0x28), iVar13 != 0)) {
          local_270 = *(undefined8 *)(pbVar8 + 0x20);
          local_300 = *(undefined8 *)(pbVar8 + 0x38);
          local_280 = *(undefined8 *)(pbVar8 + 0x30);
          if (*(int *)(pbVar8 + 0x48) != 0) {
            local_278 = *(undefined8 *)(pbVar8 + 0x40);
            local_2f0 = *(int *)(pbVar8 + 0x48);
          }
          local_2e8 = iVar13;
          if (0 < *(int *)(pbVar8 + 0x50)) {
            local_2f8 = *(int *)(pbVar8 + 0x50);
          }
        }
        if (bVar1 == 0) {
          local_2e0 = *(int *)(pbVar8 + 0x10);
          if (local_2e0 == 0) {
            local_2e0 = 0;
            local_268 = 0;
            local_248 = 0;
          }
          else {
            local_268 = *(undefined8 *)(pbVar8 + 8);
            local_248 = *(undefined8 *)(pbVar8 + 0x18);
          }
        }
        else {
          local_2e0 = 0;
          local_268 = 0;
          local_248 = 0;
        }
        uVar5 = *(undefined8 *)(pbVar8 + 0x60);
        local_308 = *(undefined8 *)(pbVar8 + 0x68);
        local_288 = *(uint *)(pbVar8 + 0x58);
      }
    }
    else {
      uVar12 = 0;
      local_248 = 0;
      local_308 = 0;
      local_288 = 0;
      local_2e0 = 0;
      local_268 = 0;
      uVar5 = 0;
    }
    if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
      auVar19 = time_Now();
      iVar13 = auVar19._8_8_;
      if ((int)auVar19._0_8_ < 0) {
        iVar13 = ((auVar19._0_8_ & 0x7fffffffffffffff) >> 0x1e) + 0xdd7b17f80;
      }
      sVar11 = 3;
      puVar9 = &local_130;
      do {
        puVar10 = puVar9;
        *puVar10 = in_XMM15_Qa;
        puVar10[1] = in_XMM15_Qb;
        puVar10[2] = in_XMM15_Qa;
        puVar10[3] = in_XMM15_Qb;
        puVar10[4] = in_XMM15_Qa;
        puVar10[5] = in_XMM15_Qb;
        puVar10[6] = in_XMM15_Qa;
        puVar10[7] = in_XMM15_Qb;
        sVar11 = sVar11 + -1;
        puVar9 = puVar10 + 8;
      } while (sVar11 != 0);
      puVar10[7] = in_XMM15_Qa;
      puVar10[8] = in_XMM15_Qb;
      uStack_128 = local_2c8;
      local_130 = local_230;
      uStack_118 = local_2c8;
      local_120 = local_230;
      local_110 = *local_290;
      uStack_108 = local_290[1];
      local_100 = local_290[2];
      uStack_f8 = local_290[3];
      local_c8 = local_2e8;
      local_d0 = local_270;
      local_b8 = local_300;
      local_c0 = local_280;
      local_a8 = local_2f0;
      uStack_b0 = local_278;
      local_a0 = local_2f8;
      local_80 = local_308;
      local_90 = local_288;
      local_78 = 2;
      local_70 = iVar13 + -0xe7791f700;
      local_98 = (char)uVar12;
      local_88 = uVar5;
      mv_daemon_provider___OfflineCacheStore__Set
                (mv_daemon_provider_GlobalOfflineCacheStore,&local_130);
    }
    local_190 = 0;
    iVar13 = local_2f8;
    uVar16 = local_288;
    if (iStack0000000000000008 != 0) {
      uVar16 = *(uint *)main__typeAssert_54;
      uVar4 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
      do {
        local_2c0 = uVar4;
        iVar15 = (local_2c0 & uVar16) * 0x10;
        iVar13 = *(int *)(main__typeAssert_54 + iVar15 + 8);
        if (iVar13 == *(int *)(iStack0000000000000008 + 8)) {
          local_190 = *(undefined8 *)(main__typeAssert_54 + iVar15 + 0x10);
          goto LAB_00c54464;
        }
        uVar4 = local_2c0 + 1;
      } while (iVar13 != 0);
      local_190 = runtime_typeAssert(&main__typeAssert_54);
      iVar13 = extraout_RSI_02;
      uVar16 = extraout_R9_00;
    }
LAB_00c54464:
    uStack_188 = uStack0000000000000010;
    _local_170 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
    local_2b8 = uVar12;
    local_208 = runtime_makemap(&DAT_00e16300,0xf,0,uVar12,iVar13,local_190,uVar16);
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effdf5,7);
    *puVar9 = &DAT_00dd2dc0;
    local_1f8 = runtime_staticuint64s + local_2b8 * 8;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_04 = extraout_RSI_01;
    }
    puVar9[1] = 0x115e2c8;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efe2bd,6);
    *puVar9 = &DAT_00dd2c00;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar7 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_05 = uVar7;
    }
    puVar9[1] = &DAT_01132ee8;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f10bff,0xc);
    *puVar9 = &DAT_00dd2d80;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar7 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_06 = uVar7;
    }
    puVar9[1] = &DAT_011352d8;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f176b7,0xf);
    *puVar9 = &DAT_00dd2c00;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar7 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_07 = uVar7;
    }
    puVar9[1] = &DAT_011352e0;
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f0cda5,0xb);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_08 = extraout_RCX_01;
    }
    puVar9[1] = &PTR_DAT_011359a0;
    local_210 = runtime_convTstring(*local_290,local_290[1]);
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a35,9);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_09 = local_210;
      extraout_R11_09[1] = extraout_RCX_02;
    }
    puVar9[1] = local_210;
    local_210 = runtime_convTstring(local_270,local_2e8);
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effe2d,7);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_10 = local_210;
      extraout_R11_10[1] = extraout_RCX_03;
    }
    puVar9[1] = local_210;
    local_210 = runtime_convTstring(local_280,local_300);
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a3e,9);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_11 = local_210;
      extraout_R11_11[1] = extraout_RCX_04;
    }
    puVar9[1] = local_210;
    local_210 = runtime_convTstring(local_278,local_2f0);
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a11,9);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_12 = local_210;
      extraout_R11_12[1] = extraout_RCX_05;
    }
    puVar9[1] = local_210;
    local_210 = runtime_convT64(local_2f8);
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a1a,9);
    *puVar9 = &DAT_00dd2b80;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar7 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_13 = local_210;
      extraout_R11_13[1] = uVar7;
    }
    puVar9[1] = local_210;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efe2c3,6);
    *puVar9 = &DAT_00dd2dc0;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar7 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_14 = uVar7;
    }
    puVar9[1] = local_1f8;
    local_210 = runtime_convTslice(local_288,uVar5,local_308);
    auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a47,9);
    puVar9 = auVar19._0_8_;
    *puVar9 = &DAT_00dc15a0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
      *extraout_R11_15 = local_210;
      extraout_R11_15[1] = extraout_RCX_06;
    }
    puVar9[1] = local_210;
    local_210 = runtime_convTstring(local_268,local_2e0);
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f02a69,8);
    *puVar9 = &DAT_00dd29c0;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_16 = local_210;
      extraout_R11_16[1] = uVar5;
    }
    puVar9[1] = local_210;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effe49,7);
    *puVar9 = &DAT_00e16200;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_17 = local_248;
      extraout_R11_17[1] = uVar5;
    }
    puVar9[1] = local_248;
    puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efb5b7,4);
    *puVar9 = &DAT_00db1b20;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar5 = puVar9[1];
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_18 = local_290;
      extraout_R11_18[1] = uVar5;
    }
    puVar9[1] = local_290;
    encoding_json___Encoder__Encode(&local_190,&DAT_00e16300,local_208);
    return;
  }
  local_1f0 = 0;
  if (iStack0000000000000008 != 0) {
    uVar12 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar13 = (uVar12 & *(uint *)main__typeAssert_55) * 0x10;
      if (*(int *)(main__typeAssert_55 + iVar13 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_1f0 = *(undefined8 *)(main__typeAssert_55 + iVar13 + 0x10);
        goto LAB_00c54b1c;
      }
      uVar12 = uVar12 + 1;
    } while (*(int *)(main__typeAssert_55 + iVar13 + 8) != 0);
    local_1f0 = runtime_typeAssert(&main__typeAssert_55);
  }
LAB_00c54b1c:
  uStack_1e8 = uStack0000000000000010;
  _local_1d0 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_208 = runtime_makemap(&DAT_00e16300,0xc,0);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effdf5,7);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier1(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_19 = extraout_RCX_07;
  }
  puVar9[1] = 0x115e2c8;
  local_210 = runtime_convT64(local_290[8]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efe2bd,6);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_20 = local_210;
    extraout_R11_20[1] = extraout_RCX_08;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convT64(local_290[5]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f10bff,0xc);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd2d80;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_21 = local_210;
    extraout_R11_21[1] = extraout_RCX_09;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convT64(local_290[6]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f176b7,0xf);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd2d80;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_22 = local_210;
    extraout_R11_22[1] = extraout_RCX_10;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convT64(local_290[7]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f132fb,0xd);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd2b80;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_23 = local_210;
    extraout_R11_23[1] = extraout_RCX_11;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convTstring(local_290[0xb],local_290[0xc]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f0cda5,0xb);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_24 = local_210;
    extraout_R11_24[1] = extraout_RCX_12;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convTstring(*local_290,local_290[1]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a35,9);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_25 = local_210;
    extraout_R11_25[1] = extraout_RCX_13;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convTstring(local_290[0xd],local_290[0xe]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00effe2d,7);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_26 = local_210;
    extraout_R11_26[1] = extraout_RCX_14;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convTstring(local_290[0xf],local_290[0x10]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a3e,9);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_27 = local_210;
    extraout_R11_27[1] = extraout_RCX_15;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convTstring(local_290[2],local_290[3]);
  auVar19 = runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a11,9);
  puVar9 = auVar19._0_8_;
  *puVar9 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar19._8_8_,puVar9[1]);
    *extraout_R11_28 = local_210;
    extraout_R11_28[1] = extraout_RCX_16;
  }
  puVar9[1] = local_210;
  local_210 = runtime_convT64(local_290[4]);
  puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00f05a1a,9);
  *puVar9 = &DAT_00dd2b80;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar5 = puVar9[1];
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_29 = local_210;
    extraout_R11_29[1] = uVar5;
  }
  puVar9[1] = local_210;
  puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_208,&DAT_00efb5b7,4);
  *puVar9 = &DAT_00db1b20;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar5 = puVar9[1];
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_30 = local_290;
    extraout_R11_30[1] = uVar5;
  }
  puVar9[1] = local_290;
  encoding_json___Encoder__Encode(&local_1f0,&DAT_00e16300,local_208);
  return;
}

