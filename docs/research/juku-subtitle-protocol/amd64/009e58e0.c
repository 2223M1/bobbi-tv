/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ExtractSubFidsFromUrl */

undefined1  [24] mv_daemon_provider_ExtractSubFidsFromUrl(undefined8 param_1,int param_2)

{
  char cVar1;
  undefined8 uVar2;
  int *piVar3;
  undefined8 extraout_RAX;
  undefined8 *puVar4;
  byte *pbVar5;
  undefined1 *puVar6;
  undefined8 *extraout_RAX_00;
  undefined8 *extraout_RAX_01;
  sdword sVar10;
  int extraout_RCX;
  byte bVar12;
  undefined1 auVar7 [24];
  undefined1 auVar8 [24];
  uint extraout_RCX_00;
  uint uVar11;
  uint extraout_RCX_01;
  uint extraout_RCX_02;
  int iVar13;
  uint uVar14;
  undefined1 auVar9 [24];
  undefined8 extraout_RBX;
  uint extraout_RBX_00;
  uint extraout_RBX_01;
  undefined8 *puVar15;
  undefined8 uVar16;
  int iVar17;
  int extraout_RSI;
  undefined8 extraout_RDI;
  undefined8 *extraout_R8;
  int iVar18;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar19 [16];
  undefined1 auVar20 [16];
  undefined8 uStack0000000000000008;
  int iStack0000000000000010;
  undefined1 auStack_1f0 [70];
  char local_1aa;
  char local_1a9;
  int local_1a8;
  undefined8 local_1a0;
  uint local_198;
  uint local_190;
  int local_188;
  int local_180;
  uint local_178;
  uint local_170;
  int local_168;
  int local_160;
  undefined8 local_158;
  undefined8 *local_150;
  undefined8 local_148;
  int *local_140;
  undefined8 *local_138;
  undefined8 *local_130;
  int *local_128;
  undefined8 local_120;
  undefined8 uStack_118;
  undefined8 local_110;
  undefined8 uStack_108;
  undefined8 local_100 [25];
  undefined1 local_38 [8];
  undefined8 uStack_30;
  undefined8 *local_28;
  
  uStack0000000000000008 = param_1;
  iStack0000000000000010 = param_2;
  while (&local_170 <= *(uint **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  if (iStack0000000000000010 == 0) {
    auVar8._0_16_ = ZEXT816(0);
    auVar8._16_8_ = 0;
    return auVar8;
  }
  uVar2 = regexp_MustCompile(&DAT_00f475cf,0x33);
  auVar19 = regexp___Regexp__FindAllStringSubmatch
                      (uVar2,uStack0000000000000008,iStack0000000000000010,0xffffffffffffffff);
  local_180 = auVar19._8_8_;
  local_140 = auVar19._0_8_;
  if (local_180 == 0) {
    auVar7._0_16_ = ZEXT816(0);
    auVar7._16_8_ = 0;
    return auVar7;
  }
  sVar10 = 3;
  puVar15 = local_100;
  do {
    puVar4 = puVar15;
    *puVar4 = in_XMM15_Qa;
    puVar4[1] = in_XMM15_Qb;
    puVar4[2] = in_XMM15_Qa;
    puVar4[3] = in_XMM15_Qb;
    puVar4[4] = in_XMM15_Qa;
    puVar4[5] = in_XMM15_Qb;
    puVar4[6] = in_XMM15_Qa;
    puVar4[7] = in_XMM15_Qb;
    sVar10 = sVar10 + -1;
    puVar15 = puVar4 + 8;
  } while (sVar10 != 0);
  puVar4[7] = in_XMM15_Qa;
  puVar4[8] = in_XMM15_Qb;
  local_100[0] = 0x8080808080808080;
  local_28 = local_100;
  uStack_30 = runtime_rand();
  auVar19._8_8_ = local_188;
  auVar19._0_8_ = local_148;
  iVar13 = 0;
  cVar1 = '\0';
  puVar15 = (undefined8 *)0x0;
  uVar14 = 0;
  uVar11 = 0;
  piVar3 = local_140;
  iVar17 = local_180;
  while( true ) {
    local_188 = auVar19._8_8_;
    local_148 = auVar19._0_8_;
    if (iVar17 <= iVar13) break;
    if (1 < piVar3[1]) {
      local_1a0 = *(undefined8 *)(*piVar3 + 0x18);
      local_158 = *(undefined8 *)(*piVar3 + 0x10);
      local_1a9 = cVar1;
      local_198 = uVar14;
      local_190 = uVar11;
      local_160 = iVar13;
      local_150 = puVar15;
      local_128 = piVar3;
      net_url_unescape(local_158,local_1a0,2);
      uVar16 = local_158;
      uVar2 = local_1a0;
      if (extraout_RCX == 0) {
        uVar16 = extraout_RAX;
        uVar2 = extraout_RBX;
      }
      auVar20 = strings_genSplit(uVar16,uVar2,&DAT_011331d8,1,0,0xffffffffffffffff);
      auVar19._8_8_ = local_188;
      auVar19._0_8_ = local_148;
      iVar18 = 0;
      uVar11 = local_190;
      uVar14 = local_198;
      puVar15 = local_150;
      cVar1 = local_1a9;
      while( true ) {
        local_188 = auVar19._8_8_;
        local_148 = auVar19._0_8_;
        local_1a8 = auVar20._8_8_;
        puVar4 = auVar20._0_8_;
        piVar3 = local_128;
        iVar17 = local_180;
        iVar13 = local_160;
        if (local_1a8 <= iVar18) break;
        local_1aa = cVar1;
        local_178 = uVar14;
        local_170 = uVar11;
        local_168 = iVar18;
        local_138 = puVar4;
        local_130 = puVar15;
        auVar19 = strings_TrimSpace(*puVar4,puVar4[1]);
        local_188 = auVar19._8_8_;
        local_148 = auVar19._0_8_;
        if (local_188 == 0) {
          bVar12 = 0;
        }
        else {
          pbVar5 = (byte *)runtime_mapaccess1_faststr(&DAT_00e16280,local_38,local_148,local_188);
          auVar19._8_8_ = local_188;
          auVar19._0_8_ = local_148;
          bVar12 = *pbVar5 ^ 1;
        }
        local_188 = auVar19._8_8_;
        local_148 = auVar19._0_8_;
        uVar11 = local_170;
        uVar14 = local_178;
        puVar15 = local_130;
        cVar1 = local_1aa;
        if (bVar12 != 0) {
          puVar6 = (undefined1 *)
                   runtime_mapassign_faststr(&DAT_00e16280,local_38,local_148,local_188);
          *puVar6 = 1;
          uVar14 = local_178 + 1;
          uVar11 = local_170;
          puVar15 = local_130;
          cVar1 = local_1aa;
          if (local_170 < uVar14) {
            if ((((int)uVar14 < 3) && (local_1aa == '\0')) && (local_178 == 0)) {
              local_120 = in_XMM15_Qa;
              uStack_118 = in_XMM15_Qb;
              local_110 = in_XMM15_Qa;
              uStack_108 = in_XMM15_Qb;
              uVar11 = 2;
              puVar15 = &local_120;
              cVar1 = '\x01';
            }
            else {
              runtime_growslice(local_130,uVar14,local_170,1,&DAT_00dd29c0);
              uVar11 = extraout_RCX_00;
              uVar14 = extraout_RBX_00;
              puVar15 = extraout_RAX_00;
              cVar1 = local_1aa;
            }
          }
          iVar17 = (uVar14 - 1) * 0x10;
          puVar15[(uVar14 - 1) * 2 + 1] = local_188;
          if (runtime_writeBarrier._0_4_ != 0) {
            cVar1 = runtime_gcWriteBarrier2();
            *extraout_R11 = local_148;
            extraout_R11[1] = extraout_RDI;
            uVar11 = extraout_RCX_01;
            iVar17 = extraout_RSI;
            puVar15 = extraout_R8;
          }
          auVar19._8_8_ = local_188;
          auVar19._0_8_ = local_148;
          *(undefined8 *)((int)puVar15 + iVar17) = local_148;
        }
        auVar20._8_8_ = local_1a8;
        auVar20._0_8_ = local_138 + 2;
        iVar18 = local_168 + 1;
      }
    }
    piVar3 = piVar3 + 3;
    iVar13 = iVar13 + 1;
  }
  if ((uint)((int)puVar15 - (int)auStack_1f0) < 0x1f8) {
    runtime_moveSliceNoCap(&DAT_00dd29c0,puVar15,uVar14);
    puVar15 = extraout_RAX_01;
    uVar14 = extraout_RBX_01;
    uVar11 = extraout_RCX_02;
  }
  auVar9._8_8_ = uVar14;
  auVar9._0_8_ = puVar15;
  auVar9._16_8_ = uVar11;
  return auVar9;
}

