/* Reconstructed pseudocode, not original Go source: main.handle115OfflineAdd */

void main_handle115OfflineAdd(int param_1,undefined8 param_2,undefined8 *param_3)

{
  undefined1 auVar1 [16];
  undefined8 uVar2;
  int *piVar3;
  undefined8 extraout_RAX;
  undefined8 *extraout_RAX_00;
  undefined8 *puVar4;
  undefined8 *puVar5;
  int iVar6;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  uint uVar7;
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
  int iVar8;
  int iVar9;
  int iVar10;
  char extraout_BL;
  int extraout_RBX;
  int extraout_RBX_00;
  sdword sVar11;
  int iVar12;
  undefined8 extraout_RSI;
  undefined8 extraout_RSI_00;
  undefined8 extraout_RSI_01;
  undefined8 extraout_RSI_02;
  undefined8 extraout_RDI;
  int extraout_RDI_00;
  int extraout_RDI_01;
  int iVar13;
  int extraout_R8;
  undefined8 extraout_R8_00;
  undefined8 extraout_R9;
  undefined8 uVar14;
  int extraout_R10;
  undefined8 extraout_R10_00;
  undefined8 *extraout_R11;
  undefined8 extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 extraout_R11_02;
  undefined8 *extraout_R11_03;
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
  int unaff_R14;
  int iVar15;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar16 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 *puStack0000000000000018;
  int local_4f0;
  undefined8 local_4e8;
  undefined8 local_4e0;
  int local_4d8;
  int local_4d0;
  int local_4c8;
  int local_4c0;
  undefined8 local_4b8;
  int local_4b0;
  int local_4a8;
  int local_4a0;
  int local_498;
  int local_490;
  int local_488;
  int local_480;
  int local_478;
  uint local_470;
  uint local_468;
  undefined8 local_460;
  undefined8 local_458;
  undefined8 local_450;
  undefined8 local_448;
  undefined8 local_440;
  undefined8 local_438;
  undefined8 local_430;
  undefined8 local_428;
  undefined8 local_420;
  undefined8 local_418;
  undefined8 local_410;
  undefined8 local_408;
  undefined8 *local_400;
  undefined8 local_3f8;
  byte *local_3f0;
  undefined8 local_3e8;
  undefined8 local_3e0;
  undefined8 local_3d8;
  undefined8 local_3d0;
  undefined8 local_3c8;
  int local_3c0;
  int local_3b8;
  undefined8 local_3b0;
  undefined8 local_3a8;
  undefined8 local_3a0;
  undefined8 local_398;
  undefined8 local_390;
  undefined8 local_388;
  int local_380;
  undefined8 local_378;
  undefined8 local_370;
  undefined8 *local_368;
  undefined8 *local_360;
  undefined8 local_358;
  undefined8 local_350;
  undefined8 uStack_348;
  undefined1 local_330;
  undefined7 uStack_32f;
  undefined8 local_2f0;
  undefined8 uStack_2e8;
  undefined1 local_2d0;
  undefined7 uStack_2cf;
  undefined8 local_290;
  int iStack_288;
  undefined8 local_280;
  int iStack_278;
  undefined8 local_270;
  int iStack_268;
  undefined8 local_260;
  int iStack_258;
  undefined8 local_250;
  int local_248;
  undefined8 local_240;
  int local_238;
  undefined8 local_230;
  int local_228;
  undefined8 local_220;
  undefined8 local_218;
  undefined8 uStack_210;
  int local_208;
  int local_200;
  byte local_1f8;
  undefined8 local_1f0;
  undefined8 local_1e8;
  undefined8 local_1e0;
  undefined8 local_1d8;
  int local_1d0;
  undefined8 local_1c8;
  int iStack_1c0;
  undefined8 local_1b8;
  int iStack_1b0;
  undefined8 local_1a8;
  int iStack_1a0;
  undefined8 local_198;
  int iStack_190;
  undefined8 local_188;
  int local_180;
  undefined8 local_178;
  int local_170;
  undefined8 local_110;
  undefined8 local_100;
  undefined8 uStack_f8;
  undefined8 local_f0;
  undefined8 uStack_e8;
  undefined1 local_d0;
  undefined7 uStack_cf;
  undefined *local_90;
  undefined8 uStack_88;
  undefined *local_80;
  undefined8 uStack_78;
  undefined *local_70;
  undefined8 uStack_68;
  undefined *local_60;
  undefined1 *puStack_58;
  undefined8 local_50;
  undefined8 local_48;
  code *local_40;
  undefined *local_38;
  undefined8 local_30;
  undefined **local_28;
  undefined8 local_20;
  undefined8 local_18;
  undefined8 *local_10;
  
  iStack0000000000000008 = param_1;
  puStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_4f0 <= *(int **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_398 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar16 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_468 = auVar16._8_8_;
  local_358 = auVar16._0_8_;
  local_360 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_360[1] = 0x10;
  *local_360 = &DAT_00f195fc;
  auVar16 = runtime_mapassign_faststr(&DAT_00e91b20,local_398,local_358,local_468);
  puVar5 = auVar16._0_8_;
  puVar5[1] = 1;
  puVar5[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,*puVar5);
    *extraout_R11 = local_360;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar5 = local_360;
  auVar16 = main_getRequestUserAgent(puStack0000000000000018);
  local_4e0 = auVar16._8_8_;
  local_420 = auVar16._0_8_;
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00efc947,5);
  if (piVar3[1] == 0) {
    iVar13 = 0;
    uVar2 = 0;
  }
  else {
    iVar13 = ((undefined8 *)*piVar3)[1];
    uVar2 = *(undefined8 *)*piVar3;
  }
  auVar1._8_8_ = iVar13;
  auVar1._0_8_ = uVar2;
  auVar16._8_8_ = iVar13;
  auVar16._0_8_ = uVar2;
  if ((iVar13 == 0) && (auVar16 = auVar1, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar16 = mv_daemon_provider___TokenStore__Get(main_tokenStore,&DAT_00f02951,8);
  }
  local_4d8 = auVar16._8_8_;
  local_418 = auVar16._0_8_;
  if (local_4d8 == 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3daf3,0x2a,0x191);
    return;
  }
  piVar3 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,&DAT_00f02951,8);
  local_3b8 = piVar3[1];
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d163,0x1d,500);
    return;
  }
  if ((undefined1 *)*piVar3 !=
      go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3a315,0x27,500);
    return;
  }
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00efaba6,3);
  if (piVar3[1] == 0) {
    iVar13 = 0;
    local_440 = 0;
  }
  else {
    iVar13 = ((undefined8 *)*piVar3)[1];
    local_440 = *(undefined8 *)*piVar3;
  }
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00efc938,5);
  if (piVar3[1] == 0) {
    iVar15 = 0;
    local_448 = 0;
  }
  else {
    iVar15 = ((undefined8 *)*piVar3)[1];
    local_448 = *(undefined8 *)*piVar3;
  }
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f05a2c,9);
  if (piVar3[1] == 0) {
    iVar8 = 0;
    local_450 = 0;
  }
  else {
    iVar8 = ((undefined8 *)*piVar3)[1];
    local_450 = *(undefined8 *)*piVar3;
  }
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00efe2b1,6);
  if (piVar3[1] == 0) {
    iVar9 = 0;
    local_458 = 0;
  }
  else {
    iVar9 = ((undefined8 *)*piVar3)[1];
    local_458 = *(undefined8 *)*piVar3;
  }
  uVar2 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f02a61,8);
  if (piVar3[1] == 0) {
    iVar12 = 0;
    local_3f8 = 0;
  }
  else {
    iVar12 = ((undefined8 *)*piVar3)[1];
    local_3f8 = *(undefined8 *)*piVar3;
  }
  local_410 = local_448;
  uVar2 = local_440;
  local_430 = local_458;
  local_438 = local_450;
  if (((puStack0000000000000018[1] == 4) && (*(sdword *)*puStack0000000000000018 == 0x54534f50)) &&
     (iVar13 == 0)) {
    local_460 = local_3f8;
    local_10 = (undefined8 *)runtime_newobject(&DAT_00e9c440);
    iVar6 = puStack0000000000000018[8];
    local_3d0 = puStack0000000000000018[9];
    uVar2 = 0;
    if (iVar6 != 0) {
      uVar7 = (uint)*(dword *)(iVar6 + 0x10);
      do {
        iVar10 = (uVar7 & *(uint *)main__typeAssert_49) * 0x10;
        if (*(int *)(main__typeAssert_49 + iVar10 + 8) == *(int *)(iVar6 + 8)) {
          uVar2 = *(undefined8 *)(main__typeAssert_49 + iVar10 + 0x10);
          goto LAB_00c5370f;
        }
        uVar7 = uVar7 + 1;
      } while (*(int *)(main__typeAssert_49 + iVar10 + 8) != 0);
      uVar2 = runtime_typeAssert(&main__typeAssert_49);
    }
LAB_00c5370f:
    local_358 = uVar2;
    puVar5 = (undefined8 *)runtime_newobject(&DAT_00eba560);
    *puVar5 = local_358;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_38 = local_3d0;
    }
    puVar5[1] = local_3d0;
    iVar6 = encoding_json___Decoder__Decode(puVar5,&DAT_00dc0fa0,local_10);
    local_410 = local_448;
    local_3f8 = local_460;
    uVar2 = local_440;
    local_430 = local_458;
    local_438 = local_450;
    if (iVar6 == 0) {
      if (local_10[1] != 0) {
        uVar2 = *local_10;
        iVar13 = local_10[1];
      }
      if (local_10[3] != 0) {
        local_410 = local_10[2];
        iVar15 = local_10[3];
      }
      if (local_10[5] != 0) {
        local_438 = local_10[4];
        iVar8 = local_10[5];
      }
      if (local_10[7] != 0) {
        local_430 = local_10[6];
        iVar9 = local_10[7];
      }
      if (local_10[9] != 0) {
        local_3f8 = local_10[8];
        iVar12 = local_10[9];
      }
      if (local_10[0xb] != 0) {
        local_4d8 = local_10[0xb];
        local_418 = local_10[10];
      }
    }
  }
  local_4f0 = iVar9;
  local_4d0 = iVar15;
  local_4c0 = iVar12;
  mv_daemon_provider_NormalizeDownloadUrl(uVar2,iVar13,local_410,iVar15);
  if (extraout_RBX == 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d180,0x1d,400);
    return;
  }
  local_4e8 = extraout_RDI;
  local_488 = extraout_R8;
  local_478 = extraout_RBX;
  local_428 = extraout_RCX_00;
  local_3b0 = extraout_RSI;
  local_388 = extraout_RAX;
  if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
    local_380 = mv_daemon_provider___OfflineCacheStore__GetValid
                          (mv_daemon_provider_GlobalOfflineCacheStore,extraout_RAX,extraout_RBX,
                           local_3b8,local_418,local_4d8);
    if ((local_380 == 0) && (local_488 != 0)) {
      local_380 = mv_daemon_provider___OfflineCacheStore__GetValid
                            (mv_daemon_provider_GlobalOfflineCacheStore,local_3b0,local_488,
                             local_3b8,local_418,local_4d8);
    }
    if ((local_380 != 0) && (*(int *)(local_380 + 0xb8) == 2)) {
      uStack_88 = runtime_convTstring(local_388,local_478);
      local_90 = &DAT_00dd29c0;
      uStack_78 = runtime_convTstring(*(undefined8 *)(local_380 + 0x60),
                                      *(undefined8 *)(local_380 + 0x68));
      local_80 = &DAT_00dd29c0;
      uStack_68 = runtime_convTstring(*(undefined8 *)(local_380 + 0x70),
                                      *(undefined8 *)(local_380 + 0x78));
      local_70 = &DAT_00dd29c0;
      local_60 = &DAT_00dd2dc0;
      puStack_58 = runtime_staticuint64s + (uint)*(byte *)(local_380 + 0x98) * 8;
      local_40 = main_handle115OfflineAdd_Printf_func1;
      local_30 = 0x59;
      local_38 = &DAT_00f5cbe6;
      local_20 = 4;
      local_18 = 4;
      local_28 = &local_90;
      log___Logger__output(log_std,0,2,&local_40);
      if (*(char *)(local_380 + 0x98) == '\0') {
        if ((*(int *)(local_380 + 0x78) == 0) && (*(int *)(local_380 + 0x68) == 0)) {
          uVar2 = 0;
          iVar15 = 0;
          local_3c8 = 0;
        }
        else {
          local_48 = local_4e0;
          local_50 = local_420;
          iVar13 = mv_daemon_provider___Cloud115Provider__Resolve115OfflineToPlay
                             (local_3b8,*(undefined8 *)(local_380 + 0x60),
                              *(undefined8 *)(local_380 + 0x68),*(undefined8 *)(local_380 + 0x70),
                              *(undefined8 *)(local_380 + 0x78),local_418,local_4d8,&local_50,
                              extraout_R11_00,&local_50,1,1);
          if (iVar13 == 0) {
            iVar15 = 0;
            local_3c8 = 0;
            uVar2 = 0;
          }
          else {
            iVar15 = *(int *)(iVar13 + 0x10);
            local_3c8 = *(undefined8 *)(iVar13 + 8);
            if (iVar15 == 0) {
              iVar15 = 0;
              local_3c8 = 0;
              uVar2 = 0;
            }
            else {
              iVar8 = *(int *)(local_380 + 0x88);
              uVar14 = *(undefined8 *)(local_380 + 0x80);
              if (iVar8 == 0) {
                iVar8 = *(int *)(iVar13 + 0x48);
                uVar14 = *(undefined8 *)(iVar13 + 0x40);
              }
              iVar9 = *(int *)(local_380 + 0x90);
              if (iVar9 < 1) {
                iVar9 = *(int *)(iVar13 + 0x50);
              }
              uVar2 = *(undefined8 *)(iVar13 + 0x18);
              *(int *)(local_380 + 0x88) = iVar8;
              iVar13 = local_380;
              if (runtime_writeBarrier._0_4_ != 0) {
                uVar2 = runtime_gcWriteBarrier2(uVar2);
                *extraout_R11_01 = extraout_R9;
                extraout_R11_01[1] = extraout_R8_00;
                local_3c8 = extraout_RSI_00;
                iVar13 = extraout_RDI_00;
                uVar14 = extraout_R9;
                iVar9 = extraout_R10;
              }
              *(undefined8 *)(iVar13 + 0x80) = uVar14;
              *(int *)(iVar13 + 0x90) = iVar9;
            }
          }
        }
      }
      else {
        uVar2 = 0;
        iVar15 = 0;
        local_3c8 = 0;
      }
      local_f0 = 0;
      local_498 = iVar15;
      local_3a0 = uVar2;
      if (iStack0000000000000008 != 0) {
        uVar7 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
        do {
          iVar13 = (uVar7 & *(uint *)main__typeAssert_50) * 0x10;
          if (*(int *)(main__typeAssert_50 + iVar13 + 8) == *(int *)(iStack0000000000000008 + 8)) {
            local_f0 = *(undefined8 *)(main__typeAssert_50 + iVar13 + 0x10);
            goto LAB_00c5305d;
          }
          uVar7 = uVar7 + 1;
        } while (*(int *)(main__typeAssert_50 + iVar13 + 8) != 0);
        local_f0 = runtime_typeAssert(&main__typeAssert_50);
      }
LAB_00c5305d:
      uStack_e8 = uStack0000000000000010;
      _local_d0 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
      local_370 = runtime_makemap(&DAT_00e16300,0xe,0);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effdf5,7);
      *puVar5 = &DAT_00dd2dc0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_24 = uVar2;
      }
      puVar5[1] = 0x115e2c8;
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2b7,6);
      *puVar5 = &DAT_00dd2dc0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_25 = uVar2;
      }
      puVar5[1] = 0x115e2c8;
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2bd,6);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd2c00;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_26 = extraout_RCX_14;
      }
      puVar5[1] = &DAT_01132ee8;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x20),
                                      *(undefined8 *)(local_380 + 0x28));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a35,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_27 = local_378;
        extraout_R11_27[1] = extraout_RCX_15;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x60),
                                      *(undefined8 *)(local_380 + 0x68));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effe2d,7);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_28 = local_378;
        extraout_R11_28[1] = extraout_RCX_16;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x70),
                                      *(undefined8 *)(local_380 + 0x78));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a3e,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_29 = local_378;
        extraout_R11_29[1] = extraout_RCX_17;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x80),
                                      *(undefined8 *)(local_380 + 0x88));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a11,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_30 = local_378;
        extraout_R11_30[1] = extraout_RCX_18;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convT64(*(undefined8 *)(local_380 + 0x90));
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a1a,9);
      *puVar5 = &DAT_00dd2b80;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_31 = local_378;
        extraout_R11_31[1] = uVar2;
      }
      puVar5[1] = local_378;
      local_468 = (uint)*(byte *)(local_380 + 0x98);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2c3,6);
      *puVar5 = &DAT_00dd2dc0;
      iVar13 = local_468 * 8;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_32 = extraout_RSI_02;
      }
      puVar5[1] = runtime_staticuint64s + iVar13;
      local_378 = runtime_convTslice(*(undefined8 *)(local_380 + 0xa0),
                                     *(undefined8 *)(local_380 + 0xa8),
                                     *(undefined8 *)(local_380 + 0xb0));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a47,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dc15a0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_33 = local_378;
        extraout_R11_33[1] = extraout_RCX_19;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_3c8,local_498);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f02a69,8);
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_34 = local_378;
        extraout_R11_34[1] = uVar2;
      }
      puVar5[1] = local_378;
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effe49,7);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00e16200;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_35 = local_3a0;
        extraout_R11_35[1] = extraout_RCX_20;
      }
      puVar5[1] = local_3a0;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x40),
                                      *(undefined8 *)(local_380 + 0x48));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a2c,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_36 = local_378;
        extraout_R11_36[1] = extraout_RCX_21;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(*(undefined8 *)(local_380 + 0x50),
                                      *(undefined8 *)(local_380 + 0x58));
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2b1,6);
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_37 = local_378;
        extraout_R11_37[1] = uVar2;
      }
      puVar5[1] = local_378;
      encoding_json___Encoder__Encode(&local_f0,&DAT_00e16300,local_370);
      return;
    }
  }
  mv_daemon_provider___Cloud115Provider__Add115OfflineTask
            (local_3b8,local_388,local_478,local_3f8,local_4c0,local_418,local_4d8);
  if (extraout_RBX_00 != 0) {
    if (extraout_RBX_00 == 0) {
      local_100 = 0;
    }
    else {
      local_100 = *(undefined8 *)(extraout_RBX_00 + 8);
    }
    local_40 = main_handle115OfflineAdd_Printf_func2;
    local_30 = 0x2a;
    local_38 = &DAT_00f3db47;
    local_20 = 1;
    local_18 = 1;
    local_28 = (undefined **)&local_100;
    local_480 = extraout_RBX_00;
    local_390 = extraout_RCX_01;
    uStack_f8 = extraout_RCX_01;
    log___Logger__output(log_std,0,2,&local_40);
    auVar16 = (**(code **)(local_480 + 0x18))(local_390);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar16._0_8_,auVar16._8_8_,
                        500);
    return;
  }
  local_4c8 = extraout_RAX_00[1];
  local_408 = *extraout_RAX_00;
  if (local_4c8 == 0) {
    local_408 = local_3b0;
    local_4c8 = local_488;
  }
  local_400 = extraout_RAX_00;
  if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
    sVar11 = 3;
    puVar5 = &local_1c8;
    do {
      puVar4 = puVar5;
      *puVar4 = in_XMM15_Qa;
      puVar4[1] = in_XMM15_Qb;
      puVar4[2] = in_XMM15_Qa;
      puVar4[3] = in_XMM15_Qb;
      puVar4[4] = in_XMM15_Qa;
      puVar4[5] = in_XMM15_Qb;
      puVar4[6] = in_XMM15_Qa;
      puVar4[7] = in_XMM15_Qb;
      sVar11 = sVar11 + -1;
      puVar5 = puVar4 + 8;
    } while (sVar11 != 0);
    puVar4[7] = in_XMM15_Qa;
    puVar4[8] = in_XMM15_Qb;
    iStack_1c0 = local_478;
    local_1c8 = local_388;
    iStack_1b0 = local_478;
    local_1b8 = local_388;
    iStack_190 = local_4d0;
    local_198 = local_410;
    local_188 = local_438;
    local_170 = local_4f0;
    local_178 = local_430;
    local_110 = 0;
    local_1a8 = local_408;
    iStack_1a0 = local_4c8;
    local_180 = iVar8;
    mv_daemon_provider___OfflineCacheStore__Set
              (mv_daemon_provider_GlobalOfflineCacheStore,&local_1c8);
  }
  time_Sleep(300000000);
  auVar16 = mv_daemon_provider___Cloud115Provider__Get115OfflineTaskStatus
                      (local_3b8,local_408,local_4c8,local_388,local_478,local_418,local_4d8);
  puVar4 = auVar16._0_8_;
  puVar5 = local_400;
  if (((auVar16._8_8_ == 0) && (puVar4 != (undefined8 *)0x0)) &&
     ((puVar4[8] == 2 || ((puVar5 = puVar4, puVar4[0xe] != 0 && (puVar4[0x10] != 0)))))) {
    local_48 = local_4e0;
    local_50 = local_420;
    local_368 = puVar4;
    auVar16 = mv_daemon_provider___Cloud115Provider__Resolve115OfflineToPlay
                        (local_3b8,puVar4[0xd],puVar4[0xe],puVar4[0xf],puVar4[0x10],local_418,
                         local_4d8,extraout_R10_00,extraout_R11_02,&local_50,1,1);
    local_3f0 = auVar16._0_8_;
    puVar5 = local_368;
    if ((auVar16._8_8_ == 0) && (puVar5 = local_368, local_3f0 != (byte *)0x0)) {
      local_3d8 = local_368[0xd];
      local_4a0 = local_368[0xe];
      local_4b8 = local_368[0x10];
      local_3e8 = local_368[0xf];
      local_4a8 = local_368[3];
      local_3e0 = local_368[2];
      local_4b0 = local_368[4];
      if (*local_3f0 == 0) {
        if (*(int *)(local_3f0 + 0x28) != 0) {
          local_3d8 = *(undefined8 *)(local_3f0 + 0x20);
          local_4b8 = *(undefined8 *)(local_3f0 + 0x38);
          local_3e8 = *(undefined8 *)(local_3f0 + 0x30);
          local_4a0 = *(int *)(local_3f0 + 0x28);
        }
        local_490 = *(int *)(local_3f0 + 0x10);
        if (*(int *)(local_3f0 + 0x48) != 0) {
          local_3e0 = *(undefined8 *)(local_3f0 + 0x40);
          local_4a8 = *(int *)(local_3f0 + 0x48);
        }
        if (0 < *(int *)(local_3f0 + 0x50)) {
          local_4b0 = *(int *)(local_3f0 + 0x50);
        }
        if (local_490 == 0) {
          local_490 = 0;
          local_3c0 = 0;
          local_3a8 = 0;
        }
        else {
          local_3c0 = *(int *)(local_3f0 + 8);
          local_3a8 = *(undefined8 *)(local_3f0 + 0x18);
        }
      }
      else {
        local_3a8 = 0;
        local_490 = 0;
        local_3c0 = 0;
      }
      if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0)
      {
        auVar16 = time_Now();
        iVar13 = auVar16._8_8_;
        if ((int)auVar16._0_8_ < 0) {
          iVar13 = ((auVar16._0_8_ & 0x7fffffffffffffff) >> 0x1e) + 0xdd7b17f80;
        }
        sVar11 = 3;
        puVar5 = &local_290;
        do {
          puVar4 = puVar5;
          *puVar4 = in_XMM15_Qa;
          puVar4[1] = in_XMM15_Qb;
          puVar4[2] = in_XMM15_Qa;
          puVar4[3] = in_XMM15_Qb;
          puVar4[4] = in_XMM15_Qa;
          puVar4[5] = in_XMM15_Qb;
          puVar4[6] = in_XMM15_Qa;
          puVar4[7] = in_XMM15_Qb;
          sVar11 = sVar11 + -1;
          puVar5 = puVar4 + 8;
        } while (sVar11 != 0);
        puVar4[7] = in_XMM15_Qa;
        puVar4[8] = in_XMM15_Qb;
        iStack_288 = local_478;
        local_290 = local_388;
        iStack_278 = local_478;
        local_280 = local_388;
        iStack_268 = local_4c8;
        local_270 = local_408;
        iStack_258 = local_4d0;
        local_260 = local_410;
        local_250 = local_438;
        local_238 = local_4f0;
        local_240 = local_430;
        local_228 = local_4a0;
        local_230 = local_3d8;
        local_218 = local_4b8;
        local_220 = local_3e8;
        local_208 = local_4a8;
        uStack_210 = local_3e0;
        local_200 = local_4b0;
        local_1f8 = *local_3f0;
        local_1f0 = *(undefined8 *)(local_3f0 + 0x58);
        local_1e8 = *(undefined8 *)(local_3f0 + 0x60);
        local_1e0 = *(undefined8 *)(local_3f0 + 0x68);
        local_1d8 = 2;
        local_1d0 = iVar13 + -0xe7791f700;
        local_248 = iVar8;
        mv_daemon_provider___OfflineCacheStore__Set
                  (mv_daemon_provider_GlobalOfflineCacheStore,&local_290);
      }
      local_2f0 = 0;
      iVar13 = local_3c0;
      if (iStack0000000000000008 != 0) {
        uVar7 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
        do {
          local_470 = uVar7;
          iVar15 = (local_470 & *(uint *)main__typeAssert_51) * 0x10;
          iVar13 = *(int *)(main__typeAssert_51 + iVar15 + 8);
          if (iVar13 == *(int *)(iStack0000000000000008 + 8)) {
            local_2f0 = *(undefined8 *)(main__typeAssert_51 + iVar15 + 0x10);
            goto LAB_00c529b1;
          }
          uVar7 = local_470 + 1;
        } while (iVar13 != 0);
        local_2f0 = runtime_typeAssert(&main__typeAssert_51);
        iVar13 = extraout_RDI_01;
      }
LAB_00c529b1:
      uStack_2e8 = uStack0000000000000010;
      _local_2d0 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
      local_370 = runtime_makemap(&DAT_00e16300,0xe,0,iVar13);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effdf5,7);
      *puVar5 = &DAT_00dd2dc0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_10 = uVar2;
      }
      puVar5[1] = 0x115e2c8;
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2b7,6);
      *puVar5 = &DAT_00dd2dc0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_11 = uVar2;
      }
      puVar5[1] = runtime_staticuint64s;
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2bd,6);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd2c00;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_12 = extraout_RCX_06;
      }
      puVar5[1] = &DAT_01132ee8;
      local_378 = runtime_convTstring(local_408,local_4c8);
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a35,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_13 = local_378;
        extraout_R11_13[1] = extraout_RCX_07;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_3d8,local_4a0);
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effe2d,7);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_14 = local_378;
        extraout_R11_14[1] = extraout_RCX_08;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_3e8,local_4b8);
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a3e,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_15 = local_378;
        extraout_R11_15[1] = extraout_RCX_09;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_3e0,local_4a8);
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a11,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_16 = local_378;
        extraout_R11_16[1] = extraout_RCX_10;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convT64(local_4b0);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a1a,9);
      *puVar5 = &DAT_00dd2b80;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_17 = local_378;
        extraout_R11_17[1] = uVar2;
      }
      puVar5[1] = local_378;
      local_468 = (uint)*local_3f0;
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2c3,6);
      *puVar5 = &DAT_00dd2dc0;
      iVar13 = local_468 * 8;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
        *extraout_R11_18 = extraout_RSI_01;
      }
      puVar5[1] = runtime_staticuint64s + iVar13;
      local_378 = runtime_convTslice(*(undefined8 *)(local_3f0 + 0x58),
                                     *(undefined8 *)(local_3f0 + 0x60),
                                     *(undefined8 *)(local_3f0 + 0x68));
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a47,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dc15a0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_19 = local_378;
        extraout_R11_19[1] = extraout_RCX_11;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_3c0,local_490);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f02a69,8);
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_20 = local_378;
        extraout_R11_20[1] = uVar2;
      }
      puVar5[1] = local_378;
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effe49,7);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00e16200;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_21 = local_3a8;
        extraout_R11_21[1] = extraout_RCX_12;
      }
      puVar5[1] = local_3a8;
      local_378 = runtime_convTstring(local_438,iVar8);
      auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a2c,9);
      puVar5 = auVar16._0_8_;
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
        *extraout_R11_22 = local_378;
        extraout_R11_22[1] = extraout_RCX_13;
      }
      puVar5[1] = local_378;
      local_378 = runtime_convTstring(local_430,local_4f0);
      puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2b1,6);
      *puVar5 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar2 = puVar5[1];
        puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_23 = local_378;
        extraout_R11_23[1] = uVar2;
      }
      puVar5[1] = local_378;
      encoding_json___Encoder__Encode(&local_2f0,&DAT_00e16300,local_370);
      return;
    }
  }
  local_350 = 0;
  local_400 = puVar5;
  if (iStack0000000000000008 != 0) {
    uVar7 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar13 = (uVar7 & *(uint *)main__typeAssert_52) * 0x10;
      if (*(int *)(main__typeAssert_52 + iVar13 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_350 = *(undefined8 *)(main__typeAssert_52 + iVar13 + 0x10);
        goto LAB_00c52635;
      }
      uVar7 = uVar7 + 1;
    } while (*(int *)(main__typeAssert_52 + iVar13 + 8) != 0);
    local_350 = runtime_typeAssert(&main__typeAssert_52);
  }
