/* Reconstructed pseudocode, not original Go source: main.handleQrCodeStatus */

void main_handleQrCodeStatus(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined1 *puVar1;
  undefined1 *puVar2;
  undefined8 uVar3;
  undefined8 *puVar4;
  int *piVar5;
  int *extraout_x0;
  sdword *psVar6;
  int extraout_x1;
  int iVar7;
  uint uVar8;
  undefined8 extraout_x2;
  undefined8 uVar9;
  int iVar10;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar11 [16];
  undefined8 local_1f8 [12];
  undefined8 local_198 [21];
  undefined1 local_f0 [88];
  undefined1 auStack_98 [96];
  undefined1 auStack_38 [56];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x170) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75e1f4;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x1f8) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x1f0) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar3 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -0x178) = uVar3;
  auVar11 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)((int)register0x00000008 + -0x160) = auVar11._0_8_;
  *(int *)((int)register0x00000008 + -0x198) = auVar11._8_8_;
  puVar4 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -0x160) = puVar4;
  *puVar4 = &DAT_009f0b73;
  puVar4[1] = 0x10;
  puVar4 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -0x168),
                      *(undefined8 *)((int)register0x00000008 + -0x158),
                      *(undefined8 *)((int)register0x00000008 + -400));
  puVar1 = (undefined1 *)((int)register0x00000008 + -0x1d0);
  puVar4[1] = 1;
  puVar4[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar3 = *(undefined8 *)((int)register0x00000008 + -0x158);
  }
  else {
    auVar11 = runtime_gcWriteBarrier2(puVar4,*puVar4);
    puVar4 = auVar11._0_8_;
    puVar1 = (undefined1 *)((int)register0x00000008 + -0x1c8);
    uVar3 = *(undefined8 *)((int)register0x00000008 + -0x150);
    *in_x25 = uVar3;
    in_x25[1] = auVar11._8_8_;
  }
  *puVar4 = uVar3;
  uVar3 = net_url___URL__Query(*(undefined8 *)(*(int *)(puVar1 + 0x208) + 0x10));
  piVar5 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar3,&DAT_009d9f87,8);
  if (piVar5[1] == 0) {
    uVar9 = 0;
    uVar3 = 0;
  }
  else {
    uVar3 = *(undefined8 *)*piVar5;
    uVar9 = ((undefined8 *)*piVar5)[1];
  }
  auVar11 = main_getRealProvider(uVar3,uVar9);
  *(int *)(puVar1 + 0x80) = auVar11._0_8_;
  *(int *)(puVar1 + 0x58) = auVar11._8_8_;
  uVar3 = net_url___URL__Query(*(undefined8 *)(*(int *)(puVar1 + 0x220) + 0x10));
  piVar5 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar3,&DAT_009d210d,3);
  if (piVar5[1] == 0) {
    uVar3 = 0;
    uVar9 = 0;
  }
  else {
    uVar3 = *(undefined8 *)*piVar5;
    uVar9 = ((undefined8 *)*piVar5)[1];
  }
  *(undefined8 *)(puVar1 + 0x58) = uVar9;
  *(undefined8 *)(puVar1 + 0x78) = uVar3;
  auVar11 = runtime_mapaccess2_faststr
                      (&DAT_008edb60,main_providers,*(undefined8 *)(puVar1 + 0x90),
                       *(undefined8 *)(puVar1 + 0x68));
  puVar2 = puVar1 + 0x30;
  if ((auVar11._8_8_ & 1) == 0) {
    main_writeJsonError(*(undefined8 *)(puVar1 + 0x228),*(undefined8 *)(puVar1 + 0x230),
                        &DAT_009f0ba3,0x10,400);
    return;
  }
  if (*(int *)(puVar1 + 0x60) == 6) {
    psVar6 = *(sdword **)(puVar1 + 0x80);
    if (*psVar6 == 0x756e616d) {
      if ((short)psVar6[1] == 0x6c61) {
        if (main_tokenStore == (mv_daemon_provider_TokenStore *)0x0) {
          auVar11 = ZEXT816(0);
        }
        else {
          auVar11 = mv_daemon_provider___TokenStore__Get
                              (main_tokenStore,*(undefined8 *)(puVar1 + 0x98),
                               *(undefined8 *)(puVar1 + 0x70));
          puVar2 = puVar1 + 0x38;
        }
        if (auVar11._8_8_ == 0) {
          iVar7 = *(int *)(puVar2 + 0x1f8);
          uVar3 = 0;
          if (iVar7 != 0) {
            uVar8 = (uint)*(dword *)(iVar7 + 0x10);
            do {
              iVar10 = (uVar8 & *(uint *)main__typeAssert_38) * 0x10;
              if (*(int *)(main__typeAssert_38 + iVar10 + 8) == *(int *)(iVar7 + 8)) {
                uVar3 = *(undefined8 *)(main__typeAssert_38 + iVar10 + 0x10);
                goto LAB_0075e088;
              }
              uVar8 = uVar8 + 1;
            } while (*(int *)(main__typeAssert_38 + iVar10 + 8) != 0);
            uVar3 = runtime_typeAssert(&main__typeAssert_38);
            puVar2 = puVar2 + 8;
          }
LAB_0075e088:
          *(undefined8 *)(puVar2 + 0xe8) = 0;
          *(undefined8 *)(puVar2 + 0xf0) = 0;
          *(undefined8 *)(puVar2 + 0xf8) = 0;
          *(undefined8 *)(puVar2 + 0x100) = 0;
          *(undefined8 *)(puVar2 + 0x108) = 0;
          *(undefined8 *)(puVar2 + 0x110) = 0;
          *(undefined8 *)(puVar2 + 0x118) = 0;
          *(undefined8 *)(puVar2 + 0x120) = 0;
          *(undefined8 *)(puVar2 + 0x128) = 0;
          *(undefined8 *)(puVar2 + 0x130) = 0;
          *(undefined8 *)(puVar2 + 0x138) = 0;
          *(undefined8 *)(puVar2 + 0x140) = 0;
          *(undefined8 *)(puVar2 + 0xe8) = uVar3;
          *(undefined8 *)(puVar2 + 0xf0) = *(undefined8 *)(puVar2 + 0x200);
          puVar2[0x108] = 1;
          encoding_json___Encoder__Encode(puVar2 + 0xe8,&DAT_0095ade0,&PTR_DAT_00c19840);
          return;
        }
        iVar7 = *(int *)(puVar2 + 0x1f8);
        uVar3 = 0;
        if (iVar7 != 0) {
          iVar10 = *(int *)(iVar7 + 8);
          uVar8 = (uint)*(dword *)(iVar7 + 0x10);
          do {
            iVar7 = (uVar8 & *(uint *)main__typeAssert_37) * 0x10;
            if (*(int *)(main__typeAssert_37 + iVar7 + 8) == iVar10) {
              uVar3 = *(undefined8 *)(main__typeAssert_37 + iVar7 + 0x10);
              goto LAB_0075e110;
            }
            uVar8 = uVar8 + 1;
          } while (*(int *)(main__typeAssert_37 + iVar7 + 8) != 0);
          *(int *)(puVar2 + 0x38) = auVar11._8_8_;
          *(int *)(puVar2 + 0x58) = auVar11._0_8_;
          uVar3 = runtime_typeAssert(&main__typeAssert_37,iVar10);
          auVar11._8_8_ = *(undefined8 *)(puVar2 + 0x40);
          auVar11._0_8_ = *(undefined8 *)(puVar2 + 0x60);
          puVar2 = puVar2 + 8;
        }
LAB_0075e110:
        *(undefined8 *)(puVar2 + 0x148) = 0;
        *(undefined8 *)(puVar2 + 0x150) = 0;
        *(undefined8 *)(puVar2 + 0x158) = 0;
        *(undefined8 *)(puVar2 + 0x160) = 0;
        *(undefined8 *)(puVar2 + 0x168) = 0;
        *(undefined8 *)(puVar2 + 0x170) = 0;
        *(undefined8 *)(puVar2 + 0x178) = 0;
        *(undefined8 *)(puVar2 + 0x180) = 0;
        *(undefined8 *)(puVar2 + 0x188) = 0;
        *(undefined8 *)(puVar2 + 400) = 0;
        *(undefined8 *)(puVar2 + 0x198) = 0;
        *(undefined8 *)(puVar2 + 0x1a0) = 0;
        *(undefined8 *)(puVar2 + 0x148) = uVar3;
        *(undefined8 *)(puVar2 + 0x150) = *(undefined8 *)(puVar2 + 0x200);
        puVar2[0x168] = 1;
        *(undefined8 *)(puVar2 + 0x1a8) = 0;
        *(undefined8 *)(puVar2 + 0x1b0) = 0;
        *(undefined8 *)(puVar2 + 0x1b8) = 0;
        *(undefined8 *)(puVar2 + 0x1c0) = 0;
        *(undefined8 *)(puVar2 + 0x1c8) = 0;
        *(undefined8 *)(puVar2 + 0x1d0) = 0;
        *(undefined8 *)(puVar2 + 0x1d8) = 0;
        *(undefined8 *)(puVar2 + 0x1e0) = 0;
        *(undefined **)(puVar2 + 0x1a8) = &DAT_009dd00d;
        *(undefined8 *)(puVar2 + 0x1b0) = 9;
        *(undefined1 (*) [16])(puVar2 + 0x1b8) = auVar11;
        uVar3 = runtime_convT(&DAT_0095ade0,puVar2 + 0x1a8);
        encoding_json___Encoder__Encode(puVar2 + 0x150,&DAT_0095ade0,uVar3);
        return;
      }
    }
  }
  else {
    psVar6 = *(sdword **)(puVar1 + 0x80);
  }
  (**(code **)(*auVar11._0_8_ + 0x30))(auVar11._0_8_[1],psVar6);
  if (extraout_x1 != 0) {
    auVar11 = (**(code **)(extraout_x1 + 0x18))(extraout_x2);
    main_writeJsonError(*(undefined8 *)(puVar1 + 0x238),*(undefined8 *)(puVar1 + 0x240),
                        auVar11._0_8_,auVar11._8_8_,500);
    return;
  }
  *(int **)(puVar1 + 0x98) = extraout_x0;
  puVar2 = puVar1 + 0x38;
  piVar5 = extraout_x0;
  if (extraout_x0[1] == 9) {
    puVar2 = puVar1 + 0x38;
    if ((*(int *)*extraout_x0 == 0x656d7269666e6f63) &&
       (puVar2 = puVar1 + 0x38, (char)((int *)*extraout_x0)[1] == 'd')) {
      puVar2 = puVar1 + 0x38;
      if (extraout_x0[3] != 0) {
        mv_daemon_provider___TokenStore__Save
                  (main_tokenStore,*(undefined8 *)(puVar1 + 0xa0),*(undefined8 *)(puVar1 + 0x78),
                   extraout_x0[2]);
        puVar2 = puVar1 + 0x40;
        piVar5 = *(int **)(puVar1 + 0xa0);
      }
    }
  }
  iVar7 = *(int *)(puVar2 + 0x1f8);
  uVar3 = 0;
  if (iVar7 != 0) {
    uVar8 = (uint)*(dword *)(iVar7 + 0x10);
    do {
      iVar10 = (uVar8 & *(uint *)main__typeAssert_39) * 0x10;
      if (*(int *)(main__typeAssert_39 + iVar10 + 8) == *(int *)(iVar7 + 8)) {
        uVar3 = *(undefined8 *)(main__typeAssert_39 + iVar10 + 0x10);
        goto LAB_0075dff8;
      }
      uVar8 = uVar8 + 1;
    } while (*(int *)(main__typeAssert_39 + iVar10 + 8) != 0);
    uVar3 = runtime_typeAssert(&main__typeAssert_39,*(int *)(iVar7 + 8));
    piVar5 = *(int **)(puVar2 + 0x68);
    puVar2 = puVar2 + 8;
  }
LAB_0075dff8:
  *(undefined8 *)(puVar2 + 0x88) = 0;
  *(undefined8 *)(puVar2 + 0x90) = 0;
  *(undefined8 *)(puVar2 + 0x98) = 0;
  *(undefined8 *)(puVar2 + 0xa0) = 0;
  *(undefined8 *)(puVar2 + 0xa8) = 0;
  *(undefined8 *)(puVar2 + 0xb0) = 0;
  *(undefined8 *)(puVar2 + 0xb8) = 0;
  *(undefined8 *)(puVar2 + 0xc0) = 0;
  *(undefined8 *)(puVar2 + 200) = 0;
  *(undefined8 *)(puVar2 + 0xd0) = 0;
  *(undefined8 *)(puVar2 + 0xd8) = 0;
  *(undefined8 *)(puVar2 + 0xe0) = 0;
  *(undefined8 *)(puVar2 + 0x88) = uVar3;
  *(undefined8 *)(puVar2 + 0x90) = *(undefined8 *)(puVar2 + 0x200);
  puVar2[0xa8] = 1;
  encoding_json___Encoder__Encode(puVar2 + 0x88,&DAT_008855a0,piVar5);
  return;
}

