/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).StartQrLoginWithType */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__StartQrLoginWithType
          (undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  undefined8 uVar1;
  byte bVar2;
  undefined1 *puVar3;
  undefined1 *puVar4;
  undefined1 *puVar5;
  undefined1 *puVar6;
  undefined1 *puVar7;
  undefined1 *puVar8;
  undefined1 *puVar9;
  undefined1 *puVar10;
  undefined1 *puVar11;
  undefined1 *puVar12;
  undefined1 *puVar13;
  undefined1 *puVar14;
  undefined1 *puVar15;
  undefined1 *puVar16;
  undefined1 *puVar17;
  undefined1 *puVar18;
  undefined1 uVar19;
  undefined8 uVar20;
  undefined8 extraout_x0;
  undefined8 *puVar21;
  undefined8 *puVar22;
  int extraout_x0_00;
  char *extraout_x0_01;
  undefined8 uVar23;
  int extraout_x1_01;
  int extraout_x1;
  int iVar29;
  undefined8 extraout_x2;
  undefined1 auVar24 [24];
  int extraout_x1_00;
  undefined8 extraout_x2_00;
  undefined1 auVar25 [24];
  int *piVar30;
  undefined1 auVar26 [24];
  undefined1 auVar27 [24];
  undefined1 auVar28 [24];
  undefined8 extraout_x2_01;
  undefined8 extraout_x3;
  undefined8 extraout_x3_00;
  undefined8 extraout_x3_01;
  int extraout_x3_02;
  undefined8 extraout_x4;
  undefined8 extraout_x4_00;
  undefined8 extraout_x4_01;
  undefined8 extraout_x4_02;
  uint uVar31;
  int iVar32;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar33 [16];
  undefined8 local_4d8 [11];
  undefined1 local_479 [17];
  undefined8 local_468 [4];
  int local_448 [9];
  undefined1 auStack_3f9 [8];
  undefined1 uStack_3f1;
  undefined8 local_3f0 [3];
  undefined1 auStack_3d2 [2];
  undefined8 local_3d0 [6];
  byte abStack_39a [8];
  byte abStack_392 [90];
  undefined8 local_338 [56];
  undefined8 local_178 [33];
  int local_70 [11];
  undefined8 local_18 [3];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x450) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x53908c;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x4d8) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x4d0) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + -0x18) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
  *(undefined1 *)((int)register0x00000008 + -0x479) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x420) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x440) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x438) = 0;
  auVar33 = mv_daemon_provider_NormalizeCloud115ClientType(param_2,param_3);
  *(int *)((int)register0x00000008 + -0x3d8) = auVar33._0_8_;
  *(int *)((int)register0x00000008 + -0x448) = auVar33._8_8_;
  auVar33 = mv_daemon_provider_get115BrowserVersion();
  *(int *)((int)register0x00000008 + -0x408) = auVar33._0_8_;
  *(int *)((int)register0x00000008 + -0x468) = auVar33._8_8_;
  *(undefined8 *)((int)register0x00000008 + -0x338) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x330) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x328) = 0;
  *(undefined8 *)((int)register0x00000008 + -800) = 0;
  uVar20 = runtime_convTstring(mv_daemon_provider_Cloud115ApiBase.str,
                               mv_daemon_provider_Cloud115ApiBase.len);
  *(undefined8 **)((int)register0x00000008 + -0x330) = &DAT_008a6880;
  *(undefined8 *)((int)register0x00000008 + -0x328) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)((int)register0x00000008 + -0x3c8),
                               *(undefined8 *)((int)register0x00000008 + -0x438));
  *(undefined8 **)((int)register0x00000008 + -0x318) = &DAT_008a6880;
  *(undefined8 *)((int)register0x00000008 + -0x310) = uVar20;
  auVar33 = fmt_Sprintf(&DAT_009fc8ab,0x17,(undefined1 *)((int)register0x00000008 + -0x328),2,2);
  net_http_NewRequestWithContext
            (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_009d2101,3,
             auVar33._0_8_,auVar33._8_8_,0,0);
  if (extraout_x1 != 0) {
    *(undefined8 *)((int)register0x00000008 + -0x3f0) = 0;
    *(int *)((int)register0x00000008 + -0x410) = extraout_x1;
    *(undefined8 *)((int)register0x00000008 + -0x408) = extraout_x2;
    auVar24._0_8_ = *(undefined8 *)((int)register0x00000008 + -0x3f0);
    auVar24._8_8_ = extraout_x1;
    auVar24._16_8_ = extraout_x2;
    return auVar24;
  }
  *(undefined8 *)((int)register0x00000008 + -0x3d0) = extraout_x0;
  *(undefined8 *)((int)register0x00000008 + -0x70) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x68) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x60) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x58) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x50) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x48) = 0;
  iVar29 = 4;
  puVar22 = (undefined8 *)((int)register0x00000008 + -0x178);
  do {
    *puVar22 = 0;
    puVar22[1] = 0;
    puVar22[2] = 0;
    puVar22[3] = 0;
    puVar22[4] = 0;
    puVar22[5] = 0;
    puVar21 = puVar22 + 8;
    puVar22[6] = 0;
    puVar22[7] = 0;
    iVar29 = iVar29 + -1;
    puVar22 = puVar21;
  } while (iVar29 != 0);
  *puVar21 = 0;
  *(undefined1 **)((int)register0x00000008 + -0x178) = &DAT_8080808080808080;
  *(undefined1 **)((int)register0x00000008 + -0x60) =
       (undefined1 *)((int)register0x00000008 + -0x178);
  uVar20 = runtime_rand();
  *(undefined8 *)((int)register0x00000008 + -0x60) = uVar20;
  puVar22 = (undefined8 *)
            runtime_mapassign_faststr
                      (&DAT_008ecae0,(undefined1 *)((int)register0x00000008 + -0x68),&DAT_009d5bdd,6
                      );
  puVar3 = (undefined1 *)((int)register0x00000008 + -0x490);
  puVar22[1] = 0x12;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar3 = (undefined1 *)((int)register0x00000008 + -0x488);
    *in_x25 = extraout_x4;
  }
  *puVar22 = &DAT_009f4eb0;
  puVar22 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar3 + 0x430,&DAT_009d73cc,7);
  puVar4 = puVar3 + 8;
  puVar22[1] = 0x13;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar4 = puVar3 + 0x10;
    *in_x25 = extraout_x4_00;
  }
  *puVar22 = &DAT_009f6896;
  auVar33 = mv_daemon_provider_get115QrUserAgent
                      (*(undefined8 *)(puVar4 + 0xf0),*(undefined8 *)(puVar4 + 0x80),
                       *(undefined8 *)(puVar4 + 0xb8),*(undefined8 *)(puVar4 + 0x58));
  *(int *)(puVar4 + 0x90) = auVar33._8_8_;
  *(int *)(puVar4 + 0x1c0) = auVar33._0_8_;
  puVar22 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar4 + 0x438,&DAT_009e173b,10);
  puVar5 = puVar4 + 0x10;
  puVar22[1] = *(undefined8 *)(puVar4 + 0x98);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar20 = *(undefined8 *)(puVar4 + 0x1c8);
  }
  else {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar5 = puVar4 + 0x18;
    uVar20 = *(undefined8 *)(puVar4 + 0x1d0);
    *in_x25 = uVar20;
    in_x25[1] = extraout_x3;
  }
  *puVar22 = uVar20;
  *(undefined8 *)(puVar5 + 0x128) = 0;
  *(undefined8 *)(puVar5 + 0x130) = 0;
  *(undefined8 *)(puVar5 + 0x138) = 0;
  *(undefined8 *)(puVar5 + 0x140) = 0;
  *(undefined8 *)(puVar5 + 0x148) = 0;
  *(undefined8 *)(puVar5 + 0x150) = 0;
  *(undefined8 *)(puVar5 + 0x158) = 0;
  *(undefined8 *)(puVar5 + 0x160) = 0;
  *(undefined8 *)(puVar5 + 0x168) = 0;
  *(undefined8 *)(puVar5 + 0x170) = 0;
  *(undefined8 *)(puVar5 + 0x178) = 0;
  *(undefined8 *)(puVar5 + 0x180) = 0;
  runtime_mapIterStart(&DAT_008ecae0,puVar5 + 0x430);
  puVar6 = puVar5 + 8;
  while (puVar22 = *(undefined8 **)(puVar6 + 0x128), puVar22 != (undefined8 *)0x0) {
    uVar20 = *puVar22;
    uVar1 = puVar22[1];
    uVar23 = **(undefined8 **)(puVar6 + 0x130);
    *(undefined8 *)(puVar6 + 0x68) = (*(undefined8 **)(puVar6 + 0x130))[1];
    *(undefined8 *)(puVar6 + 200) = uVar23;
    *(undefined8 *)(puVar6 + 0x1b0) = *(undefined8 *)(*(int *)(puVar6 + 0xd0) + 0x38);
    auVar33 = net_textproto_CanonicalMIMEHeaderKey(uVar20,uVar1);
    *(int *)(puVar6 + 0x1c0) = auVar33._0_8_;
    *(int *)(puVar6 + 0x90) = auVar33._8_8_;
    puVar22 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
    puVar7 = puVar6 + 0x10;
    puVar22[1] = *(undefined8 *)(puVar6 + 0x78);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar20 = *(undefined8 *)(puVar6 + 0xd8);
    }
    else {
      puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar7 = puVar6 + 0x18;
      uVar20 = *(undefined8 *)(puVar6 + 0xe0);
      *in_x25 = uVar20;
    }
    *(undefined8 **)(puVar7 + 0x1a8) = puVar22;
    *puVar22 = uVar20;
    puVar22 = (undefined8 *)
              runtime_mapassign_faststr
                        (&DAT_00969220,*(undefined8 *)(puVar7 + 0x1b0),
                         *(undefined8 *)(puVar7 + 0x1b8),*(undefined8 *)(puVar7 + 0x88));
    puVar8 = puVar7 + 8;
    puVar22[1] = 1;
    puVar22[2] = 1;
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar20 = *(undefined8 *)(puVar7 + 0x1b0);
    }
    else {
      auVar33 = runtime_gcWriteBarrier2(puVar22,*puVar22);
      puVar22 = auVar33._0_8_;
      puVar8 = puVar7 + 0x10;
      uVar20 = *(undefined8 *)(puVar7 + 0x1b8);
      *in_x25 = uVar20;
      in_x25[1] = auVar33._8_8_;
    }
    *puVar22 = uVar20;
    runtime_mapIterNext(puVar8 + 0x128);
    puVar6 = puVar8 + 8;
  }
  net_http___Client__do(net_http_DefaultClient,*(undefined8 *)(puVar6 + 0xd0));
  if (extraout_x1_00 != 0) {
    *(undefined8 *)(puVar6 + 0xb8) = 0;
    *(int *)(puVar6 + 0x98) = extraout_x1_00;
    *(undefined8 *)(puVar6 + 0xa0) = extraout_x2_00;
    auVar25._0_8_ = *(undefined8 *)(puVar6 + 0xb8);
    auVar25._8_8_ = extraout_x1_00;
    auVar25._16_8_ = extraout_x2_00;
    return auVar25;
  }
  *(int *)(puVar6 + 0xb0) = extraout_x0_00;
  uVar20 = *(undefined8 *)(extraout_x0_00 + 0x40);
  uVar23 = *(undefined8 *)(extraout_x0_00 + 0x48);
  *(code **)(puVar6 + 0x318) =
       mv_daemon_provider___Cloud115Provider__StartQrLoginWithType_deferwrap1;
  *(undefined8 *)(puVar6 + 800) = uVar20;
  *(undefined8 *)(puVar6 + 0x328) = uVar23;
  *(undefined1 **)(puVar6 + 0x4c0) = puVar6 + 0x318;
  puVar6[0x5f] = 1;
  uVar20 = runtime_newobject(&DAT_00909fe0);
  *(undefined8 *)(puVar6 + 0x4c0) = uVar20;
  iVar29 = *(int *)(*(int *)(puVar6 + 0xb8) + 0x40);
  *(undefined8 *)(puVar6 + 0xe8) = *(undefined8 *)(*(int *)(puVar6 + 0xb8) + 0x48);
  uVar20 = 0;
  puVar10 = puVar6 + 0x10;
  if (iVar29 != 0) {
    uVar31 = (uint)*(dword *)(iVar29 + 0x10);
    do {
      iVar32 = (uVar31 & *(uint *)mv_daemon_provider__typeAssert_69) * 0x10;
      if (*(int *)(mv_daemon_provider__typeAssert_69 + iVar32 + 8) == *(int *)(iVar29 + 8)) {
        uVar20 = *(undefined8 *)(mv_daemon_provider__typeAssert_69 + iVar32 + 0x10);
        puVar10 = puVar6 + 0x10;
        goto LAB_0053890c;
      }
      uVar31 = uVar31 + 1;
    } while (*(int *)(mv_daemon_provider__typeAssert_69 + iVar32 + 8) != 0);
    uVar20 = runtime_typeAssert(&mv_daemon_provider__typeAssert_69,*(int *)(iVar29 + 8));
    puVar10 = puVar6 + 0x18;
  }
