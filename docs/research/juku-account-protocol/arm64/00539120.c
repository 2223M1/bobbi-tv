/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).PollQrLogin */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__PollQrLogin
          (undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  sdword *psVar1;
  undefined8 *puVar2;
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
  undefined1 *puVar19;
  undefined1 *puVar20;
  undefined1 *puVar21;
  undefined1 *puVar22;
  undefined1 *puVar23;
  undefined1 *puVar24;
  undefined1 *puVar25;
  undefined1 *puVar26;
  undefined1 *puVar27;
  undefined1 *puVar28;
  undefined1 *puVar29;
  undefined1 *puVar30;
  undefined1 uVar31;
  undefined8 extraout_x0;
  int extraout_x0_00;
  undefined8 *puVar32;
  int extraout_x0_01;
  int extraout_x0_02;
  int extraout_x0_03;
  undefined8 extraout_x0_04;
  undefined8 *extraout_x0_05;
  undefined8 uVar33;
  undefined8 extraout_x1_04;
  undefined *extraout_x1_05;
  undefined *extraout_x1_06;
  uint extraout_x1_07;
  undefined8 extraout_x1;
  int extraout_x1_00;
  int extraout_x1_01;
  undefined8 extraout_x2;
  undefined8 extraout_x2_00;
  undefined8 extraout_x2_01;
  undefined8 extraout_x2_02;
  undefined1 auVar34 [24];
  undefined1 auVar35 [24];
  undefined1 auVar36 [24];
  undefined1 auVar37 [24];
  int extraout_x1_02;
  int *piVar44;
  undefined8 *puVar45;
  short *psVar46;
  undefined8 extraout_x2_03;
  undefined1 auVar38 [24];
  undefined1 auVar39 [24];
  undefined1 auVar40 [24];
  int extraout_x1_03;
  undefined8 extraout_x2_04;
  undefined1 auVar41 [24];
  undefined8 extraout_x2_05;
  undefined1 auVar42 [24];
  undefined1 auVar43 [24];
  uint uVar47;
  uint extraout_x2_06;
  undefined8 uVar48;
  undefined8 extraout_x3;
  int extraout_x3_00;
  undefined8 uVar49;
  undefined8 extraout_x4;
  undefined8 extraout_x4_00;
  undefined8 extraout_x4_01;
  undefined8 extraout_x4_02;
  undefined8 *extraout_x5;
  int *piVar50;
  int *extraout_x5_00;
  uint uVar51;
  int iVar52;
  undefined *puVar53;
  int iVar54;
  undefined1 (*in_x25) [16];
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar55 [16];
  undefined1 auVar56 [16];
  undefined1 auVar57 [16];
  undefined1 auVar58 [16];
  undefined8 local_738 [15];
  undefined8 local_6c0 [14];
  int local_650 [12];
  undefined8 local_5f0 [12];
  int local_590 [23];
  int local_4d8 [4];
  undefined8 local_4b8 [13];
  undefined8 local_450 [124];
  int local_70 [14];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x6b0) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x53a70c;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x738) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x730) = in_x30;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + -0x560) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x588) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x580) = 0;
  auVar55 = strings_genSplit(param_2,param_3,&DAT_00c0a630,1,0,0xffffffffffffffff);
  puVar32 = auVar55._0_8_;
  if (auVar55._8_8_ < 4) {
    puVar32 = (undefined8 *)runtime_newobject(&DAT_008f85a0);
    *puVar32 = &DAT_009f0d63;
    puVar32[1] = 0x10;
    *(undefined8 *)((int)register0x00000008 + -0x550) = 0;
    *(undefined1 **)((int)register0x00000008 + -0x578) = go_itab__errors_errorString_error;
    *(undefined8 **)((int)register0x00000008 + -0x570) = puVar32;
    runtime_deferreturn();
    auVar37._0_8_ = *(undefined8 *)((int)register0x00000008 + -0x548);
    auVar37._8_8_ = *(undefined8 *)((int)register0x00000008 + -0x570);
    auVar37._16_8_ = *(undefined8 *)((int)register0x00000008 + -0x568);
    return auVar37;
  }
  uVar48 = *puVar32;
  *(undefined8 *)((int)register0x00000008 + -0x6a8) = puVar32[1];
  *(undefined8 *)((int)register0x00000008 + -0x540) = uVar48;
  uVar48 = puVar32[2];
  *(undefined8 *)((int)register0x00000008 + -0x680) = puVar32[3];
  *(undefined8 *)((int)register0x00000008 + -0x518) = uVar48;
  uVar48 = puVar32[4];
  *(undefined8 *)((int)register0x00000008 + -0x6a0) = puVar32[5];
  *(undefined8 *)((int)register0x00000008 + -0x538) = uVar48;
  uVar48 = puVar32[6];
  *(undefined8 *)((int)register0x00000008 + -0x6c0) = puVar32[7];
  *(undefined8 *)((int)register0x00000008 + -0x550) = uVar48;
  if (auVar55._8_8_ < 5) {
    puVar53 = &DAT_009d21df;
    iVar54 = 3;
  }
  else {
    puVar53 = (undefined *)puVar32[8];
    iVar54 = puVar32[9];
    if (iVar54 == 0) {
      puVar53 = &DAT_009d21df;
      iVar54 = 3;
    }
  }
  *(int *)((int)register0x00000008 + -0x628) = iVar54;
  *(undefined **)((int)register0x00000008 + -0x498) = puVar53;
  context_WithTimeout(go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,30000000000);
  *(undefined8 *)((int)register0x00000008 + -0x650) = extraout_x0;
  *(undefined8 *)((int)register0x00000008 + -0x4b8) = extraout_x1;
  *(undefined8 *)((int)register0x00000008 + -0x590) = extraout_x2;
  runtime_deferprocStack((undefined1 *)((int)register0x00000008 + -0x5a8));
  *(undefined8 *)((int)register0x00000008 + -0x70) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x68) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x60) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x58) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x50) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x48) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x40) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x38) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x30) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x28) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x20) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x18) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
  *(undefined8 *)((int)register0x00000008 + -8) = 0;
  *(uint8 **)((int)register0x00000008 + -0x70) = mv_daemon_provider_Cloud115ApiBase.str;
  *(int *)((int)register0x00000008 + -0x68) = mv_daemon_provider_Cloud115ApiBase.len;
  *(undefined **)((int)register0x00000008 + -0x60) = &DAT_009f29c2;
  *(undefined8 *)((int)register0x00000008 + -0x58) = 0x11;
  *(undefined8 *)((int)register0x00000008 + -0x50) =
       *(undefined8 *)((int)register0x00000008 + -0x530);
  *(undefined8 *)((int)register0x00000008 + -0x48) =
       *(undefined8 *)((int)register0x00000008 + -0x698);
  *(undefined **)((int)register0x00000008 + -0x40) = &DAT_009d5c73;
  *(undefined8 *)((int)register0x00000008 + -0x38) = 6;
  *(undefined8 *)((int)register0x00000008 + -0x30) =
       *(undefined8 *)((int)register0x00000008 + -0x508);
  *(undefined8 *)((int)register0x00000008 + -0x28) =
       *(undefined8 *)((int)register0x00000008 + -0x670);
  *(undefined **)((int)register0x00000008 + -0x20) = &DAT_009d5c79;
  *(undefined8 *)((int)register0x00000008 + -0x18) = 6;
  *(undefined8 *)((int)register0x00000008 + -0x10) =
       *(undefined8 *)((int)register0x00000008 + -0x528);
  *(undefined8 *)((int)register0x00000008 + -8) = *(undefined8 *)((int)register0x00000008 + -0x690);
  auVar55 = runtime_concatstrings(0,(undefined8 *)((int)register0x00000008 + -0x70),7,7);
  net_http_NewRequestWithContext
            (*(undefined8 *)((int)register0x00000008 + -0x640),
             *(undefined8 *)((int)register0x00000008 + -0x4a8),&DAT_009d2101,3,auVar55._0_8_,
             auVar55._8_8_,0,0);
  if (extraout_x1_00 != 0) {
    *(undefined8 *)((int)register0x00000008 + -0x538) = 0;
    *(int *)((int)register0x00000008 + -0x560) = extraout_x1_00;
    *(undefined8 *)((int)register0x00000008 + -0x558) = extraout_x2_00;
    runtime_deferreturn();
    auVar36._0_8_ = *(undefined8 *)((int)register0x00000008 + -0x530);
    auVar36._8_8_ = *(undefined8 *)((int)register0x00000008 + -0x558);
    auVar36._16_8_ = *(undefined8 *)((int)register0x00000008 + -0x550);
    return auVar36;
  }
  *(int *)((int)register0x00000008 + -0x4d8) = extraout_x0_00;
  *(undefined8 *)((int)register0x00000008 + -0x4b0) = *(undefined8 *)(extraout_x0_00 + 0x38);
  auVar55 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e173b,10);
  *(int *)((int)register0x00000008 + -0x450) = auVar55._0_8_;
  *(int *)((int)register0x00000008 + -0x5f0) = auVar55._8_8_;
  puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
  *(undefined8 **)((int)register0x00000008 + -0x450) = puVar32;
  *puVar32 = &DAT_009e85e2;
  puVar32[1] = 0xc;
  auVar55 = runtime_mapassign_faststr
                      (&DAT_00969220,*(undefined8 *)((int)register0x00000008 + -0x4a0),
                       *(undefined8 *)((int)register0x00000008 + -0x448),
                       *(undefined8 *)((int)register0x00000008 + -0x5e8));
  puVar32 = auVar55._0_8_;
  puVar3 = (undefined1 *)((int)register0x00000008 + -0x6f0);
  puVar32[1] = 1;
  puVar32[2] = 1;
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar48 = *(undefined8 *)((int)register0x00000008 + -0x448);
  }
  else {
    puVar32 = (undefined8 *)runtime_gcWriteBarrier2(puVar32,auVar55._8_8_,*puVar32);
    puVar3 = (undefined1 *)((int)register0x00000008 + -0x6e8);
    uVar48 = *(undefined8 *)((int)register0x00000008 + -0x440);
    *(undefined8 *)*in_x25 = uVar48;
    *(undefined8 *)(*in_x25 + 8) = extraout_x2_01;
  }
  *puVar32 = uVar48;
  net_http___Client__do(net_http_DefaultClient,*(undefined8 *)(puVar3 + 0x230));
  if (extraout_x1_01 != 0) {
    *(undefined8 *)(puVar3 + 0x268) = extraout_x2_02;
    *(int *)(puVar3 + 0xd0) = extraout_x1_01;
    auVar55 = (**(code **)(*(int *)(puVar3 + 0xd8) + 0x28))(*(undefined8 *)(puVar3 + 0x270));
    uVar51 = errors_Is(auVar55._0_8_,auVar55._8_8_,context_DeadlineExceeded.tab,
                       context_DeadlineExceeded.data);
    if ((uVar51 & 1) == 0) {
      *(undefined8 *)(puVar3 + 0x1e8) = 0;
      *(undefined8 *)(puVar3 + 0x1c0) = *(undefined8 *)(puVar3 + 0xe0);
      *(undefined8 *)(puVar3 + 0x1c8) = *(undefined8 *)(puVar3 + 0x278);
      runtime_deferreturn();
      auVar35._0_8_ = *(undefined8 *)(puVar3 + 0x1f0);
      auVar35._8_8_ = *(undefined8 *)(puVar3 + 0x1c8);
      auVar35._16_8_ = *(undefined8 *)(puVar3 + 0x1d0);
      return auVar35;
    }
    puVar32 = (undefined8 *)runtime_newobject(&DAT_0095ade0);
    *puVar32 = &DAT_009d73b7;
    puVar32[1] = 7;
    *(undefined8 **)(puVar3 + 0x1f0) = puVar32;
    *(undefined8 *)(puVar3 + 0x1c8) = 0;
    *(undefined8 *)(puVar3 + 0x1d0) = 0;
    runtime_deferreturn();
    auVar34._0_8_ = *(undefined8 *)(puVar3 + 0x1f8);
    auVar34._8_8_ = *(undefined8 *)(puVar3 + 0x1d0);
    auVar34._16_8_ = *(undefined8 *)(puVar3 + 0x1d8);
    return auVar34;
  }
  *(int *)(puVar3 + 0x1d0) = extraout_x0_01;
  uVar48 = *(undefined8 *)(extraout_x0_01 + 0x40);
  uVar33 = *(undefined8 *)(extraout_x0_01 + 0x48);
  *(code **)(puVar3 + 0x5f8) = mv_daemon_provider___Cloud115Provider__PollQrLogin_deferwrap1;
  *(undefined8 *)(puVar3 + 0x600) = uVar48;
  *(undefined8 *)(puVar3 + 0x608) = uVar33;
  *(undefined1 **)(puVar3 + 0x168) = puVar3 + 0x5f8;
  runtime_deferprocStack(puVar3 + 0x150);
  uVar48 = runtime_newobject(&DAT_008e5c80);
  *(undefined8 *)(puVar3 + 0x730) = uVar48;
  iVar54 = *(int *)(*(int *)(puVar3 + 0x1e0) + 0x40);
  *(undefined8 *)(puVar3 + 0x250) = *(undefined8 *)(*(int *)(puVar3 + 0x1e0) + 0x48);
  uVar48 = 0;
  puVar25 = puVar3 + 0x18;
  if (iVar54 != 0) {
    uVar51 = (uint)*(dword *)(iVar54 + 0x10);
    do {
      iVar52 = (uVar51 & *(uint *)mv_daemon_provider__typeAssert_71) * 0x10;
      if (*(int *)(mv_daemon_provider__typeAssert_71 + iVar52 + 8) == *(int *)(iVar54 + 8)) {
        uVar48 = *(undefined8 *)(mv_daemon_provider__typeAssert_71 + iVar52 + 0x10);
        puVar25 = puVar3 + 0x18;
        goto LAB_00539504;
      }
      uVar51 = uVar51 + 1;
    } while (*(int *)(mv_daemon_provider__typeAssert_71 + iVar52 + 8) != 0);
    uVar48 = runtime_typeAssert(&mv_daemon_provider__typeAssert_71,*(int *)(iVar54 + 8));
    puVar25 = puVar3 + 0x20;
  }
