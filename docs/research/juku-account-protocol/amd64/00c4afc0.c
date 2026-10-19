/* Reconstructed pseudocode, not original Go source: main.handleQrCodeStatus */

void main_handleQrCodeStatus(int param_1,undefined8 param_2,int param_3)

{
  undefined8 uVar1;
  undefined8 *puVar2;
  undefined8 *puVar3;
  int *piVar4;
  undefined8 uVar5;
  int *extraout_RAX;
  undefined8 extraout_RCX;
  uint uVar6;
  undefined8 extraout_RCX_00;
  int iVar7;
  sdword *psVar8;
  char extraout_BL;
  undefined8 uVar9;
  int extraout_RBX;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined1 auVar10 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_168;
  undefined8 uStack_160;
  undefined1 local_148;
  undefined7 uStack_147;
  undefined8 local_108;
  undefined8 uStack_100;
  undefined1 local_e8;
  undefined7 uStack_e7;
  undefined8 local_a8;
  undefined8 uStack_a0;
  undefined1 local_88;
  undefined7 uStack_87;
  undefined8 *local_48;
  undefined8 uStack_40;
  undefined1 local_38 [16];
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (&local_168 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar1 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar10 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  puVar2 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  puVar2[1] = 0x10;
  *puVar2 = &DAT_00f195fc;
  auVar10 = runtime_mapassign_faststr(&DAT_00e91b20,uVar1,auVar10._0_8_,auVar10._8_8_);
  puVar3 = auVar10._0_8_;
  puVar3[1] = 1;
  puVar3[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar3 = (undefined8 *)runtime_gcWriteBarrier2(puVar3,auVar10._8_8_,*puVar3);
    *extraout_R11 = puVar2;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar3 = puVar2;
  uVar1 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar4 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar1,&DAT_00f02a51,8);
  if (piVar4[1] == 0) {
    uVar1 = 0;
    uVar5 = 0;
  }
  else {
    uVar1 = ((undefined8 *)*piVar4)[1];
    uVar5 = *(undefined8 *)*piVar4;
  }
  auVar10 = main_getRealProvider(uVar5,uVar1);
  uVar9 = auVar10._8_8_;
  uVar1 = auVar10._0_8_;
  uVar5 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  puVar2 = (undefined8 *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar5,&DAT_00efabaf,3);
  if (puVar2[1] == 0) {
    psVar8 = (sdword *)0x0;
    iVar7 = 0;
  }
  else {
    iVar7 = ((undefined8 *)*puVar2)[1];
    psVar8 = *(sdword **)*puVar2;
  }
  piVar4 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,uVar1,uVar9);
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f1962c,0x10,400);
    return;
  }
  if (((iVar7 == 6) && (*psVar8 == 0x756e616d)) && ((short)psVar8[1] == 0x6c61)) {
    if (main_tokenStore == (mv_daemon_provider_TokenStore *)0x0) {
      auVar10 = ZEXT816(0);
    }
    else {
      auVar10 = mv_daemon_provider___TokenStore__Get(main_tokenStore,uVar1,uVar9);
    }
    if (auVar10._8_8_ == 0) {
      local_108 = 0;
      if (iStack0000000000000008 != 0) {
        uVar6 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
        do {
          iVar7 = (uVar6 & *(uint *)main__typeAssert_38) * 0x10;
          if (*(int *)(main__typeAssert_38 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
            local_108 = *(undefined8 *)(main__typeAssert_38 + iVar7 + 0x10);
            goto LAB_00c4b39d;
          }
          uVar6 = uVar6 + 1;
        } while (*(int *)(main__typeAssert_38 + iVar7 + 8) != 0);
        local_108 = runtime_typeAssert(&main__typeAssert_38);
      }
LAB_00c4b39d:
      uStack_100 = uStack0000000000000010;
      _local_e8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
      encoding_json___Encoder__Encode(&local_108,&DAT_00e836e0,&PTR_DAT_01143ac0);
      return;
    }
    local_a8 = 0;
    if (iStack0000000000000008 != 0) {
      uVar6 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
      do {
        iVar7 = (uVar6 & *(uint *)main__typeAssert_37) * 0x10;
        if (*(int *)(main__typeAssert_37 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
          local_a8 = *(undefined8 *)(main__typeAssert_37 + iVar7 + 0x10);
          goto LAB_00c4b439;
        }
        uVar6 = uVar6 + 1;
      } while (*(int *)(main__typeAssert_37 + iVar7 + 8) != 0);
      local_a8 = runtime_typeAssert(&main__typeAssert_37,*(int *)(iStack0000000000000008 + 8));
    }
LAB_00c4b439:
    uStack_a0 = uStack0000000000000010;
    _local_88 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
    local_48 = &DAT_00f059ff;
    uStack_40 = 9;
    local_38 = auVar10;
    uVar1 = runtime_convT(&DAT_00e836e0,&local_48);
    encoding_json___Encoder__Encode(&local_a8,&DAT_00e836e0,uVar1);
    return;
  }
  (**(code **)(*piVar4 + 0x30))(piVar4[1],psVar8);
  if (extraout_RBX != 0) {
    auVar10 = (**(code **)(extraout_RBX + 0x18))(extraout_RCX_00);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar10._0_8_,auVar10._8_8_,
                        500);
    return;
  }
  if (((extraout_RAX[1] == 9) && (*(int *)*extraout_RAX == 0x656d7269666e6f63)) &&
     (((char)((int *)*extraout_RAX)[1] == 'd' && (extraout_RAX[3] != 0)))) {
    mv_daemon_provider___TokenStore__Save(main_tokenStore,uVar1,uVar9,extraout_RAX[2]);
  }
  local_168 = 0;
  if (iStack0000000000000008 != 0) {
    uVar6 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar7 = (uVar6 & *(uint *)main__typeAssert_39) * 0x10;
      if (*(int *)(main__typeAssert_39 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_168 = *(undefined8 *)(main__typeAssert_39 + iVar7 + 0x10);
        goto LAB_00c4b2fd;
      }
      uVar6 = uVar6 + 1;
    } while (*(int *)(main__typeAssert_39 + iVar7 + 8) != 0);
    local_168 = runtime_typeAssert(&main__typeAssert_39);
  }
LAB_00c4b2fd:
  uStack_160 = uStack0000000000000010;
  _local_148 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_168,&DAT_00db1a20,extraout_RAX);
  return;
}

