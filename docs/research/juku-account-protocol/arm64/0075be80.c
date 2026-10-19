/* Reconstructed pseudocode, not original Go source: main.handleQrCode */

void main_handleQrCode(int param_1,undefined8 param_2,undefined8 param_3)

{
  undefined1 auVar1 [16];
  undefined8 *puVar2;
  undefined1 *puVar3;
  undefined1 *puVar4;
  undefined1 *puVar5;
  undefined1 *puVar6;
  undefined8 uVar7;
  undefined8 *puVar8;
  int *piVar9;
  int extraout_x0;
  int extraout_x0_00;
  int extraout_x0_01;
  uint uVar10;
  undefined8 extraout_x0_02;
  int extraout_x1;
  int iVar11;
  int extraout_x1_00;
  int extraout_x1_01;
  undefined8 extraout_x1_02;
  undefined8 extraout_x2;
  undefined8 extraout_x2_00;
  undefined8 extraout_x2_01;
  undefined8 extraout_x2_02;
  undefined8 extraout_x2_03;
  undefined8 uVar12;
  int extraout_x3;
  int iVar13;
  int extraout_x4;
  int iVar14;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar15 [16];
  undefined8 local_158 [13];
  undefined8 local_f0 [18];
  undefined1 local_60 [96];
  
  for (; (undefined8 *)((int)register0x00000008 + -0xd0) <= *(undefined8 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(int *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75c334;
    runtime_morestack_noctxt_abi0();
    param_1 = *(int *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x158) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x150) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(int *)((int)register0x00000008 + 8) = param_1;
  uVar7 = (**(code **)(param_1 + 0x18))(param_2);
  *(undefined8 *)((int)register0x00000008 + -0xd8) = uVar7;
  auVar15 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
  *(int *)register0x00000008 = auVar15._0_8_;
  *(int *)((int)register0x00000008 + -0xf0) = auVar15._8_8_;
  puVar8 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)register0x00000008 = puVar8;
  *puVar8 = &DAT_009f0b73;
  puVar8[1] = 0x10;
  puVar8 = (undefined8 *)
           runtime_mapassign_faststr
                     (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -200),
                      *(undefined8 *)((int)register0x00000008 + 8),
                      *(undefined8 *)((int)register0x00000008 + -0xe8));
  puVar2 = (undefined8 *)((int)register0x00000008 + -0x130);
  puVar8[1] = 1;
  puVar8[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar7 = *(undefined8 *)((int)register0x00000008 + 8);
  }
  else {
    auVar15 = runtime_gcWriteBarrier2(puVar8,*puVar8);
    puVar8 = auVar15._0_8_;
    puVar2 = (undefined8 *)((int)register0x00000008 + -0x128);
    uVar7 = *(undefined8 *)((int)register0x00000008 + 0x10);
    *in_x25 = uVar7;
    in_x25[1] = auVar15._8_8_;
  }
  *puVar8 = uVar7;
  uVar7 = net_url___URL__Query(*(undefined8 *)(*(int *)((int)puVar2 + 0x168) + 0x10));
  piVar9 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar7,&DAT_009d9f87,8);
  if (piVar9[1] == 0) {
    uVar12 = 0;
    uVar7 = 0;
  }
  else {
    uVar7 = *(undefined8 *)*piVar9;
    uVar12 = ((undefined8 *)*piVar9)[1];
  }
  auVar15 = main_getRealProvider(uVar7,uVar12);
  *(int *)((int)puVar2 + 0x78) = auVar15._0_8_;
  *(int *)((int)puVar2 + 0x48) = auVar15._8_8_;
  auVar15 = runtime_mapaccess2_faststr(&DAT_008edb60,main_providers,auVar15._0_8_,auVar15._8_8_);
  iVar13 = *auVar15._0_8_;
  if ((auVar15._8_8_ & 1) == 0) {
    main_writeJsonError(*(undefined8 *)((int)puVar2 + 0x178),*(undefined8 *)((int)puVar2 + 0x180),
                        &DAT_009f0ba3,0x10,400);
    return;
  }
  if ((*(int *)((int)puVar2 + 0x50) == 8) && (**(int **)((int)puVar2 + 0x80) == 0x35313144554f4c43))
  {
    *(int *)((int)puVar2 + 0x88) = auVar15._0_8_[1];
    *(int *)((int)puVar2 + 0x58) = iVar13;
    uVar7 = net_url___URL__Query(*(undefined8 *)(*(int *)((int)puVar2 + 0x188) + 0x10));
    piVar9 = (int *)runtime_mapaccess1_faststr(&DAT_00973360,uVar7,&DAT_009e4344,0xb);
    if (piVar9[1] == 0) {
      iVar13 = 0;
      uVar7 = 0;
    }
    else {
      uVar7 = *(undefined8 *)*piVar9;
      iVar13 = ((undefined8 *)*piVar9)[1];
    }
    auVar1._8_8_ = iVar13;
    auVar1._0_8_ = uVar7;
    auVar15._8_8_ = iVar13;
    auVar15._0_8_ = uVar7;
    puVar3 = (undefined1 *)((int)puVar2 + 0x30);
    if ((iVar13 == 0) &&
       (puVar3 = (undefined1 *)((int)puVar2 + 0x30), auVar15 = auVar1,
       main_global115ClientTypeStore != (main_Pan115ClientTypeStore *)0x0)) {
      auVar15 = main___Pan115ClientTypeStore__Get();
      puVar3 = (undefined1 *)((int)puVar2 + 0x38);
    }
    if (*(undefined1 **)(puVar3 + 0x38) ==
        go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
      *(int *)(puVar3 + 0x48) = auVar15._8_8_;
      *(int *)(puVar3 + 0x80) = auVar15._0_8_;
      mv_daemon_provider___Cloud115Provider__StartQrLoginWithType
                (*(undefined8 *)(puVar3 + 0x68),auVar15._0_8_,auVar15._8_8_);
      puVar4 = puVar3 + 8;
      iVar13 = extraout_x0;
      iVar11 = extraout_x1;
      uVar7 = extraout_x2;
      if (((extraout_x1 == 0) && (puVar4 = puVar3 + 8, *(int *)(puVar3 + 0x50) != 0)) &&
         (puVar4 = puVar3 + 8, main_global115ClientTypeStore != (main_Pan115ClientTypeStore *)0x0))
      {
        *(undefined8 *)(puVar3 + 0x48) = 0;
        *(undefined8 *)(puVar3 + 0x80) = extraout_x2;
        *(int *)(puVar3 + 0x60) = extraout_x0;
        main___Pan115ClientTypeStore__Save
                  (main_global115ClientTypeStore,*(undefined8 *)(puVar3 + 0x88),
                   *(int *)(puVar3 + 0x50));
        puVar4 = puVar3 + 0x10;
        iVar13 = *(int *)(puVar3 + 0x68);
        iVar11 = *(int *)(puVar3 + 0x50);
        uVar7 = *(undefined8 *)(puVar3 + 0x88);
      }
    }
    else {
      (**(code **)(*(undefined1 **)(puVar3 + 0x38) + 0x48))(*(undefined8 *)(puVar3 + 0x68));
      puVar4 = puVar3 + 8;
      iVar13 = extraout_x0_00;
      iVar11 = extraout_x1_00;
      uVar7 = extraout_x2_00;
    }
  }
  else {
    (**(code **)(iVar13 + 0x48))();
    puVar4 = (undefined1 *)((int)puVar2 + 0x28);
    iVar13 = extraout_x0_01;
    iVar11 = extraout_x1_01;
    uVar7 = extraout_x2_01;
  }
  if (iVar11 != 0) {
    auVar15 = (**(code **)(iVar11 + 0x18))(uVar7);
    main_writeJsonError(*(undefined8 *)(puVar4 + 0x160),*(undefined8 *)(puVar4 + 0x168),
                        auVar15._0_8_,auVar15._8_8_,500);
    return;
  }
  *(int *)(puVar4 + 0x58) = iVar13;
  uVar7 = *(undefined8 *)(iVar13 + 0x10);
  iVar11 = *(int *)(iVar13 + 0x18);
  puVar3 = puVar4;
  if (iVar11 != 0) {
    *(int *)(puVar4 + 0x50) = iVar11;
    puVar5 = puVar4;
    if (9 < iVar11) {
      *(undefined8 *)(puVar4 + 0x140) = uVar7;
      uVar10 = runtime_memequal(uVar7,&DAT_009e17b3,10);
      puVar5 = puVar4 + 8;
      puVar3 = puVar4 + 8;
      if ((uVar10 & 1) != 0) {
        iVar13 = *(int *)(puVar4 + 0x60);
        goto LAB_0075c218;
      }
      iVar11 = *(int *)(puVar4 + 0x58);
      uVar7 = *(undefined8 *)(puVar4 + 0x148);
    }
    mv_daemon_provider_EncodeQRCodeRGBA(uVar7,iVar11,1,300);
    puVar6 = puVar5 + 8;
    if (extraout_x3 == 0) {
      auVar15 = encoding_base64___Encoding__EncodeToString
                          (encoding_base64_StdEncoding,extraout_x0_02,extraout_x1_02,extraout_x2_02)
      ;
      auVar15 = runtime_concatstring2(0,&DAT_009fafac,0x16,auVar15._0_8_,auVar15._8_8_);
      uVar7 = auVar15._0_8_;
      puVar6 = puVar5 + 0x18;
      iVar13 = *(int *)(puVar5 + 0x70);
      *(int *)(iVar13 + 0x18) = auVar15._8_8_;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar7 = runtime_gcWriteBarrier2(uVar7,auVar15._8_8_,*(undefined8 *)(iVar13 + 0x10));
        puVar6 = puVar5 + 0x20;
        *in_x25 = uVar7;
        in_x25[1] = extraout_x2_03;
        iVar13 = extraout_x4;
      }
      *(undefined8 *)(iVar13 + 0x10) = uVar7;
    }
    *(undefined8 *)(puVar6 + 0xe8) = 0;
    *(undefined8 *)(puVar6 + 0xf0) = 0;
    *(undefined8 *)(puVar6 + 0xf8) = 0;
    *(undefined8 *)(puVar6 + 0x100) = 0;
    uVar7 = runtime_convTstring(*(undefined8 *)(puVar6 + 0x60),*(undefined8 *)(puVar6 + 0x30));
    *(undefined8 **)(puVar6 + 0xf0) = &DAT_008a6880;
    *(undefined8 *)(puVar6 + 0xf8) = uVar7;
    uVar7 = runtime_convT64(*(undefined8 *)(puVar6 + 0x58));
    *(undefined4 **)(puVar6 + 0x108) = &DAT_008a6ac0;
    *(undefined8 *)(puVar6 + 0x110) = uVar7;
    *(code **)(puVar6 + 0x118) = main_handleQrCode_Printf_func1;
    *(undefined **)(puVar6 + 0x120) = &DAT_00a20cd3;
    *(undefined8 *)(puVar6 + 0x128) = 0x36;
    *(undefined8 *)(puVar6 + 0x140) = 2;
    *(undefined1 **)(puVar6 + 0x130) = puVar6 + 0xf8;
    *(undefined8 *)(puVar6 + 0x138) = 2;
    log___Logger__output(log_std,0,2,puVar6 + 0x118);
    puVar3 = puVar6 + 0x18;
    iVar13 = *(int *)(puVar6 + 0x70);
  }