LAB_0053890c:
  *(undefined8 *)(puVar10 + 0x1b8) = uVar20;
  puVar22 = (undefined8 *)runtime_newobject(&DAT_00991b80);
  puVar9 = puVar10 + 8;
  *puVar22 = *(undefined8 *)(puVar10 + 0x1c0);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar20 = *(undefined8 *)(puVar10 + 0xe0);
  }
  else {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar9 = puVar10 + 0x10;
    uVar20 = *(undefined8 *)(puVar10 + 0xe8);
    *in_x25 = uVar20;
  }
  puVar22[1] = uVar20;
  auVar33 = encoding_json___Decoder__Decode(puVar22,&DAT_00899ee0,*(undefined8 *)(puVar9 + 0x4b0));
  if (auVar33._0_8_ != 0) {
    *(undefined8 *)(puVar9 + 0xb8) = 0;
    *(undefined1 (*) [16])(puVar9 + 0x98) = auVar33;
    puVar9[0x5f] = 0;
    (*(code *)**(undefined8 **)(puVar9 + 0x4c0))();
    auVar27._0_8_ = *(undefined8 *)(puVar9 + 0xc0);
    auVar27._8_8_ = *(undefined8 *)(puVar9 + 0xa0);
    auVar27._16_8_ = *(undefined8 *)(puVar9 + 0xa8);
    return auVar27;
  }
  piVar30 = *(int **)(puVar9 + 0x4b8);
  if (*piVar30 != 1) {
    puVar22 = (undefined8 *)runtime_newobject(&DAT_008f85a0);
    *puVar22 = &DAT_00a009fa;
    puVar22[1] = 0x1a;
    *(undefined8 *)(puVar9 + 0xc0) = 0;
    *(undefined1 **)(puVar9 + 0xa0) = go_itab__errors_errorString_error;
    *(undefined8 **)(puVar9 + 0xa8) = puVar22;
    puVar9[0x67] = 0;
    (*(code *)**(undefined8 **)(puVar9 + 0x4c8))();
    auVar26._0_8_ = *(undefined8 *)(puVar9 + 200);
    auVar26._8_8_ = *(undefined8 *)(puVar9 + 0xa8);
    auVar26._16_8_ = *(undefined8 *)(puVar9 + 0xb0);
    return auVar26;
  }
  iVar29 = piVar30[6];
  *(int *)(puVar9 + 0x78) = piVar30[7];
  *(int *)(puVar9 + 0xe8) = iVar29;
  *(undefined8 *)(puVar9 + 0x100) = 0;
  *(undefined8 *)(puVar9 + 0x108) = 0;
  *(undefined8 *)(puVar9 + 0x110) = 0;
  *(undefined8 *)(puVar9 + 0x118) = 0;
  *(undefined8 *)(puVar9 + 0x120) = 0;
  *(undefined8 *)(puVar9 + 0x128) = 0;
  uVar20 = runtime_convTstring(mv_daemon_provider_Cloud115ApiBase.str,
                               mv_daemon_provider_Cloud115ApiBase.len);
  *(undefined8 **)(puVar9 + 0x108) = &DAT_008a6880;
  *(undefined8 *)(puVar9 + 0x110) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)(puVar9 + 0x100),*(undefined8 *)(puVar9 + 0x90));
  *(undefined8 **)(puVar9 + 0x120) = &DAT_008a6880;
  *(undefined8 *)(puVar9 + 0x128) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)(*(int *)(puVar9 + 0x4c8) + 8),
                               *(undefined8 *)(*(int *)(puVar9 + 0x4c8) + 0x10));
  *(undefined8 **)(puVar9 + 0x138) = &DAT_008a6880;
  *(undefined8 *)(puVar9 + 0x140) = uVar20;
  auVar33 = fmt_Sprintf(&DAT_00a07372,0x1f,puVar9 + 0x118,3,3);
  auVar33 = net_http_NewRequestWithContext
                      (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_009d2101
                       ,3,auVar33._0_8_,auVar33._8_8_,0,0);
  puVar10 = puVar9 + 0x30;
  if (auVar33._8_8_ == 0) {
    *(int *)(puVar9 + 0xd0) = auVar33._0_8_;
    *(undefined8 *)(puVar9 + 0x310) = 0;
    *(undefined8 *)(puVar9 + 0x318) = 0;
    *(undefined8 *)(puVar9 + 800) = 0;
    *(undefined8 *)(puVar9 + 0x328) = 0;
    *(undefined8 *)(puVar9 + 0x330) = 0;
    *(undefined8 *)(puVar9 + 0x338) = 0;
    iVar29 = 4;
    puVar22 = (undefined8 *)(puVar9 + 0x208);
    do {
      *puVar22 = 0;
      puVar22[1] = 0;
      puVar22[2] = 0;
      puVar22[3] = 0;
      puVar22[4] = 0;
      puVar22[5] = 0;
      puVar21 = puVar22 + 8;
      puVar22[6] = 0;
      puVar22[7] = 0;
      iVar29 = iVar29 + -1;
      puVar22 = puVar21;
    } while (iVar29 != 0);
    *puVar21 = 0;
    *(undefined1 **)(puVar9 + 0x208) = &DAT_8080808080808080;
    *(undefined1 **)(puVar9 + 800) = puVar9 + 0x208;
    uVar20 = runtime_rand();
    *(undefined8 *)(puVar9 + 800) = uVar20;
    puVar22 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar9 + 0x318,&DAT_009d5bdd,6);
    puVar11 = puVar9 + 0x40;
    puVar22[1] = 0x12;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar11 = puVar9 + 0x48;
      *in_x25 = extraout_x4_01;
    }
    *puVar22 = &DAT_009f4eb0;
    puVar22 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar11 + 0x2e0,&DAT_009d73cc,7)
    ;
    puVar12 = puVar11 + 8;
    puVar22[1] = 0x13;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar12 = puVar11 + 0x10;
      *in_x25 = extraout_x4_02;
    }
    *puVar22 = &DAT_009f6896;
    auVar33 = mv_daemon_provider_get115QrUserAgent
                        (*(undefined8 *)(puVar12 + 0xf0),*(undefined8 *)(puVar12 + 0x80),
                         *(undefined8 *)(puVar12 + 0xb8),*(undefined8 *)(puVar12 + 0x58));
    *(int *)(puVar12 + 0x90) = auVar33._8_8_;
    *(int *)(puVar12 + 0x1c0) = auVar33._0_8_;
    puVar22 = (undefined8 *)
              runtime_mapassign_faststr(&DAT_008ecae0,puVar12 + 0x2e8,&DAT_009e173b,10);
    puVar13 = puVar12 + 0x10;
    puVar22[1] = *(undefined8 *)(puVar12 + 0x98);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar20 = *(undefined8 *)(puVar12 + 0x1c8);
    }
    else {
      puVar22 = (undefined8 *)runtime_gcWriteBarrier2();
      puVar13 = puVar12 + 0x18;
      uVar20 = *(undefined8 *)(puVar12 + 0x1d0);
      *in_x25 = uVar20;
      in_x25[1] = extraout_x3_00;
    }
    *puVar22 = uVar20;
    *(undefined8 *)(puVar13 + 0x128) = 0;
    *(undefined8 *)(puVar13 + 0x130) = 0;
    *(undefined8 *)(puVar13 + 0x138) = 0;
    *(undefined8 *)(puVar13 + 0x140) = 0;
    *(undefined8 *)(puVar13 + 0x148) = 0;
    *(undefined8 *)(puVar13 + 0x150) = 0;
    *(undefined8 *)(puVar13 + 0x158) = 0;
    *(undefined8 *)(puVar13 + 0x160) = 0;
    *(undefined8 *)(puVar13 + 0x168) = 0;
    *(undefined8 *)(puVar13 + 0x170) = 0;
    *(undefined8 *)(puVar13 + 0x178) = 0;
    *(undefined8 *)(puVar13 + 0x180) = 0;
    runtime_mapIterStart(&DAT_008ecae0,puVar13 + 0x2e0);
    puVar14 = puVar13 + 8;
    while (puVar22 = *(undefined8 **)(puVar14 + 0x128), puVar22 != (undefined8 *)0x0) {
      uVar20 = *puVar22;
      uVar1 = puVar22[1];
      uVar23 = **(undefined8 **)(puVar14 + 0x130);
      *(undefined8 *)(puVar14 + 0x60) = (*(undefined8 **)(puVar14 + 0x130))[1];
      *(undefined8 *)(puVar14 + 0xc0) = uVar23;
      *(undefined8 *)(puVar14 + 0x1b0) = *(undefined8 *)(*(int *)(puVar14 + 0xa0) + 0x38);
      auVar33 = net_textproto_CanonicalMIMEHeaderKey(uVar20,uVar1);
      *(int *)(puVar14 + 0x1c0) = auVar33._0_8_;
      *(int *)(puVar14 + 0x90) = auVar33._8_8_;
      puVar22 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
      puVar16 = puVar14 + 0x10;
      puVar22[1] = *(undefined8 *)(puVar14 + 0x70);
      if (runtime_writeBarrier._0_4_ == 0) {
        uVar20 = *(undefined8 *)(puVar14 + 0xd0);
      }
      else {
        puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
        puVar16 = puVar14 + 0x18;
        uVar20 = *(undefined8 *)(puVar14 + 0xd8);
        *in_x25 = uVar20;
      }
      *(undefined8 **)(puVar16 + 0x1a8) = puVar22;
      *puVar22 = uVar20;
      puVar22 = (undefined8 *)
                runtime_mapassign_faststr
                          (&DAT_00969220,*(undefined8 *)(puVar16 + 0x1b0),
                           *(undefined8 *)(puVar16 + 0x1b8),*(undefined8 *)(puVar16 + 0x88));
      puVar17 = puVar16 + 8;
      puVar22[1] = 1;
      puVar22[2] = 1;
      if (runtime_writeBarrier._0_4_ == 0) {
        uVar20 = *(undefined8 *)(puVar16 + 0x1b0);
      }
      else {
        auVar33 = runtime_gcWriteBarrier2(puVar22,*puVar22);
        puVar22 = auVar33._0_8_;
        puVar17 = puVar16 + 0x10;
        uVar20 = *(undefined8 *)(puVar16 + 0x1b8);
        *in_x25 = uVar20;
        in_x25[1] = auVar33._8_8_;
      }
      *puVar22 = uVar20;
      runtime_mapIterNext(puVar17 + 0x128);
      puVar14 = puVar17 + 8;
    }
    auVar33 = net_http___Client__do(net_http_DefaultClient,*(undefined8 *)(puVar14 + 0xa0));
    iVar29 = auVar33._0_8_;
    puVar10 = puVar14 + 8;
    if (auVar33._8_8_ == 0) {
      uVar20 = *(undefined8 *)(iVar29 + 0x40);
      uVar23 = *(undefined8 *)(iVar29 + 0x48);
      *(code **)(puVar14 + 0x1c8) =
           mv_daemon_provider___Cloud115Provider__StartQrLoginWithType_deferwrap2;
      *(undefined8 *)(puVar14 + 0x1d0) = uVar20;
      *(undefined8 *)(puVar14 + 0x1d8) = uVar23;
      *(undefined1 **)(puVar14 + 0x4c8) = puVar14 + 0x1c8;
      puVar14[0x5f] = 3;
      iVar32 = *(int *)(iVar29 + 0x40);
      uVar20 = *(undefined8 *)(iVar29 + 0x48);
      uVar23 = 0;
      puVar18 = puVar14 + 8;
      if (iVar32 != 0) {
        iVar29 = *(int *)(iVar32 + 8);
        uVar31 = (uint)*(dword *)(iVar32 + 0x10);
        do {
          iVar32 = (uVar31 & *(uint *)mv_daemon_provider__typeAssert_70) * 0x10;
          if (*(int *)(mv_daemon_provider__typeAssert_70 + iVar32 + 8) == iVar29) {
            uVar23 = *(undefined8 *)(mv_daemon_provider__typeAssert_70 + iVar32 + 0x10);
            puVar18 = puVar14 + 8;
            goto LAB_00538f0c;
          }
          uVar31 = uVar31 + 1;
        } while (*(int *)(mv_daemon_provider__typeAssert_70 + iVar32 + 8) != 0);
        *(undefined8 *)(puVar14 + 0x1c0) = uVar20;
        uVar23 = runtime_typeAssert(&mv_daemon_provider__typeAssert_70,iVar29);
        uVar20 = *(undefined8 *)(puVar14 + 0x1c8);
        puVar18 = puVar14 + 0x10;
      }
LAB_00538f0c:
      io_ReadAll(uVar23,uVar20);
      puVar10 = puVar18 + 8;
      if (extraout_x3_02 == 0) {
        if (extraout_x1_01 < 9) {
          auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
          auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
        }
        else if (*extraout_x0_01 == -0x77) {
          if (extraout_x0_01[1] == 'P') {
            if (extraout_x0_01[2] == 'N') {
              if (extraout_x0_01[3] == 'G') {
                auVar33 = encoding_base64___Encoding__EncodeToString
                                    (encoding_base64_StdEncoding,extraout_x0_01,extraout_x1_01,
                                     extraout_x2_01);
                auVar33 = runtime_concatstring2(0,&DAT_009fafac,0x16,auVar33._0_8_,auVar33._8_8_);
                puVar10 = puVar18 + 0x18;
              }
              else {
                auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
                auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
                puVar10 = puVar18 + 8;
              }
            }
            else {
              auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
              auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
              puVar10 = puVar18 + 8;
            }
          }
          else {
            auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
            auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
            puVar10 = puVar18 + 8;
          }
        }
        else {
          auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
          auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
          puVar10 = puVar18 + 8;
        }
      }
      else {
        auVar33._8_8_ = *(undefined8 *)(puVar18 + 0x78);
        auVar33._0_8_ = *(undefined8 *)(puVar18 + 0xe8);
        puVar10 = puVar18 + 8;
      }
      uVar19 = 3;
    }
    else {
      uVar19 = 1;
      auVar33._8_8_ = *(undefined8 *)(puVar14 + 0x78);
      auVar33._0_8_ = *(undefined8 *)(puVar14 + 0xe8);
    }
  }
  else {
    uVar19 = 1;
    auVar33._8_8_ = *(undefined8 *)(puVar9 + 0xa0);
    auVar33._0_8_ = *(undefined8 *)(puVar9 + 0x110);
  }
  puVar10[0x56] = uVar19;
  *(int *)(puVar10 + 0xe0) = auVar33._0_8_;
  *(int *)(puVar10 + 0x70) = auVar33._8_8_;
  *(undefined8 *)(puVar10 + 0x460) = 0;
  *(undefined8 *)(puVar10 + 0x468) = 0;
  *(undefined8 *)(puVar10 + 0x470) = 0;
  *(undefined8 *)(puVar10 + 0x478) = 0;
  *(undefined8 *)(puVar10 + 0x480) = 0;
  *(undefined8 *)(puVar10 + 0x488) = 0;
  *(undefined8 *)(puVar10 + 0x490) = 0;
  *(undefined8 *)(puVar10 + 0x498) = 0;
  *(undefined8 *)(puVar10 + 0x4a0) = 0;
  *(undefined8 *)(puVar10 + 0x4a8) = 0;
  uVar20 = runtime_convTstring(*(undefined8 *)(*(int *)(puVar10 + 0x4b0) + 8),
                               *(undefined8 *)(*(int *)(puVar10 + 0x4b0) + 0x10));
  *(undefined8 **)(puVar10 + 0x468) = &DAT_008a6880;
  *(undefined8 *)(puVar10 + 0x470) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)(*(int *)(puVar10 + 0x4b8) + 0x20),
                               *(undefined8 *)(*(int *)(puVar10 + 0x4b8) + 0x28));
  *(undefined8 **)(puVar10 + 0x480) = &DAT_008a6880;
  *(undefined8 *)(puVar10 + 0x488) = uVar20;
  uVar20 = runtime_convT64(*(undefined8 *)(*(int *)(puVar10 + 0x4c0) + 0x18));
  *(undefined **)(puVar10 + 0x498) = &DAT_008a6a40;
  *(undefined8 *)(puVar10 + 0x4a0) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)(puVar10 + 0xd0),*(undefined8 *)(puVar10 + 0x70));
  *(undefined8 **)(puVar10 + 0x4b0) = &DAT_008a6880;
  *(undefined8 *)(puVar10 + 0x4b8) = uVar20;
  uVar20 = runtime_convTstring(*(undefined8 *)(puVar10 + 0x110),*(undefined8 *)(puVar10 + 0xa0));
  *(undefined8 **)(puVar10 + 0x4c8) = &DAT_008a6880;
  *(undefined8 *)(puVar10 + 0x4d0) = uVar20;
  auVar33 = fmt_Sprintf(&DAT_009ecd01,0xe,puVar10 + 0x488,5,5);
  *(int *)(puVar10 + 0xa8) = auVar33._8_8_;
  *(int *)(puVar10 + 0x118) = auVar33._0_8_;
  puVar22 = (undefined8 *)runtime_newobject(&DAT_00941060);
  puVar15 = puVar10 + 0x38;
  puVar22[5] = *(undefined8 *)(puVar10 + 0xb0);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar20 = *(undefined8 *)(puVar10 + 0x120);
    uVar23 = *(undefined8 *)(puVar10 + 0x118);
  }
  else {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier2();
    puVar15 = puVar10 + 0x40;
    uVar20 = *(undefined8 *)(puVar10 + 0x128);
    uVar23 = *(undefined8 *)(puVar10 + 0x120);
    *in_x25 = uVar20;
    in_x25[1] = uVar23;
  }
  puVar22[4] = uVar20;
  uVar20 = *(undefined8 *)(puVar15 + 0x70);
  puVar22[2] = uVar23;
  puVar22[3] = uVar20;
  uVar20 = *(undefined8 *)(*(int *)(puVar15 + 0x4b0) + 0x30);
  puVar22[1] = *(undefined8 *)(*(int *)(puVar15 + 0x4b0) + 0x38);
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar22 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar15 = puVar15 + 8;
    *in_x25 = extraout_x3_01;
    uVar20 = extraout_x3_01;
  }
  *puVar22 = uVar20;
  *(undefined8 **)(puVar15 + 0xb0) = puVar22;
  *(undefined8 *)(puVar15 + 0x90) = 0;
  *(undefined8 *)(puVar15 + 0x98) = 0;
  bVar2 = puVar15[0x56];
  puVar10 = puVar15;
  if ((bVar2 >> 1 & 1) != 0) {
    puVar15[0x56] = bVar2 & 0xfd;
    puVar15[0x57] = bVar2 & 0xfd;
    (*(code *)**(undefined8 **)(puVar15 + 0x4c0))();
    puVar10 = puVar15 + 8;
    bVar2 = puVar15[0x5e];
  }
  if ((bVar2 & 1) != 0) {
    puVar10[0x57] = bVar2 & 0xfe;
    (*(code *)**(undefined8 **)(puVar10 + 0x4b8))();
    puVar10 = puVar10 + 8;
  }
  auVar28._0_8_ = *(undefined8 *)(puVar10 + 0xb0);
  auVar28._8_8_ = *(undefined8 *)(puVar10 + 0x90);
  auVar28._16_8_ = *(undefined8 *)(puVar10 + 0x98);
  return auVar28;
}

