/* Reconstructed pseudocode, not original Go source: mv-daemon/pkg/proxy.(*ProxyManager).RegisterFull */

undefined1  [16]
mv_daemon_pkg_proxy___ProxyManager__RegisterFull
          (sdword *param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,int param_5,
          int param_6,int param_7,char param_8,int param_9)

{
  sdword sVar1;
  byte bVar2;
  undefined1 auVar3 [16];
  undefined1 auVar4 [16];
  undefined1 auVar5 [16];
  undefined1 auVar6 [16];
  char cVar7;
  undefined8 extraout_RAX;
  undefined8 extraout_RAX_00;
  undefined8 **extraout_RAX_01;
  undefined8 extraout_RAX_02;
  undefined1 *puVar8;
  undefined8 *puVar9;
  undefined8 uVar10;
  undefined8 **extraout_RAX_03;
  undefined8 **ppuVar11;
  int extraout_RAX_04;
  int extraout_RAX_05;
  int extraout_RAX_06;
  undefined8 **extraout_RAX_07;
  int extraout_RAX_08;
  int extraout_RAX_09;
  int extraout_RAX_10;
  undefined8 **extraout_RAX_11;
  int extraout_RAX_12;
  int extraout_RAX_13;
  int extraout_RAX_14;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  uint extraout_RCX_01;
  int iVar12;
  int extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 uVar13;
  uint extraout_RCX_05;
  undefined8 extraout_RCX_06;
  int extraout_RCX_07;
  int extraout_RCX_08;
  uint extraout_RCX_09;
  undefined8 extraout_RCX_10;
  int extraout_RCX_11;
  int extraout_RCX_12;
  uint extraout_RCX_13;
  undefined8 extraout_RCX_14;
  int extraout_RCX_15;
  int iVar14;
  int extraout_RCX_16;
  uint uVar15;
  char extraout_BL;
  undefined8 extraout_RBX;
  undefined8 extraout_RBX_00;
  uint extraout_RBX_01;
  undefined8 **extraout_RBX_02;
  undefined8 extraout_RBX_03;
  char extraout_BL_00;
  uint extraout_RBX_04;
  uint extraout_RBX_05;
  uint extraout_RBX_06;
  undefined8 extraout_RBX_07;
  uint extraout_RBX_08;
  uint extraout_RBX_09;
  uint extraout_RBX_10;
  undefined8 extraout_RBX_11;
  uint extraout_RBX_12;
  uint uVar16;
  uint extraout_RBX_13;
  uint extraout_RBX_14;
  undefined8 extraout_RBX_15;
  undefined8 extraout_RSI;
  int extraout_RSI_00;
  undefined8 extraout_RDI;
  int extraout_R8;
  undefined8 extraout_R8_00;
  undefined8 extraout_R8_01;
  sdword *extraout_R8_02;
  sdword *psVar17;
  sdword *extraout_R8_03;
  sdword *extraout_R8_04;
  uint uVar18;
  undefined8 extraout_R9;
  undefined8 extraout_R9_00;
  undefined8 extraout_R9_01;
  undefined8 extraout_R10;
  undefined8 *extraout_R11;
  int *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  undefined8 *extraout_R11_03;
  int *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  int *extraout_R11_07;
  undefined8 *extraout_R11_08;
  undefined8 *extraout_R11_09;
  int *extraout_R11_10;
  undefined8 *extraout_R11_11;
  int unaff_R14;
  bool bVar19;
  undefined8 *in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar20 [16];
  undefined1 auVar21 [16];
  undefined1 auVar22 [16];
  sdword *psStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 uStack0000000000000018;
  undefined8 uStack0000000000000020;
  int iStack0000000000000028;
  int iStack0000000000000030;
  int iStack0000000000000038;
  char cStack0000000000000040;
  int iStack0000000000000048;
  undefined1 local_378 [32];
  undefined1 local_358 [24];
  undefined1 local_340 [8];
  undefined1 local_338 [32];
  undefined8 *local_318;
  int local_310;
  uint local_308;
  int local_300;
  int local_2f8;
  int local_2f0;
  undefined8 local_2e8;
  undefined8 local_2e0;
  uint local_2d8;
  uint local_2d0;
  undefined8 *local_2c8;
  undefined8 *local_2c0;
  uint local_2b8;
  uint local_2b0;
  uint local_2a8;
  int local_2a0;
  int local_298;
  uint local_290;
  uint local_288;
  undefined1 local_280 [32];
  undefined1 local_260 [120];
  undefined8 local_1e8;
  undefined8 local_1e0;
  undefined8 *puStack_1d8;
  undefined8 local_1d0;
  undefined8 local_1c8;
  undefined8 local_1c0;
  undefined8 local_1b8;
  undefined8 local_1b0;
  undefined8 **local_1a8;
  undefined8 *local_1a0;
  undefined8 local_198;
  undefined8 local_190;
  undefined8 local_188;
  undefined8 local_180;
  undefined8 local_178;
  undefined8 **local_170;
  undefined8 **local_168;
  undefined8 *local_160;
  undefined8 uStack_158;
  undefined8 *local_150;
  undefined8 uStack_148;
  undefined *local_140;
  undefined8 uStack_138;
  undefined *local_130;
  undefined8 uStack_128;
  undefined *local_120;
  undefined8 uStack_118;
  undefined *local_110;
  undefined8 uStack_108;
  undefined *local_100;
  undefined8 uStack_f8;
  undefined *local_f0;
  undefined8 uStack_e8;
  undefined *local_e0;
  undefined8 uStack_d8;
  code *local_d0;
  sdword *local_c8;
  code *local_c0;
  undefined *local_b8;
  undefined8 local_b0;
  undefined **local_a8;
  undefined8 local_a0;
  undefined8 local_98;
  undefined8 *local_90 [12];
  undefined *local_30;
  undefined8 uStack_28;
  char *local_20;
  char *local_18;
  code **local_10;
  
  psStack0000000000000008 = param_1;
  uStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  iStack0000000000000028 = param_5;
  uStack0000000000000020 = param_4;
  iStack0000000000000030 = param_6;
  iStack0000000000000038 = param_7;
  iStack0000000000000048 = param_9;
  cStack0000000000000040 = param_8;
  while (local_340 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  crypto_internal_fips140_sha256___Digest__Reset();
  runtime_stringtoslicebyte(local_338,uStack0000000000000010,uStack0000000000000018);
  crypto_internal_fips140_sha256___Digest__Write(local_260,extraout_RAX,extraout_RBX,extraout_RCX);
  uStack_28 = runtime_convT64(iStack0000000000000028);
  local_30 = &DAT_00dd2b80;
  auVar20 = fmt_Sprintf(&DAT_00efa6de,2,&local_30,1,1);
  runtime_stringtoslicebyte(local_358,auVar20._0_8_,auVar20._8_8_);
  crypto_internal_fips140_sha256___Digest__Write
            (local_260,extraout_RAX_00,extraout_RBX_00,extraout_RCX_00);
  local_90[0] = in_XMM15_Qa;
  runtime_mapIterStart(&DAT_00e16200,uStack0000000000000020);
  bVar19 = false;
  uVar16 = 0;
  uVar15 = 0;
  local_168 = (undefined8 **)0x0;
  while (local_90[0] != (undefined8 *)0x0) {
    uVar18 = uVar16 + 1;
    uVar10 = *local_90[0];
    puVar9 = (undefined8 *)local_90[0][1];
    if (uVar15 < uVar18) {
      local_2c0 = puVar9;
      local_198 = uVar10;
      if (((2 < (int)uVar18) || (bVar19)) || (uVar16 != 0)) {
        runtime_growslice(local_168,uVar18,uVar15,1,&DAT_00dd29c0);
        uVar15 = extraout_RCX_01;
        local_168 = extraout_RAX_01;
        puVar9 = local_2c0;
        uVar18 = extraout_RBX_01;
        uVar10 = local_198;
      }
      else {
        local_168 = &local_160;
        local_160 = in_XMM15_Qa;
        uStack_158 = in_XMM15_Qb;
        local_150 = in_XMM15_Qa;
        uStack_148 = in_XMM15_Qb;
        uVar15 = 2;
        bVar19 = true;
      }
    }
    iVar12 = (uVar18 - 1) * 0x10;
    local_168[(uVar18 - 1) * 2 + 1] = puVar9;
    local_2d8 = uVar18;
    local_2d0 = uVar15;
    if (runtime_writeBarrier._0_4_ != 0) {
      runtime_gcWriteBarrier2();
      *extraout_R11 = extraout_R10;
      extraout_R11[1] = extraout_RSI;
      iVar12 = extraout_RCX_02;
      local_168 = extraout_RBX_02;
      uVar10 = extraout_R10;
    }
    *(undefined8 *)((int)local_168 + iVar12) = uVar10;
    local_1a8 = local_168;
    runtime_mapIterNext(local_90);
    uVar16 = local_2d8;
    uVar15 = local_2d0;
    local_168 = local_1a8;
  }
  local_2d8 = uVar16;
  sort_Strings(local_168,uVar16,uVar15);
  iVar12 = 0;
  ppuVar11 = local_168;
  while (iVar12 < (int)local_2d8) {
    local_1a0 = *ppuVar11;
    local_2c8 = ppuVar11[1];
    local_288 = iVar12;
    local_170 = ppuVar11;
    puVar9 = (undefined8 *)runtime_mapaccess1_faststr(&DAT_00e16200,uStack0000000000000020);
    runtime_concatbyte3(local_378,local_1a0,local_2c8,&DAT_01133210,1,*puVar9,puVar9[1]);
    crypto_internal_fips140_sha256___Digest__Write
              (local_260,extraout_RAX_02,extraout_RBX_03,extraout_RCX_03);
    ppuVar11 = local_170 + 2;
    iVar12 = local_288 + 1;
  }
  auVar20 = crypto_internal_fips140_sha256___Digest__Sum(local_260,0,0,0);
  uVar16 = auVar20._8_8_ * 2;
  if (uVar16 < 0x21) {
    puVar8 = local_280;
  }
  else {
    local_308 = uVar16;
    local_2f8 = auVar20._8_8_;
    local_1d0 = auVar20._0_8_;
    puVar8 = (undefined1 *)runtime_makeslice(&DAT_00dd2a40,uVar16);
    auVar20._8_8_ = local_2f8;
    auVar20._0_8_ = local_1d0;
    uVar16 = local_308;
  }
  uVar15 = 0;
  for (iVar12 = 0; iVar12 < auVar20._8_8_; iVar12 = iVar12 + 1) {
    bVar2 = *(byte *)(auVar20._0_8_ + iVar12);
    if (uVar16 <= uVar15) {
                    /* WARNING: Subroutine does not return */
      runtime_panicBounds();
    }
    puVar8[uVar15] = (&DAT_00f1956c)[bVar2 >> 4];
    if (uVar16 <= uVar15 + 1) {
                    /* WARNING: Subroutine does not return */
      runtime_panicBounds();
    }
    puVar8[uVar15 + 1] = (&DAT_00f1956c)[bVar2 & 0xf];
    uVar15 = uVar15 + 2;
  }
  auVar21 = runtime_slicebytetostring(0,puVar8);
  local_318 = auVar21._8_8_;
  local_1e8 = auVar21._0_8_;
  LOCK();
  sVar1 = *psStack0000000000000008;
  if (sVar1 == 0) {
    *psStack0000000000000008 = 1;
  }
  UNLOCK();
  if (sVar1 != 0) {
    internal_sync___Mutex__lockSlow(psStack0000000000000008,local_318,local_1e8);
    auVar21._8_8_ = local_318;
    auVar21._0_8_ = local_1e8;
  }
  local_318 = auVar21._8_8_;
  local_1e8 = auVar21._0_8_;
  local_d0 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull_deferwrap1;
  local_c8 = psStack0000000000000008;
  local_10 = &local_d0;
  puVar9 = (undefined8 *)
           runtime_mapaccess2_faststr
                     (&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2),local_1e8,local_318
                     );
  if (extraout_BL != '\0') {
    uVar10 = *puVar9;
    if (iStack0000000000000048 != 0) {
      local_180 = *puVar9;
      mv_daemon_pkg_proxy___Downloader__SetRefresher();
      uVar10 = local_180;
    }
    if (cStack0000000000000040 != '\0') {
      mv_daemon_pkg_proxy___Downloader__SetPassthrough(uVar10,1);
    }
    ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
    uVar16 = *(uint *)(psStack0000000000000008 + 6);
    uVar15 = 0;
    psVar17 = psStack0000000000000008;
    puVar9 = local_318;
    local_288 = uVar16;
    do {
      if ((int)uVar16 <= (int)uVar15) {
LAB_00aa5f8b:
        uVar16 = *(int *)(psVar17 + 6) + 1;
        iVar12 = *(int *)(psVar17 + 4);
        if (*(uint *)(psVar17 + 8) < uVar16) {
          runtime_growslice();
          psVar17 = psStack0000000000000008;
          *(undefined8 *)(psStack0000000000000008 + 8) = extraout_RCX_14;
          iVar12 = extraout_RAX_12;
          uVar16 = extraout_RBX_13;
          if (runtime_writeBarrier._0_4_ != 0) {
            runtime_gcWriteBarrier2
                      (extraout_RAX_12,extraout_RBX_13,*(undefined8 *)(psStack0000000000000008 + 4))
            ;
            *extraout_R11_10 = extraout_RAX_13;
            extraout_R11_10[1] = extraout_RCX_15;
            iVar12 = extraout_RAX_13;
            uVar16 = extraout_RBX_14;
          }
          *(int *)(psVar17 + 4) = iVar12;
          puVar9 = local_318;
        }
        *(uint *)(psVar17 + 6) = uVar16;
        iVar14 = (uVar16 - 1) * 0x10;
        *(undefined8 **)(iVar12 + 8 + iVar14) = puVar9;
        if (runtime_writeBarrier._0_4_ != 0) {
          runtime_gcWriteBarrier2(iVar12,*(undefined8 *)(iVar14 + iVar12));
          *extraout_R11_11 = local_1e8;
          extraout_R11_11[1] = extraout_RBX_15;
          iVar12 = extraout_RAX_14;
          iVar14 = extraout_RCX_16;
        }
        *(undefined8 *)(iVar12 + iVar14) = local_1e8;
        local_1e0 = local_1e8;
        puStack_1d8 = puVar9;
        (**local_10)();
        auVar5._8_8_ = puStack_1d8;
        auVar5._0_8_ = local_1e0;
        return auVar5;
      }
      if ((puVar9 == ppuVar11[1]) &&
         (local_2a8 = uVar15, local_170 = ppuVar11, cVar7 = runtime_memequal(*ppuVar11,local_1e8),
         uVar15 = local_2a8, psVar17 = psStack0000000000000008, ppuVar11 = local_170,
         uVar16 = local_288, puVar9 = local_318, cVar7 != '\0')) {
        uVar16 = *(uint *)(psStack0000000000000008 + 8);
        if (uVar16 < local_2a8) {
                    /* WARNING: Subroutine does not return */
          runtime_panicBounds();
        }
        uVar15 = *(uint *)(psStack0000000000000008 + 6);
        if (uVar15 < local_2a8 + 1) {
                    /* WARNING: Subroutine does not return */
          runtime_panicBounds();
        }
        local_290 = uVar15 - 1;
        ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
        local_168 = (undefined8 **)
                    ((int)ppuVar11 +
                    ((local_2a8 + 1) * 0x10 & (int)-((uVar16 - local_2a8) + -1) >> 0x3f));
        local_288 = (uVar15 - local_2a8) + -1;
        if (uVar16 < local_290) {
          runtime_growslice(ppuVar11,local_290,uVar16,local_288,&DAT_00dd29c0);
          ppuVar11 = extraout_RAX_11;
          uVar16 = extraout_RCX_13;
          local_290 = extraout_RBX_12;
        }
        iVar12 = local_288;
        local_288 = uVar16;
        iVar14 = (int)local_168;
        local_168 = ppuVar11;
        runtime_typedslicecopy
                  (&DAT_00dd29c0,
                   (int)ppuVar11 + ((int)(local_2a8 - uVar16) >> 0x3f & local_2a8 << 4),
                   local_290 - local_2a8,iVar14,iVar12);
        *(uint *)(psStack0000000000000008 + 6) = local_290;
        *(uint *)(psStack0000000000000008 + 8) = local_288;
        psVar17 = psStack0000000000000008;
        if (runtime_writeBarrier._0_4_ != 0) {
          runtime_gcWriteBarrier2();
          *extraout_R11_09 = local_168;
          extraout_R11_09[1] = extraout_R9_01;
          psVar17 = extraout_R8_04;
        }
        *(undefined8 ***)(psVar17 + 4) = local_168;
        puVar9 = local_318;
        goto LAB_00aa5f8b;
      }
      ppuVar11 = ppuVar11 + 2;
      uVar15 = uVar15 + 1;
    } while( true );
  }
  while( true ) {
    psVar17 = psStack0000000000000008;
    if (*(int **)(psStack0000000000000008 + 2) == (int *)0x0) {
      iVar12 = 0;
    }
    else {
      iVar12 = **(int **)(psStack0000000000000008 + 2);
    }
    if ((iVar12 < *(int *)(psStack0000000000000008 + 10)) ||
       (*(int *)(psStack0000000000000008 + 6) == 0)) break;
    puVar9 = *(undefined8 **)(psStack0000000000000008 + 4);
    iVar12 = *(int *)(psStack0000000000000008 + 8);
    uVar10 = puVar9[1];
    uVar13 = *puVar9;
    *(int *)(psStack0000000000000008 + 6) = *(int *)(psStack0000000000000008 + 6) + -1;
    *(int *)(psStack0000000000000008 + 8) = iVar12 + -1;
    iVar12 = (uint)((dword)(-(iVar12 + -1) >> 0x3f) & 0x10) + (int)puVar9;
    if (runtime_writeBarrier._0_4_ != 0) {
      runtime_gcWriteBarrier2();
      *extraout_R11_00 = extraout_RSI_00;
      extraout_R11_00[1] = extraout_R8;
      uVar13 = extraout_RCX_04;
      iVar12 = extraout_RSI_00;
      uVar10 = extraout_RDI;
    }
    *(int *)(psVar17 + 4) = iVar12;
    local_2e8 = uVar10;
    local_1c0 = uVar13;
    puVar9 = (undefined8 *)runtime_mapaccess2_faststr(&DAT_00e18f00,*(undefined8 *)(psVar17 + 2));
    if (extraout_BL_00 != '\0') {
      local_1b8 = *puVar9;
      uStack_d8 = runtime_convTstring(local_1c0,local_2e8);
      local_e0 = &DAT_00dd29c0;
      local_c0 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull_Printf_func1;
      local_b0 = 0x30;
      local_b8 = &DAT_00f44a80;
      local_a0 = 1;
      local_98 = 1;
      local_a8 = &local_e0;
      log___Logger__output(log_std,0,2,&local_c0);
      mv_daemon_pkg_proxy___Downloader__Close(local_1b8);
      runtime_mapdelete_faststr
                (&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2),local_1c0,local_2e8);
    }
  }
  auVar22 = strings_ToLower(uStack0000000000000010,uStack0000000000000018);
  local_2e0 = auVar22._8_8_;
  local_1b0 = auVar22._0_8_;
  if (cStack0000000000000040 == '\0') {
    iVar12 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00efb583,4);
    if (iVar12 < 0) {
      iVar12 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00efb557,4);
      if (iVar12 < 0) {
        iVar12 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00efb84f,4);
        bVar19 = -1 < iVar12;
      }
      else {
        bVar19 = true;
      }
    }
    else {
      bVar19 = true;
    }
    auVar22._8_8_ = local_2e0;
    auVar22._0_8_ = local_1b0;
    if (bVar19) {
      bVar19 = true;
    }
    else {
      iVar12 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00efb5a7,4);
      auVar22._8_8_ = local_2e0;
      auVar22._0_8_ = local_1b0;
      auVar6._8_8_ = local_2e0;
      auVar6._0_8_ = local_1b0;
      if (iVar12 < 0) {
        bVar19 = iStack0000000000000028 < 1;
      }
      else {
        bVar19 = true;
        auVar22 = auVar6;
      }
    }
  }
  else {
    bVar19 = false;
  }
  local_2e0 = auVar22._8_8_;
  local_1b0 = auVar22._0_8_;
  if ((bVar19) || (cStack0000000000000040 != '\0')) {
    uStack_f8 = runtime_convTstring(uStack0000000000000010,uStack0000000000000018);
    local_100 = &DAT_00dd29c0;
    uStack_e8 = runtime_convT64(iStack0000000000000028);
    local_f0 = &DAT_00dd2b80;
    local_c0 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull_Printf_func2;
    local_b0 = 0x60;
    local_b8 = &DAT_00f5e8c1;
    local_a0 = 2;
    local_98 = 2;
    local_a8 = &local_100;
    log___Logger__output(log_std,0,2,&local_c0);
    local_188 = mv_daemon_pkg_proxy_NewDownloaderWithPassthrough
                          (uStack0000000000000010,uStack0000000000000018,uStack0000000000000020,
                           iStack0000000000000028,0x100000,0,0,1);
    mv_daemon_pkg_proxy___Downloader__SetRefresher(local_188,iStack0000000000000048);
    puVar9 = (undefined8 *)
             runtime_mapassign_faststr
                       (&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2),local_1e8,
                        local_318);
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_01 = local_188;
      extraout_R11_01[1] = extraout_R8_00;
    }
    *puVar9 = local_188;
    ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
    uVar16 = *(uint *)(psStack0000000000000008 + 6);
    uVar15 = 0;
    psVar17 = psStack0000000000000008;
    puVar9 = local_318;
    local_288 = uVar16;
    do {
      if ((int)uVar16 <= (int)uVar15) {
LAB_00aa5d0b:
        uVar16 = *(int *)(psVar17 + 6) + 1;
        iVar12 = *(int *)(psVar17 + 4);
        if (*(uint *)(psVar17 + 8) < uVar16) {
          runtime_growslice();
          psVar17 = psStack0000000000000008;
          *(undefined8 *)(psStack0000000000000008 + 8) = extraout_RCX_10;
          iVar12 = extraout_RAX_08;
          uVar16 = extraout_RBX_09;
          if (runtime_writeBarrier._0_4_ != 0) {
            runtime_gcWriteBarrier2
                      (extraout_RAX_08,extraout_RBX_09,*(undefined8 *)(psStack0000000000000008 + 4))
            ;
            *extraout_R11_07 = extraout_RAX_09;
            extraout_R11_07[1] = extraout_RCX_11;
            iVar12 = extraout_RAX_09;
            uVar16 = extraout_RBX_10;
          }
          *(int *)(psVar17 + 4) = iVar12;
          puVar9 = local_318;
        }
        *(uint *)(psVar17 + 6) = uVar16;
        iVar14 = (uVar16 - 1) * 0x10;
        *(undefined8 **)(iVar12 + 8 + iVar14) = puVar9;
        if (runtime_writeBarrier._0_4_ != 0) {
          runtime_gcWriteBarrier2(iVar12,*(undefined8 *)(iVar14 + iVar12));
          *extraout_R11_08 = local_1e8;
          extraout_R11_08[1] = extraout_RBX_11;
          iVar12 = extraout_RAX_10;
          iVar14 = extraout_RCX_12;
        }
        *(undefined8 *)(iVar12 + iVar14) = local_1e8;
        local_1e0 = local_1e8;
        puStack_1d8 = puVar9;
        (**local_10)();
        auVar4._8_8_ = puStack_1d8;
        auVar4._0_8_ = local_1e0;
        return auVar4;
      }
      if ((puVar9 == ppuVar11[1]) &&
         (local_2b0 = uVar15, local_170 = ppuVar11, cVar7 = runtime_memequal(*ppuVar11,local_1e8),
         uVar15 = local_2b0, psVar17 = psStack0000000000000008, ppuVar11 = local_170,
         uVar16 = local_288, puVar9 = local_318, cVar7 != '\0')) {
        local_290 = *(uint *)(psStack0000000000000008 + 8);
        if (local_290 < local_2b0) {
                    /* WARNING: Subroutine does not return */
          runtime_panicBounds();
        }
        uVar16 = *(uint *)(psStack0000000000000008 + 6);
        if (uVar16 < local_2b0 + 1) {
                    /* WARNING: Subroutine does not return */
          runtime_panicBounds();
        }
        uVar15 = uVar16 - 1;
        ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
        local_168 = (undefined8 **)
                    ((int)ppuVar11 +
                    ((local_2b0 + 1) * 0x10 & (int)-((local_290 - local_2b0) + -1) >> 0x3f));
        local_288 = (uVar16 - local_2b0) + -1;
        if (local_290 < uVar15) {
          runtime_growslice(ppuVar11,uVar15,local_290,local_288,&DAT_00dd29c0);
          ppuVar11 = extraout_RAX_07;
          local_290 = extraout_RCX_09;
          uVar15 = extraout_RBX_08;
        }
        iVar12 = local_288;
        local_288 = uVar15;
        iVar14 = (int)local_168;
        local_168 = ppuVar11;
        runtime_typedslicecopy
                  (&DAT_00dd29c0,
                   (int)ppuVar11 + ((int)(local_2b0 - local_290) >> 0x3f & local_2b0 << 4),
                   uVar15 - local_2b0,iVar14,iVar12);
        *(uint *)(psStack0000000000000008 + 6) = local_288;
        *(uint *)(psStack0000000000000008 + 8) = local_290;
        psVar17 = psStack0000000000000008;
        if (runtime_writeBarrier._0_4_ != 0) {
          runtime_gcWriteBarrier2();
          *extraout_R11_06 = local_168;
          extraout_R11_06[1] = extraout_R9_00;
          psVar17 = extraout_R8_03;
        }
        *(undefined8 ***)(psVar17 + 4) = local_168;
        puVar9 = local_318;
        goto LAB_00aa5d0b;
      }
      ppuVar11 = ppuVar11 + 2;
      uVar15 = uVar15 + 1;
    } while( true );
  }
  local_310 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00efc8bb,5);
  iVar12 = internal_stringslite_Index(local_1b0,local_2e0,&DAT_00f0d4bc,0xb);
  if (iVar12 < 0) {
    iVar12 = internal_stringslite_Index
                       (local_1b0,local_2e0,
                        "alipannetdnsdomaingophertelnet.locallisten.onionsendtoip+netsocketacceptwritev\n    \thangupkilledallow"
                        ,6);
    bVar19 = -1 < iVar12;
  }
  else {
    bVar19 = true;
  }
  local_300 = iStack0000000000000030;
  if (iStack0000000000000030 < 0x10) {
    local_300 = 0x10;
  }
  iVar12 = iStack0000000000000030;
  local_2a0 = iStack0000000000000038;
  if (0 < iStack0000000000000038) goto LAB_00aa5681;
  if (local_310 < 0) {
    if (!bVar19) goto LAB_00aa5681;
    if (-1 < local_310) goto LAB_00aa5411;
    if (bVar19) {
      if (mv_daemon_pkg_proxy_GlobalTokenStore.tab == (internal_abi_ITab *)0x0) {
        cVar7 = '\0';
      }
      else {
        auVar20 = (*(code *)(mv_daemon_pkg_proxy_GlobalTokenStore.tab)->Fun[0])
                            (mv_daemon_pkg_proxy_GlobalTokenStore.data,&DAT_00efe18b,6);
        if (auVar20._8_8_ == 0) {
          cVar7 = '\0';
        }
        else {
          local_298 = auVar20._8_8_;
          local_178 = auVar20._0_8_;
          local_18 = (char *)runtime_newobject(&DAT_00e0d840);
          runtime_stringtoslicebyte(0,local_178,local_298);
          encoding_json_Unmarshal();
          cVar7 = *local_18;
        }
      }
    }
    else {
      cVar7 = '\0';
    }
  }
  else {
LAB_00aa5411:
    if (mv_daemon_pkg_proxy_GlobalTokenStore.tab == (internal_abi_ITab *)0x0) {
      cVar7 = '\0';
    }
    else {
      auVar20 = (*(code *)(mv_daemon_pkg_proxy_GlobalTokenStore.tab)->Fun[0])
                          (mv_daemon_pkg_proxy_GlobalTokenStore.data,&DAT_00efc8c5,5);
      if (auVar20._8_8_ == 0) {
        cVar7 = '\0';
      }
      else {
        local_2f0 = auVar20._8_8_;
        local_1c8 = auVar20._0_8_;
        auVar20 = strings_TrimSpace();
        if (auVar20._8_8_ == 0) {
          bVar19 = false;
        }
        else {
          bVar19 = *auVar20._0_8_ == '{';
        }
        if (bVar19) {
          local_20 = (char *)runtime_newobject(&DAT_00e0d840);
          runtime_stringtoslicebyte(0,local_1c8,local_2f0);
          encoding_json_Unmarshal();
          cVar7 = *local_20;
        }
        else {
          cVar7 = '\0';
        }
      }
    }
  }
  if (cVar7 == '\0') {
    if (local_310 < 0) {
      iVar12 = 0x20;
      local_2a0 = 0x20000;
    }
    else {
      iVar12 = 0xc;
      local_2a0 = 0x80000;
    }
  }
  else {
    if (iStack0000000000000028 < 0x3c0000001) {
      if (iStack0000000000000028 < 0x140000001) {
        if (0x40000000 < iStack0000000000000028) {
          local_300 = 0x18;
        }
        local_2a0 = 0x80000;
        if (0x40000000 < iStack0000000000000028) {
          local_2a0 = 0x100000;
        }
      }
      else {
        local_300 = 0x20;
        local_2a0 = 0x200000;
      }
    }
    else {
      local_300 = 0x20;
      local_2a0 = 0x400000;
    }
    iVar12 = 8;
  }