LAB_00c52635:
  uStack_348 = uStack0000000000000010;
  _local_330 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_370 = runtime_makemap_small();
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00effdf5,7);
  *puVar5 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = puVar5[1];
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_03 = uVar2;
  }
  puVar5[1] = 0x115e2c8;
  auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2b7,6);
  puVar5 = auVar16._0_8_;
  *puVar5 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1(puVar5,auVar16._8_8_,puVar5[1]);
    *extraout_R11_04 = extraout_RCX_02;
  }
  puVar5[1] = runtime_staticuint64s;
  local_378 = runtime_convT64(local_400[8]);
  auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efe2bd,6);
  puVar5 = auVar16._0_8_;
  *puVar5 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
    *extraout_R11_05 = local_378;
    extraout_R11_05[1] = extraout_RCX_03;
  }
  puVar5[1] = local_378;
  local_378 = runtime_convTstring(local_408,local_4c8);
  auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f05a35,9);
  puVar5 = auVar16._0_8_;
  *puVar5 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
    *extraout_R11_06 = local_378;
    extraout_R11_06[1] = extraout_RCX_04;
  }
  puVar5[1] = local_378;
  local_378 = runtime_convTstring(local_388,local_478);
  auVar16 = runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efaba6,3);
  puVar5 = auVar16._0_8_;
  *puVar5 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar16._8_8_,puVar5[1]);
    *extraout_R11_07 = local_378;
    extraout_R11_07[1] = extraout_RCX_05;
  }
  puVar5[1] = local_378;
  local_378 = runtime_convTstring(local_428,local_4e8);
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00f02a71,8);
  *puVar5 = &DAT_00dd29c0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = puVar5[1];
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_08 = local_378;
    extraout_R11_08[1] = uVar2;
  }
  puVar5[1] = local_378;
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_370,&DAT_00efb5b7,4);
  *puVar5 = &DAT_00db1b20;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = puVar5[1];
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_09 = local_400;
    extraout_R11_09[1] = uVar2;
  }
  puVar5[1] = local_400;
  encoding_json___Encoder__Encode(&local_350,&DAT_00e16300,local_370);
  return;
}

