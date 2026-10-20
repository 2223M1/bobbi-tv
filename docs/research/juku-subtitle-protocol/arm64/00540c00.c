/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).resolve115Subtitles */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__resolve115Subtitles
          (undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,
          undefined8 param_5,undefined8 param_6,undefined8 param_7,undefined8 param_8,
          undefined8 param_9,undefined8 param_10,undefined8 param_11,undefined8 param_12,
          undefined8 param_13,undefined8 param_14)

{
  int iVar1;
  undefined1 *puVar2;
  undefined1 *puVar3;
  undefined8 *puVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  byte *pbVar7;
  undefined1 *puVar8;
  undefined8 extraout_x0;
  undefined8 extraout_x0_00;
  int extraout_x0_01;
  int extraout_x0_02;
  undefined8 extraout_x0_03;
  undefined8 extraout_x0_04;
  int extraout_x0_05;
  int iVar11;
  int iVar12;
  int extraout_x1;
  int extraout_x1_00;
  uint extraout_x1_01;
  int extraout_x1_02;
  uint extraout_x1_03;
  int extraout_x1_04;
  int extraout_x1_05;
  uint extraout_x1_06;
  undefined8 extraout_x2;
  undefined8 extraout_x2_00;
  uint extraout_x2_01;
  undefined1 auVar10 [24];
  uint extraout_x2_02;
  undefined8 extraout_x2_03;
  undefined8 extraout_x2_04;
  uint extraout_x2_05;
  uint uVar13;
  int extraout_x3;
  int extraout_x3_00;
  int extraout_x3_01;
  int extraout_x3_02;
  uint uVar14;
  int extraout_x4;
  int extraout_x4_00;
  int iVar15;
  byte bVar16;
  char *pcVar17;
  undefined8 uVar18;
  undefined8 uVar19;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 uVar20;
  undefined1 auVar21 [16];
  undefined8 local_338 [62];
  undefined8 local_148 [25];
  int local_80 [16];
  int *piVar9;
  
  for (; (undefined1 *)((int)register0x00000008 + -0x2b0) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
    *(undefined8 *)((int)register0x00000008 + 0x28) = param_5;
    *(undefined8 *)((int)register0x00000008 + 0x30) = param_6;
    *(undefined8 *)((int)register0x00000008 + 0x38) = param_7;
    *(undefined8 *)((int)register0x00000008 + 0x40) = param_8;
    *(undefined8 *)((int)register0x00000008 + 0x48) = param_9;
    *(undefined8 *)((int)register0x00000008 + 0x50) = param_10;
    *(undefined8 *)((int)register0x00000008 + 0x58) = param_11;
    *(undefined8 *)((int)register0x00000008 + 0x60) = param_12;
    *(undefined8 *)((int)register0x00000008 + 0x68) = param_13;
    *(undefined8 *)((int)register0x00000008 + 0x70) = param_14;
    in_x30 = 0x541404;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
    param_4 = *(undefined8 *)((int)register0x00000008 + 0x28);
    param_5 = *(undefined8 *)((int)register0x00000008 + 0x30);
    param_6 = *(undefined8 *)((int)register0x00000008 + 0x38);
    param_7 = *(undefined8 *)((int)register0x00000008 + 0x40);
    param_8 = *(undefined8 *)((int)register0x00000008 + 0x48);
    param_9 = *(undefined8 *)((int)register0x00000008 + 0x50);
    param_10 = *(undefined8 *)((int)register0x00000008 + 0x58);
    param_11 = *(undefined8 *)((int)register0x00000008 + 0x60);
    param_12 = *(undefined8 *)((int)register0x00000008 + 0x68);
    param_13 = *(undefined8 *)((int)register0x00000008 + 0x70);
    param_14 = *(undefined8 *)((int)register0x00000008 + 0x78);
  }
  *(undefined8 *)((int)register0x00000008 + -0x338) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x330) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x30) = param_6;
  *(undefined8 *)((int)register0x00000008 + 0x28) = param_5;
  *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
  *(undefined8 *)((int)register0x00000008 + 0x70) = param_14;
  *(undefined8 *)((int)register0x00000008 + 0x68) = param_13;
  *(undefined8 *)((int)register0x00000008 + 0x58) = param_11;
  *(undefined8 *)((int)register0x00000008 + 0x50) = param_10;
  *(undefined8 *)((int)register0x00000008 + 0x38) = param_7;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + 0x48) = param_9;
  *(undefined8 *)((int)register0x00000008 + 0x40) = param_8;
  *(undefined8 *)((int)register0x00000008 + -0x80) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x78) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x70) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x68) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x60) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x58) = 0;
  iVar11 = 3;
  puVar6 = (undefined8 *)((int)register0x00000008 + -0x148);
  do {
    *puVar6 = 0;
    puVar6[1] = 0;
    puVar6[2] = 0;
    puVar6[3] = 0;
    puVar6[4] = 0;
    puVar6[5] = 0;
    puVar4 = puVar6 + 8;
    puVar6[6] = 0;
    puVar6[7] = 0;
    iVar11 = iVar11 + -1;
    puVar6 = puVar4;
  } while (iVar11 != 0);
  *puVar4 = 0;
  *(undefined1 **)((int)register0x00000008 + -0x148) = &DAT_8080808080808080;
  *(undefined1 **)((int)register0x00000008 + -0x70) =
       (undefined1 *)((int)register0x00000008 + -0x148);
  uVar5 = runtime_rand();
  puVar2 = (undefined1 *)((int)register0x00000008 + -0x328);
  *(undefined8 *)((int)register0x00000008 + -0x70) = uVar5;
  puVar6 = *(undefined8 **)((int)register0x00000008 + 0x58);
  iVar12 = *(int *)((int)register0x00000008 + 0x60);
  iVar11 = 0;
  uVar13 = 0;
  uVar14 = 0;
  iVar15 = 0;
  while( true ) {
    *(uint *)(puVar2 + 0x90) = uVar13;
    *(uint *)(puVar2 + 0x88) = uVar14;
    *(int *)(puVar2 + 0x110) = iVar15;
    if (iVar12 <= iVar11) break;
    *(int *)(puVar2 + 0x108) = iVar11;
    *(undefined8 **)(puVar2 + 800) = puVar6;
    uVar5 = puVar6[2];
    *(undefined8 *)(puVar2 + 0x100) = puVar6[3];
    *(undefined8 *)(puVar2 + 0x318) = uVar5;
    uVar5 = *puVar6;
    iVar1 = puVar6[1];
    *(int *)(puVar2 + 0xf8) = iVar1;
    *(undefined8 *)(puVar2 + 0x310) = uVar5;
    if (iVar1 == 0) {
      bVar16 = 1;
      uVar18 = 0;
    }
    else {
      pbVar7 = (byte *)runtime_mapaccess1_faststr(&DAT_008ecb60,puVar2 + 0x2b0,uVar5,iVar1);
      bVar16 = *pbVar7;
      puVar6 = *(undefined8 **)(puVar2 + 0x328);
      iVar12 = *(int *)(puVar2 + 0x390);
      iVar11 = *(int *)(puVar2 + 0x110);
      uVar13 = *(uint *)(puVar2 + 0x98);
      iVar15 = *(int *)(puVar2 + 0x118);
      uVar5 = *(undefined8 *)(puVar2 + 0x318);
      uVar18 = *(undefined8 *)(puVar2 + 0x100);
      uVar14 = *(uint *)(puVar2 + 0x90);
      puVar2 = puVar2 + 8;
    }
    if ((bVar16 & 1) == 0) {
      puVar8 = (undefined1 *)runtime_mapassign_faststr(&DAT_008ecb60,puVar2 + 0x2b0,uVar5,uVar18);
      *puVar8 = 1;
      mv_daemon_provider_get115WindowsShareDownurl
                (*(undefined8 *)(puVar2 + 0x348),*(undefined8 *)(puVar2 + 0x350),
                 *(undefined8 *)(puVar2 + 0x358),*(undefined8 *)(puVar2 + 0x360),
                 *(undefined8 *)(puVar2 + 0x318),*(undefined8 *)(puVar2 + 0x100),
                 *(undefined8 *)(puVar2 + 0x3a0),*(undefined8 *)(puVar2 + 0x3a8));
      if ((extraout_x4 != 0) ||
         (puVar8 = puVar2 + 0x10, uVar18 = extraout_x0, iVar15 = extraout_x1, uVar5 = extraout_x2,
         iVar11 = extraout_x3, extraout_x1 == 0)) {
        mv_daemon_provider_get115ShareDownurl
                  (*(undefined8 *)(puVar2 + 0x350),*(undefined8 *)(puVar2 + 0x358),
                   *(undefined8 *)(puVar2 + 0x360),*(undefined8 *)(puVar2 + 0x368),
                   *(undefined8 *)(puVar2 + 800),*(undefined8 *)(puVar2 + 0x108),
                   *(undefined8 *)(puVar2 + 0x3a8),*(undefined8 *)(puVar2 + 0x3b0),0,0,0);
        puVar8 = puVar2 + 0x18;
        uVar18 = extraout_x0_00;
        iVar15 = extraout_x1_00;
        uVar5 = extraout_x2_00;
        iVar11 = extraout_x3_00;
      }
      puVar2 = puVar8;
      if (iVar15 == 0) {
        uVar13 = *(uint *)(puVar2 + 0x90);
        uVar14 = *(uint *)(puVar2 + 0x88);
        iVar15 = *(int *)(puVar2 + 0x110);
      }
      else {
        uVar14 = *(int *)(puVar2 + 0x88) + 1;
        iVar12 = *(int *)(puVar2 + 0x100);
        if (iVar12 != 0) {
          iVar11 = iVar12;
        }
        if (iVar12 != 0) {
          uVar5 = *(undefined8 *)(puVar2 + 0x318);
        }
        *(undefined8 *)(puVar2 + 0x120) = uVar5;
        *(int *)(puVar2 + 0x128) = iVar11;
        *(undefined8 *)(puVar2 + 0x130) = uVar18;
        *(int *)(puVar2 + 0x138) = iVar15;
        *(undefined8 *)(puVar2 + 0x140) = 100;
        uVar13 = *(uint *)(puVar2 + 0x90);
        if (uVar13 < uVar14) {
          runtime_growslice(*(undefined8 *)(puVar2 + 0x110),uVar14,uVar13,1,&DAT_00940fa0);
          puVar8 = puVar2 + 8;
          iVar15 = extraout_x0_01;
          uVar14 = extraout_x1_01;
          uVar13 = extraout_x2_01;
        }
        else {
          iVar15 = *(int *)(puVar2 + 0x110);
          puVar8 = puVar2;
        }
        puVar6 = (undefined8 *)(iVar15 + uVar14 * 0x28 + -0x28);
        puVar2 = puVar8;
        if (runtime_writeBarrier._0_4_ != 0) {
          *(int *)(puVar8 + 0x308) = iVar15;
          *(uint *)(puVar8 + 0xf0) = uVar14;
          *(uint *)(puVar8 + 0xe8) = uVar13;
          *(undefined8 **)(puVar8 + 0x300) = puVar6;
          runtime_wbMove(&DAT_00940fa0,puVar6,puVar8 + 0x120);
          puVar2 = puVar8 + 8;
          iVar15 = *(int *)(puVar8 + 0x310);
          uVar14 = *(uint *)(puVar8 + 0xf8);
          uVar13 = *(uint *)(puVar8 + 0xf0);
          puVar6 = *(undefined8 **)(puVar8 + 0x308);
        }
        uVar18 = *(undefined8 *)(puVar2 + 0x128);
        uVar5 = *(undefined8 *)(puVar2 + 0x130);
        uVar20 = *(undefined8 *)(puVar2 + 0x138);
        uVar19 = *(undefined8 *)(puVar2 + 0x140);
        *puVar6 = *(undefined8 *)(puVar2 + 0x120);
        puVar6[1] = uVar18;
        puVar6[2] = uVar5;
        puVar6[3] = uVar20;
        puVar6[4] = uVar19;
      }
      puVar6 = *(undefined8 **)(puVar2 + 800);
      iVar12 = *(int *)(puVar2 + 0x388);
      iVar11 = *(int *)(puVar2 + 0x108);
    }
    puVar6 = puVar6 + 4;
    iVar11 = iVar11 + 1;
  }
  if ((uVar14 == 0) && (iVar11 = *(int *)(puVar2 + 0x368), iVar11 != 0)) {
    if (iVar11 == 1) {
      pcVar17 = *(char **)(puVar2 + 0x360);
      if (*pcVar17 == '0') goto LAB_00540f64;
    }
    else {
      pcVar17 = *(char **)(puVar2 + 0x360);
    }
    auVar21 = mv_daemon_provider_cloud115ListFilesSinglePage
                        (*(undefined8 *)(puVar2 + 0x340),*(undefined8 *)(puVar2 + 0x348),
                         *(undefined8 *)(puVar2 + 0x350),*(undefined8 *)(puVar2 + 0x358),pcVar17,
                         iVar11,1,100);
    piVar9 = auVar21._0_8_;
    if (auVar21._8_8_ == 0) {
      if (piVar9 == (int *)0x0) {
        uVar13 = *(uint *)(puVar2 + 0x98);
        uVar14 = *(uint *)(puVar2 + 0x90);
        iVar15 = *(int *)(puVar2 + 0x118);
      }
      else {
        puVar6 = (undefined8 *)*piVar9;
        iVar11 = piVar9[1];
        if (iVar11 == 0) {
          uVar13 = *(uint *)(puVar2 + 0x98);
          uVar14 = *(uint *)(puVar2 + 0x90);
          iVar15 = *(int *)(puVar2 + 0x118);
        }
        else {
          *(int *)(puVar2 + 0x110) = iVar11;
          iVar15 = 0;
          uVar13 = 0;
          uVar14 = 0;
          iVar12 = 0;
          puVar2 = puVar2 + 8;
          while( true ) {
            *(uint *)(puVar2 + 0xb0) = uVar13;
            *(uint *)(puVar2 + 0xa8) = uVar14;
            *(int *)(puVar2 + 400) = iVar12;
            if (iVar11 <= iVar15) break;
            uVar5 = puVar6[1];
            uVar18 = puVar6[2];
            uVar20 = puVar6[3];
            *(undefined8 *)(puVar2 + 0x120) = *puVar6;
            *(undefined8 *)(puVar2 + 0x128) = uVar5;
            *(undefined8 *)(puVar2 + 0x130) = uVar18;
            *(undefined8 *)(puVar2 + 0x138) = uVar20;
            uVar5 = puVar6[5];
            uVar18 = puVar6[6];
            uVar20 = puVar6[7];
            *(undefined8 *)(puVar2 + 0x140) = puVar6[4];
            *(undefined8 *)(puVar2 + 0x148) = uVar5;
            *(undefined8 *)(puVar2 + 0x150) = uVar18;
            *(undefined8 *)(puVar2 + 0x158) = uVar20;
            uVar5 = puVar6[9];
            uVar18 = puVar6[10];
            uVar20 = puVar6[0xb];
            *(undefined8 *)(puVar2 + 0x160) = puVar6[8];
            *(undefined8 *)(puVar2 + 0x168) = uVar5;
            *(undefined8 *)(puVar2 + 0x170) = uVar18;
            *(undefined8 *)(puVar2 + 0x178) = uVar20;
            uVar5 = puVar6[0xd];
            *(undefined8 *)(puVar2 + 0x180) = puVar6[0xc];
            *(undefined8 *)(puVar2 + 0x188) = uVar5;
            puVar8 = puVar2;
            if ((puVar2[0x140] & 1) == 0) {
              *(int *)(puVar2 + 0x100) = iVar15;
              *(undefined8 **)(puVar2 + 800) = puVar6;
              mv_daemon_matcher_InferSubtitleMimeType
                        (*(undefined8 *)(puVar2 + 0x130),*(undefined8 *)(puVar2 + 0x138));
              puVar8 = puVar2 + 8;
              if (extraout_x1_02 == 0) {
                iVar15 = *(int *)(puVar2 + 0x108);
                puVar6 = *(undefined8 **)(puVar2 + 0x328);
                iVar11 = *(int *)(puVar2 + 0x110);
                uVar13 = *(uint *)(puVar2 + 0xb8);
                uVar14 = *(uint *)(puVar2 + 0xb0);
                iVar12 = *(int *)(puVar2 + 0x198);
              }
              else {
                auVar21 = mv_daemon_provider_CleanPanFileId
                                    (*(undefined8 *)(puVar2 + 0x128),*(undefined8 *)(puVar2 + 0x130)
                                    );
                iVar11 = auVar21._8_8_;
                puVar8 = puVar2 + 0x10;
                if (iVar11 == 0) {
                  uVar13 = *(uint *)(puVar2 + 0xc0);
                  uVar14 = *(uint *)(puVar2 + 0xb8);
                  iVar12 = *(int *)(puVar2 + 0x1a0);
                }
                else {
                  *(int *)(puVar2 + 0xa8) = iVar11;
                  *(int *)(puVar2 + 0x128) = auVar21._0_8_;
                  pbVar7 = (byte *)runtime_mapaccess1_faststr
                                             (&DAT_008ecb60,puVar2 + 0x2c0,auVar21._0_8_,iVar11);
                  puVar8 = puVar2 + 0x18;
                  if ((*pbVar7 & 1) == 0) {
                    *(undefined8 *)(puVar2 + 0x1b0) = 0;
                    *(undefined8 *)(puVar2 + 0x1b8) = 0;
                    *(undefined8 *)(puVar2 + 0x1c0) = 0;
                    *(undefined8 *)(puVar2 + 0x1c8) = 0;
                    *(undefined8 *)(puVar2 + 0x1d0) = 0;
                    *(undefined8 *)(puVar2 + 0x1d8) = 0;
                    *(undefined8 *)(puVar2 + 0x1e0) = 0;
                    *(undefined8 *)(puVar2 + 0x1e8) = 0;
                    *(undefined8 *)(puVar2 + 0x1f0) = 0;
                    *(undefined8 *)(puVar2 + 0x1f8) = 0;
                    *(undefined8 *)(puVar2 + 0x1b0) = *(undefined8 *)(puVar2 + 0x130);
                    *(undefined8 *)(puVar2 + 0x1b8) = *(undefined8 *)(puVar2 + 0xb0);
                    *(int *)(puVar2 + 0x110) = *(int *)(puVar2 + 0xc0) + 1;
                    *(undefined8 *)(puVar2 + 0x1c0) = *(undefined8 *)(puVar2 + 0x148);
                    *(undefined8 *)(puVar2 + 0x1c8) = *(undefined8 *)(puVar2 + 0x150);
                    auVar21 = runtime_concatstring4
                                        (0,&DAT_009dd4e7,9,*(undefined8 *)(puVar2 + 0x358),
                                         *(undefined8 *)(puVar2 + 0x360),&DAT_00c0a628,1,
                                         *(undefined8 *)(puVar2 + 0x378),
                                         *(undefined8 *)(puVar2 + 0x380));
                    puVar3 = puVar2 + 0x20;
                    *(undefined1 (*) [16])(puVar2 + 0x1d8) = auVar21;
                    *(undefined8 *)(puVar2 + 0x1e8) = *(undefined8 *)(puVar2 + 0x138);
                    *(undefined8 *)(puVar2 + 0x1f0) = *(undefined8 *)(puVar2 + 0xb8);
                    uVar13 = *(uint *)(puVar2 + 0xd0);
                    uVar14 = *(uint *)(puVar2 + 0x118);
                    if (uVar13 < uVar14) {
                      runtime_growslice(*(undefined8 *)(puVar2 + 0x1b0),uVar14,uVar13,1,
                                        &DAT_0096d7a0);
                      puVar3 = puVar2 + 0x28;
                      iVar12 = extraout_x0_02;
                      uVar14 = extraout_x1_03;
                      uVar13 = extraout_x2_02;
                    }
                    else {
                      iVar12 = *(int *)(puVar2 + 0x1b0);
                    }
                    puVar6 = (undefined8 *)(iVar12 + uVar14 * 0x50 + -0x50);
                    puVar8 = puVar3;
                    if (runtime_writeBarrier._0_4_ != 0) {
                      *(int *)(puVar3 + 0x2f8) = iVar12;
                      *(uint *)(puVar3 + 0xe0) = uVar14;
                      *(uint *)(puVar3 + 0xd8) = uVar13;
                      *(undefined8 **)(puVar3 + 0x2f0) = puVar6;
                      runtime_wbMove(&DAT_0096d7a0,puVar6,puVar3 + 0x198);
                      puVar8 = puVar3 + 8;
                      iVar12 = *(int *)(puVar3 + 0x300);
                      uVar14 = *(uint *)(puVar3 + 0xe8);
                      uVar13 = *(uint *)(puVar3 + 0xe0);
                      puVar6 = *(undefined8 **)(puVar3 + 0x2f8);
                    }
                    uVar5 = *(undefined8 *)(puVar8 + 0x1a0);
                    uVar18 = *(undefined8 *)(puVar8 + 0x1a8);
                    uVar20 = *(undefined8 *)(puVar8 + 0x1b0);
                    *puVar6 = *(undefined8 *)(puVar8 + 0x198);
                    puVar6[1] = uVar5;
                    puVar6[2] = uVar18;
                    puVar6[3] = uVar20;
                    uVar5 = *(undefined8 *)(puVar8 + 0x1c0);
                    uVar18 = *(undefined8 *)(puVar8 + 0x1c8);
                    uVar20 = *(undefined8 *)(puVar8 + 0x1d0);
                    puVar6[4] = *(undefined8 *)(puVar8 + 0x1b8);
                    puVar6[5] = uVar5;
                    puVar6[6] = uVar18;
                    puVar6[7] = uVar20;
                    uVar5 = *(undefined8 *)(puVar8 + 0x1e0);
                    puVar6[8] = *(undefined8 *)(puVar8 + 0x1d8);
                    puVar6[9] = uVar5;
                  }
                  else {
                    uVar13 = *(uint *)(puVar2 + 200);
                    uVar14 = *(uint *)(puVar2 + 0xc0);
                    iVar12 = *(int *)(puVar2 + 0x1a8);
                  }
                }
                puVar6 = *(undefined8 **)(puVar8 + 800);
                iVar11 = *(int *)(puVar8 + 0x108);
                iVar15 = *(int *)(puVar8 + 0x100);
              }
            }
            puVar6 = puVar6 + 0xe;
            iVar15 = iVar15 + 1;
            puVar2 = puVar8;
          }
          if (uVar14 == 0) {
            uVar14 = *(uint *)(puVar2 + 0x88);
            uVar13 = *(uint *)(puVar2 + 0x90);
            iVar15 = *(int *)(puVar2 + 0x110);
          }
          else {
            auVar21 = runtime_concatstring4
                                (puVar2 + 0x68,&DAT_009dd4e7,9,*(undefined8 *)(puVar2 + 0x340),
                                 *(undefined8 *)(puVar2 + 0x348),&DAT_00c0a628,1,
                                 *(undefined8 *)(puVar2 + 0x360),*(undefined8 *)(puVar2 + 0x368));
            auVar21 = mv_daemon_provider_MatchAndConvertSubtitles
                                (*(undefined8 *)(puVar2 + 0x378),*(undefined8 *)(puVar2 + 0x380),
                                 auVar21._0_8_,auVar21._8_8_,*(undefined8 *)(puVar2 + 0x198),
                                 *(undefined8 *)(puVar2 + 0xb0),*(undefined8 *)(puVar2 + 0xb8));
            *(int *)(puVar2 + 0xb0) = auVar21._8_8_;
            uVar13 = *(uint *)(puVar2 + 0xa0);
            iVar15 = *(int *)(puVar2 + 0x120);
            uVar14 = *(uint *)(puVar2 + 0x98);
            iVar11 = 0;
            puVar2 = puVar2 + 0x10;
            while (puVar6 = auVar21._0_8_, iVar11 < auVar21._8_8_) {
              *(uint *)(puVar2 + 0xd0) = uVar13;
              *(int *)(puVar2 + 0x108) = iVar11;
              *(uint *)(puVar2 + 200) = uVar14;
              *(int *)(puVar2 + 0x2e8) = iVar15;
              *(undefined8 **)(puVar2 + 800) = puVar6;
              uVar18 = puVar6[1];
              uVar5 = puVar6[2];
              uVar20 = puVar6[3];
              uVar19 = puVar6[4];
              *(undefined8 *)(puVar2 + 0x120) = *puVar6;
              *(undefined8 *)(puVar2 + 0x128) = uVar18;
              *(undefined8 *)(puVar2 + 0x130) = uVar5;
              *(undefined8 *)(puVar2 + 0x138) = uVar20;
              *(undefined8 *)(puVar2 + 0x140) = uVar19;
              pbVar7 = (byte *)runtime_mapaccess1_faststr
                                         (&DAT_008ecb60,puVar2 + 0x2b0,
                                          *(undefined8 *)(puVar2 + 0x130),
                                          *(undefined8 *)(puVar2 + 0x138));
              puVar8 = puVar2 + 8;
              if ((*pbVar7 & 1) == 0) {
                puVar8 = (undefined1 *)
                         runtime_mapassign_faststr
                                   (&DAT_008ecb60,puVar2 + 0x2b8,*(undefined8 *)(puVar2 + 0x138),
                                    *(undefined8 *)(puVar2 + 0x140));
                *puVar8 = 1;
                mv_daemon_provider_get115WindowsShareDownurl
                          (*(undefined8 *)(puVar2 + 0x350),*(undefined8 *)(puVar2 + 0x358),
                           *(undefined8 *)(puVar2 + 0x360),*(undefined8 *)(puVar2 + 0x368),
                           *(undefined8 *)(puVar2 + 0x140),*(undefined8 *)(puVar2 + 0x148),
                           *(undefined8 *)(puVar2 + 0x3a8),*(undefined8 *)(puVar2 + 0x3b0));
                puVar8 = puVar2 + 0x18;
                if ((extraout_x4_00 != 0) ||
                   (uVar18 = extraout_x0_03, iVar15 = extraout_x1_04, uVar5 = extraout_x2_03,
                   iVar11 = extraout_x3_01, extraout_x1_04 == 0)) {
                  mv_daemon_provider_get115ShareDownurl
                            (*(undefined8 *)(puVar2 + 0x358),*(undefined8 *)(puVar2 + 0x360),
                             *(undefined8 *)(puVar2 + 0x368),*(undefined8 *)(puVar2 + 0x370),
                             *(undefined8 *)(puVar2 + 0x148),*(undefined8 *)(puVar2 + 0x150),
                             *(undefined8 *)(puVar2 + 0x3b0),*(undefined8 *)(puVar2 + 0x3b8),0,0,0);
                  puVar8 = puVar2 + 0x20;
                  uVar18 = extraout_x0_04;
                  iVar15 = extraout_x1_05;
                  uVar5 = extraout_x2_04;
                  iVar11 = extraout_x3_02;
                }
                if (iVar15 == 0) {
                  uVar14 = *(uint *)(puVar8 + 200);
                  uVar13 = *(uint *)(puVar8 + 0xd0);
                  iVar15 = *(int *)(puVar8 + 0x2e8);
                }
                else {
                  if (iVar11 == 0) {
                    uVar5 = *(undefined8 *)(puVar8 + 0x120);
                    iVar11 = *(int *)(puVar8 + 0x128);
                  }
                  *(undefined8 *)(puVar8 + 0x120) = uVar5;
                  *(int *)(puVar8 + 0x128) = iVar11;
                  *(undefined8 *)(puVar8 + 0x130) = uVar18;
                  *(int *)(puVar8 + 0x138) = iVar15;
                  *(undefined8 *)(puVar8 + 0x140) = 100;
                  uVar14 = *(int *)(puVar8 + 200) + 1;
                  uVar13 = *(uint *)(puVar8 + 0xd0);
                  if (uVar13 < uVar14) {
                    runtime_growslice(*(undefined8 *)(puVar8 + 0x2e8),uVar14,uVar13,1,&DAT_00940fa0)
                    ;
                    puVar2 = puVar8 + 8;
                    iVar15 = extraout_x0_05;
                    uVar14 = extraout_x1_06;
                    uVar13 = extraout_x2_05;
                  }
                  else {
                    iVar15 = *(int *)(puVar8 + 0x2e8);
                    puVar2 = puVar8;
                  }
                  puVar6 = (undefined8 *)(iVar15 + uVar14 * 0x28 + -0x28);
                  puVar8 = puVar2;
                  if (runtime_writeBarrier._0_4_ != 0) {
                    *(int *)(puVar2 + 0x2e0) = iVar15;
                    *(uint *)(puVar2 + 0xc0) = uVar14;
                    *(uint *)(puVar2 + 0xb8) = uVar13;
                    *(undefined8 **)(puVar2 + 0x308) = puVar6;
                    runtime_wbMove(&DAT_00940fa0,puVar6,puVar2 + 0x120);
                    puVar8 = puVar2 + 8;
                    iVar15 = *(int *)(puVar2 + 0x2e8);
                    uVar14 = *(uint *)(puVar2 + 200);
                    uVar13 = *(uint *)(puVar2 + 0xc0);
                    puVar6 = *(undefined8 **)(puVar2 + 0x310);
                  }
                  uVar18 = *(undefined8 *)(puVar8 + 0x128);
                  uVar5 = *(undefined8 *)(puVar8 + 0x130);
                  uVar20 = *(undefined8 *)(puVar8 + 0x138);
                  uVar19 = *(undefined8 *)(puVar8 + 0x140);
                  *puVar6 = *(undefined8 *)(puVar8 + 0x120);
                  puVar6[1] = uVar18;
                  puVar6[2] = uVar5;
                  puVar6[3] = uVar20;
                  puVar6[4] = uVar19;
                }
              }
              else {
                uVar13 = *(uint *)(puVar2 + 0xd8);
                uVar14 = *(uint *)(puVar2 + 0xd0);
                iVar15 = *(int *)(puVar2 + 0x2f0);
              }
              auVar21._8_8_ = *(undefined8 *)(puVar8 + 0xa0);
              auVar21._0_8_ = *(int *)(puVar8 + 800) + 0x28;
              puVar2 = puVar8;
              iVar11 = *(int *)(puVar8 + 0x108) + 1;
            }
          }
        }
      }
    }
    else {
      uVar13 = *(uint *)(puVar2 + 0x98);
      uVar14 = *(uint *)(puVar2 + 0x90);
      iVar15 = *(int *)(puVar2 + 0x118);
    }
  }
LAB_00540f64:
  auVar10._8_8_ = uVar14;
  auVar10._0_8_ = iVar15;
  auVar10._16_8_ = uVar13;
  return auVar10;
}

