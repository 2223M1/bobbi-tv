/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Save */

undefined1  [16]
mv_daemon_provider___TokenStore__Save
          (dword *param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,
          undefined8 param_5)

{
  dword dVar1;
  undefined8 uVar2;
  undefined1 auVar3 [16];
  uint uVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  undefined8 extraout_RAX;
  undefined8 extraout_RAX_00;
  undefined8 extraout_RAX_01;
  undefined8 extraout_RAX_02;
  dword *extraout_RCX;
  dword *pdVar7;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  int extraout_RCX_03;
  undefined8 extraout_RCX_04;
  int extraout_RBX;
  undefined8 extraout_RBX_00;
  undefined8 extraout_RBX_01;
  undefined8 extraout_RBX_02;
  undefined8 extraout_RBX_03;
  undefined8 extraout_RSI;
  int extraout_RDI;
  undefined8 extraout_RDI_00;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  int unaff_R14;
  undefined1 auVar8 [16];
  dword *pdStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 uStack0000000000000018;
  undefined8 uStack0000000000000020;
  undefined8 uStack0000000000000028;
  undefined1 local_68 [32];
  undefined8 local_48;
  undefined8 local_40;
  undefined1 local_38 [16];
  undefined8 local_28;
  code *local_20;
  dword *local_18;
  code **local_10;
  
  pdStack0000000000000008 = param_1;
  uStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  uStack0000000000000028 = param_5;
  uStack0000000000000020 = param_4;
  while (&local_20 <= *(code ***)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar4 = 0;
  LOCK();
  dVar1 = *pdStack0000000000000008;
  if (dVar1 == 0) {
    *pdStack0000000000000008 = 1;
  }
  else {
    uVar4 = (uint)dVar1;
  }
  UNLOCK();
  if (dVar1 != 0) {
    uVar4 = internal_sync___Mutex__lockSlow(pdStack0000000000000008);
  }
  local_20 = mv_daemon_provider___TokenStore__Save_deferwrap1;
  local_10 = &local_20;
  local_18 = pdStack0000000000000008;
  if (*(int *)(pdStack0000000000000008 + 6) == 0) {
    uVar5 = runtime_makemap_small(uVar4,uStack0000000000000010,uStack0000000000000018);
    pdVar7 = pdStack0000000000000008;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar2 = *(undefined8 *)(pdStack0000000000000008 + 6);
      uVar5 = runtime_gcWriteBarrier2();
      *extraout_R11 = uVar5;
      extraout_R11[1] = uVar2;
      pdVar7 = extraout_RCX;
    }
    *(undefined8 *)(pdVar7 + 6) = uVar5;
  }
  strings_TrimSpace(uStack0000000000000020,uStack0000000000000028);
  if (extraout_RBX == 0) {
    runtime_mapdelete_faststr
              (&DAT_00e16200,*(undefined8 *)(pdStack0000000000000008 + 6),uStack0000000000000010,
               uStack0000000000000018);
  }
  else {
    auVar8 = runtime_mapassign_faststr
                       (&DAT_00e16200,*(undefined8 *)(pdStack0000000000000008 + 6),
                        uStack0000000000000010,uStack0000000000000018);
    puVar6 = auVar8._0_8_;
    puVar6[1] = uStack0000000000000028;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar6 = (undefined8 *)runtime_gcWriteBarrier2(puVar6,auVar8._8_8_,*puVar6);
      *extraout_R11_00 = uStack0000000000000020;
      extraout_R11_00[1] = extraout_RCX_00;
    }
    *puVar6 = uStack0000000000000020;
  }
  encoding_json_Marshal(&DAT_00e16200,*(undefined8 *)(pdStack0000000000000008 + 6));
  if (extraout_RDI != 0) {
    local_38._0_8_ = extraout_RDI;
    local_38._8_8_ = extraout_RSI;
    (**local_10)();
    auVar3._8_8_ = local_38._8_8_;
    auVar3._0_8_ = local_38._0_8_;
    return auVar3;
  }
  local_48 = extraout_RBX_00;
  local_40 = extraout_RCX_01;
  local_28 = extraout_RAX;
  mv_daemon_pkg_auth_GetEncryptionKey();
  mv_daemon_pkg_auth_EncryptGCM
            (local_28,local_48,local_40,extraout_RAX_00,extraout_RBX_01,extraout_RCX_02);
  if (extraout_RCX_03 == 0) {
    runtime_stringtoslicebyte(local_68,extraout_RAX_01,extraout_RBX_02);
    local_38 = os_WriteFile(*(undefined8 *)(pdStack0000000000000008 + 2),
                            *(undefined8 *)(pdStack0000000000000008 + 4),extraout_RAX_02,
                            extraout_RBX_03,extraout_RCX_04,0x180);
    (**local_10)();
    return local_38;
  }
  local_38._0_8_ = extraout_RCX_03;
  local_38._8_8_ = extraout_RDI_00;
  (**local_10)();
  auVar8._8_8_ = local_38._8_8_;
  auVar8._0_8_ = local_38._0_8_;
  return auVar8;
}

