/* Reconstructed pseudocode, not original Go source: main.handleManualInputUrl */

void main_handleManualInputUrl(int param_1,undefined8 param_2,int param_3)

{
  undefined8 uVar1;
  undefined8 uVar2;
  int *piVar3;
  undefined8 extraout_RAX;
  undefined8 uVar4;
  undefined8 *puVar5;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  uint uVar6;
  int iVar7;
  char extraout_BL;
  undefined8 extraout_RBX;
  undefined8 extraout_RSI;
  int extraout_RDI;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar8 [16];
  undefined1 auVar9 [16];
  undefined1 auVar10 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_a8;
  undefined8 local_a0;
  undefined8 *local_98;
  undefined8 local_90;
  undefined8 local_88;
  undefined8 uStack_80;
  undefined1 local_68;
  undefined7 uStack_67;
  undefined *local_28;
  undefined8 uStack_20;
  undefined *local_18;
  undefined8 uStack_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_a8 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar2 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar8 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_90 = auVar8._0_8_;
  local_98 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_98[1] = 0x10;
  *local_98 = &DAT_00f195fc;
  auVar8 = runtime_mapassign_faststr(&DAT_00e91b20,uVar2,local_90,auVar8._8_8_);
  puVar5 = auVar8._0_8_;
  puVar5[1] = 1;
  puVar5[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2(puVar5,auVar8._8_8_,*puVar5);
    *extraout_R11 = local_98;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar5 = local_98;
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f02a51,8);
  if (piVar3[1] == 0) {
    uVar2 = 0;
    uVar4 = 0;
  }
  else {
    uVar2 = ((undefined8 *)*piVar3)[1];
    uVar4 = *(undefined8 *)*piVar3;
  }
  auVar8 = main_getRealProvider(uVar4,uVar2);
  runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,auVar8._0_8_,auVar8._8_8_);
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1962c,0x10,400);
    return;
  }
  auVar9 = main_getLocalIP();
  uVar2 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar3 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar2,&DAT_00f02a51,8);
  if (piVar3[1] == 0) {
    uVar2 = 0;
    uVar4 = 0;
  }
  else {
    uVar2 = ((undefined8 *)*piVar3)[1];
    uVar4 = *(undefined8 *)*piVar3;
  }
  auVar10 = strings_TrimSpace(uVar4,uVar2);
  local_a0 = auVar10._0_8_;
  uStack_20 = runtime_convTstring(auVar9._0_8_,auVar9._8_8_);
  auVar9._8_8_ = auVar10._8_8_;
  auVar9._0_8_ = local_a0;
  local_28 = &DAT_00dd29c0;
  if (auVar10._8_8_ == 0) {
    auVar9 = auVar8;
  }
  uStack_10 = runtime_convTstring(auVar9._0_8_,auVar9._8_8_);
  local_18 = &DAT_00dd29c0;
  auVar8 = fmt_Sprintf(&DAT_00f23a70,0x16,&local_28,2,2);
  uVar2 = auVar8._0_8_;
  mv_daemon_provider_EncodeQRCodeRGBA(uVar2,auVar8._8_8_,1,300);
  if (extraout_RDI != 0) {
    auVar8 = (**(code **)(extraout_RDI + 0x18))(extraout_RSI);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar8._0_8_,auVar8._8_8_,500)
    ;
    return;
  }
  auVar9 = encoding_base64___Encoding__EncodeToString
                     (encoding_base64_StdEncoding,extraout_RAX,extraout_RBX,extraout_RCX_00);
  auVar9 = runtime_concatstring2(0,&DAT_00f23a5a,0x16,auVar9._0_8_,auVar9._8_8_);
  local_a8 = auVar9._0_8_;
  uVar4 = runtime_makemap_small();
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,uVar4,&DAT_00efabaf,3);
  puVar5[1] = 6;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar1 = *puVar5;
    puVar5 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar1;
  }
  *puVar5 = &DAT_00efe2a5;
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,uVar4,&DAT_00efaba6,3);
  puVar5[1] = auVar8._8_8_;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar1 = *puVar5;
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_01 = uVar2;
    extraout_R11_01[1] = uVar1;
  }
  *puVar5 = uVar2;
  puVar5 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16200,uVar4,&DAT_00efe2ab,6);
  puVar5[1] = auVar9._8_8_;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = *puVar5;
    puVar5 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_02 = local_a8;
    extraout_R11_02[1] = uVar2;
  }
  *puVar5 = local_a8;
  local_88 = 0;
  if (iStack0000000000000008 != 0) {
    uVar6 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar7 = (uVar6 & *(uint *)main__typeAssert_34) * 0x10;
      if (*(int *)(main__typeAssert_34 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_88 = *(undefined8 *)(main__typeAssert_34 + iVar7 + 0x10);
        goto LAB_00c4a8a1;
      }
      uVar6 = uVar6 + 1;
    } while (*(int *)(main__typeAssert_34 + iVar7 + 8) != 0);
    local_88 = runtime_typeAssert(&main__typeAssert_34);
  }
LAB_00c4a8a1:
  uStack_80 = uStack0000000000000010;
  _local_68 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_88,&DAT_00e16200,uVar4);
  return;
}

