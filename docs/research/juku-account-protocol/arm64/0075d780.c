/* Reconstructed pseudocode, not original Go source: main.handleManualInput */

void main_handleManualInput(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined1 (*pauVar1) [16];
  undefined8 *puVar2;
  undefined1 *puVar3;
  undefined1 *puVar4;
  undefined1 *puVar5;
  undefined1 *puVar6;
  undefined1 *puVar7;
  undefined8 uVar8;
  undefined8 *puVar9;
  int iVar10;
  undefined8 extraout_x0;
  undefined8 extraout_x1;
  uint extraout_x1_00;
  undefined8 *extraout_x2;
  undefined8 extraout_x3;
  undefined8 extraout_x4;
  undefined8 extraout_x5;
  int *piVar11;
  uint uVar12;
  int iVar13;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar14 [16];
  undefined1 auVar15 [16];
  undefined8 local_108 [11];
  undefined8 local_b0 [15];
  undefined1 auStack_38 [48];
  undefined8 local_8;
  
  for (; (undefined8 *)((int)register0x00000008 + -0x80) <= *(undefined8 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75dce0;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x108) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x100) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar8 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -0xa0) = uVar8;
  auVar14 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)((int)register0x00000008 + -8) = auVar14._0_8_;
  *(int *)((int)register0x00000008 + -0xb0) = auVar14._8_8_;
  puVar9 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -8) = puVar9;
  *puVar9 = &DAT_009f0b73;
  puVar9[1] = 0x10;
  puVar9 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -0x90),
                      *(undefined8 *)register0x00000008,
                      *(undefined8 *)((int)register0x00000008 + -0xa8));
  puVar2 = (undefined8 *)((int)register0x00000008 + -0xe0);
  puVar9[1] = 1;
  puVar9[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar8 = *(undefined8 *)register0x00000008;
  }
  else {
    puVar9 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar2 = (undefined8 *)((int)register0x00000008 + -0xd8);
    uVar8 = *(undefined8 *)((int)register0x00000008 + 8);
    *in_x25 = uVar8;
    in_x25[1] = extraout_x5;
  }
  *puVar9 = uVar8;
  if ((*(undefined8 **)((int)puVar2 + 0x118))[1] == 4) {
    if (*(sdword *)**(undefined8 **)((int)puVar2 + 0x118) == 0x54534f50) {
      uVar8 = runtime_newobject(&DAT_009053e0);
      *(undefined8 *)((int)puVar2 + 0xf8) = uVar8;
      iVar10 = *(int *)(*(int *)((int)puVar2 + 0x120) + 0x40);
      *(undefined8 *)((int)puVar2 + 0x58) = *(undefined8 *)(*(int *)((int)puVar2 + 0x120) + 0x48);
      uVar8 = 0;
      puVar5 = (undefined1 *)((int)puVar2 + 8);
      if (iVar10 != 0) {
        uVar12 = (uint)*(dword *)(iVar10 + 0x10);
        do {
          iVar13 = (uVar12 & *(uint *)main__typeAssert_35) * 0x10;
          if (*(int *)(main__typeAssert_35 + iVar13 + 8) == *(int *)(iVar10 + 8)) {
            uVar8 = *(undefined8 *)(main__typeAssert_35 + iVar13 + 0x10);
            puVar5 = (undefined1 *)((int)puVar2 + 8);
            goto LAB_0075d8c8;
          }
          uVar12 = uVar12 + 1;
        } while (*(int *)(main__typeAssert_35 + iVar13 + 8) != 0);
        uVar8 = runtime_typeAssert(&main__typeAssert_35,*(int *)(iVar10 + 8));
        puVar5 = (undefined1 *)((int)puVar2 + 0x10);
      }
LAB_0075d8c8:
      *(undefined8 *)(puVar5 + 0xe8) = uVar8;
      puVar9 = (undefined8 *)runtime_newobject(&DAT_00991b80);
      puVar3 = puVar5 + 8;
      *puVar9 = *(undefined8 *)(puVar5 + 0xf0);
      if (runtime_writeBarrier._0_4_ == 0) {
        uVar8 = *(undefined8 *)(puVar5 + 0x58);
      }
      else {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        puVar3 = puVar5 + 0x10;
        uVar8 = *(undefined8 *)(puVar5 + 0x60);
        *in_x25 = uVar8;
      }
      puVar9[1] = uVar8;
      iVar10 = encoding_json___Decoder__Decode(puVar9,&DAT_008941e0,*(undefined8 *)(puVar3 + 0xf0));
      if (iVar10 != 0) {
        main_writeJsonError(*(undefined8 *)(puVar3 + 0x110),*(undefined8 *)(puVar3 + 0x118),
                            &DAT_009e435a,0xb,400);
        return;
      }
      auVar14 = main_getRealProvider
                          (**(undefined8 **)(puVar3 + 0xf8),(*(undefined8 **)(puVar3 + 0xf8))[1]);
      puVar4 = puVar3 + 0x10;
      puVar9 = *(undefined8 **)(puVar3 + 0x100);
      puVar9[1] = auVar14._8_8_;
      if (runtime_writeBarrier._0_4_ != 0) {
        runtime_gcWriteBarrier2();
        auVar14._8_8_ = extraout_x1;
        auVar14._0_8_ = extraout_x0;
        puVar4 = puVar3 + 0x18;
        *in_x25 = extraout_x0;
        in_x25[1] = extraout_x4;
        puVar9 = extraout_x2;
      }
      *puVar9 = auVar14._0_8_;
      runtime_mapaccess2_faststr(&DAT_008edb60,main_providers,auVar14._0_8_,auVar14._8_8_);
      if ((extraout_x1_00 & 1) == 0) {
        main_writeJsonError(*(undefined8 *)(puVar4 + 0x110),*(undefined8 *)(puVar4 + 0x118),
                            &DAT_009f0ba3,0x10,400);
        return;
      }
      piVar11 = *(int **)(puVar4 + 0xf8);
      pauVar1 = (undefined1 (*) [16])(piVar11 + 2);
      iVar10 = *(int *)*pauVar1;
      iVar13 = piVar11[3];
      puVar5 = puVar4 + 8;
      auVar15 = *pauVar1;
      if (((piVar11[1] == 6) &&
          (puVar5 = puVar4 + 8, auVar15 = *pauVar1, *(sdword *)*piVar11 == 0x59494c41)) &&
         (puVar5 = puVar4 + 8, auVar15 = *pauVar1, (short)((sdword *)*piVar11)[1] == 0x4e55)) {
        *(int *)(puVar4 + 0x38) = iVar13;
        *(int *)(puVar4 + 0x50) = iVar10;
        iVar10 = internal_stringslite_Index(iVar10,iVar13,&DAT_009eec2e,0xf);
        puVar5 = puVar4 + 0x10;
        if (iVar10 < 0) {
          *(undefined8 *)(puVar4 + 0xd0) = 0;
          *(undefined8 *)(puVar4 + 0xd8) = 0;
          uVar8 = runtime_convTstring(*(undefined8 *)(puVar4 + 0x58),*(undefined8 *)(puVar4 + 0x40))
          ;
          *(undefined8 **)(puVar4 + 0xd8) = &DAT_008a6880;
          *(undefined8 *)(puVar4 + 0xe0) = uVar8;
          auVar15 = fmt_Sprintf(&DAT_009f65d7,0x13,puVar4 + 0xd8,1,1);
          puVar5 = puVar4 + 0x20;
        }
        else {
          auVar15._8_8_ = *(undefined8 *)(puVar4 + 0x40);
          auVar15._0_8_ = *(undefined8 *)(puVar4 + 0x58);
        }
        piVar11 = *(int **)(puVar5 + 0xf0);
      }
      puVar6 = puVar5;
      if (piVar11[1] == 6) {
        if (*(sdword *)*piVar11 == 0x4c4e5558) {
          if ((short)((sdword *)*piVar11)[1] == 0x4945) {
            *(int *)(puVar5 + 0x38) = auVar15._8_8_;
            *(int *)(puVar5 + 0xd8) = auVar15._0_8_;
            iVar10 = internal_stringslite_Index(auVar15._0_8_,auVar15._8_8_,&DAT_009eec2e,0xf);
            puVar6 = puVar5 + 8;
            if (iVar10 < 0) {
              iVar10 = internal_stringslite_Index
                                 (*(undefined8 *)(puVar5 + 0xe0),*(undefined8 *)(puVar5 + 0x40),
                                  &DAT_009ec9e3,0xe);
              puVar6 = puVar5 + 0x10;
              if (iVar10 < 0) {
                *(undefined8 *)(puVar5 + 0xd0) = 0;
                *(undefined8 *)(puVar5 + 0xd8) = 0;
                uVar8 = runtime_convTstring(*(undefined8 *)(puVar5 + 0xe8),
                                            *(undefined8 *)(puVar5 + 0x48));
                *(undefined8 **)(puVar5 + 0xd8) = &DAT_008a6880;
                *(undefined8 *)(puVar5 + 0xe0) = uVar8;
                auVar15 = fmt_Sprintf(&DAT_009f65d7,0x13,puVar5 + 0xd8,1,1);
                puVar6 = puVar5 + 0x20;
              }
              else {
                auVar15._8_8_ = *(undefined8 *)(puVar5 + 0x48);
                auVar15._0_8_ = *(undefined8 *)(puVar5 + 0xe8);
              }
            }
            else {
              auVar15._8_8_ = *(undefined8 *)(puVar5 + 0x40);
              auVar15._0_8_ = *(undefined8 *)(puVar5 + 0xe0);
            }
            piVar11 = *(int **)(puVar6 + 0xf0);
          }
        }
      }
      puVar5 = puVar6;
      if (main_tokenStore != (mv_daemon_provider_TokenStore *)0x0) {
        auVar14 = mv_daemon_provider___TokenStore__Save
                            (main_tokenStore,*piVar11,piVar11[1],auVar15._0_8_,auVar15._8_8_);
        puVar5 = puVar6 + 8;
        if (auVar14._0_8_ != 0) {
          auVar14 = (**(code **)(auVar14._0_8_ + 0x18))(auVar14._8_8_);
          auVar14 = runtime_concatstring2(0,&DAT_009fafd8,0x16,auVar14._0_8_,auVar14._8_8_);
          main_writeJsonError(*(undefined8 *)(puVar6 + 0x120),*(undefined8 *)(puVar6 + 0x128),
                              auVar14._0_8_,auVar14._8_8_,500);
          return;
        }
      }
      iVar10 = *(int *)(puVar5 + 0x108);
      uVar8 = 0;
      if (iVar10 != 0) {
        uVar12 = (uint)*(dword *)(iVar10 + 0x10);
        do {
          iVar13 = (uVar12 & *(uint *)main__typeAssert_36) * 0x10;
          if (*(int *)(main__typeAssert_36 + iVar13 + 8) == *(int *)(iVar10 + 8)) {
            uVar8 = *(undefined8 *)(main__typeAssert_36 + iVar13 + 0x10);
            goto LAB_0075dbb8;
          }
          uVar12 = uVar12 + 1;
        } while (*(int *)(main__typeAssert_36 + iVar13 + 8) != 0);
        uVar8 = runtime_typeAssert(&main__typeAssert_36);
        puVar5 = puVar5 + 8;
      }
LAB_0075dbb8:
      *(undefined8 *)(puVar5 + 0x60) = 0;
      *(undefined8 *)(puVar5 + 0x68) = 0;
      *(undefined8 *)(puVar5 + 0x70) = 0;
      *(undefined8 *)(puVar5 + 0x78) = 0;
      *(undefined8 *)(puVar5 + 0x80) = 0;
      *(undefined8 *)(puVar5 + 0x88) = 0;
      *(undefined8 *)(puVar5 + 0x90) = 0;
      *(undefined8 *)(puVar5 + 0x98) = 0;
      *(undefined8 *)(puVar5 + 0xa0) = 0;
      *(undefined8 *)(puVar5 + 0xa8) = 0;
      *(undefined8 *)(puVar5 + 0xb0) = 0;
      *(undefined8 *)(puVar5 + 0xb8) = 0;
      *(undefined8 *)(puVar5 + 0x60) = uVar8;
      *(undefined8 *)(puVar5 + 0x68) = *(undefined8 *)(puVar5 + 0x110);
      puVar5[0x80] = 1;
      uVar8 = runtime_makemap_small();
      *(undefined8 *)(puVar5 + 0xd8) = uVar8;
      puVar9 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecbe0,uVar8,&DAT_009d739b,7);
      puVar7 = puVar5 + 0x10;
      *puVar9 = &DAT_008a6c80;
      if (runtime_writeBarrier._0_4_ != 0) {
        puVar9 = (undefined8 *)runtime_gcWriteBarrier1();
        puVar7 = puVar5 + 0x18;
        *in_x25 = extraout_x3;
      }
      puVar9[1] = 0xc327c8;
      encoding_json___Encoder__Encode(puVar7 + 0x60,&DAT_008ecbe0,*(undefined8 *)(puVar7 + 0xd0));
      return;
    }
  }
  main_writeJsonError(*(undefined8 *)((int)puVar2 + 0x108),*(undefined8 *)((int)puVar2 + 0x110),
                      &DAT_009f4a9c,0x12,0x195);
  return;
}

