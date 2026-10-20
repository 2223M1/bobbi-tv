/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).resolve115Subtitles */

undefined8 *
mv_daemon_provider___Cloud115Provider__resolve115Subtitles
          (undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,
          undefined8 param_5,char *param_6,int param_7,undefined8 param_8,undefined8 param_9,
          undefined8 *param_10,int param_11,undefined8 param_12,undefined8 param_13,
          undefined8 param_14)

{
  char *pcVar1;
  undefined1 *puVar2;
  undefined8 extraout_RAX;
  undefined8 extraout_RAX_00;
  undefined8 *extraout_RAX_01;
  int iVar3;
  int extraout_RAX_02;
  int iVar4;
  undefined8 extraout_RAX_03;
  undefined8 extraout_RAX_04;
  undefined8 uVar5;
  undefined8 *extraout_RAX_05;
  undefined8 *puVar6;
  sdword sVar7;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  uint extraout_RCX_01;
  uint extraout_RCX_02;
  uint uVar8;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 uVar9;
  uint extraout_RCX_05;
  int iVar10;
  uint uVar11;
  undefined8 *puVar12;
  int extraout_RBX;
  int extraout_RBX_00;
  uint extraout_RBX_01;
  int extraout_RBX_02;
  uint extraout_RBX_03;
  int extraout_RBX_04;
  int extraout_RBX_05;
  uint uVar13;
  uint extraout_RBX_06;
  int extraout_RSI;
  int extraout_RSI_00;
  uint extraout_RDI;
  uint extraout_RDI_00;
  int extraout_RDI_01;
  int extraout_RDI_02;
  char cVar14;
  undefined8 extraout_R11;
  undefined8 extraout_R11_00;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar15 [16];
  undefined8 uStack0000000000000038;
  undefined8 uStack0000000000000040;
  undefined8 uStack0000000000000048;
  undefined8 uStack0000000000000050;
  char *pcStack0000000000000058;
  int iStack0000000000000060;
  undefined8 uStack0000000000000068;
  undefined8 uStack0000000000000070;
  undefined1 local_2c8 [32];
  uint local_2a8;
  uint local_2a0;
  int local_298;
  int local_290;
  uint local_288;
  uint local_280;
  uint local_278;
  uint local_270;
  uint local_268;
  uint local_260;
  uint local_258;
  uint local_250;
  uint local_248;
  uint local_240;
  uint local_238;
  int local_230;
  int local_228;
  undefined8 *local_220;
  undefined8 local_218;
  undefined8 local_210;
  uint uStack_208;
  undefined8 local_200;
  int iStack_1f8;
  undefined8 local_1f0;
  undefined8 uStack_1e8;
  undefined8 local_1e0;
  undefined8 uStack_1d8;
  undefined8 local_1d0;
  undefined8 uStack_1c8;
  undefined8 local_1c0;
  undefined8 uStack_1b8;
  undefined8 local_1b0;
  undefined8 uStack_1a8;
  int local_1a0;
  undefined8 local_198;
  int iStack_190;
  undefined8 local_188;
  int iStack_180;
  undefined1 local_178 [16];
  undefined8 local_168;
  int iStack_160;
  undefined8 local_158;
  undefined8 uStack_150;
  undefined8 local_148 [25];
  undefined1 local_80 [8];
  undefined8 uStack_78;
  undefined8 *local_70;
  undefined8 *local_50;
  undefined8 *local_48;
  undefined8 *local_40;
  int local_38;
  undefined8 *local_30;
  undefined8 *local_28;
  undefined8 local_20;
  undefined8 local_18;
  undefined8 *local_10;
  
  uStack0000000000000040 = param_3;
  uStack0000000000000038 = param_2;
  uStack0000000000000050 = param_5;
  uStack0000000000000048 = param_4;
  pcStack0000000000000058 = param_6;
  iStack0000000000000060 = param_7;
  uStack0000000000000068 = param_8;
  uStack0000000000000070 = param_9;
  while (&local_2a0 <= *(uint **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  sVar7 = 3;
  puVar6 = local_148;
  do {
    puVar12 = puVar6;
    *puVar12 = in_XMM15_Qa;
    puVar12[1] = in_XMM15_Qb;
    puVar12[2] = in_XMM15_Qa;
    puVar12[3] = in_XMM15_Qb;
    puVar12[4] = in_XMM15_Qa;
    puVar12[5] = in_XMM15_Qb;
    puVar12[6] = in_XMM15_Qa;
    puVar12[7] = in_XMM15_Qb;
    sVar7 = sVar7 + -1;
    puVar6 = puVar12 + 8;
  } while (sVar7 != 0);
  puVar12[7] = in_XMM15_Qa;
  puVar12[8] = in_XMM15_Qb;
  local_148[0] = 0x8080808080808080;
  local_70 = local_148;
  uStack_78 = runtime_rand();
  local_2a8 = 0;
  local_2a0 = 0;
  local_220 = (undefined8 *)0x0;
  iVar10 = 0;
  while (iVar10 < param_11) {
    local_230 = param_10[1];
    local_18 = *param_10;
    local_238 = param_10[3];
    local_20 = param_10[2];
    local_228 = iVar10;
    local_10 = param_10;
    if (local_230 == 0) {
      cVar14 = '\x01';
    }
    else {
      pcVar1 = (char *)runtime_mapaccess1_faststr(&DAT_00e16280,local_80,local_18,local_230);
      cVar14 = *pcVar1;
    }
    if (cVar14 == '\0') {
      puVar2 = (undefined1 *)runtime_mapassign_faststr(&DAT_00e16280,local_80,local_18,local_230);
      *puVar2 = 1;
      mv_daemon_provider_get115WindowsShareDownurl
                (uStack0000000000000038,uStack0000000000000040,uStack0000000000000048,
                 uStack0000000000000050,local_18,local_230,param_13,param_14);
      if ((extraout_RSI != 0) ||
         (uVar5 = extraout_RAX, uVar9 = extraout_RCX, iVar10 = extraout_RBX, uVar8 = extraout_RDI,
         extraout_RBX == 0)) {
        mv_daemon_provider_get115ShareDownurl
                  (uStack0000000000000038,uStack0000000000000040,uStack0000000000000048,
                   uStack0000000000000050,local_18,local_230,param_13,param_14,extraout_R11,
                   in_XMM15_Qa,in_XMM15_Qb,0);
        uVar5 = extraout_RAX_00;
        uVar9 = extraout_RCX_00;
        iVar10 = extraout_RBX_00;
        uVar8 = extraout_RDI_00;
      }
      if (iVar10 != 0) {
        uVar11 = local_2a8 + 1;
        local_210 = local_20;
        uStack_208 = local_238;
        if (local_238 == 0) {
          local_210 = uVar9;
          uStack_208 = uVar8;
        }
        local_1f0 = 100;
        puVar6 = local_220;
        uVar8 = local_2a0;
        local_200 = uVar5;
        iStack_1f8 = iVar10;
        if (local_2a0 < uVar11) {
          runtime_growslice(local_220,uVar11,local_2a0,1,&DAT_00e698a0);
          puVar6 = extraout_RAX_01;
          uVar8 = extraout_RCX_01;
          uVar11 = extraout_RBX_01;
        }
        puVar12 = puVar6 + uVar11 * 5 + -5;
        if (runtime_writeBarrier._0_4_ != 0) {
          local_248 = uVar8;
          local_240 = uVar11;
          local_30 = puVar12;
          local_28 = puVar6;
          runtime_wbMove(&DAT_00e698a0,puVar12,&local_210);
          puVar6 = local_28;
          uVar8 = local_248;
          puVar12 = local_30;
          uVar11 = local_240;
        }
        *puVar12 = local_210;
        puVar12[1] = uStack_208;
        puVar12[2] = local_200;
        puVar12[3] = iStack_1f8;
        puVar12[3] = iStack_1f8;
        puVar12[4] = local_1f0;
        local_2a8 = uVar11;
        local_2a0 = uVar8;
        local_220 = puVar6;
      }
    }
    param_10 = local_10 + 4;
    iVar10 = local_228 + 1;
  }
  local_48 = local_220;
  if (((local_2a8 == 0) && (iStack0000000000000060 != 0)) &&
     ((iStack0000000000000060 != 1 || (*pcStack0000000000000058 != '0')))) {
    auVar15 = mv_daemon_provider_cloud115ListFilesSinglePage
                        (uStack0000000000000038,uStack0000000000000040,uStack0000000000000048,
                         uStack0000000000000050,pcStack0000000000000058,iStack0000000000000060,1,100
                        );
    puVar6 = auVar15._0_8_;
    local_48 = local_220;
    if (((auVar15._8_8_ == 0) && (puVar6 != (undefined8 *)0x0)) && (iVar10 = puVar6[1], iVar10 != 0)
       ) {
      puVar6 = (undefined8 *)*puVar6;
      local_280 = 0;
      local_288 = 0;
      local_1a0 = 0;
      local_228 = iVar10;
      for (iVar3 = 0; iVar3 < iVar10; iVar3 = iVar3 + 1) {
        local_210 = *puVar6;
        uStack_208 = puVar6[1];
        local_200 = puVar6[2];
        iStack_1f8 = puVar6[3];
        local_1f0 = puVar6[4];
        uStack_1e8 = puVar6[5];
        local_1e0 = puVar6[6];
        uStack_1d8 = puVar6[7];
        local_1d0 = puVar6[8];
        uStack_1c8 = puVar6[9];
        local_1c0 = puVar6[10];
        uStack_1b8 = puVar6[0xb];
        local_1b0 = puVar6[0xc];
        uStack_1a8 = puVar6[0xd];
        if ((char)local_1f0 == '\0') {
          local_230 = iVar3;
          local_10 = puVar6;
          mv_daemon_matcher_InferSubtitleMimeType(local_200,iStack_1f8);
          iVar3 = local_230;
          iVar10 = local_228;
          puVar6 = local_10;
          if (extraout_RBX_02 != 0) {
            auVar15 = mv_daemon_provider_CleanPanFileId(local_210,uStack_208);
            iVar4 = auVar15._8_8_;
            iVar3 = local_230;
            iVar10 = local_228;
            puVar6 = local_10;
            if (iVar4 != 0) {
              local_298 = iVar4;
              local_218 = auVar15._0_8_;
              pcVar1 = (char *)runtime_mapaccess1_faststr
                                         (&DAT_00e16280,local_80,auVar15._0_8_,iVar4);
              iVar3 = local_230;
              iVar10 = local_228;
              puVar6 = local_10;
              if (*pcVar1 == '\0') {
                local_198 = local_218;
                iStack_190 = local_298;
                local_238 = local_288 + 1;
                local_188 = local_200;
                iStack_180 = iStack_1f8;
                local_158 = in_XMM15_Qa;
                uStack_150 = in_XMM15_Qb;
                local_178 = runtime_concatstring4
                                      (0,&DAT_00f05ed9,9,uStack0000000000000038,
                                       uStack0000000000000040,&DAT_01133210,1,
                                       pcStack0000000000000058,iStack0000000000000060);
                local_168 = local_218;
                iStack_160 = local_298;
                iVar4 = local_1a0;
                uVar8 = local_280;
                uVar11 = local_238;
                if (local_280 < local_238) {
                  runtime_growslice(local_1a0,local_238,local_280,1,&DAT_00e960a0);
                  iVar4 = extraout_RAX_02;
                  uVar8 = extraout_RCX_02;
                  uVar11 = extraout_RBX_03;
                }
                puVar6 = (undefined8 *)(uVar11 * 0x50 + iVar4 + -0x50);
                if (runtime_writeBarrier._0_4_ != 0) {
                  local_258 = uVar8;
                  local_250 = uVar11;
                  local_40 = puVar6;
                  local_38 = iVar4;
                  runtime_wbMove(&DAT_00e960a0,puVar6,&local_198);
                  iVar4 = local_38;
                  uVar8 = local_258;
                  puVar6 = local_40;
                  uVar11 = local_250;
                }
                *puVar6 = local_198;
                puVar6[1] = iStack_190;
                puVar6[2] = local_188;
                puVar6[3] = iStack_180;
                *(undefined1 (*) [16])(puVar6 + 4) = local_178;
                puVar6[6] = local_168;
                puVar6[7] = iStack_160;
                puVar6[8] = local_158;
                puVar6[9] = uStack_150;
                iVar3 = local_230;
                local_280 = uVar8;
                iVar10 = local_228;
                local_288 = uVar11;
                local_1a0 = iVar4;
                puVar6 = local_10;
              }
            }
          }
        }
        puVar6 = puVar6 + 0xe;
      }
      local_48 = local_220;
      if (local_288 != 0) {
        auVar15 = runtime_concatstring4
                            (local_2c8,&DAT_00f05ed9,9,uStack0000000000000038,uStack0000000000000040
                             ,&DAT_01133210,1,pcStack0000000000000058,iStack0000000000000060);
        auVar15 = mv_daemon_provider_MatchAndConvertSubtitles
                            (uStack0000000000000068,uStack0000000000000070,auVar15._0_8_,
                             auVar15._8_8_,local_1a0,local_288,local_280);
        local_228 = 0;
        local_260 = local_2a0;
        local_48 = local_220;
        local_268 = local_2a8;
        while( true ) {
          local_290 = auVar15._8_8_;
          local_10 = auVar15._0_8_;
          if (local_290 <= local_228) break;
          local_210 = *local_10;
          uStack_208 = local_10[1];
          local_200 = local_10[2];
          iStack_1f8 = local_10[3];
          local_1f0 = local_10[4];
          pcVar1 = (char *)runtime_mapaccess1_faststr(&DAT_00e16280,local_80,local_200,iStack_1f8);
          if (*pcVar1 == '\0') {
            puVar2 = (undefined1 *)
                     runtime_mapassign_faststr(&DAT_00e16280,local_80,local_200,iStack_1f8);
            *puVar2 = 1;
            mv_daemon_provider_get115WindowsShareDownurl
                      (uStack0000000000000038,uStack0000000000000040,uStack0000000000000048,
                       uStack0000000000000050,local_200,iStack_1f8,param_13,param_14);
            if ((extraout_RSI_00 != 0) ||
               (uVar5 = extraout_RAX_03, uVar9 = extraout_RCX_03, iVar10 = extraout_RBX_04,
               uVar8 = extraout_RDI_01, extraout_RBX_04 == 0)) {
              mv_daemon_provider_get115ShareDownurl
                        (uStack0000000000000038,uStack0000000000000040,uStack0000000000000048,
                         uStack0000000000000050,local_200,iStack_1f8,param_13,param_14,
                         extraout_R11_00,in_XMM15_Qa,in_XMM15_Qb,0);
              uVar5 = extraout_RAX_04;
              uVar9 = extraout_RCX_04;
              iVar10 = extraout_RBX_05;
              uVar8 = extraout_RDI_02;
            }
            if (iVar10 != 0) {
              if (uVar8 == 0) {
                uVar9 = local_210;
                uVar8 = uStack_208;
              }
              local_1f0 = 100;
              uVar13 = local_268 + 1;
              puVar6 = local_48;
              uVar11 = local_260;
              local_210 = uVar9;
              uStack_208 = uVar8;
              local_200 = uVar5;
              iStack_1f8 = iVar10;
              if (local_260 < uVar13) {
                runtime_growslice(local_48,uVar13,local_260,1,&DAT_00e698a0);
                puVar6 = extraout_RAX_05;
                uVar11 = extraout_RCX_05;
                uVar13 = extraout_RBX_06;
              }
              puVar12 = puVar6 + uVar13 * 5 + -5;
              if (runtime_writeBarrier._0_4_ != 0) {
                local_278 = uVar11;
                local_270 = uVar13;
                local_50 = puVar6;
                local_28 = puVar12;
                runtime_wbMove(&DAT_00e698a0,puVar12,&local_210);
                puVar6 = local_50;
                uVar11 = local_278;
                puVar12 = local_28;
                uVar13 = local_270;
              }
              *puVar12 = local_210;
              puVar12[1] = uStack_208;
              puVar12[2] = local_200;
              puVar12[3] = iStack_1f8;
              puVar12[3] = iStack_1f8;
              puVar12[4] = local_1f0;
              local_48 = puVar6;
              local_260 = uVar11;
              local_268 = uVar13;
            }
          }
          auVar15._8_8_ = local_290;
          auVar15._0_8_ = local_10 + 5;
          local_228 = local_228 + 1;
        }
      }
    }
  }
  return local_48;
}

