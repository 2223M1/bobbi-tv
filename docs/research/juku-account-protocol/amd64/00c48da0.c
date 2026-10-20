/* Reconstructed pseudocode, not original Go source: main.handleQrCode */

void main_handleQrCode(int param_1,undefined8 param_2,int param_3)

{
  undefined1 *puVar1;
  undefined1 auVar2 [16];
  char cVar3;
  undefined8 uVar4;
  undefined8 *puVar5;
  int *piVar6;
  int *piVar7;
  int extraout_RAX;
  int extraout_RAX_00;
  int extraout_RAX_01;
  int iVar8;
  undefined8 extraout_RAX_02;
  undefined8 uVar9;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  uint uVar10;
  int iVar11;
  char extraout_BL;
  int extraout_RBX;
  int extraout_RBX_00;
  int extraout_RBX_01;
  int iVar12;
  undefined8 extraout_RBX_02;
  int iVar13;
  int extraout_RDI;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar14 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_d0;
  undefined8 local_c8;
  undefined8 uStack_c0;
  undefined1 local_a8;
  undefined7 uStack_a7;
  undefined *local_68;
  undefined8 uStack_60;
  undefined *local_58;
  undefined8 uStack_50;
  code *local_48;
  undefined *local_40;
  undefined8 local_38;
  undefined **local_30;
  undefined8 local_28;
  undefined8 local_20;
  undefined8 *local_18;
  undefined8 local_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_d0 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar4 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar14 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_10 = auVar14._0_8_;
  local_18 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_18[1] = 0x10;
  *local_18 = &DAT_00f195fc;
  auVar14 = runtime_mapassign_faststr(&DAT_00e91b20,uVar4,local_10,auVar14._8_8_);
  puVar5 = auVar14._0_8_;
  puVar5[1] = 1;
  puVar5[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar14._8_8_,*puVar5);
    *extraout_R11 = local_18;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar5 = local_18;
  uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar6 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00f02a51,8);
  if (piVar6[1] == 0) {
    uVar4 = 0;
    uVar9 = 0;
  }
  else {
    uVar4 = ((undefined8 *)*piVar6)[1];
    uVar9 = *(undefined8 *)*piVar6;
  }
  auVar14 = main_getRealProvider(uVar9,uVar4);
  iVar11 = auVar14._8_8_;
  piVar6 = auVar14._0_8_;
  piVar7 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,piVar6,iVar11);
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1962c,0x10,400);
    return;
  }
  puVar1 = (undefined1 *)*piVar7;
  iVar8 = piVar7[1];
  if ((iVar11 == 8) && (*piVar6 == 0x35313144554f4c43)) {
    uVar4 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
    piVar7 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar4,&DAT_00f0cd84,0xb);
    if (piVar7[1] == 0) {
      iVar12 = 0;
      uVar4 = 0;
    }
    else {
      iVar12 = ((undefined8 *)*piVar7)[1];
      uVar4 = *(undefined8 *)*piVar7;
    }
    auVar2._8_8_ = iVar12;
    auVar2._0_8_ = uVar4;
    auVar14._8_8_ = iVar12;
    auVar14._0_8_ = uVar4;
    if ((iVar12 == 0) &&
       (auVar14 = auVar2, main_global115ClientTypeStore != (main_Pan115ClientTypeStore *)0x0)) {
      auVar14 = main___Pan115ClientTypeStore__Get();
    }
    iVar13 = auVar14._8_8_;
    if (puVar1 == go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
      local_d0 = auVar14._0_8_;
      mv_daemon_provider___Cloud115Provider__StartQrLoginWithType(iVar8,auVar14._0_8_,iVar13);
      iVar8 = extraout_RAX;
      uVar4 = extraout_RCX_00;
      iVar12 = extraout_RBX;
      if (((extraout_RBX == 0) && (iVar13 != 0)) &&
         (main_global115ClientTypeStore != (main_Pan115ClientTypeStore *)0x0)) {
        main___Pan115ClientTypeStore__Save(main_global115ClientTypeStore,local_d0,iVar13);
      }
    }
    else {
      (**(code **)(puVar1 + 0x48))(iVar8);
      iVar8 = extraout_RAX_00;
      uVar4 = extraout_RCX_01;
      iVar12 = extraout_RBX_00;
    }
  }
  else {
    (**(code **)(puVar1 + 0x48))();
    iVar8 = extraout_RAX_01;
    uVar4 = extraout_RCX_02;
    iVar12 = extraout_RBX_01;
  }
  if (iVar12 != 0) {
    auVar14 = (**(code **)(iVar12 + 0x18))(uVar4);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar14._0_8_,auVar14._8_8_,
                        500);
    return;
  }
  if (*(int *)(iVar8 + 0x18) != 0) {
    if (*(int *)(iVar8 + 0x18) < 10) {
      cVar3 = '\0';
    }
    else {
      cVar3 = runtime_memequal(*(undefined8 *)(iVar8 + 0x10),&DAT_00f0a1b7,10);
    }
    if (cVar3 == '\0') {
      uVar4 = *(undefined8 *)(iVar8 + 0x18);
      mv_daemon_provider_EncodeQRCodeRGBA(*(undefined8 *)(iVar8 + 0x10),uVar4,1,300);
      if (extraout_RDI == 0) {
        auVar14 = encoding_base64___Encoding__EncodeToString
                            (encoding_base64_StdEncoding,extraout_RAX_02,extraout_RBX_02,
                             extraout_RCX_03);
        auVar14 = runtime_concatstring2(0,&DAT_00f23a5a,0x16,auVar14._0_8_,auVar14._8_8_);
        uVar9 = auVar14._0_8_;
        *(int *)(iVar8 + 0x18) = auVar14._8_8_;
        if (runtime_writeBarrier._0_4_ != 0) {
          uVar9 = runtime_gcWriteBarrier2(uVar9,auVar14._8_8_,*(undefined8 *)(iVar8 + 0x10));
          *extraout_R11_00 = uVar9;
          extraout_R11_00[1] = extraout_RCX_04;
        }
        *(undefined8 *)(iVar8 + 0x10) = uVar9;
      }
      uStack_60 = runtime_convTstring(piVar6,iVar11);
      local_68 = &DAT_00dd29c0;
      uStack_50 = runtime_convT64(uVar4);
      local_58 = &DAT_00dd2c00;
      local_48 = main_handleQrCode_Printf_func1;
      local_38 = 0x36;
      local_40 = &DAT_00f497fe;
      local_28 = 2;
      local_20 = 2;
      local_30 = &local_68;
      log___Logger__output(log_std,0,2,&local_48);
    }
  }
  local_c8 = 0;
  if (iStack0000000000000008 != 0) {
    uVar10 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar11 = (uVar10 & *(uint *)main__typeAssert_31) * 0x10;
      if (*(int *)(main__typeAssert_31 + iVar11 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_c8 = *(undefined8 *)(main__typeAssert_31 + iVar11 + 0x10);
        goto LAB_00c4925e;
      }
      uVar10 = uVar10 + 1;
    } while (*(int *)(main__typeAssert_31 + iVar11 + 8) != 0);
    local_c8 = runtime_typeAssert(&main__typeAssert_31);
  }
LAB_00c4925e:
  uStack_c0 = uStack0000000000000010;
  _local_a8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_c8,&DAT_00db1ae0,iVar8);
  return;
}

