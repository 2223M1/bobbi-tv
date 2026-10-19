/* Reconstructed pseudocode, not original Go source: main.handle115OfflineDelete */

void main_handle115OfflineDelete(int param_1,undefined8 param_2,undefined8 *param_3)

{
  undefined *puVar1;
  double *pdVar2;
  undefined1 auVar3 [16];
  undefined1 auVar4 [16];
  undefined8 uVar5;
  int *piVar6;
  undefined8 *extraout_RAX;
  undefined8 *puVar7;
  char *pcVar8;
  undefined1 *puVar9;
  undefined8 *extraout_RAX_00;
  undefined8 *extraout_RAX_01;
  undefined8 extraout_RAX_02;
  undefined8 *extraout_RAX_03;
  undefined8 *extraout_RAX_04;
  undefined8 *extraout_RAX_05;
  undefined8 *puVar10;
  undefined8 *extraout_RAX_06;
  undefined8 *extraout_RAX_07;
  undefined8 uVar11;
  undefined8 extraout_RCX;
  uint extraout_RCX_00;
  undefined8 *extraout_RCX_01;
  uint extraout_RCX_02;
  uint extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 extraout_RCX_05;
  uint extraout_RCX_06;
  uint extraout_RCX_07;
  uint extraout_RCX_08;
  uint extraout_RCX_09;
  uint extraout_RCX_10;
  uint extraout_RCX_11;
  uint extraout_RCX_12;
  uint extraout_RCX_13;
  uint extraout_RCX_14;
  uint extraout_RCX_15;
  int iVar12;
  uint uVar13;
  sdword *psVar14;
  int iVar15;
  undefined8 *puVar16;
  char extraout_BL;
  uint extraout_RBX;
  uint uVar17;
  uint extraout_RBX_00;
  uint extraout_RBX_01;
  int extraout_RBX_02;
  uint extraout_RBX_03;
  uint extraout_RBX_04;
  int extraout_RBX_05;
  uint extraout_RBX_06;
  int extraout_RBX_07;
  uint extraout_RBX_08;
  int extraout_RBX_09;
  uint extraout_RBX_10;
  sdword sVar18;
  uint uVar19;
  uint extraout_RSI;
  undefined8 extraout_RSI_00;
  undefined8 *extraout_RSI_01;
  undefined8 *extraout_RSI_02;
  undefined8 *extraout_RSI_03;
  undefined8 *extraout_RSI_04;
  undefined8 *extraout_RSI_05;
  int extraout_RDI;
  uint extraout_R8;
  int iVar20;
  int extraout_R8_00;
  int extraout_R8_01;
  undefined8 *puVar21;
  int extraout_R8_02;
  undefined8 extraout_R9;
  int extraout_R9_00;
  int extraout_R9_01;
  undefined8 extraout_R9_02;
  undefined8 extraout_R9_03;
  undefined8 extraout_R9_04;
  undefined8 extraout_R10;
  undefined8 extraout_R10_00;
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
  bool bVar22;
  byte bVar23;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar24 [16];
  undefined1 auVar25 [16];
  undefined1 auVar26 [16];
  undefined1 auVar27 [16];
  undefined1 auVar28 [16];
  undefined1 auVar29 [16];
  undefined1 auVar30 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 *puStack0000000000000018;
  int local_320;
  undefined8 local_318;
  undefined8 local_310;
  uint local_308;
  uint local_300;
  int local_2f8;
  int local_2f0;
  int local_2e8;
  int local_2e0;
  undefined8 local_2d8;
  uint local_2d0;
  uint local_2c8;
  uint local_2c0;
  uint local_2b8;
  uint local_2b0;
  int local_2a8;
  undefined8 *local_2a0;
  undefined8 local_298;
  undefined8 local_290;
  undefined8 local_288;
  undefined8 local_280;
  int local_278;
  undefined8 *local_270;
  undefined8 local_268;
  undefined8 local_260;
  undefined8 local_258;
  undefined8 local_250;
  undefined8 local_248;
  undefined8 *local_240;
  undefined8 *local_238;
  undefined8 *local_230;
  undefined8 local_228;
  undefined8 *local_220;
  undefined8 *local_218;
  undefined8 local_210;
  undefined8 local_208;
  undefined8 uStack_200;
  undefined8 local_1f8;
  undefined8 uStack_1f0;
  undefined8 local_1e8;
  undefined8 uStack_1e0;
  undefined1 local_1c8;
  undefined7 uStack_1c7;
  undefined *local_188;
  undefined8 uStack_180;
  undefined *local_178;
  undefined8 uStack_170;
  undefined8 local_168;
  undefined8 uStack_160;
  undefined *local_158;
  undefined8 uStack_150;
  undefined *local_148;
  undefined1 *puStack_140;
  undefined8 local_138 [25];
  undefined1 local_70 [8];
  undefined8 uStack_68;
  undefined8 *local_60;
  code *local_40;
  undefined *puStack_38;
  undefined8 local_30;
  undefined **ppuStack_28;
  undefined8 local_20;
  undefined8 uStack_18;
  undefined8 *local_10;
  
  iStack0000000000000008 = param_1;
  puStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_320 <= *(int **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  local_258 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar24 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_2a8 = auVar24._8_8_;
  local_210 = auVar24._0_8_;
  local_218 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_218[1] = 0x10;
  *local_218 = &DAT_00f195fc;
  auVar24 = runtime_mapassign_faststr(&DAT_00e91b20,local_258,local_210,local_2a8);
  puVar7 = auVar24._0_8_;
  puVar7[1] = 1;
  puVar7[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar7 = (undefined8 *)runtime_gcWriteBarrier2(puVar7,auVar24._8_8_,*puVar7);
    *extraout_R11 = local_218;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar7 = local_218;
  uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efc947,5);
  if (piVar6[1] == 0) {
    iVar15 = 0;
    uVar5 = 0;
  }
  else {
    iVar15 = ((undefined8 *)*piVar6)[1];
    uVar5 = *(undefined8 *)*piVar6;
  }
  auVar3._8_8_ = iVar15;
  auVar3._0_8_ = uVar5;
  auVar24._8_8_ = iVar15;
  auVar24._0_8_ = uVar5;
  if ((iVar15 == 0) && (auVar24 = auVar3, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar24 = mv_daemon_provider___TokenStore__Get(main_tokenStore,&DAT_00f02951,8);
  }
  iVar15 = auVar24._8_8_;
  local_298 = auVar24._0_8_;
  uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efb5bb,4);
  if (piVar6[1] == 0) {
    iVar20 = 0;
    uVar5 = 0;
  }
  else {
    iVar20 = ((undefined8 *)*piVar6)[1];
    uVar5 = *(undefined8 *)*piVar6;
  }
  if (iVar20 == 0) {
    uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
    piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efe2c9,6);
    if (piVar6[1] == 0) {
      iVar20 = 0;
      uVar5 = 0;
    }
    else {
      iVar20 = ((undefined8 *)*piVar6)[1];
      uVar5 = *(undefined8 *)*piVar6;
    }
  }
  if (iVar20 == 0) {
    uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
    piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f05a35,9);
    if (piVar6[1] == 0) {
      iVar20 = 0;
      uVar5 = 0;
    }
    else {
      iVar20 = ((undefined8 *)*piVar6)[1];
      uVar5 = *(undefined8 *)*piVar6;
    }
  }
  auVar4._8_8_ = local_2f0;
  auVar4._0_8_ = local_260;
  if (iVar20 == 0) {
    local_270 = (undefined8 *)0x0;
    local_308 = 0;
    local_300 = 0;
  }
  else {
    auVar24 = strings_genSplit(uVar5,iVar20,&DAT_011331d8,1,0,0xffffffffffffffff);
    auVar4._8_8_ = local_2f0;
    auVar4._0_8_ = local_260;
    puVar7 = auVar24._0_8_;
    iVar20 = 0;
    uVar19 = 0;
    local_308 = 0;
    local_300 = 0;
    local_270 = (undefined8 *)0x0;
    while( true ) {
      local_2f0 = auVar4._8_8_;
      local_260 = auVar4._0_8_;
      if (auVar24._8_8_ <= iVar20) break;
      local_2a8 = iVar20;
      local_220 = puVar7;
      auVar25 = strings_TrimSpace(*puVar7,puVar7[1]);
      auVar4._8_8_ = local_2f0;
      auVar4._0_8_ = local_260;
      local_2f0 = auVar25._8_8_;
      local_260 = auVar25._0_8_;
      if (local_2f0 == 0) {
        uVar19 = uVar19 & 0xff;
      }
      else {
        uVar17 = local_308 + 1;
        if (local_300 < uVar17) {
          if ((((int)uVar17 < 3) && ((char)uVar19 == '\0')) && (local_308 == 0)) {
            puVar7 = &local_208;
            local_208 = in_XMM15_Qa;
            uStack_200 = in_XMM15_Qb;
            local_1f8 = in_XMM15_Qa;
            uStack_1f0 = in_XMM15_Qb;
            uVar13 = 2;
            uVar19 = 1;
            auVar4 = auVar25;
          }
          else {
            runtime_growslice(local_270,uVar17,local_300,1,&DAT_00dd29c0);
            auVar25._8_8_ = local_2f0;
            auVar25._0_8_ = local_260;
            uVar19 = uVar19 & 0xff;
            puVar7 = extraout_RAX;
            uVar13 = extraout_RCX_00;
            uVar17 = extraout_RBX;
            auVar4 = auVar25;
          }
        }
        else {
          uVar19 = uVar19 & 0xff;
          puVar7 = local_270;
          uVar13 = local_300;
        }
        local_2f0 = auVar4._8_8_;
        local_260 = auVar4._0_8_;
        uVar5 = auVar25._0_8_;
        iVar20 = (uVar17 - 1) * 0x10;
        puVar7[(uVar17 - 1) * 2 + 1] = auVar25._8_8_;
        if (runtime_writeBarrier._0_4_ != 0) {
          uVar5 = runtime_gcWriteBarrier2();
          auVar4._8_8_ = local_2f0;
          auVar4._0_8_ = local_260;
          *extraout_R11_00 = uVar5;
          extraout_R11_00[1] = extraout_R9;
          puVar7 = extraout_RCX_01;
          uVar19 = extraout_RSI;
          iVar20 = extraout_RDI;
          uVar17 = extraout_R8;
        }
        *(undefined8 *)((int)puVar7 + iVar20) = uVar5;
        local_270 = puVar7;
        local_300 = uVar13;
        local_308 = uVar17;
      }
      puVar7 = local_220 + 2;
      iVar20 = local_2a8 + 1;
      uVar19 = uVar19 & 0xffffffff;
    }
  }
  local_2f0 = auVar4._8_8_;
  local_260 = auVar4._0_8_;
  uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
  puVar7 = (undefined8 *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f10c0b,0xc);
  if (puVar7[1] == 0) {
    iVar20 = 0;
    pcVar8 = (char *)0x0;
  }
  else {
    iVar20 = ((undefined8 *)*puVar7)[1];
    pcVar8 = *(char **)*puVar7;
  }
  if ((iVar20 == 1) && (*pcVar8 == '1')) {
    bVar22 = true;
  }
  else {
    uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
    puVar7 = (undefined8 *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f10c0b,0xc);
    if (puVar7[1] == 0) {
      iVar20 = 0;
      psVar14 = (sdword *)0x0;
    }
    else {
      iVar20 = ((undefined8 *)*puVar7)[1];
      psVar14 = *(sdword **)*puVar7;
    }
    if (iVar20 == 4) {
      bVar22 = *psVar14 == 0x65757274;
    }
    else {
      bVar22 = false;
    }
  }
  if (!bVar22) {
    uVar5 = net_url___URL__Query(puStack0000000000000018[2]);
    puVar7 = (undefined8 *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00f02a79,8);
    if (puVar7[1] == 0) {
      iVar20 = 0;
      pcVar8 = (char *)0x0;
    }
    else {
      iVar20 = ((undefined8 *)*puVar7)[1];
      pcVar8 = *(char **)*puVar7;
    }
    if (iVar20 != 1) {
      bVar23 = 0;
      goto LAB_00c56578;
    }
    if (*pcVar8 != '1') {
      bVar23 = 0;
      goto LAB_00c56578;
    }
  }
  bVar23 = 1;
