/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).load */

void mv_daemon_provider___TokenStore__load(sdword *param_1)

{
  sdword sVar1;
  undefined8 extraout_RAX;
  undefined8 extraout_RAX_00;
  undefined8 extraout_RAX_01;
  undefined8 uVar2;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 uVar3;
  undefined8 extraout_RBX;
  undefined8 extraout_RBX_00;
  undefined8 extraout_RBX_01;
  undefined8 uVar4;
  int extraout_RDI;
  int extraout_RDI_00;
  int unaff_R14;
  undefined1 auVar5 [16];
  sdword *psStack0000000000000008;
  undefined1 local_68 [32];
  undefined8 local_48;
  undefined8 local_40;
  int local_38;
  undefined8 local_30;
  int3 *local_28;
  code *local_20;
  sdword *local_18;
  code **local_10;
  
  psStack0000000000000008 = param_1;
  while (&local_18 <= *(sdword ***)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  LOCK();
  sVar1 = *psStack0000000000000008;
  if (sVar1 == 0) {
    *psStack0000000000000008 = 1;
  }
  UNLOCK();
  if (sVar1 != 0) {
    internal_sync___Mutex__lockSlow(psStack0000000000000008);
  }
  local_20 = mv_daemon_provider___TokenStore__load_deferwrap1;
  local_10 = &local_20;
  local_18 = psStack0000000000000008;
  os_ReadFile(*(undefined8 *)(psStack0000000000000008 + 2),
              *(undefined8 *)(psStack0000000000000008 + 4));
  if (extraout_RDI != 0) {
    (**local_10)();
    return;
  }
  local_48 = extraout_RBX;
  local_40 = extraout_RCX;
  local_30 = extraout_RAX;
  runtime_slicebytetostring(local_68,extraout_RAX,extraout_RBX);
  auVar5 = strings_TrimSpace();
  uVar2 = local_30;
  uVar3 = local_40;
  uVar4 = local_48;
  if ((2 < auVar5._8_8_) && (*auVar5._0_8_ == 0x3a3176)) {
    local_38 = auVar5._8_8_;
    local_28 = auVar5._0_8_;
    mv_daemon_pkg_auth_GetEncryptionKey();
    mv_daemon_pkg_auth_DecryptGCM(local_28,local_38,extraout_RAX_00,extraout_RBX_00,extraout_RCX_00)
    ;
    uVar2 = extraout_RAX_01;
    uVar3 = extraout_RCX_01;
    uVar4 = extraout_RBX_01;
    if (extraout_RDI_00 != 0) {
      uVar2 = local_30;
      uVar3 = local_40;
      uVar4 = local_48;
    }
  }
  encoding_json_Unmarshal(uVar2,uVar4,uVar3,&DAT_00dbf360,psStack0000000000000008 + 6);
  (**local_10)();
  return;
}

