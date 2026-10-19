/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*LifeSyncManager).oncePoll */

void mv_daemon_provider___LifeSyncManager__oncePoll
               (undefined8 param_1,int param_2,undefined8 param_3)

{
  char cVar1;
  byte bVar2;
  int extraout_RAX;
  undefined8 *puVar3;
  char *pcVar4;
  byte *pbVar5;
  undefined8 uVar6;
  int extraout_RCX;
  int iVar7;
  undefined8 extraout_RCX_00;
  undefined *puVar8;
  int iVar9;
  int extraout_RBX;
  int extraout_RBX_00;
  int extraout_RBX_01;
  int extraout_RBX_02;
  int extraout_RBX_03;
  int extraout_RBX_04;
  int extraout_RBX_05;
  int extraout_RBX_06;
  int extraout_RBX_07;
  int extraout_RBX_08;
  int extraout_RBX_09;
  int extraout_RBX_10;
  undefined8 extraout_RSI;
  int extraout_RSI_00;
  int iVar10;
  int extraout_RDI;
  undefined8 extraout_RDI_00;
  int extraout_RDI_01;
  int extraout_R8;
  undefined8 extraout_R9;
  int extraout_R10;
  int extraout_R10_00;
  int iVar11;
  undefined8 extraout_R10_01;
  undefined8 extraout_R11;
  undefined8 extraout_R11_00;
  undefined8 extraout_R11_01;
  int unaff_R14;
  undefined1 auVar12 [16];
  undefined1 auVar13 [16];
  undefined8 uStack0000000000000008;
  int iStack0000000000000010;
  undefined8 uStack0000000000000018;
  undefined1 local_408 [54];
  byte local_3d2;
  char local_3d1;
  undefined8 local_3d0;
  undefined8 local_3c8;
  int local_3c0;
  int local_3b8;
  int local_3b0;
  int local_3a8;
  int local_3a0;
  int local_398;
  int local_390;
  int local_388;
  int local_380;
  int local_378;
  int local_370;
  undefined8 local_368;
  undefined8 local_360;
  undefined8 *local_358;
  undefined8 *local_350;
  undefined8 local_348;
  undefined8 uStack_340;
  int local_338;
  undefined8 uStack_330;
  int *local_328;
  int iStack_320;
  int local_318;
  int iStack_310;
  undefined8 local_308;
  undefined8 uStack_300;
  undefined8 local_2f8;
  undefined8 uStack_2f0;
  undefined8 local_2e8;
  int iStack_2e0;
  undefined8 local_2d8;
  undefined8 uStack_2d0;
  undefined8 local_2c8;
  undefined8 local_2c0;
  undefined8 uStack_2b8;
  int local_2b0;
  undefined8 uStack_2a8;
  int *local_2a0;
  int iStack_298;
  int local_290;
  int iStack_288;
  undefined8 local_280;
  undefined8 uStack_278;
  undefined8 local_270;
  undefined8 uStack_268;
  undefined8 local_260;
  int iStack_258;
  undefined8 local_250;
  undefined8 uStack_248;
  undefined8 *local_240;
  undefined *local_238;
  undefined8 uStack_230;
  undefined8 local_228;
  undefined8 uStack_220;
  undefined8 local_218;
  undefined8 local_210;
  int *local_208;
  int iStack_200;
  undefined8 local_1f8;
  undefined8 uStack_1f0;
  code *local_1e8;
  undefined *local_1e0;
  undefined8 local_1d8;
  undefined **local_1d0;
  undefined8 local_1c8;
  undefined8 local_1c0;
  undefined8 local_1b8;
  undefined8 uStack_1b0;
  int local_1a8;
  undefined8 uStack_1a0;
  int *local_198;
  int iStack_190;
  int local_188;
  int iStack_180;
  undefined8 local_178;
  undefined8 uStack_170;
  undefined8 local_168;
  undefined8 uStack_160;
  undefined8 local_158;
  int iStack_150;
  undefined8 local_148;
  undefined8 uStack_140;
  undefined8 *local_138;
  undefined8 *local_130;
  undefined *local_128;
  undefined8 uStack_120;
  undefined *local_118;
  undefined8 uStack_110;
  undefined *local_108;
  undefined8 uStack_100;
  undefined *local_f8;
  undefined8 uStack_f0;
  undefined *local_e8;
  undefined8 uStack_e0;
  undefined *local_d8;
  undefined8 uStack_d0;
  undefined *local_c8;
  undefined8 uStack_c0;
  undefined *local_b8;
  undefined8 uStack_b0;
  undefined *local_a8;
  undefined8 uStack_a0;
  undefined *local_98;
  undefined8 uStack_90;
  undefined *local_88;
  undefined8 uStack_80;
  undefined *local_78;
  undefined8 uStack_70;
  undefined *local_68;
  undefined8 uStack_60;
  undefined *local_58;
  undefined8 uStack_50;
  undefined *local_48;
  undefined8 uStack_40;
  undefined *local_38;
  undefined8 uStack_30;
  undefined8 local_28;
  undefined8 uStack_20;
  undefined8 local_18;
  undefined8 uStack_10;
  
  uStack0000000000000008 = param_1;
  uStack0000000000000018 = param_3;
  iStack0000000000000010 = param_2;
  while (local_408 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  if (mv_daemon_provider_GlobalPrivateLibStore == (mv_daemon_provider_PrivateLibStore *)0x0) {
    return;
  }
  auVar12 = mv_daemon_provider___PrivateLibStore__GetAllActivePanSyncDirs
                      (mv_daemon_provider_GlobalPrivateLibStore);
  local_388 = auVar12._8_8_;
  local_240 = auVar12._0_8_;
  if (extraout_RDI != 0) {
    local_228 = *(undefined8 *)(extraout_RDI + 8);
    local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func1;
    local_1d8 = 0x2a;
    local_1e0 = &DAT_00f3df61;
    local_1c8 = 1;
    local_1c0 = 1;
    local_1d0 = (undefined **)&local_228;
    uStack_220 = extraout_RSI;
    log___Logger__output(log_std,0,2,&local_1e8);
    return;
  }
  if (local_388 == 0) {
    return;
  }
  if (mv_daemon_provider_GlobalTokenStore == (mv_daemon_provider_TokenStore *)0x0) {
    auVar13 = ZEXT816(0);
  }
  else {
    auVar13 = mv_daemon_provider___TokenStore__Get
                        (mv_daemon_provider_GlobalTokenStore,&DAT_00f02951,8);
    auVar12._8_8_ = local_388;
    auVar12._0_8_ = local_240;
  }
  local_3d0 = auVar13._8_8_;
  local_368 = auVar13._0_8_;
  local_388 = auVar12._8_8_;
  local_240 = auVar12._0_8_;
  strings_TrimSpace(local_368,local_3d0);
  if (extraout_RBX == 0) {
    return;
  }
  mv_daemon_provider___PrivateLibStore__GetLifeCursor
            (mv_daemon_provider_GlobalPrivateLibStore,&DAT_00f02951,8);
  local_3b0 = extraout_RBX_00;
  local_3a8 = extraout_RAX;
  if (extraout_RCX != 0) {
    local_238 = *(undefined **)(extraout_RCX + 8);
    local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func2;
    local_1d8 = 0x2a;
    local_1e0 = &DAT_00f3df8b;
    local_1c8 = 1;
    local_1c0 = 1;
    local_1d0 = &local_238;
    uStack_230 = extraout_RDI_00;
    log___Logger__output(log_std,0,2,&local_1e8);
  }
  auVar12 = mv_daemon_provider_Pull115LifeEvents(local_368,local_3d0,local_3a8,local_3b0);
  local_3a0 = auVar12._8_8_;
  local_350 = auVar12._0_8_;
  if (extraout_R8 != 0) {
    local_18 = *(undefined8 *)(extraout_R8 + 8);
    local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func3;
    local_1d8 = 0x2a;
    local_1e0 = &DAT_00f3dfb5;
    local_1c8 = 1;
    local_1c0 = 1;
    local_1d0 = (undefined **)&local_18;
    uStack_10 = extraout_R9;
    log___Logger__output(log_std,0,2,&local_1e8);
    return;
  }
  local_3c0 = extraout_RSI_00;
  local_3b8 = extraout_RDI_01;
  mv_daemon_provider_CleanExpired115DirCache();
  local_390 = 0;
  iVar7 = 0;
  puVar3 = local_350;
  iVar10 = extraout_RBX_01;
  while (iVar7 < local_3a0) {
    local_348 = *puVar3;
    uStack_340 = puVar3[1];
    local_338 = puVar3[2];
    uStack_330 = puVar3[3];
    local_328 = (int *)puVar3[4];
    iStack_320 = puVar3[5];
    local_318 = puVar3[6];
    iStack_310 = puVar3[7];
    local_308 = puVar3[8];
    uStack_300 = puVar3[9];
    local_2f8 = puVar3[10];
    uStack_2f0 = puVar3[0xb];
    local_2e8 = puVar3[0xc];
    iStack_2e0 = puVar3[0xd];
    local_2d8 = puVar3[0xe];
    uStack_2d0 = puVar3[0xf];
    local_370 = iVar7;
    local_1b8 = local_348;
    uStack_1b0 = uStack_340;
    local_1a8 = local_338;
    uStack_1a0 = uStack_330;
    local_198 = local_328;
    iStack_190 = iStack_320;
    local_188 = local_318;
    iStack_180 = iStack_310;
    local_178 = local_308;
    uStack_170 = uStack_300;
    local_168 = local_2f8;
    uStack_160 = uStack_2f0;
    local_158 = local_2e8;
    iStack_150 = iStack_2e0;
    local_148 = local_2d8;
    uStack_140 = uStack_2d0;
    local_130 = puVar3;
    auVar12 = (**(code **)(iStack0000000000000010 + 0x28))(uStack0000000000000018);
    iVar10 = auVar12._8_8_;
    if (auVar12._0_8_ != 0) break;
    if (iStack_320 != 0) {
      iVar7 = 0;
      iVar9 = local_388;
      puVar3 = local_240;
      iVar11 = extraout_R10;
      uVar6 = extraout_R11;
      while (iVar7 < iVar9) {
        iVar11 = iVar7;
        if ((puVar3[iVar7 * 0x10 + 5] == 8) &&
           (*(int *)puVar3[iVar7 * 0x10 + 4] == 0x35313144554f4c43)) {
          local_380 = iVar7 * 0x80;
          local_378 = iVar7;
          local_358 = puVar3 + iVar7 * 0x10;
          cVar1 = mv_daemon_provider_Is115DirDescendantOf
                            (local_308,uStack_300,puVar3[iVar7 * 0x10 + 6],puVar3[iVar7 * 0x10 + 7],
                             local_368,local_3d0);
          iVar10 = 0;
          if (extraout_RBX_02 != 0) {
            local_3d1 = cVar1;
            local_398 = extraout_RBX_02;
            local_2c8 = extraout_RCX_00;
            uStack_40 = runtime_convTstring(local_308,uStack_300);
            local_48 = &DAT_00dd29c0;
            uStack_30 = runtime_convTstring(*(undefined8 *)(local_380 + 0x30 + (int)local_240),
                                            *(undefined8 *)(local_380 + 0x38 + (int)local_240));
            local_38 = &DAT_00dd29c0;
            if (local_398 == 0) {
              local_28 = 0;
            }
            else {
              local_28 = *(undefined8 *)(local_398 + 8);
            }
            uStack_20 = local_2c8;
            local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func4;
            local_1d8 = 0x4b;
            local_1e0 = &DAT_00f56c63;
            local_1c8 = 3;
            local_1c0 = 3;
            local_1d0 = &local_48;
            log___Logger__output(log_std,0,2,&local_1e8);
            iVar10 = extraout_RBX_03;
            cVar1 = local_3d1;
          }
          iVar9 = local_388;
          puVar3 = local_240;
          iVar11 = local_378;
          if (cVar1 != '\0') {
            uStack_90 = runtime_convTstring(local_328,iStack_320);
            local_98 = &DAT_00dd29c0;
            uStack_80 = runtime_convTstring(local_318,iStack_310);
            local_88 = &DAT_00dd29c0;
            uStack_70 = runtime_convTstring(local_308,uStack_300);
            local_78 = &DAT_00dd29c0;
            uStack_60 = runtime_convTstring(*(undefined8 *)((int)local_240 + local_380 + 0x40),
                                            *(undefined8 *)((int)local_240 + local_380 + 0x48));
            local_68 = &DAT_00dd29c0;
            uStack_50 = runtime_convTstring(*(undefined8 *)(local_380 + 0x30 + (int)local_240),
                                            *(undefined8 *)(local_380 + 0x38 + (int)local_240));
            local_58 = &DAT_00dd29c0;
            local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func5;
            local_1d8 = 0x60;
            local_1e0 = &DAT_00f5e741;
            local_1c8 = 5;
            local_1c0 = 5;
            local_1d0 = &local_98;
            log___Logger__output(log_std,0,2,&local_1e8);
            puVar3 = local_358;
            iVar10 = extraout_RBX_04;
            iVar11 = extraout_R10_00;
            uVar6 = extraout_R11_00;
            goto LAB_00a03d91;
          }
        }
        uVar6 = 0x35313144554f4c43;
        iVar7 = iVar11 + 1;
      }
      puVar3 = (undefined8 *)0x0;
LAB_00a03d91:
      if (puVar3 == (undefined8 *)0x0) {
        iVar7 = iStack_310;
        if (((local_338 == 6) || (local_338 == 5)) || (local_338 == 0x16)) {
          do {
            iVar7 = iVar7 + -1;
            if ((iVar7 < 0) || (*(char *)(local_318 + iVar7) == '/')) {
              iVar7 = 0;
              iVar10 = 0;
              goto LAB_00a04058;
            }
          } while (*(char *)(local_318 + iVar7) != '.');
          iVar10 = local_318 + iVar7;
          iVar7 = iStack_310 - iVar7;
LAB_00a04058:
          auVar12 = strings_ToLower(iVar10,iVar7);
          pcVar4 = auVar12._0_8_;
          if ((auVar12._8_8_ != 0) && (*pcVar4 == '.')) {
            pcVar4 = pcVar4 + ((dword)(-(auVar12._8_8_ + -1) >> 0x3f) & 1);
          }
          if (iStack_2e0 == 0) {
            auVar12 = mv_daemon_provider_CleanExt(pcVar4);
            pbVar5 = (byte *)runtime_mapaccess1_faststr
                                       (&DAT_00e16280,mv_daemon_provider_videoExtsMap,auVar12._0_8_,
                                        auVar12._8_8_);
            local_3d2 = *pbVar5 ^ 1;
          }
          else {
            local_3d2 = 0;
          }
          iStack_200 = iStack_320;
          local_208 = local_328;
          uStack_1f0 = uStack_300;
          local_1f8 = local_308;
          mv_daemon_provider_Invalidate115DirCache(&local_208,2,2);
          iVar10 = extraout_RBX_07;
          if (local_3d2 != 0) {
            mv_daemon_provider_ClearAll115DirCache();
            iVar10 = extraout_RBX_08;
          }
          puVar3 = local_240;
          iVar9 = local_388;
          bVar2 = local_3d2;
          for (iVar7 = 0; iVar7 < iVar9; iVar7 = iVar7 + 1) {
            local_2c0 = *puVar3;
            uStack_2b8 = puVar3[1];
            local_2b0 = puVar3[2];
            uStack_2a8 = puVar3[3];
            local_2a0 = (int *)puVar3[4];
            iStack_298 = puVar3[5];
            local_290 = puVar3[6];
            iStack_288 = puVar3[7];
            local_280 = puVar3[8];
            uStack_278 = puVar3[9];
            local_270 = puVar3[10];
            uStack_268 = puVar3[0xb];
            local_260 = puVar3[0xc];
            iStack_258 = puVar3[0xd];
            local_250 = puVar3[0xe];
            uStack_248 = puVar3[0xf];
            local_1b8 = local_2c0;
            uStack_1b0 = uStack_2b8;
            local_1a8 = local_2b0;
            uStack_1a0 = uStack_2a8;
            local_198 = local_2a0;
            iStack_190 = iStack_298;
            local_188 = local_290;
            iStack_180 = iStack_288;
            local_178 = local_280;
            uStack_170 = uStack_278;
            local_168 = local_270;
            uStack_160 = uStack_268;
            local_158 = local_260;
            iStack_150 = iStack_258;
            local_148 = local_250;
            uStack_140 = uStack_248;
            if ((iStack_298 == 8) && (*local_2a0 == 0x35313144554f4c43)) {
              local_378 = iVar7;
              local_138 = puVar3;
              if (bVar2 == 0) {
                auVar12 = mv_daemon_provider___LifeSyncManager__resolveEventPickCode
                                    (uStack0000000000000008,&local_348,local_368,local_3d0);
                local_3c8 = auVar12._8_8_;
                local_360 = auVar12._0_8_;
                local_218 = local_360;
                local_210 = local_3c8;
                auVar12 = mv_daemon_provider___PrivateLibStore__FindLinkByFileIDAndLib
                                    (mv_daemon_provider_GlobalPrivateLibStore,local_2b0,uStack_2a8,
                                     &DAT_00f02951,8,local_328,iStack_320,extraout_R10_01,
                                     extraout_R11_01,&local_218,1,1);
                iVar10 = auVar12._8_8_;
                iVar7 = local_378;
                puVar3 = local_138;
                iVar9 = local_388;
                bVar2 = local_3d2;
                if ((iVar10 != 0) && (auVar12._0_8_ != 0)) {
                  if ((local_338 == 6) || (local_338 == 5)) {
                    uVar6 = 0x12;
                    puVar8 = &DAT_00f1d991;
                  }
                  else {
                    uVar6 = 6;
                    puVar8 = &DAT_00efe75b;
                  }
                  uStack_e0 = runtime_convTstring(puVar8,uVar6);
                  local_e8 = &DAT_00dd29c0;
                  uStack_d0 = runtime_convTstring(local_328,iStack_320);
                  local_d8 = &DAT_00dd29c0;
                  uStack_c0 = runtime_convTstring(local_360,local_3c8);
                  local_c8 = &DAT_00dd29c0;
                  uStack_b0 = runtime_convTstring(local_318,iStack_310);
                  local_b8 = &DAT_00dd29c0;
                  uStack_a0 = runtime_convTstring(local_2b0,uStack_2a8);
                  local_a8 = &DAT_00dd29c0;
                  local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func6;
                  local_1d8 = 0x47;
                  local_1e0 = &DAT_00f54ed8;
                  local_1c8 = 5;
                  local_1c0 = 5;
                  local_1d0 = &local_e8;
                  log___Logger__output(log_std,0,2,&local_1e8);
                  bVar2 = mv_daemon_provider___LifeSyncManager__handleDeleteEvent
                                    (uStack0000000000000008,iStack0000000000000010,
                                     uStack0000000000000018,&local_2c0);
                  local_390 = local_390 + (uint)bVar2;
                  iVar10 = extraout_RBX_10;
                  break;
                }
              }
              else {
                cVar1 = mv_daemon_provider___LifeSyncManager__handleDeleteFolderEvent
                                  (uStack0000000000000008,iStack0000000000000010,
                                   uStack0000000000000018);
                iVar7 = local_378;
                iVar10 = extraout_RBX_09;
                puVar3 = local_138;
                iVar9 = local_388;
                bVar2 = local_3d2;
                if (cVar1 != '\0') {
                  local_390 = local_390 + 1;
                  break;
                }
              }
            }
            puVar3 = puVar3 + 0x10;
          }
        }
      }
      else {
        bVar2 = mv_daemon_provider___LifeSyncManager__handleEventForDir
                          (uStack0000000000000008,iStack0000000000000010,uStack0000000000000018,
                           puVar3,local_368,local_3d0,&local_348,iVar11,uVar6,local_348,uStack_340,
                           local_338,uStack_330,local_328,iStack_320,local_318,iStack_310,local_308,
                           uStack_300,local_2f8,uStack_2f0,local_2e8,iStack_2e0,local_2d8,uStack_2d0
                          );
        local_390 = (uint)bVar2 + local_390;
        iVar10 = extraout_RBX_05;
      }
    }
    puVar3 = local_130 + 0x10;
    iVar7 = local_370 + 1;
  }
  if ((local_3a8 < local_3b8) || (local_3b0 < local_3c0)) {
    mv_daemon_provider___PrivateLibStore__SaveLifeCursor
              (mv_daemon_provider_GlobalPrivateLibStore,&DAT_00f02951,8,local_3b8,local_3c0);
    iVar10 = extraout_RBX_06;
  }
  if ((local_3a0 != 0) || (0 < local_390)) {
    uStack_120 = runtime_convT64(local_3a0,iVar10,&local_128,local_3b8,local_3c0);
    local_128 = &DAT_00dd2c00;
    uStack_110 = runtime_convT64(local_390);
    local_118 = &DAT_00dd2c00;
    uStack_100 = runtime_convT64(local_3b8);
    local_108 = &DAT_00dd2b80;
    uStack_f0 = runtime_convT64(local_3c0);
    local_f8 = &DAT_00dd2b80;
    local_1e8 = mv_daemon_provider___LifeSyncManager__oncePoll_Printf_func7;
    local_1d8 = 0x5a;
    local_1e0 = &DAT_00f5d22f;
    local_1c8 = 4;
    local_1c0 = 4;
    local_1d0 = &local_128;
    log___Logger__output(log_std,0,2,&local_1e8);
  }
  return;
}