LAB_00539504:
  *(undefined8 *)(puVar25 + 0x2b0) = uVar48;
  puVar32 = (undefined8 *)runtime_newobject(&DAT_00991b80);
  puVar4 = puVar25 + 8;
  *puVar32 = *(undefined8 *)(puVar25 + 0x2b8);
  if (runtime_writeBarrier._0_4_ == 0) {
    uVar48 = *(undefined8 *)(puVar25 + 0x240);
  }
  else {
    puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
    puVar4 = puVar25 + 0x10;
    uVar48 = *(undefined8 *)(puVar25 + 0x248);
    *(undefined8 *)*in_x25 = uVar48;
  }
  puVar32[1] = uVar48;
  auVar55 = encoding_json___Decoder__Decode(puVar32,&DAT_008985e0,*(undefined8 *)(puVar4 + 0x718));
  if (auVar55._0_8_ != 0) {
    *(undefined8 *)(puVar4 + 0x1d8) = 0;
    *(undefined1 (*) [16])(puVar4 + 0x1b0) = auVar55;
    runtime_deferreturn();
    auVar39._0_8_ = *(undefined8 *)(puVar4 + 0x1e0);
    auVar39._8_8_ = *(undefined8 *)(puVar4 + 0x1b8);
    auVar39._16_8_ = *(undefined8 *)(puVar4 + 0x1c0);
    return auVar39;
  }
  iVar54 = **(int **)(puVar4 + 0x720);
  if (iVar54 == 1) {
    uVar48 = 7;
    puVar53 = &DAT_009d76ea;
  }
  else if (iVar54 == 2) {
    uVar48 = 9;
    puVar53 = &DAT_009dd00d;
  }
  else {
    if (iVar54 == -1) {
      puVar53 = &DAT_009d76f1;
    }
    else {
      puVar53 = &DAT_009d73b7;
    }
    uVar48 = 7;
  }
  *(undefined8 *)(puVar4 + 0xa8) = uVar48;
  *(undefined **)(puVar4 + 0x210) = puVar53;
  iVar54 = runtime_newobject(&DAT_0095ade0);
  puVar5 = puVar4 + 0x10;
  auVar55._8_8_ = *(undefined8 *)(puVar4 + 0xb0);
  auVar55._0_8_ = iVar54;
  *(undefined8 *)(iVar54 + 8) = *(undefined8 *)(puVar4 + 0xb0);
  if (runtime_writeBarrier._0_4_ == 0) {
    piVar44 = *(int **)(puVar4 + 0x218);
  }
  else {
    auVar55 = runtime_gcWriteBarrier1();
    puVar5 = puVar4 + 0x18;
    piVar44 = *(int **)(puVar4 + 0x220);
    *(int **)*in_x25 = piVar44;
  }
  piVar50 = auVar55._0_8_;
  *piVar50 = (int)piVar44;
  if (((auVar55._8_8_ == 9) && (*piVar44 == 0x656d7269666e6f63)) && ((char)piVar44[1] == 'd')) {
    *(int **)(puVar5 + 0x220) = piVar50;
    *(undefined8 *)(puVar5 + 0x698) = 0;
    *(undefined8 *)(puVar5 + 0x6a0) = 0;
    uVar48 = runtime_convTstring(*(undefined8 *)(puVar5 + 0x290),*(undefined8 *)(puVar5 + 0x100));
    *(undefined8 **)(puVar5 + 0x6a0) = &DAT_008a6880;
    *(undefined8 *)(puVar5 + 0x6a8) = uVar48;
    auVar55 = fmt_Sprintf(&DAT_00a21f6e,0x37,puVar5 + 0x6a0,1,1);
    *(int *)(puVar5 + 0x290) = auVar55._0_8_;
    *(int *)(puVar5 + 0xf8) = auVar55._8_8_;
    *(undefined8 *)(puVar5 + 0x5d0) = 0;
    *(undefined8 *)(puVar5 + 0x5d8) = 0;
    *(undefined8 *)(puVar5 + 0x5e0) = 0;
    *(undefined8 *)(puVar5 + 0x5e8) = 0;
    *(undefined8 *)(puVar5 + 0x5f0) = 0;
    *(undefined8 *)(puVar5 + 0x5f8) = 0;
    iVar54 = 5;
    puVar32 = (undefined8 *)(puVar5 + 0x488);
    do {
      *puVar32 = 0;
      puVar32[1] = 0;
      puVar32[2] = 0;
      puVar32[3] = 0;
      puVar32[4] = 0;
      puVar32[5] = 0;
      puVar45 = puVar32 + 8;
      puVar32[6] = 0;
      puVar32[7] = 0;
      iVar54 = iVar54 + -1;
      puVar32 = puVar45;
    } while (iVar54 != 0);
    *puVar45 = 0;
    *(undefined1 **)(puVar5 + 0x488) = &DAT_8080808080808080;
    *(undefined1 **)(puVar5 + 0x5e0) = puVar5 + 0x488;
    uVar48 = runtime_rand();
    *(undefined8 *)(puVar5 + 0x5e0) = uVar48;
    puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
    puVar6 = puVar5 + 0x20;
    puVar32[1] = *(undefined8 *)(puVar5 + 0xa0);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar5 + 0x208);
    }
    else {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar6 = puVar5 + 0x28;
      uVar48 = *(undefined8 *)(puVar5 + 0x210);
      *(undefined8 *)*in_x25 = uVar48;
    }
    *(undefined8 **)(puVar6 + 0x2a8) = puVar32;
    *puVar32 = uVar48;
    puVar32 = (undefined8 *)runtime_mapassign_faststr(&DAT_00973360,puVar6 + 0x5c0,&DAT_009d7722,7);
    puVar7 = puVar6 + 8;
    puVar32[1] = 1;
    puVar32[2] = 1;
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar6 + 0x2b0);
    }
    else {
      auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
      puVar32 = auVar55._0_8_;
      puVar7 = puVar6 + 0x10;
      uVar48 = *(undefined8 *)(puVar6 + 0x2b8);
      *(undefined8 *)*in_x25 = uVar48;
      *(int *)(*in_x25 + 8) = auVar55._8_8_;
    }
    *puVar32 = uVar48;
    puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
    puVar8 = puVar7 + 8;
    puVar32[1] = *(undefined8 *)(puVar7 + 0x108);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar7 + 0x298);
    }
    else {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar8 = puVar7 + 0x10;
      uVar48 = *(undefined8 *)(puVar7 + 0x2a0);
      *(undefined8 *)*in_x25 = uVar48;
    }
    *(undefined8 **)(puVar8 + 0x2a8) = puVar32;
    *puVar32 = uVar48;
    puVar32 = (undefined8 *)runtime_mapassign_faststr(&DAT_00973360,puVar8 + 0x5c0,&DAT_009d2233,3);
    puVar9 = puVar8 + 8;
    puVar32[1] = 1;
    puVar32[2] = 1;
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar8 + 0x2b0);
    }
    else {
      auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
      puVar32 = auVar55._0_8_;
      puVar9 = puVar8 + 0x10;
      uVar48 = *(undefined8 *)(puVar8 + 0x2b8);
      *(undefined8 *)*in_x25 = uVar48;
      *(int *)(*in_x25 + 8) = auVar55._8_8_;
    }
    *puVar32 = uVar48;
    iVar54 = *(int *)(puVar9 + 0x100);
    if (iVar54 == 3) {
      psVar46 = *(short **)(puVar9 + 0x290);
      if ((*psVar46 == 0x6577) && ((char)psVar46[1] == 'b')) {
        puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
        puVar10 = puVar9 + 8;
        puVar32[1] = *(undefined8 *)(puVar9 + 0xb0);
        if (runtime_writeBarrier._0_4_ == 0) {
          uVar48 = *(undefined8 *)(puVar9 + 0x218);
        }
        else {
          puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
          puVar10 = puVar9 + 0x10;
          uVar48 = *(undefined8 *)(puVar9 + 0x220);
          *(undefined8 *)*in_x25 = uVar48;
        }
        *(undefined8 **)(puVar10 + 0x2a8) = puVar32;
        *puVar32 = uVar48;
        puVar32 = (undefined8 *)
                  runtime_mapassign_faststr(&DAT_00973360,puVar10 + 0x5c0,&DAT_009d2c50,4);
        puVar11 = puVar10 + 8;
        puVar32[1] = 1;
        puVar32[2] = 1;
        if (runtime_writeBarrier._0_4_ == 0) {
          uVar48 = *(undefined8 *)(puVar10 + 0x2b0);
        }
        else {
          auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
          puVar32 = auVar55._0_8_;
          puVar11 = puVar10 + 0x10;
          uVar48 = *(undefined8 *)(puVar10 + 0x2b8);
          *(undefined8 *)*in_x25 = uVar48;
          *(int *)(*in_x25 + 8) = auVar55._8_8_;
        }
        *puVar32 = uVar48;
        puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
        puVar12 = puVar11 + 8;
        puVar32[1] = *(undefined8 *)(puVar11 + 0x90);
        if (runtime_writeBarrier._0_4_ == 0) {
          uVar48 = *(undefined8 *)(puVar11 + 0x1f8);
        }
        else {
          puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
          puVar12 = puVar11 + 0x10;
          uVar48 = *(undefined8 *)(puVar11 + 0x200);
          *(undefined8 *)*in_x25 = uVar48;
        }
        *(undefined8 **)(puVar12 + 0x2a8) = puVar32;
        *puVar32 = uVar48;
        auVar55 = runtime_mapassign_faststr(&DAT_00973360,puVar12 + 0x5c0,&DAT_009d2c28,4);
        puVar32 = auVar55._0_8_;
        puVar9 = puVar12 + 8;
        puVar32[1] = 1;
        puVar32[2] = 1;
        if (runtime_writeBarrier._0_4_ == 0) {
          psVar46 = *(short **)(puVar12 + 0x2b0);
        }
        else {
          auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
          puVar9 = puVar12 + 0x10;
          psVar46 = *(short **)(puVar12 + 0x2b8);
          *(short **)*in_x25 = psVar46;
          *(int *)(*in_x25 + 8) = auVar55._8_8_;
        }
        iVar54 = auVar55._8_8_;
        *auVar55._0_8_ = psVar46;
      }
    }
    else {
      psVar46 = *(short **)(puVar9 + 0x290);
    }
    auVar55 = net_url_Values_Encode(puVar9 + 0x5c0,iVar54,psVar46);
    *(int *)(puVar9 + 0xb8) = auVar55._8_8_;
    *(int *)(puVar9 + 0x220) = auVar55._0_8_;
    puVar32 = (undefined8 *)runtime_newobject(&DAT_00940be0);
    puVar13 = puVar9 + 0x10;
    puVar32[1] = *(undefined8 *)(puVar9 + 0xc0);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar9 + 0x228);
    }
    else {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar13 = puVar9 + 0x18;
      uVar48 = *(undefined8 *)(puVar9 + 0x230);
      *(undefined8 *)*in_x25 = uVar48;
    }
    *puVar32 = uVar48;
    puVar32[2] = 0;
    puVar32[3] = 0xffffffffffffffff;
    net_http_NewRequestWithContext
              (go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_009d2ad8,4,
               *(undefined8 *)(puVar13 + 0x280),*(undefined8 *)(puVar13 + 0xe8),
               go_itab__strings_Reader_io_Reader,puVar32);
    if (extraout_x1_02 != 0) {
      *(undefined8 *)(puVar13 + 0x1d8) = 0;
      *(int *)(puVar13 + 0x1b0) = extraout_x1_02;
      *(undefined8 *)(puVar13 + 0x1b8) = extraout_x2_03;
      runtime_deferreturn();
      auVar38._0_8_ = *(undefined8 *)(puVar13 + 0x1e0);
      auVar38._8_8_ = *(undefined8 *)(puVar13 + 0x1b8);
      auVar38._16_8_ = *(undefined8 *)(puVar13 + 0x1c0);
      return auVar38;
    }
    *(int *)(puVar13 + 0x230) = extraout_x0_02;
    *(undefined8 *)(puVar13 + 600) = *(undefined8 *)(extraout_x0_02 + 0x38);
    auVar55 = net_textproto_CanonicalMIMEHeaderKey(&DAT_009e80ea,0xc);
    *(int *)(puVar13 + 0x2c0) = auVar55._0_8_;
    *(int *)(puVar13 + 0x120) = auVar55._8_8_;
    puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
    *(undefined8 **)(puVar13 + 0x2c0) = puVar32;
    *puVar32 = &DAT_00a09c3a;
    puVar32[1] = 0x21;
    puVar32 = (undefined8 *)
              runtime_mapassign_faststr
                        (&DAT_00969220,*(undefined8 *)(puVar13 + 0x268),
                         *(undefined8 *)(puVar13 + 0x2c8),*(undefined8 *)(puVar13 + 0x128));
    puVar14 = puVar13 + 0x20;
    puVar32[1] = 1;
    puVar32[2] = 1;
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar13 + 0x2c8);
    }
    else {
      auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
      puVar32 = auVar55._0_8_;
      puVar14 = puVar13 + 0x28;
      uVar48 = *(undefined8 *)(puVar13 + 0x2d0);
      *(undefined8 *)*in_x25 = uVar48;
      *(int *)(*in_x25 + 8) = auVar55._8_8_;
    }
    *puVar32 = uVar48;
    *(undefined8 *)(puVar14 + 0x448) = 0;
    *(undefined8 *)(puVar14 + 0x450) = 0;
    *(undefined8 *)(puVar14 + 0x458) = 0;
    *(undefined8 *)(puVar14 + 0x460) = 0;
    *(undefined8 *)(puVar14 + 0x468) = 0;
    *(undefined8 *)(puVar14 + 0x470) = 0;
    iVar54 = 4;
    puVar32 = (undefined8 *)(puVar14 + 0x340);
    do {
      *puVar32 = 0;
      puVar32[1] = 0;
      puVar32[2] = 0;
      puVar32[3] = 0;
      puVar32[4] = 0;
      puVar32[5] = 0;
      puVar45 = puVar32 + 8;
      puVar32[6] = 0;
      puVar32[7] = 0;
      iVar54 = iVar54 + -1;
      puVar32 = puVar45;
    } while (iVar54 != 0);
    *puVar45 = 0;
    *(undefined1 **)(puVar14 + 0x340) = &DAT_8080808080808080;
    *(undefined1 **)(puVar14 + 0x458) = puVar14 + 0x340;
    uVar48 = runtime_rand();
    *(undefined8 *)(puVar14 + 0x458) = uVar48;
    puVar32 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar14 + 0x450,&DAT_009d5bdd,6)
    ;
    puVar15 = puVar14 + 0x10;
    puVar32[1] = 0x12;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar15 = puVar14 + 0x18;
      *(undefined8 *)*in_x25 = extraout_x4;
    }
    *puVar32 = &DAT_009f4eb0;
    puVar32 = (undefined8 *)runtime_mapassign_faststr(&DAT_008ecae0,puVar15 + 0x448,&DAT_009d73cc,7)
    ;
    puVar16 = puVar15 + 8;
    puVar32[1] = 0x13;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
      puVar16 = puVar15 + 0x10;
      *(undefined8 *)*in_x25 = extraout_x4_00;
    }
    *puVar32 = &DAT_009f6896;
    auVar55 = mv_daemon_provider_get115QrUserAgent
                        (*(undefined8 *)(puVar16 + 0x290),*(undefined8 *)(puVar16 + 0x100),
                         *(undefined8 *)(puVar16 + 0x1d8),*(undefined8 *)(puVar16 + 0x68));
    *(int *)(puVar16 + 0x118) = auVar55._8_8_;
    *(int *)(puVar16 + 0x2b8) = auVar55._0_8_;
    puVar32 = (undefined8 *)
              runtime_mapassign_faststr(&DAT_008ecae0,puVar16 + 0x450,&DAT_009e173b,10);
    puVar17 = puVar16 + 0x10;
    puVar32[1] = *(undefined8 *)(puVar16 + 0x120);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar48 = *(undefined8 *)(puVar16 + 0x2c0);
    }
    else {
      puVar32 = (undefined8 *)runtime_gcWriteBarrier2();
      puVar17 = puVar16 + 0x18;
      uVar48 = *(undefined8 *)(puVar16 + 0x2c8);
      *(undefined8 *)*in_x25 = uVar48;
      *(undefined8 *)(*in_x25 + 8) = extraout_x3;
    }
    *puVar32 = uVar48;
    *(undefined8 *)(puVar17 + 0x638) = 0;
    *(undefined8 *)(puVar17 + 0x640) = 0;
    *(undefined8 *)(puVar17 + 0x648) = 0;
    *(undefined8 *)(puVar17 + 0x650) = 0;
    *(undefined8 *)(puVar17 + 0x658) = 0;
    *(undefined8 *)(puVar17 + 0x660) = 0;
    *(undefined8 *)(puVar17 + 0x668) = 0;
    *(undefined8 *)(puVar17 + 0x670) = 0;
    *(undefined8 *)(puVar17 + 0x678) = 0;
    *(undefined8 *)(puVar17 + 0x680) = 0;
    *(undefined8 *)(puVar17 + 0x688) = 0;
    *(undefined8 *)(puVar17 + 0x690) = 0;
    runtime_mapIterStart(&DAT_008ecae0,puVar17 + 0x448);
    puVar18 = puVar17 + 8;
    while (puVar32 = *(undefined8 **)(puVar18 + 0x638), puVar32 != (undefined8 *)0x0) {
      uVar48 = *puVar32;
      uVar49 = puVar32[1];
      uVar33 = **(undefined8 **)(puVar18 + 0x640);
      *(undefined8 *)(puVar18 + 0x78) = (*(undefined8 **)(puVar18 + 0x640))[1];
      *(undefined8 *)(puVar18 + 0x1e0) = uVar33;
      *(undefined8 *)(puVar18 + 0x2a0) = *(undefined8 *)(*(int *)(puVar18 + 0x228) + 0x38);
      auVar55 = net_textproto_CanonicalMIMEHeaderKey(uVar48,uVar49);
      *(int *)(puVar18 + 0x2b8) = auVar55._0_8_;
      *(int *)(puVar18 + 0x118) = auVar55._8_8_;
      puVar32 = (undefined8 *)runtime_newobject(&DAT_008b05c0);
      puVar19 = puVar18 + 0x10;
      puVar32[1] = *(undefined8 *)(puVar18 + 0x88);
      if (runtime_writeBarrier._0_4_ == 0) {
        uVar48 = *(undefined8 *)(puVar18 + 0x1f0);
      }
      else {
        puVar32 = (undefined8 *)runtime_gcWriteBarrier1();
        puVar19 = puVar18 + 0x18;
        uVar48 = *(undefined8 *)(puVar18 + 0x1f8);
        *(undefined8 *)*in_x25 = uVar48;
      }
      *(undefined8 **)(puVar19 + 0x2a8) = puVar32;
      *puVar32 = uVar48;
      puVar32 = (undefined8 *)
                runtime_mapassign_faststr
                          (&DAT_00969220,*(undefined8 *)(puVar19 + 0x2a0),
                           *(undefined8 *)(puVar19 + 0x2b0),*(undefined8 *)(puVar19 + 0x110));
      puVar20 = puVar19 + 8;
      puVar32[1] = 1;
      puVar32[2] = 1;
      if (runtime_writeBarrier._0_4_ == 0) {
        uVar48 = *(undefined8 *)(puVar19 + 0x2b0);
      }
      else {
        auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
        puVar32 = auVar55._0_8_;
        puVar20 = puVar19 + 0x10;
        uVar48 = *(undefined8 *)(puVar19 + 0x2b8);
        *(undefined8 *)*in_x25 = uVar48;
        *(int *)(*in_x25 + 8) = auVar55._8_8_;
      }
      *puVar32 = uVar48;
      runtime_mapIterNext(puVar20 + 0x638);
      puVar18 = puVar20 + 8;
    }
    net_http___Client__do(net_http_DefaultClient,*(undefined8 *)(puVar18 + 0x228));
    if (extraout_x1_03 != 0) {
      *(undefined8 *)(puVar18 + 0x1d8) = 0;
      *(int *)(puVar18 + 0x1b0) = extraout_x1_03;
      *(undefined8 *)(puVar18 + 0x1b8) = extraout_x2_04;
      runtime_deferreturn();
      auVar41._0_8_ = *(undefined8 *)(puVar18 + 0x1e0);
      auVar41._8_8_ = *(undefined8 *)(puVar18 + 0x1b8);
      auVar41._16_8_ = *(undefined8 *)(puVar18 + 0x1c0);
      return auVar41;
    }
    *(int *)(puVar18 + 0x1c8) = extraout_x0_03;
    uVar48 = *(undefined8 *)(extraout_x0_03 + 0x40);
    uVar33 = *(undefined8 *)(extraout_x0_03 + 0x48);
    *(code **)(puVar18 + 0x330) = mv_daemon_provider___Cloud115Provider__PollQrLogin_deferwrap2;
    *(undefined8 *)(puVar18 + 0x338) = uVar48;
    *(undefined8 *)(puVar18 + 0x340) = uVar33;
    *(undefined1 **)(puVar18 + 0x138) = puVar18 + 0x330;
    runtime_deferprocStack(puVar18 + 0x120);
    iVar54 = *(int *)(*(int *)(puVar18 + 0x1d0) + 0x40);
    uVar48 = *(undefined8 *)(*(int *)(puVar18 + 0x1d0) + 0x48);
    uVar33 = 0;
    puVar25 = puVar18 + 0x10;
    if (iVar54 != 0) {
      iVar52 = *(int *)(iVar54 + 8);
      uVar51 = (uint)*(dword *)(iVar54 + 0x10);
      do {
        iVar54 = (uVar51 & *(uint *)mv_daemon_provider__typeAssert_72) * 0x10;
        if (*(int *)(mv_daemon_provider__typeAssert_72 + iVar54 + 8) == iVar52) {
          uVar33 = *(undefined8 *)(mv_daemon_provider__typeAssert_72 + iVar54 + 0x10);
          puVar25 = puVar18 + 0x10;
          goto LAB_00539d54;
        }
        uVar51 = uVar51 + 1;
      } while (*(int *)(mv_daemon_provider__typeAssert_72 + iVar54 + 8) != 0);
      *(undefined8 *)(puVar18 + 0x2c0) = uVar48;
      uVar33 = runtime_typeAssert(&mv_daemon_provider__typeAssert_72,iVar52);
      uVar48 = *(undefined8 *)(puVar18 + 0x2c8);
      puVar25 = puVar18 + 0x18;
    }
