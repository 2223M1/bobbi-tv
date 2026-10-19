/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ExtractSubFidsFromUrl */

undefined1  [24] mv_daemon_provider_ExtractSubFidsFromUrl(undefined8 param_1,int param_2)

{
  int iVar1;
  undefined8 *puVar2;
  undefined1 *puVar3;
  undefined1 *puVar4;
  undefined8 uVar5;
  int *piVar6;
  undefined8 extraout_x0;
  byte *pbVar7;
  undefined1 *puVar8;
  undefined8 *extraout_x0_00;
  uint extraout_x0_01;
  undefined8 *extraout_x0_02;
  int iVar12;
  int iVar13;
  undefined1 auVar9 [24];
  undefined1 auVar10 [24];
  undefined8 extraout_x1;
  undefined8 uVar14;
  uint extraout_x1_00;
  uint extraout_x1_01;
  uint extraout_x1_02;
  int extraout_x2;
  uint extraout_x2_00;
  uint extraout_x2_01;
  uint extraout_x2_02;
  undefined1 auVar11 [24];
  uint uVar15;
  undefined8 *extraout_x3;
  byte bVar16;
  undefined8 *puVar17;
  undefined8 extraout_x4;
  uint uVar18;
  uint uVar19;
  undefined8 *extraout_x6;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar20 [16];
  undefined8 local_208 [19];
  int local_170 [8];
  undefined8 local_130 [8];
  undefined8 local_f0 [25];
  undefined8 local_28 [5];
  
  for (; (undefined8 *)((int)register0x00000008 + -0x180) <= *(undefined8 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(int *)((int)register0x00000008 + 0x10) = param_2;
    in_x30 = 0x55a534;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(int *)((int)register0x00000008 + 0x18);
  }
  *(undefined8 *)((int)register0x00000008 + -0x208) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x200) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 8) = param_1;
  if (param_2 != 0) {
    *(int *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    uVar5 = regexp_MustCompile(&DAT_00a1eaa4,0x33);
    auVar20 = regexp___Regexp__FindAllStringSubmatch
                        (uVar5,*(undefined8 *)((int)register0x00000008 + 0x10),
                         *(undefined8 *)((int)register0x00000008 + 0x18),0xffffffffffffffff);
    if (auVar20._8_8_ != 0) {
      *(int *)((int)register0x00000008 + -0x170) = auVar20._8_8_;
      *(int *)((int)register0x00000008 + -0x130) = auVar20._0_8_;
      *(undefined8 *)((int)register0x00000008 + -0x28) = 0;
      *(undefined8 *)((int)register0x00000008 + -0x20) = 0;
      *(undefined8 *)((int)register0x00000008 + -0x18) = 0;
      *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
      *(undefined8 *)((int)register0x00000008 + -8) = 0;
      *(undefined8 *)register0x00000008 = 0;
      iVar12 = 3;
      puVar17 = (undefined8 *)((int)register0x00000008 + -0xf0);
      do {
        *puVar17 = 0;
        puVar17[1] = 0;
        puVar17[2] = 0;
        puVar17[3] = 0;
        puVar17[4] = 0;
        puVar17[5] = 0;
        puVar2 = puVar17 + 8;
        puVar17[6] = 0;
        puVar17[7] = 0;
        iVar12 = iVar12 + -1;
        puVar17 = puVar2;
      } while (iVar12 != 0);
      *puVar2 = 0;
      *(undefined1 **)((int)register0x00000008 + -0xf0) = &DAT_8080808080808080;
      *(undefined8 **)((int)register0x00000008 + -0x18) =
           (undefined8 *)((int)register0x00000008 + -0xf0);
      uVar5 = runtime_rand();
      *(undefined8 *)((int)register0x00000008 + -0x18) = uVar5;
      piVar6 = *(int **)((int)register0x00000008 + -0x128);
      iVar13 = *(int *)((int)register0x00000008 + -0x168);
      uVar15 = 0;
      puVar17 = (undefined8 *)0x0;
      uVar18 = 0;
      uVar19 = 0;
      puVar2 = (undefined8 *)((int)register0x00000008 + -0x1e8);
      for (iVar12 = 0; iVar12 < iVar13; iVar12 = iVar12 + 1) {
        iVar1 = *piVar6;
        puVar3 = (undefined1 *)puVar2;
        if (1 < piVar6[1]) {
          *(int *)((int)puVar2 + 0xa0) = iVar12;
          *(int **)((int)puVar2 + 0xd8) = piVar6;
          *(char *)((int)puVar2 + 0x57) = (char)uVar15;
          *(uint *)((int)puVar2 + 0x70) = uVar19;
          *(uint *)((int)puVar2 + 0x68) = uVar18;
          *(undefined8 **)((int)puVar2 + 0xb0) = puVar17;
          uVar5 = *(undefined8 *)(iVar1 + 0x10);
          uVar14 = *(undefined8 *)(iVar1 + 0x18);
          *(undefined8 *)((int)puVar2 + 0x60) = uVar14;
          *(undefined8 *)((int)puVar2 + 0xa8) = uVar5;
          net_url_unescape(uVar5,uVar14,2);
          uVar5 = extraout_x1;
          if (extraout_x2 != 0) {
            uVar5 = *(undefined8 *)((int)puVar2 + 0x68);
          }
          uVar14 = extraout_x0;
          if (extraout_x2 != 0) {
            uVar14 = *(undefined8 *)((int)puVar2 + 0xb0);
          }
          auVar20 = strings_genSplit(uVar14,uVar5,&DAT_00c0a5f0,1,0,0xffffffffffffffff);
          puVar3 = (undefined1 *)((int)puVar2 + 0x10);
          *(int *)((int)puVar2 + 0x68) = auVar20._8_8_;
          uVar15 = (uint)*(byte *)((int)puVar2 + 0x67);
          uVar19 = *(uint *)((int)puVar2 + 0x80);
          uVar18 = *(uint *)((int)puVar2 + 0x78);
          puVar17 = *(undefined8 **)((int)puVar2 + 0xc0);
          iVar12 = 0;
          while (puVar2 = auVar20._0_8_, iVar12 < auVar20._8_8_) {
            *(int *)(puVar3 + 0x98) = iVar12;
            puVar3[0x56] = (char)uVar15;
            *(uint *)(puVar3 + 0x90) = uVar19;
            *(uint *)(puVar3 + 0x88) = uVar18;
            *(undefined8 **)(puVar3 + 0xd0) = puVar17;
            *(undefined8 **)(puVar3 + 200) = puVar2;
            auVar20 = strings_TrimSpace(*puVar2,puVar2[1]);
            iVar12 = auVar20._8_8_;
            uVar5 = auVar20._0_8_;
            *(undefined8 *)(puVar3 + 0xc0) = uVar5;
            *(int *)(puVar3 + 0x80) = iVar12;
            if (iVar12 == 0) {
              bVar16 = 0;
              uVar14 = 0;
              puVar3 = puVar3 + 8;
            }
            else {
              pbVar7 = (byte *)runtime_mapaccess1_faststr(&DAT_008ecb60,puVar3 + 0x1d0,uVar5,iVar12)
              ;
              bVar16 = *pbVar7 ^ 1;
              uVar5 = *(undefined8 *)(puVar3 + 200);
              uVar14 = *(undefined8 *)(puVar3 + 0x88);
              puVar3 = puVar3 + 0x10;
            }
            if ((bVar16 & 1) == 0) {
              uVar18 = *(uint *)(puVar3 + 0x88);
              uVar19 = *(uint *)(puVar3 + 0x90);
              uVar15 = (uint)(byte)puVar3[0x56];
              puVar17 = *(undefined8 **)(puVar3 + 0xd0);
            }
            else {
              puVar8 = (undefined1 *)
                       runtime_mapassign_faststr(&DAT_008ecb60,puVar3 + 0x1c8,uVar5,uVar14);
              puVar4 = puVar3 + 8;
              *puVar8 = 1;
              uVar18 = *(int *)(puVar3 + 0x90) + 1;
              uVar19 = *(uint *)(puVar3 + 0x98);
              if (uVar19 < uVar18) {
                if ((((int)uVar18 < 3) && ((puVar3[0x5e] & 1) == 0)) &&
                   (*(int *)(puVar3 + 0x90) == 0)) {
                  puVar17 = (undefined8 *)(puVar3 + 0xe8);
                  *puVar17 = 0;
                  *(undefined8 *)(puVar3 + 0xf0) = 0;
                  *(undefined8 *)(puVar3 + 0xf8) = 0;
                  *(undefined8 *)(puVar3 + 0x100) = 0;
                  uVar19 = 2;
                  uVar15 = 1;
                }
                else {
                  runtime_growslice(*(undefined8 *)(puVar3 + 0xd8),uVar18,uVar19,1,&DAT_008a6880);
                  puVar4 = puVar3 + 0x10;
                  uVar15 = (uint)(byte)puVar3[0x66];
                  uVar18 = extraout_x1_00;
                  uVar19 = extraout_x2_00;
                  puVar17 = extraout_x0_00;
                }
              }
              else {
                puVar17 = *(undefined8 **)(puVar3 + 0xd8);
                uVar15 = (uint)(byte)puVar3[0x5e];
                puVar4 = puVar3 + 8;
              }
              puVar2 = puVar17 + (uVar18 - 1) * 2;
              puVar2[1] = *(undefined8 *)(puVar4 + 0x78);
              if (runtime_writeBarrier._0_4_ == 0) {
                uVar5 = *(undefined8 *)(puVar4 + 0xb8);
                puVar3 = puVar4;
              }
              else {
                runtime_gcWriteBarrier2();
                puVar3 = puVar4 + 8;
                uVar5 = *(undefined8 *)(puVar4 + 0xc0);
                *in_x25 = uVar5;
                in_x25[1] = extraout_x4;
                uVar15 = extraout_x0_01;
                uVar18 = extraout_x1_01;
                uVar19 = extraout_x2_01;
                puVar2 = extraout_x3;
                puVar17 = extraout_x6;
              }
              *puVar2 = uVar5;
            }
            auVar20._8_8_ = *(undefined8 *)(puVar3 + 0x58);
            auVar20._0_8_ = *(int *)(puVar3 + 200) + 0x10;
            iVar12 = *(int *)(puVar3 + 0x98) + 1;
          }
          piVar6 = *(int **)(puVar3 + 0xd8);
          iVar13 = *(int *)(puVar3 + 0x80);
          iVar12 = *(int *)(puVar3 + 0xa0);
        }
        piVar6 = piVar6 + 3;
        puVar2 = (undefined8 *)puVar3;
      }
      if ((uint)((int)puVar17 - (int)puVar2) < 0x200) {
        runtime_moveSliceNoCap(&DAT_008a6880,puVar17,uVar18);
        puVar17 = extraout_x0_02;
        uVar18 = extraout_x1_02;
        uVar19 = extraout_x2_02;
      }
      auVar11._8_8_ = uVar18;
      auVar11._0_8_ = puVar17;
      auVar11._16_8_ = uVar19;
      return auVar11;
    }
    auVar9._0_16_ = ZEXT816(0);
    auVar9._16_8_ = 0;
    return auVar9;
  }
  auVar10._0_16_ = ZEXT816(0);
  auVar10._16_8_ = 0;
  return auVar10;
}