LAB_00c56578:
  uVar5 = local_298;
  if ((puStack0000000000000018[1] == 4) && (*(sdword *)*puStack0000000000000018 == 0x54534f50)) {
    iVar20 = puStack0000000000000018[8];
    uVar5 = puStack0000000000000018[9];
    uVar11 = 0;
    if (iVar20 != 0) {
      uVar19 = (uint)*(dword *)(iVar20 + 0x10);
      do {
        iVar12 = (uVar19 & *(uint *)main__typeAssert_57) * 0x10;
        if (*(int *)(main__typeAssert_57 + iVar12 + 8) == *(int *)(iVar20 + 8)) {
          uVar11 = *(undefined8 *)(main__typeAssert_57 + iVar12 + 0x10);
          goto LAB_00c56f85;
        }
        uVar19 = uVar19 + 1;
      } while (*(int *)(main__typeAssert_57 + iVar12 + 8) != 0);
      local_210 = uVar5;
      uVar11 = runtime_typeAssert(&main__typeAssert_57,*(int *)(iVar20 + 8));
      uVar5 = local_210;
    }
LAB_00c56f85:
    io_ReadAll(uVar11,uVar5);
    uVar5 = local_298;
    if (extraout_RBX_02 != 0) {
      local_2e0 = extraout_RBX_02;
      local_2d8 = extraout_RCX_05;
      local_248 = extraout_RAX_02;
      local_10 = (undefined8 *)runtime_newobject(&DAT_00e9c280);
      iVar20 = encoding_json_Unmarshal(local_248,local_2e0,local_2d8,&DAT_00dc00a0,local_10);
      uVar5 = local_298;
      if (iVar20 == 0) {
        if (local_10[0xb] != 0) {
          local_298 = local_10[10];
          iVar15 = local_10[0xb];
        }
        uVar19 = local_300;
        uVar17 = local_308;
        puVar7 = local_270;
        if (local_10[1] != 0) {
          auVar26 = strings_TrimSpace(*local_10);
          uVar17 = local_308 + 1;
          uVar19 = local_300;
          puVar7 = local_270;
          if (local_300 < uVar17) {
            local_2a8 = auVar26._8_8_;
            local_210 = auVar26._0_8_;
            runtime_growslice(local_270,uVar17,local_300,1,&DAT_00dd29c0);
            auVar26._8_8_ = local_2a8;
            auVar26._0_8_ = local_210;
            uVar17 = extraout_RBX_03;
            uVar19 = extraout_RCX_06;
            puVar7 = extraout_RAX_03;
          }
          uVar5 = auVar26._0_8_;
          iVar20 = (uVar17 - 1) * 0x10;
          puVar7[(uVar17 - 1) * 2 + 1] = auVar26._8_8_;
          if (runtime_writeBarrier._0_4_ != 0) {
            uVar5 = runtime_gcWriteBarrier2();
            *extraout_R11_04 = uVar5;
            extraout_R11_04[1] = extraout_R10;
            uVar17 = extraout_RCX_07;
            puVar7 = extraout_RSI_01;
            iVar20 = extraout_R9_00;
          }
          *(undefined8 *)((int)puVar7 + iVar20) = uVar5;
        }
        if (local_10[3] != 0) {
          local_2b8 = uVar17;
          local_2b0 = uVar19;
          local_230 = puVar7;
          auVar27 = strings_TrimSpace(local_10[2]);
          uVar17 = local_2b8 + 1;
          uVar19 = local_2b0;
          puVar7 = local_230;
          if (local_2b0 < uVar17) {
            local_2a8 = auVar27._8_8_;
            local_210 = auVar27._0_8_;
            runtime_growslice(local_230,uVar17,local_2b0,1,&DAT_00dd29c0);
            auVar27._8_8_ = local_2a8;
            auVar27._0_8_ = local_210;
            uVar17 = extraout_RBX_04;
            uVar19 = extraout_RCX_08;
            puVar7 = extraout_RAX_04;
          }
          uVar5 = auVar27._0_8_;
          iVar20 = (uVar17 - 1) * 0x10;
          puVar7[(uVar17 - 1) * 2 + 1] = auVar27._8_8_;
          if (runtime_writeBarrier._0_4_ != 0) {
            uVar5 = runtime_gcWriteBarrier2();
            *extraout_R11_05 = uVar5;
            extraout_R11_05[1] = extraout_R10_00;
            uVar17 = extraout_RCX_09;
            puVar7 = extraout_RSI_02;
            iVar20 = extraout_R9_01;
          }
          *(undefined8 *)((int)puVar7 + iVar20) = uVar5;
        }
        puVar1 = (undefined *)local_10[4];
        puVar16 = local_10;
        uVar5 = local_298;
        if (puVar1 != (undefined *)0x0) {
          sVar18 = *(sdword *)(puVar1 + 0x10);
          puVar10 = (undefined8 *)local_10[5];
          if (sVar18 == 0x1701f1b5) {
            if (puVar1 == &DAT_00dc8480) {
              puVar21 = (undefined8 *)*puVar10;
              iVar20 = puVar10[1];
              iVar12 = 0;
              while (puVar16 = local_10, uVar5 = local_298, iVar12 < iVar20) {
                local_288 = *puVar21;
                local_318 = puVar21[1];
                local_300 = uVar19;
                local_2c0 = uVar17;
                local_2a8 = iVar12;
                local_238 = puVar7;
                local_220 = puVar21;
                strings_TrimSpace();
                uVar17 = local_2c0;
                uVar19 = local_300;
                puVar7 = local_238;
                if (extraout_RBX_05 != 0) {
                  auVar28 = strings_TrimSpace(local_288,local_318);
                  uVar17 = local_2c0 + 1;
                  uVar19 = local_300;
                  puVar7 = local_238;
                  if (local_300 < uVar17) {
                    local_2b0 = auVar28._8_8_;
                    local_210 = auVar28._0_8_;
                    runtime_growslice(local_238,uVar17,local_300,1,&DAT_00dd29c0);
                    auVar28._8_8_ = local_2b0;
                    auVar28._0_8_ = local_210;
                    uVar17 = extraout_RBX_06;
                    uVar19 = extraout_RCX_10;
                    puVar7 = extraout_RAX_05;
                  }
                  uVar5 = auVar28._0_8_;
                  iVar12 = (uVar17 - 1) * 0x10;
                  puVar7[(uVar17 - 1) * 2 + 1] = auVar28._8_8_;
                  if (runtime_writeBarrier._0_4_ != 0) {
                    uVar5 = runtime_gcWriteBarrier2();
                    *extraout_R11_06 = uVar5;
                    extraout_R11_06[1] = extraout_R9_02;
                    uVar17 = extraout_RCX_11;
                    puVar7 = extraout_RSI_03;
                    iVar12 = extraout_R8_00;
                  }
                  *(undefined8 *)((int)puVar7 + iVar12) = uVar5;
                }
                puVar21 = local_220 + 2;
                iVar12 = local_2a8 + 1;
              }
            }
          }
          else if (sVar18 == -0xd99de8a) {
            if (puVar1 == &DAT_00dc8500) {
              puVar21 = (undefined8 *)*puVar10;
              iVar20 = puVar10[1];
              for (iVar12 = 0; iVar12 < iVar20; iVar12 = iVar12 + 1) {
                if ((undefined *)*puVar21 == &DAT_00dd29c0) {
                  local_280 = *(undefined8 *)puVar21[1];
                  local_310 = ((undefined8 *)puVar21[1])[1];
                  local_2c8 = uVar19;
                  local_2c0 = uVar17;
                  local_2a8 = iVar12;
                  local_238 = puVar7;
                  local_220 = puVar21;
                  strings_TrimSpace(local_280,local_310);
                  uVar19 = local_2c8;
                  uVar17 = local_2c0;
                  puVar16 = local_10;
                  iVar12 = local_2a8;
                  puVar7 = local_238;
                  puVar21 = local_220;
                  uVar5 = local_298;
                  if (extraout_RBX_09 != 0) {
                    auVar30 = strings_TrimSpace(local_280,local_310);
                    uVar17 = local_2c0 + 1;
                    uVar19 = local_2c8;
                    puVar7 = local_238;
                    if (local_2c8 < uVar17) {
                      local_2b0 = auVar30._8_8_;
                      local_210 = auVar30._0_8_;
                      runtime_growslice(local_238,uVar17,local_2c8,1,&DAT_00dd29c0);
                      auVar30._8_8_ = local_2b0;
                      auVar30._0_8_ = local_210;
                      uVar17 = extraout_RBX_10;
                      uVar19 = extraout_RCX_14;
                      puVar7 = extraout_RAX_07;
                    }
                    uVar5 = auVar30._0_8_;
                    iVar12 = (uVar17 - 1) * 0x10;
                    puVar7[(uVar17 - 1) * 2 + 1] = auVar30._8_8_;
                    if (runtime_writeBarrier._0_4_ != 0) {
                      uVar5 = runtime_gcWriteBarrier2();
                      *extraout_R11_08 = uVar5;
                      extraout_R11_08[1] = extraout_R9_04;
                      uVar17 = extraout_RCX_15;
                      puVar7 = extraout_RSI_05;
                      iVar12 = extraout_R8_02;
                    }
                    *(undefined8 *)((int)puVar7 + iVar12) = uVar5;
                    puVar16 = local_10;
                    iVar12 = local_2a8;
                    puVar21 = local_220;
                    uVar5 = local_298;
                  }
                }
                puVar21 = puVar21 + 2;
              }
            }
          }
          else if ((sVar18 == -0x778cd48) && (puVar1 == &DAT_00dd29c0)) {
            local_2c8 = uVar17;
            local_2c0 = uVar19;
            local_238 = puVar7;
            auVar24 = strings_genSplit(*puVar10,puVar10[1],&DAT_011331d8,1,0,0xffffffffffffffff);
            puVar10 = auVar24._0_8_;
            iVar20 = 0;
            uVar19 = local_2c0;
            puVar7 = local_238;
            uVar17 = local_2c8;
            while (puVar16 = local_10, uVar5 = local_298, iVar20 < auVar24._8_8_) {
              local_290 = *puVar10;
              local_320 = puVar10[1];
              local_300 = uVar19;
              local_2d0 = uVar17;
              local_2a8 = iVar20;
              local_240 = puVar7;
              local_220 = puVar10;
              strings_TrimSpace(local_290);
              uVar17 = local_2d0;
              uVar19 = local_300;
              puVar7 = local_240;
              if (extraout_RBX_07 != 0) {
                auVar29 = strings_TrimSpace(local_290,local_320);
                uVar17 = local_2d0 + 1;
                uVar19 = local_300;
                puVar7 = local_240;
                if (local_300 < uVar17) {
                  local_2b0 = auVar29._8_8_;
                  local_210 = auVar29._0_8_;
                  runtime_growslice(local_240,uVar17,local_300,1,&DAT_00dd29c0);
                  auVar29._8_8_ = local_2b0;
                  auVar29._0_8_ = local_210;
                  uVar17 = extraout_RBX_08;
                  uVar19 = extraout_RCX_12;
                  puVar7 = extraout_RAX_06;
                }
                uVar5 = auVar29._0_8_;
                iVar20 = (uVar17 - 1) * 0x10;
                puVar7[(uVar17 - 1) * 2 + 1] = auVar29._8_8_;
                if (runtime_writeBarrier._0_4_ != 0) {
                  uVar5 = runtime_gcWriteBarrier2();
                  *extraout_R11_07 = uVar5;
                  extraout_R11_07[1] = extraout_R9_03;
                  uVar17 = extraout_RCX_13;
                  puVar7 = extraout_RSI_04;
                  iVar20 = extraout_R8_01;
                }
                *(undefined8 *)((int)puVar7 + iVar20) = uVar5;
              }
              puVar10 = local_220 + 2;
              iVar20 = local_2a8 + 1;
            }
          }
        }
        puVar1 = (undefined *)puVar16[6];
        local_308 = uVar17;
        local_270 = puVar7;
        if (puVar1 != (undefined *)0x0) {
          sVar18 = *(sdword *)(puVar1 + 0x10);
          pdVar2 = (double *)puVar16[7];
          if (sVar18 == 0x4ff46048) {
            if (puVar1 == &DAT_00dd2dc0) {
              bVar23 = *(byte *)pdVar2;
            }
          }
          else if (sVar18 == 0x6ca6d294) {
            if (puVar1 == &DAT_00dd2d80) {
              bVar23 = _f64_3ff0000000000000 == *pdVar2;
            }
          }
          else if ((sVar18 == -0x778cd48) && (puVar1 == &DAT_00dd29c0)) {
            if ((pdVar2[1] == 4.94065645841247e-324) && (*(char *)*pdVar2 == '1')) {
              bVar23 = 1;
            }
            else {
              auVar24 = strings_ToLower();
              puVar16 = local_10;
              uVar5 = local_298;
              if (auVar24._8_8_ == 4) {
                bVar23 = *auVar24._0_8_ == 0x65757274;
              }
              else {
                bVar23 = 0;
              }
            }
          }
        }
        puVar1 = (undefined *)puVar16[8];
        if (puVar1 != (undefined *)0x0) {
          sVar18 = *(sdword *)(puVar1 + 0x10);
          pdVar2 = (double *)puVar16[9];
          if (sVar18 == 0x4ff46048) {
            if (puVar1 == &DAT_00dd2dc0) {
              bVar23 = *(byte *)pdVar2;
            }
          }
          else if (sVar18 == 0x6ca6d294) {
            if (puVar1 == &DAT_00dd2d80) {
              bVar23 = *pdVar2 == _f64_3ff0000000000000;
            }
          }
          else if ((sVar18 == -0x778cd48) && (puVar1 == &DAT_00dd29c0)) {
            if ((pdVar2[1] == 4.94065645841247e-324) && (*(char *)*pdVar2 == '1')) {
              bVar23 = 1;
            }
            else {
              auVar24 = strings_ToLower((char *)*pdVar2,pdVar2[1],local_308);
              uVar5 = local_298;
              if (auVar24._8_8_ == 4) {
                bVar23 = *auVar24._0_8_ == 0x65757274;
              }
              else {
                bVar23 = 0;
              }
            }
          }
        }
      }
    }
  }
  if (iVar15 == 0) {
    local_40 = main_handle115OfflineDelete_Printf_func1;
    local_30 = 0x4d;
    puStack_38 = &DAT_00f577ec;
    log___Logger__output(log_std,0,2);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3daf3,0x2a,0x191);
    return;
  }
  local_298 = uVar5;
  piVar6 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,&DAT_00f02951,8);
  local_278 = piVar6[1];
  if (extraout_BL == '\0') {
    local_40 = main_handle115OfflineDelete_Printf_func2;
    local_30 = 0x29;
    puStack_38 = &DAT_00f3ca73;
    log___Logger__output(log_std,0,2);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d163,0x1d,500);
    return;
  }
  if ((undefined1 *)*piVar6 !=
      go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    local_40 = main_handle115OfflineDelete_Printf_func3;
    local_30 = 0x32;
    puStack_38 = &DAT_00f464bb;
    log___Logger__output(log_std,0,2);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3a315,0x27,500);
    return;
  }
  local_220 = (undefined8 *)runtime_makeslice(&DAT_00dd29c0,0,local_308);
  sVar18 = 3;
  puVar7 = local_138;
  do {
    puVar16 = puVar7;
    *puVar16 = in_XMM15_Qa;
    puVar16[1] = in_XMM15_Qb;
    puVar16[2] = in_XMM15_Qa;
    puVar16[3] = in_XMM15_Qb;
    puVar16[4] = in_XMM15_Qa;
    puVar16[5] = in_XMM15_Qb;
    puVar16[6] = in_XMM15_Qa;
    puVar16[7] = in_XMM15_Qb;
    sVar18 = sVar18 + -1;
    puVar7 = puVar16 + 8;
  } while (sVar18 != 0);
  puVar16[7] = in_XMM15_Qa;
  puVar16[8] = in_XMM15_Qb;
  local_138[0] = 0x8080808080808080;
  local_60 = local_138;
  uStack_68 = runtime_rand();
  uVar17 = 0;
  iVar20 = 0;
  puVar7 = local_270;
  uVar19 = local_308;
  local_2a0 = local_220;
  while (iVar20 < (int)local_308) {
    local_2a8 = iVar20;
    local_220 = puVar7;
    auVar24 = strings_TrimSpace(*puVar7,puVar7[1]);
    iVar20 = auVar24._8_8_;
    if ((iVar20 != 0) &&
       (local_2f8 = iVar20, local_268 = auVar24._0_8_,
       pcVar8 = (char *)runtime_mapaccess1_faststr(&DAT_00e16280,local_70,auVar24._0_8_,iVar20),
       *pcVar8 == '\0')) {
      puVar9 = (undefined1 *)runtime_mapassign_faststr(&DAT_00e16280,local_70,local_268,local_2f8);
      *puVar9 = 1;
      uVar17 = uVar17 + 1;
      puVar7 = local_2a0;
      if (uVar19 < uVar17) {
        runtime_growslice(local_2a0,uVar17,uVar19,1,&DAT_00dd29c0);
        puVar7 = extraout_RAX_00;
        uVar19 = extraout_RCX_02;
        uVar17 = extraout_RBX_00;
      }
      iVar20 = uVar17 - 1;
      puVar7[iVar20 * 2 + 1] = local_2f8;
      if (runtime_writeBarrier._0_4_ != 0) {
        runtime_gcWriteBarrier2();
        *extraout_R11_01 = local_268;
        extraout_R11_01[1] = extraout_RSI_00;
        puVar7 = extraout_RAX_01;
        uVar19 = extraout_RCX_03;
        uVar17 = extraout_RBX_01;
      }
      puVar7[iVar20 * 2] = local_268;
      local_2a0 = puVar7;
    }
    puVar7 = local_220 + 2;
    iVar20 = local_2a8 + 1;
  }
  if (uVar17 == 0) {
    local_40 = main_handle115OfflineDelete_Printf_func4;
    local_30 = 0x3c;
    puStack_38 = &DAT_00f4e2b4;
    log___Logger__output(log_std,0,2);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f30e7c,0x20,400);
    return;
  }
  uStack_150 = runtime_convTslice(local_2a0,uVar17,uVar19);
  local_158 = &DAT_00dc8480;
  local_148 = &DAT_00dd2dc0;
  puStack_140 = runtime_staticuint64s + (uint)bVar23 * 8;
  local_40 = main_handle115OfflineDelete_Printf_func5;
  local_30 = 0x49;
  puStack_38 = &DAT_00f55d65;
  local_20 = 2;
  uStack_18 = 2;
  ppuStack_28 = &local_158;
  log___Logger__output(log_std,0,2,&local_40);
  auVar24 = mv_daemon_provider___Cloud115Provider__Delete115OfflineTasks
                      (local_278,local_2a0,uVar17,uVar19,bVar23,local_298,iVar15);
  local_250 = auVar24._8_8_;
  local_2e8 = auVar24._0_8_;
  if (local_2e8 != 0) {
    uStack_170 = runtime_convTslice(local_2a0,uVar17,uVar19);
    local_178 = &DAT_00dc8480;
    if (local_2e8 == 0) {
      local_168 = 0;
    }
    else {
      local_168 = *(undefined8 *)(local_2e8 + 8);
    }
    uStack_160 = local_250;
    local_40 = main_handle115OfflineDelete_Printf_func6;
    local_30 = 0x44;
    puStack_38 = &DAT_00f52d98;
    local_20 = 2;
    uStack_18 = 2;
    ppuStack_28 = &local_178;
    log___Logger__output(log_std,0,2,&local_40);
    auVar24 = (**(code **)(local_2e8 + 0x18))(local_250);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar24._0_8_,auVar24._8_8_,
                        500);
    return;
  }
  if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
    iVar15 = 0;
    puVar7 = local_2a0;
    while (iVar15 < (int)uVar17) {
      local_2a8 = iVar15;
      local_220 = puVar7;
      mv_daemon_provider___OfflineCacheStore__Delete
                (mv_daemon_provider_GlobalOfflineCacheStore,*puVar7,puVar7[1]);
      puVar7 = local_220 + 2;
      iVar15 = local_2a8 + 1;
    }
  }
  uStack_180 = runtime_convTslice(local_2a0,uVar17,uVar19);
  local_188 = &DAT_00dc8480;
  local_40 = main_handle115OfflineDelete_Printf_func7;
  local_30 = 0x2b;
  puStack_38 = &DAT_00f3ed7f;
  local_20 = 1;
  uStack_18 = 1;
  ppuStack_28 = &local_188;
  log___Logger__output(log_std,0,2,&local_40);
  local_1e8 = 0;
  if (iStack0000000000000008 != 0) {
    uVar19 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar15 = (uVar19 & *(uint *)main__typeAssert_58) * 0x10;
      if (*(int *)(main__typeAssert_58 + iVar15 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_1e8 = *(undefined8 *)(main__typeAssert_58 + iVar15 + 0x10);
        goto LAB_00c56dc5;
      }
      uVar19 = uVar19 + 1;
    } while (*(int *)(main__typeAssert_58 + iVar15 + 8) != 0);
    local_1e8 = runtime_typeAssert(&main__typeAssert_58);
  }
LAB_00c56dc5:
  uStack_1e0 = uStack0000000000000010;
  _local_1c8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_228 = runtime_makemap_small();
  auVar24 = runtime_mapassign_faststr(&DAT_00e16300,local_228,&DAT_00effdf5,7);
  puVar7 = auVar24._0_8_;
  *puVar7 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar7 = (undefined8 *)runtime_gcWriteBarrier1(puVar7,auVar24._8_8_,puVar7[1]);
    *extraout_R11_02 = extraout_RCX_04;
  }
  puVar7[1] = 0x115e2c8;
  local_220 = (undefined8 *)runtime_convT64(uVar17);
  puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_228,&DAT_00effe50,7);
  *puVar7 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar5 = puVar7[1];
    puVar7 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_03 = local_220;
    extraout_R11_03[1] = uVar5;
  }
  puVar7[1] = local_220;
  encoding_json___Encoder__Encode(&local_1e8,&DAT_00e16300,local_228);
  return;
}

