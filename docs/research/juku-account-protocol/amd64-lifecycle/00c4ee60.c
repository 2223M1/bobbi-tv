/* Reconstructed pseudocode, not original Go source: main.handleUserFiles */

void main_handleUserFiles(int param_1,undefined8 param_2,int param_3)

{
  int iVar1;
  undefined1 auVar2 [16];
  undefined8 uVar3;
  undefined8 *puVar4;
  int *piVar5;
  undefined8 uVar6;
  undefined8 extraout_RAX;
  undefined8 extraout_RCX;
  undefined8 uVar7;
  undefined8 extraout_RCX_00;
  uint uVar8;
  int iVar9;
  char extraout_BL;
  int extraout_RBX;
  int iVar10;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar11 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_c8;
  undefined8 uStack_c0;
  undefined1 local_a8;
  undefined7 uStack_a7;
  undefined *local_68;
  undefined8 uStack_60;
  undefined8 local_58;
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
  while (&local_c8 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar3 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar11 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_10 = auVar11._0_8_;
  local_18 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_18[1] = 0x10;
  *local_18 = &DAT_00f195fc;
  auVar11 = runtime_mapassign_faststr(&DAT_00e91b20,uVar3,local_10,auVar11._8_8_);
  puVar4 = auVar11._0_8_;
  puVar4[1] = 1;
  puVar4[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar11._8_8_,*puVar4);
    *extraout_R11 = local_18;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar4 = local_18;
  uVar3 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar5 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar3,&DAT_00f02a51,8);
  if (piVar5[1] == 0) {
    uVar3 = 0;
    uVar7 = 0;
  }
  else {
    uVar3 = ((undefined8 *)*piVar5)[1];
    uVar7 = *(undefined8 *)*piVar5;
  }
  auVar11 = main_getRealProvider(uVar7,uVar3);
  piVar5 = (int *)runtime_mapaccess2_faststr
                            (&DAT_00e17280,main_providers,auVar11._0_8_,auVar11._8_8_);
  iVar9 = *piVar5;
  iVar1 = piVar5[1];
  if (extraout_BL == '\0') {
    auVar11 = runtime_concatstring2(0,&DAT_00f1d559,0x12,auVar11._0_8_,auVar11._8_8_);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar11._0_8_,auVar11._8_8_,
                        400);
    return;
  }
  uVar3 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar5 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar3,&DAT_00f1546b,0xe);
  if (piVar5[1] == 0) {
    uVar3 = 0;
    uVar7 = 0;
  }
  else {
    uVar3 = ((undefined8 *)*piVar5)[1];
    uVar7 = *(undefined8 *)*piVar5;
  }
  uVar6 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar5 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar6,&DAT_00efc947,5);
  if (piVar5[1] == 0) {
    iVar10 = 0;
    uVar6 = 0;
  }
  else {
    iVar10 = ((undefined8 *)*piVar5)[1];
    uVar6 = *(undefined8 *)*piVar5;
  }
  auVar2._8_8_ = iVar10;
  auVar2._0_8_ = uVar6;
  auVar11._8_8_ = iVar10;
  auVar11._0_8_ = uVar6;
  if ((iVar10 == 0) && (auVar11 = auVar2, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar11 = (**(code **)(iVar9 + 0x28))(iVar1);
    auVar11 = mv_daemon_provider___TokenStore__Get(main_tokenStore,auVar11._0_8_,auVar11._8_8_);
  }
  (**(code **)(iVar9 + 0x20))(iVar1,uVar7,uVar3,auVar11._0_8_,auVar11._8_8_);
  if (extraout_RBX != 0) {
    (**(code **)(iVar9 + 0x28))(iVar1);
    uStack_60 = runtime_convTstring();
    local_68 = &DAT_00dd29c0;
    if (extraout_RBX == 0) {
      local_58 = 0;
    }
    else {
      local_58 = *(undefined8 *)(extraout_RBX + 8);
    }
    local_48 = main_handleUserFiles_Printf_func1;
    local_38 = 0x30;
    local_40 = &DAT_00f44120;
    local_28 = 2;
    local_20 = 2;
    local_30 = &local_68;
    uStack_50 = extraout_RCX_00;
    log___Logger__output(log_std,0,2,&local_48);
    auVar11 = (**(code **)(extraout_RBX + 0x18))(extraout_RCX_00);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar11._0_8_,auVar11._8_8_,
                        500);
    return;
  }
  local_c8 = 0;
  if (iStack0000000000000008 != 0) {
    uVar8 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar9 = (uVar8 & *(uint *)main__typeAssert_44) * 0x10;
      if (*(int *)(main__typeAssert_44 + iVar9 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_c8 = *(undefined8 *)(main__typeAssert_44 + iVar9 + 0x10);
        goto LAB_00c4f25a;
      }
      uVar8 = uVar8 + 1;
    } while (*(int *)(main__typeAssert_44 + iVar9 + 8) != 0);
    local_c8 = runtime_typeAssert(&main__typeAssert_44);
  }
LAB_00c4f25a:
  uStack_c0 = uStack0000000000000010;
  _local_a8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_c8,&DAT_00db19e0,extraout_RAX);
  return;
}