LAB_00aa5681:
  if (local_2a0 < 1) {
    if (iStack0000000000000028 < 0x3c0000001) {
      if (iStack0000000000000028 < 0x140000001) {
        if (0x40000000 < iStack0000000000000028) {
          local_300 = 0x18;
        }
        local_2a0 = 0x100000;
      }
      else {
        local_300 = 0x20;
        local_2a0 = 0x200000;
      }
    }
    else {
      local_300 = 0x20;
      local_2a0 = 0x400000;
    }
  }
  else if (local_300 < 0x18) {
    if (local_2a0 < 0x800000) {
      local_300 = 0x20;
      if (0x3fffff < local_2a0) {
        local_300 = 0x18;
      }
    }
    else {
      local_300 = 0x10;
    }
  }
  local_288 = iVar12;
  uStack_138 = runtime_convT64();
  local_140 = &DAT_00dd2b80;
  uStack_128 = runtime_convT64(local_288);
  local_130 = &DAT_00dd2c00;
  uStack_118 = runtime_convT64(local_2a0);
  local_120 = &DAT_00dd2c00;
  uStack_108 = runtime_convT64(local_300);
  local_110 = &DAT_00dd2c00;
  local_c0 = mv_daemon_pkg_proxy___ProxyManager__RegisterFull_Printf_func3;
  local_b0 = 0x51;
  local_b8 = &DAT_00f59eb9;
  local_a0 = 4;
  local_98 = 4;
  local_a8 = &local_140;
  log___Logger__output(log_std,0,2,&local_c0);
  local_190 = mv_daemon_pkg_proxy_NewDownloaderWithPassthrough
                        (uStack0000000000000010,uStack0000000000000018,uStack0000000000000020,
                         iStack0000000000000028,local_2a0,local_300,local_288,0);
  mv_daemon_pkg_proxy___Downloader__SetRefresher(local_190,iStack0000000000000048);
  puVar9 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2),local_1e8,local_318
                     );
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_02 = local_190;
    extraout_R11_02[1] = extraout_R8_01;
  }
  *puVar9 = local_190;
  ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
  uVar16 = *(uint *)(psStack0000000000000008 + 6);
  uVar15 = 0;
  psVar17 = psStack0000000000000008;
  puVar9 = local_318;
  local_288 = uVar16;
  do {
    if ((int)uVar16 <= (int)uVar15) {
LAB_00aa5a8b:
      uVar16 = *(int *)(psVar17 + 6) + 1;
      iVar12 = *(int *)(psVar17 + 4);
      if (*(uint *)(psVar17 + 8) < uVar16) {
        runtime_growslice();
        psVar17 = psStack0000000000000008;
        *(undefined8 *)(psStack0000000000000008 + 8) = extraout_RCX_06;
        iVar12 = extraout_RAX_04;
        uVar16 = extraout_RBX_05;
        if (runtime_writeBarrier._0_4_ != 0) {
          runtime_gcWriteBarrier2
                    (extraout_RAX_04,extraout_RBX_05,*(undefined8 *)(psStack0000000000000008 + 4));
          *extraout_R11_04 = extraout_RAX_05;
          extraout_R11_04[1] = extraout_RCX_07;
          iVar12 = extraout_RAX_05;
          uVar16 = extraout_RBX_06;
        }
        *(int *)(psVar17 + 4) = iVar12;
        puVar9 = local_318;
      }
      *(uint *)(psVar17 + 6) = uVar16;
      iVar14 = (uVar16 - 1) * 0x10;
      *(undefined8 **)(iVar12 + 8 + iVar14) = puVar9;
      if (runtime_writeBarrier._0_4_ != 0) {
        runtime_gcWriteBarrier2(iVar12,*(undefined8 *)(iVar14 + iVar12));
        *extraout_R11_05 = local_1e8;
        extraout_R11_05[1] = extraout_RBX_07;
        iVar12 = extraout_RAX_06;
        iVar14 = extraout_RCX_08;
      }
      *(undefined8 *)(iVar12 + iVar14) = local_1e8;
      local_1e0 = local_1e8;
      puStack_1d8 = puVar9;
      (**local_10)();
      auVar3._8_8_ = puStack_1d8;
      auVar3._0_8_ = local_1e0;
      return auVar3;
    }
    if ((puVar9 == ppuVar11[1]) &&
       (local_2b8 = uVar15, local_170 = ppuVar11, cVar7 = runtime_memequal(*ppuVar11,local_1e8),
       uVar15 = local_2b8, psVar17 = psStack0000000000000008, ppuVar11 = local_170,
       uVar16 = local_288, puVar9 = local_318, cVar7 != '\0')) {
      local_290 = *(uint *)(psStack0000000000000008 + 8);
      if (local_290 < local_2b8) {
                    /* WARNING: Subroutine does not return */
        runtime_panicBounds();
      }
      uVar16 = *(uint *)(psStack0000000000000008 + 6);
      if (uVar16 < local_2b8 + 1) {
                    /* WARNING: Subroutine does not return */
        runtime_panicBounds();
      }
      uVar15 = uVar16 - 1;
      ppuVar11 = *(undefined8 ***)(psStack0000000000000008 + 4);
      local_168 = (undefined8 **)
                  ((int)ppuVar11 +
                  ((local_2b8 + 1) * 0x10 & (int)-((local_290 - local_2b8) + -1) >> 0x3f));
      local_288 = (uVar16 - local_2b8) + -1;
      if (local_290 < uVar15) {
        runtime_growslice(ppuVar11,uVar15,local_290,local_288,&DAT_00dd29c0);
        ppuVar11 = extraout_RAX_03;
        local_290 = extraout_RCX_05;
        uVar15 = extraout_RBX_04;
      }
      iVar12 = local_288;
      local_288 = uVar15;
      iVar14 = (int)local_168;
      local_168 = ppuVar11;
      runtime_typedslicecopy
                (&DAT_00dd29c0,
                 (int)ppuVar11 + ((int)(local_2b8 - local_290) >> 0x3f & local_2b8 << 4),
                 uVar15 - local_2b8,iVar14,iVar12);
      *(uint *)(psStack0000000000000008 + 6) = local_288;
      *(uint *)(psStack0000000000000008 + 8) = local_290;
      psVar17 = psStack0000000000000008;
      if (runtime_writeBarrier._0_4_ != 0) {
        runtime_gcWriteBarrier2();
        *extraout_R11_03 = local_168;
        extraout_R11_03[1] = extraout_R9;
        psVar17 = extraout_R8_02;
      }
      *(undefined8 ***)(psVar17 + 4) = local_168;
      puVar9 = local_318;
      goto LAB_00aa5a8b;
    }
    ppuVar11 = ppuVar11 + 2;
    uVar15 = uVar15 + 1;
  } while( true );
}