LAB_00539d54:
    io_ReadAll(uVar33,uVar48);
    if (extraout_x3_00 != 0) {
      *(undefined8 *)(puVar25 + 0x1d8) = 0;
      *(int *)(puVar25 + 0x1b0) = extraout_x3_00;
      *(undefined8 *)(puVar25 + 0x1b8) = extraout_x4_01;
      runtime_deferreturn();
      auVar42._0_8_ = *(undefined8 *)(puVar25 + 0x1e0);
      auVar42._8_8_ = *(undefined8 *)(puVar25 + 0x1b8);
      auVar42._16_8_ = *(undefined8 *)(puVar25 + 0x1c0);
      return auVar42;
    }
    *(undefined8 *)(puVar25 + 0x100) = extraout_x2_05;
    *(undefined8 *)(puVar25 + 0xf8) = extraout_x1_04;
    *(undefined8 *)(puVar25 + 0x290) = extraout_x0_04;
    uVar48 = runtime_newobject(&DAT_00952180);
    *(undefined8 *)(puVar25 + 0x730) = uVar48;
    auVar55 = encoding_json_Unmarshal
                        (*(undefined8 *)(puVar25 + 0x298),*(undefined8 *)(puVar25 + 0x100),
                         *(undefined8 *)(puVar25 + 0x108),&DAT_00899f20,uVar48);
    iVar54 = auVar55._0_8_;
    puVar21 = puVar25 + 0x18;
    if (iVar54 != 0) {
      *(undefined8 *)(puVar25 + 800) = 0;
      *(undefined8 *)(puVar25 + 0x328) = 0;
      *(undefined8 *)(puVar25 + 0x330) = 0;
      *(undefined8 *)(puVar25 + 0x338) = 0;
      uVar48 = 0;
      if (iVar54 != 0) {
        uVar48 = *(undefined8 *)(iVar54 + 8);
      }
      *(undefined8 *)(puVar25 + 800) = uVar48;
      *(int *)(puVar25 + 0x328) = auVar55._8_8_;
      runtime_slicebytetostring(0,*(undefined8 *)(puVar25 + 0x2a0),*(undefined8 *)(puVar25 + 0x108))
      ;
      uVar48 = runtime_convTstring();
      *(undefined8 **)(puVar25 + 0x340) = &DAT_008a6880;
      *(undefined8 *)(puVar25 + 0x348) = uVar48;
      *(code **)(puVar25 + 0x630) = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func1;
      *(undefined **)(puVar25 + 0x638) = &DAT_00a2944c;
      *(undefined8 *)(puVar25 + 0x640) = 0x42;
      *(undefined8 *)(puVar25 + 0x658) = 2;
      *(undefined1 **)(puVar25 + 0x648) = puVar25 + 0x330;
      *(undefined8 *)(puVar25 + 0x650) = 2;
      log___Logger__output(log_std,0,2,puVar25 + 0x630);
      puVar21 = puVar25 + 0x30;
    }
    iVar54 = *(int *)(puVar21 + 0x720);
    if (*(int *)(iVar54 + 0x20) != 0) {
      *(undefined8 *)(puVar21 + 0x2f8) = 0;
      *(undefined8 *)(puVar21 + 0x300) = 0;
      uVar48 = runtime_convTstring(*(undefined8 *)(iVar54 + 0x18),*(undefined8 *)(iVar54 + 0x20));
      *(undefined8 **)(puVar21 + 0x300) = &DAT_008a6880;
      *(undefined8 *)(puVar21 + 0x308) = uVar48;
      *(code **)(puVar21 + 0x610) = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func2;
      *(undefined **)(puVar21 + 0x618) = &DAT_00a1f6a5;
      *(undefined8 *)(puVar21 + 0x620) = 0x34;
      *(undefined8 *)(puVar21 + 0x638) = 1;
      *(undefined1 **)(puVar21 + 0x628) = puVar21 + 0x300;
      *(undefined8 *)(puVar21 + 0x630) = 1;
      log___Logger__output(log_std,0,2,puVar21 + 0x610);
      puVar21 = puVar21 + 0x10;
    }
    uVar48 = runtime_makemap_small();
    *(undefined8 *)(puVar21 + 0x280) = uVar48;
    auVar56 = net_http_readSetCookies(*(undefined8 *)(*(int *)(puVar21 + 0x1c8) + 0x38));
    *(int *)(puVar21 + 0x1c8) = auVar56._0_8_;
    *(int *)(puVar21 + 0x70) = auVar56._8_8_;
    puVar25 = puVar21 + 0x10;
    for (iVar54 = 0; iVar54 < auVar56._8_8_; iVar54 = iVar54 + 1) {
      puVar32 = *(undefined8 **)(auVar56._0_8_ + iVar54 * 8);
      uVar48 = *puVar32;
      puVar22 = puVar25;
      if (puVar32[1] != 0) {
        uVar33 = puVar32[2];
        if (puVar32[3] != 0) {
          *(undefined8 *)(puVar25 + 0x110) = puVar32[3];
          *(undefined8 *)(puVar25 + 0x2b0) = uVar33;
          *(int *)(puVar25 + 0x108) = iVar54;
          puVar32 = (undefined8 *)
                    runtime_mapassign_faststr(&DAT_008ecae0,*(undefined8 *)(puVar25 + 0x278),uVar48)
          ;
          puVar22 = puVar25 + 8;
          puVar32[1] = *(undefined8 *)(puVar25 + 0x118);
          if (runtime_writeBarrier._0_4_ == 0) {
            uVar48 = *(undefined8 *)(puVar25 + 0x2b8);
          }
          else {
            puVar32 = (undefined8 *)runtime_gcWriteBarrier2();
            puVar22 = puVar25 + 0x10;
            uVar48 = *(undefined8 *)(puVar25 + 0x2c0);
            *(undefined8 *)*in_x25 = uVar48;
            *(undefined8 *)(*in_x25 + 8) = extraout_x4_02;
          }
          *puVar32 = uVar48;
          auVar56._8_8_ = *(undefined8 *)(puVar22 + 0x60);
          auVar56._0_8_ = *(undefined8 *)(puVar22 + 0x1b8);
          iVar54 = *(int *)(puVar22 + 0x108);
        }
      }
      puVar25 = puVar22;
    }
    if (*(int *)(*(int *)(puVar25 + 0x720) + 0x28) != 0) {
      puVar32 = (undefined8 *)
                runtime_mapaccess1_faststr
                          (&DAT_008ecbe0,*(int *)(*(int *)(puVar25 + 0x720) + 0x28),&DAT_009d5991,6)
      ;
      puVar22 = puVar25 + 8;
      uVar48 = puVar32[1];
      if ((undefined *)*puVar32 == &DAT_008ecbe0) {
        *(undefined8 *)(puVar25 + 0x640) = 0;
        *(undefined8 *)(puVar25 + 0x648) = 0;
        *(undefined8 *)(puVar25 + 0x650) = 0;
        *(undefined8 *)(puVar25 + 0x658) = 0;
        *(undefined8 *)(puVar25 + 0x660) = 0;
        *(undefined8 *)(puVar25 + 0x668) = 0;
        *(undefined8 *)(puVar25 + 0x670) = 0;
        *(undefined8 *)(puVar25 + 0x678) = 0;
        *(undefined8 *)(puVar25 + 0x680) = 0;
        *(undefined8 *)(puVar25 + 0x688) = 0;
        *(undefined8 *)(puVar25 + 0x690) = 0;
        *(undefined8 *)(puVar25 + 0x698) = 0;
        runtime_mapIterStart(&DAT_008ecbe0,uVar48);
        for (puVar22 = puVar25 + 0x10; puVar32 = *(undefined8 **)(puVar22 + 0x638),
            puVar32 != (undefined8 *)0x0; puVar22 = puVar22 + 8) {
          uVar48 = *puVar32;
          puVar45 = (undefined8 *)**(undefined8 **)(puVar22 + 0x640);
          puVar2 = (undefined8 *)(*(undefined8 **)(puVar22 + 0x640))[1];
          if (puVar45 == &DAT_008a6880) {
            uVar33 = *puVar2;
            if (puVar2[1] == 0) goto LAB_0053a058;
            *(undefined8 *)(puVar22 + 0x98) = puVar2[1];
            *(undefined8 *)(puVar22 + 0x200) = uVar33;
            auVar55 = runtime_mapassign_faststr(&DAT_008ecae0,*(undefined8 *)(puVar22 + 0x278));
            puVar32 = auVar55._0_8_;
            puVar23 = puVar22 + 8;
            puVar32[1] = *(undefined8 *)(puVar22 + 0xa0);
            if (runtime_writeBarrier._0_4_ == 0) {
              uVar48 = *(undefined8 *)(puVar22 + 0x208);
            }
            else {
              auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
              puVar23 = puVar22 + 0x10;
              uVar48 = *(undefined8 *)(puVar22 + 0x210);
              *(undefined8 *)*in_x25 = uVar48;
              *(int *)(*in_x25 + 8) = auVar55._8_8_;
            }
            puVar53 = auVar55._8_8_;
            *auVar55._0_8_ = uVar48;
            puVar22 = puVar23;
          }
          else {
LAB_0053a058:
            puVar53 = &DAT_008a6c40;
            if (puVar45 == (undefined8 *)&DAT_008a6c40) {
              uVar33 = *puVar2;
              *(undefined8 *)(puVar22 + 0xc0) = puVar32[1];
              *(undefined8 *)(puVar22 + 0x248) = uVar48;
              *(undefined8 *)(puVar22 + 0x698) = 0;
              *(undefined8 *)(puVar22 + 0x6a0) = 0;
              uVar48 = runtime_convT64(uVar33);
              *(undefined **)(puVar22 + 0x6a0) = &DAT_008a6c40;
              *(undefined8 *)(puVar22 + 0x6a8) = uVar48;
              auVar55 = fmt_Sprintf(&DAT_009d2c0c,4,puVar22 + 0x6a0,1,1);
              *(int *)(puVar22 + 0x120) = auVar55._8_8_;
              *(int *)(puVar22 + 0x2c0) = auVar55._0_8_;
              puVar32 = (undefined8 *)
                        runtime_mapassign_faststr
                                  (&DAT_008ecae0,*(undefined8 *)(puVar22 + 0x288),
                                   *(undefined8 *)(puVar22 + 600),*(undefined8 *)(puVar22 + 0xd0));
              puVar24 = puVar22 + 0x18;
              puVar32[1] = *(undefined8 *)(puVar22 + 0x128);
              if (runtime_writeBarrier._0_4_ == 0) {
                uVar48 = *(undefined8 *)(puVar22 + 0x2c8);
              }
              else {
                auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
                puVar32 = auVar55._0_8_;
                puVar24 = puVar22 + 0x20;
                uVar48 = *(undefined8 *)(puVar22 + 0x2d0);
                *(undefined8 *)*in_x25 = uVar48;
                *(int *)(*in_x25 + 8) = auVar55._8_8_;
              }
              *puVar32 = uVar48;
              puVar53 = &DAT_008a6c40;
              puVar22 = puVar24;
            }
          }
          runtime_mapIterNext(puVar22 + 0x638,puVar53);
        }
      }
      uVar48 = *(undefined8 *)(*(int *)(puVar22 + 0x720) + 0x28);
      *(undefined8 *)(puVar22 + 0x638) = 0;
      *(undefined8 *)(puVar22 + 0x640) = 0;
      *(undefined8 *)(puVar22 + 0x648) = 0;
      *(undefined8 *)(puVar22 + 0x650) = 0;
      *(undefined8 *)(puVar22 + 0x658) = 0;
      *(undefined8 *)(puVar22 + 0x660) = 0;
      *(undefined8 *)(puVar22 + 0x668) = 0;
      *(undefined8 *)(puVar22 + 0x670) = 0;
      *(undefined8 *)(puVar22 + 0x678) = 0;
      *(undefined8 *)(puVar22 + 0x680) = 0;
      *(undefined8 *)(puVar22 + 0x688) = 0;
      *(undefined8 *)(puVar22 + 0x690) = 0;
      runtime_mapIterStart(&DAT_008ecbe0,uVar48);
      puVar53 = extraout_x1_05;
      for (puVar25 = puVar22 + 8; piVar44 = *(int **)(puVar25 + 0x638), piVar44 != (int *)0x0;
          puVar25 = puVar25 + 8) {
        psVar1 = (sdword *)*piVar44;
        puVar32 = (undefined8 *)**(undefined8 **)(puVar25 + 0x640);
        puVar45 = (undefined8 *)(*(undefined8 **)(puVar25 + 0x640))[1];
        if (((piVar44[1] != 6) || (*psVar1 != 0x6b6f6f63)) || ((short)psVar1[1] != 0x6569)) {
          if (puVar32 == &DAT_008a6880) {
            iVar54 = puVar45[1];
            if (iVar54 != 0) {
              *(undefined8 *)(puVar25 + 0x1f8) = *puVar45;
              *(int *)(puVar25 + 0x90) = iVar54;
              auVar55 = runtime_mapassign_faststr(&DAT_008ecae0,*(undefined8 *)(puVar25 + 0x278));
              puVar32 = auVar55._0_8_;
              puVar26 = puVar25 + 8;
              puVar32[1] = *(undefined8 *)(puVar25 + 0x98);
              if (runtime_writeBarrier._0_4_ == 0) {
                uVar48 = *(undefined8 *)(puVar25 + 0x200);
              }
              else {
                auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
                puVar26 = puVar25 + 0x10;
                uVar48 = *(undefined8 *)(puVar25 + 0x208);
                *(undefined8 *)*in_x25 = uVar48;
                *(int *)(*in_x25 + 8) = auVar55._8_8_;
              }
              puVar53 = auVar55._8_8_;
              *auVar55._0_8_ = uVar48;
              puVar25 = puVar26;
              goto LAB_0053a154;
            }
          }
          puVar53 = &DAT_008a6c40;
          if (puVar32 == (undefined8 *)&DAT_008a6c40) {
            uVar48 = *puVar45;
            *(int *)(puVar25 + 0xb8) = piVar44[1];
            *(sdword **)(puVar25 + 0x240) = psVar1;
            *(undefined8 *)(puVar25 + 0x698) = 0;
            *(undefined8 *)(puVar25 + 0x6a0) = 0;
            uVar48 = runtime_convT64(uVar48);
            *(undefined **)(puVar25 + 0x6a0) = &DAT_008a6c40;
            *(undefined8 *)(puVar25 + 0x6a8) = uVar48;
            auVar55 = fmt_Sprintf(&DAT_009d2c0c,4,puVar25 + 0x6a0,1,1);
            *(int *)(puVar25 + 0x120) = auVar55._8_8_;
            *(int *)(puVar25 + 0x2c0) = auVar55._0_8_;
            puVar32 = (undefined8 *)
                      runtime_mapassign_faststr
                                (&DAT_008ecae0,*(undefined8 *)(puVar25 + 0x288),
                                 *(undefined8 *)(puVar25 + 0x250),*(undefined8 *)(puVar25 + 200));
            puVar27 = puVar25 + 0x18;
            puVar32[1] = *(undefined8 *)(puVar25 + 0x128);
            if (runtime_writeBarrier._0_4_ == 0) {
              uVar48 = *(undefined8 *)(puVar25 + 0x2c8);
            }
            else {
              auVar55 = runtime_gcWriteBarrier2(puVar32,*puVar32);
              puVar32 = auVar55._0_8_;
              puVar27 = puVar25 + 0x20;
              uVar48 = *(undefined8 *)(puVar25 + 0x2d0);
              *(undefined8 *)*in_x25 = uVar48;
              *(int *)(*in_x25 + 8) = auVar55._8_8_;
            }
            *puVar32 = uVar48;
            puVar53 = &DAT_008a6c40;
            puVar25 = puVar27;
          }
        }
LAB_0053a154:
        runtime_mapIterNext(puVar25 + 0x638,puVar53);
        puVar53 = extraout_x1_06;
      }
    }
    *(undefined8 *)(puVar25 + 0x638) = 0;
    *(undefined8 *)(puVar25 + 0x640) = 0;
    *(undefined8 *)(puVar25 + 0x648) = 0;
    *(undefined8 *)(puVar25 + 0x650) = 0;
    *(undefined8 *)(puVar25 + 0x658) = 0;
    *(undefined8 *)(puVar25 + 0x660) = 0;
    *(undefined8 *)(puVar25 + 0x668) = 0;
    *(undefined8 *)(puVar25 + 0x670) = 0;
    *(undefined8 *)(puVar25 + 0x678) = 0;
    *(undefined8 *)(puVar25 + 0x680) = 0;
    *(undefined8 *)(puVar25 + 0x688) = 0;
    *(undefined8 *)(puVar25 + 0x690) = 0;
    runtime_mapIterStart(&DAT_008ecae0,*(undefined8 *)(puVar25 + 0x278));
    puVar28 = puVar25 + 8;
    while( true ) {
      puVar32 = *(undefined8 **)(puVar28 + 0x638);
      iVar54 = 0;
      puVar25 = puVar28;
      if (puVar32 == (undefined8 *)0x0) break;
      *(undefined8 **)(puVar28 + 0x298) = puVar32;
      uVar48 = *puVar32;
      uVar33 = puVar32[1];
      *(undefined8 *)(puVar28 + 0x70) = *(undefined8 *)(*(int *)(puVar28 + 0x640) + 8);
      auVar55 = strings_ToUpper(uVar48,uVar33);
      iVar54 = auVar55._8_8_;
      piVar44 = auVar55._0_8_;
      puVar25 = puVar28 + 8;
      if ((((iVar54 == 3) &&
           ((((short)*piVar44 == 0x4955 && (*(char *)((int)piVar44 + 2) == 'D')) ||
            (((short)*piVar44 == 0x4943 && (*(char *)((int)piVar44 + 2) == 'D')))))) ||
          (((iVar54 == 4 && ((sdword)*piVar44 == 0x44494553)) ||
           ((iVar54 == 0xb &&
            (((*piVar44 == 0x524553555f353131 && ((short)piVar44[1] == 0x495f)) &&
             (*(char *)((int)piVar44 + 10) == 'D')))))))) && (*(int *)(puVar28 + 0x78) != 0)) {
        iVar54 = *(int *)(puVar28 + 0x2a0);
        break;
      }
      runtime_mapIterNext(puVar28 + 0x640);
      puVar28 = puVar28 + 0x10;
    }
    if (iVar54 == 0) {
      *(undefined8 *)(puVar25 + 0x2d8) = 0;
      *(undefined8 *)(puVar25 + 0x2e0) = 0;
      *(undefined8 *)(puVar25 + 0x2e8) = 0;
      *(undefined8 *)(puVar25 + 0x2f0) = 0;
      *(undefined **)(puVar25 + 0x2d8) = &DAT_008ecae0;
      *(undefined8 *)(puVar25 + 0x2e0) = *(undefined8 *)(puVar25 + 0x278);
      runtime_slicebytetostring(0,*(undefined8 *)(puVar25 + 0x288),*(undefined8 *)(puVar25 + 0xf0));
      uVar48 = runtime_convTstring();
      *(undefined8 **)(puVar25 + 0x2f8) = &DAT_008a6880;
      *(undefined8 *)(puVar25 + 0x300) = uVar48;
      *(code **)(puVar25 + 0x618) = mv_daemon_provider___Cloud115Provider__PollQrLogin_Printf_func3;
      *(undefined **)(puVar25 + 0x620) = &DAT_00a37791;
      *(undefined8 *)(puVar25 + 0x628) = 0x66;
      *(undefined8 *)(puVar25 + 0x640) = 2;
      *(undefined1 **)(puVar25 + 0x630) = puVar25 + 0x2e8;
      *(undefined8 *)(puVar25 + 0x638) = 2;
      log___Logger__output(log_std,0,2,puVar25 + 0x618);
      auVar57 = fmt_errorf(&DAT_00a2efe8,0x4d,0,0,0);
      puVar30 = puVar25 + 0x20;
      if (auVar57._0_8_ == 0) {
        puVar32 = (undefined8 *)runtime_newobject(&DAT_008f85a0);
        puVar30 = puVar25 + 0x28;
        *puVar32 = &DAT_00a2efe8;
        puVar32[1] = 0x4d;
        auVar57._8_8_ = puVar32;
        auVar57._0_8_ = go_itab__errors_errorString_error;
      }
      *(undefined8 *)(puVar30 + 0x1d0) = 0;
      *(undefined1 (*) [16])(puVar30 + 0x1a8) = auVar57;
      runtime_deferreturn();
      auVar43._0_8_ = *(undefined8 *)(puVar30 + 0x1d8);
      auVar43._8_8_ = *(undefined8 *)(puVar30 + 0x1b0);
      auVar43._16_8_ = *(undefined8 *)(puVar30 + 0x1b8);
      return auVar43;
    }
    *(undefined8 *)(puVar25 + 0x638) = 0;
    *(undefined8 *)(puVar25 + 0x640) = 0;
    *(undefined8 *)(puVar25 + 0x648) = 0;
    *(undefined8 *)(puVar25 + 0x650) = 0;
    *(undefined8 *)(puVar25 + 0x658) = 0;
    *(undefined8 *)(puVar25 + 0x660) = 0;
    *(undefined8 *)(puVar25 + 0x668) = 0;
    *(undefined8 *)(puVar25 + 0x670) = 0;
    *(undefined8 *)(puVar25 + 0x678) = 0;
    *(undefined8 *)(puVar25 + 0x680) = 0;
    *(undefined8 *)(puVar25 + 0x688) = 0;
    *(undefined8 *)(puVar25 + 0x690) = 0;
    runtime_mapIterStart(&DAT_008ecae0,*(undefined8 *)(puVar25 + 0x278));
    uVar31 = 0;
    uVar48 = 0;
    uVar33 = 0;
    uVar49 = 0;
    puVar29 = puVar25 + 8;
    while (puVar32 = *(undefined8 **)(puVar29 + 0x638), puVar32 != (undefined8 *)0x0) {
      *(undefined8 *)(puVar29 + 0xe0) = uVar48;
      *(undefined8 *)(puVar29 + 0xd8) = uVar33;
      *(undefined8 *)(puVar29 + 0x270) = uVar49;
      puVar29[0x5f] = uVar31;
      auVar58 = runtime_concatstring3
                          (0,*puVar32,puVar32[1],&DAT_00c0a5f8,1,**(undefined8 **)(puVar29 + 0x640),
                           (*(undefined8 **)(puVar29 + 0x640))[1]);
      puVar25 = puVar29 + 8;
      uVar51 = *(int *)(puVar29 + 0xe0) + 1;
      uVar47 = *(uint *)(puVar29 + 0xe8);
      if (uVar47 < uVar51) {
        *(int *)(puVar29 + 0x118) = auVar58._8_8_;
        *(int *)(puVar29 + 0x2b8) = auVar58._0_8_;
        if ((((int)uVar51 < 3) && ((puVar29[0x67] & 1) == 0)) && (*(int *)(puVar29 + 0xe0) == 0)) {
          puVar32 = (undefined8 *)(puVar29 + 0x2c0);
          *puVar32 = 0;
          *(undefined8 *)(puVar29 + 0x2c8) = 0;
          *(undefined8 *)(puVar29 + 0x2d0) = 0;
          *(undefined8 *)(puVar29 + 0x2d8) = 0;
          uVar47 = 2;
          uVar31 = 1;
        }
        else {
          runtime_growslice(*(undefined8 *)(puVar29 + 0x278),uVar51,uVar47,1,&DAT_008a6880);
          puVar25 = puVar29 + 0x10;
          uVar31 = puVar29[0x6f];
          auVar58._8_8_ = *(undefined8 *)(puVar29 + 0x120);
          auVar58._0_8_ = *(undefined8 *)(puVar29 + 0x2c0);
          uVar47 = extraout_x2_06;
          puVar32 = extraout_x0_05;
          uVar51 = extraout_x1_07;
        }
      }
      else {
        puVar32 = *(undefined8 **)(puVar29 + 0x278);
        uVar31 = puVar29[0x67];
        puVar25 = puVar29 + 8;
      }
      uVar48 = auVar58._0_8_;
      *(undefined8 **)(puVar25 + 0x270) = puVar32;
      *(uint *)(puVar25 + 0xd8) = uVar51;
      *(uint *)(puVar25 + 0xe0) = uVar47;
      puVar25[0x5f] = uVar31;
      puVar32 = puVar32 + (uVar51 - 1) * 2;
      puVar32[1] = auVar58._8_8_;
      if (runtime_writeBarrier._0_4_ != 0) {
        auVar55 = runtime_gcWriteBarrier2(uVar48,*puVar32);
        uVar48 = auVar55._0_8_;
        puVar25 = puVar25 + 8;
        *in_x25 = auVar55;
        puVar32 = extraout_x5;
      }
      *puVar32 = uVar48;
      runtime_mapIterNext(puVar25 + 0x638);
      uVar31 = puVar25[0x67];
      uVar48 = *(undefined8 *)(puVar25 + 0xe8);
      uVar33 = *(undefined8 *)(puVar25 + 0xe0);
      uVar49 = *(undefined8 *)(puVar25 + 0x278);
      puVar29 = puVar25 + 8;
    }
    auVar55 = strings_Join(uVar49,uVar33,uVar48,&DAT_009d1c5a,2);
    iVar54 = auVar55._0_8_;
    puVar5 = puVar29 + 8;
    piVar50 = *(int **)(puVar29 + 0x228);
    piVar50[3] = auVar55._8_8_;
    if (runtime_writeBarrier._0_4_ != 0) {
      auVar55 = runtime_gcWriteBarrier2(iVar54,piVar50[2]);
      iVar54 = auVar55._0_8_;
      puVar5 = puVar29 + 0x10;
      *in_x25 = auVar55;
      piVar50 = extraout_x5_00;
    }
    piVar50[2] = iVar54;
  }
  *(int **)(puVar5 + 0x1d0) = piVar50;
  *(undefined8 *)(puVar5 + 0x1a8) = 0;
  *(undefined8 *)(puVar5 + 0x1b0) = 0;
  runtime_deferreturn();
  auVar40._0_8_ = *(undefined8 *)(puVar5 + 0x1d8);
  auVar40._8_8_ = *(undefined8 *)(puVar5 + 0x1b0);
  auVar40._16_8_ = *(undefined8 *)(puVar5 + 0x1b8);
  return auVar40;
}