LAB_0075c218:
  iVar11 = *(int *)(puVar3 + 0x158);
  uVar7 = 0;
  if (iVar11 != 0) {
    uVar10 = (uint)*(dword *)(iVar11 + 0x10);
    do {
      iVar14 = (uVar10 & *(uint *)main__typeAssert_31) * 0x10;
      if (*(int *)(main__typeAssert_31 + iVar14 + 8) == *(int *)(iVar11 + 8)) {
        uVar7 = *(undefined8 *)(main__typeAssert_31 + iVar14 + 0x10);
        goto LAB_0075c294;
      }
      uVar10 = uVar10 + 1;
    } while (*(int *)(main__typeAssert_31 + iVar14 + 8) != 0);
    uVar7 = runtime_typeAssert(&main__typeAssert_31,*(int *)(iVar11 + 8));
    iVar13 = *(int *)(puVar3 + 0x60);
    puVar3 = puVar3 + 8;
  }
LAB_0075c294:
  *(undefined8 *)(puVar3 + 0x88) = 0;
  *(undefined8 *)(puVar3 + 0x90) = 0;
  *(undefined8 *)(puVar3 + 0x98) = 0;
  *(undefined8 *)(puVar3 + 0xa0) = 0;
  *(undefined8 *)(puVar3 + 0xa8) = 0;
  *(undefined8 *)(puVar3 + 0xb0) = 0;
  *(undefined8 *)(puVar3 + 0xb8) = 0;
  *(undefined8 *)(puVar3 + 0xc0) = 0;
  *(undefined8 *)(puVar3 + 200) = 0;
  *(undefined8 *)(puVar3 + 0xd0) = 0;
  *(undefined8 *)(puVar3 + 0xd8) = 0;
  *(undefined8 *)(puVar3 + 0xe0) = 0;
  *(undefined8 *)(puVar3 + 0x88) = uVar7;
  *(undefined8 *)(puVar3 + 0x90) = *(undefined8 *)(puVar3 + 0x160);
  puVar3[0xa8] = 1;
  encoding_json___Encoder__Encode(puVar3 + 0x88,&DAT_00885660,iVar13);
  return;
}

