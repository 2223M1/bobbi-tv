/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*OfflineCacheStore).Get */

int mv_daemon_provider___OfflineCacheStore__Get
              (sdword *param_1,undefined8 param_2,undefined8 param_3)

{
  sdword sVar1;
  int iVar2;
  undefined8 uVar3;
  int iVar4;
  undefined8 extraout_RCX;
  undefined8 extraout_RCX_00;
  int extraout_RBX;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  int unaff_R14;
  undefined1 auVar5 [16];
  sdword *psStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined *local_140;
  int local_138;
  undefined *local_130;
  int local_128;
  undefined *local_120;
  int local_118;
  undefined *local_110;
  int local_108;
  undefined *local_100;
  undefined8 *local_f8;
  undefined *local_f0;
  undefined8 *local_e8;
  undefined *local_e0;
  int local_d8;
  undefined *local_d0;
  int local_c8;
  undefined *local_c0;
  int local_b8;
  undefined *local_b0;
  int local_a8;
  undefined *local_a0;
  int *local_98;
  undefined *local_90;
  undefined8 *local_88;
  undefined *local_80;
  int local_78;
  undefined *local_70;
  int local_68;
  undefined *local_60;
  undefined8 uStack_58;
  undefined *local_50;
  undefined8 uStack_48;
  undefined *local_40;
  undefined8 uStack_38;
  undefined8 *local_30;
  undefined8 *local_28;
  undefined8 *local_20;
  int local_18;
  int *local_10;
  
  psStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&local_110 <= *(undefined ***)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  strings_TrimSpace(uStack0000000000000010,param_3);
  auVar5 = strings_ToLower();
  iVar4 = auVar5._8_8_;
  uVar3 = auVar5._0_8_;
  if (iVar4 == 0) {
    return 0;
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
  iVar2 = *(int *)(psStack0000000000000008 + 2);
  LOCK();
  sVar1 = *psStack0000000000000008;
  *psStack0000000000000008 = *psStack0000000000000008 + -1;
  UNLOCK();
  if ((sdword)(sVar1 + -1) != 0) {
    internal_sync___Mutex__unlockSlow(psStack0000000000000008,sVar1 + -1);
  }
  if (iVar2 == 0) {
    return 0;
  }
  uStack_58 = runtime_convTstring(uVar3,iVar4);
  local_60 = &DAT_00dd29c0;
  uStack_48 = runtime_convTstring(uVar3,iVar4);
  local_50 = &DAT_00dd29c0;
  uStack_38 = runtime_convTstring(uVar3,iVar4);
  local_40 = &DAT_00dd29c0;
  uVar3 = database_sql___DB__QueryRow(iVar2,&DAT_00f67ee5,0xe7,&local_60,3,3);
  local_18 = runtime_newobject(&DAT_00ed1800);
  local_10 = (int *)runtime_newobject(&DAT_00dd2c00);
  local_20 = (undefined8 *)runtime_newobject(&DAT_00e66440);
  local_30 = (undefined8 *)runtime_newobject(&DAT_00e66440);
  local_e8 = (undefined8 *)runtime_newobject(&DAT_00e66440);
  local_140 = &DAT_00db4260;
  local_138 = local_18 + 0x20;
  local_130 = &DAT_00db4260;
  local_128 = local_18;
  local_120 = &DAT_00db4260;
  local_118 = local_18 + 0x10;
  local_110 = &DAT_00db4260;
  local_108 = local_18 + 0x30;
  local_100 = &DAT_00e068c0;
  local_f8 = local_30;
  local_f0 = &DAT_00e068c0;
  local_e0 = &DAT_00db4260;
  local_d8 = local_18 + 0x60;
  local_d0 = &DAT_00db4260;
  local_c8 = local_18 + 0x70;
  local_c0 = &DAT_00db4260;
  local_b8 = local_18 + 0x80;
  local_b0 = &DAT_00db4420;
  local_a8 = local_18 + 0x90;
  local_a0 = &DAT_00db44a0;
  local_98 = local_10;
  local_90 = &DAT_00e068c0;
  local_88 = local_20;
  local_80 = &DAT_00db44a0;
  local_78 = local_18 + 0xb8;
  local_70 = &DAT_00db4420;
  local_68 = local_18 + 0xc0;
  local_28 = local_e8;
  iVar4 = database_sql___Row__Scan(uVar3,&local_140,0xe,0xe);
  if (iVar4 != 0) {
    return 0;
  }
  *(bool *)(local_18 + 0x98) = *local_10 == 1;
  iVar4 = local_18;
  if (*(char *)(local_30 + 2) != '\0') {
    uVar3 = *local_30;
    *(undefined8 *)(local_18 + 0x48) = local_30[1];
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar3 = *(undefined8 *)(local_18 + 0x40);
      iVar4 = runtime_gcWriteBarrier2();
      *extraout_R11 = extraout_RCX;
      extraout_R11[1] = uVar3;
      uVar3 = extraout_RCX;
    }
    *(undefined8 *)(iVar4 + 0x40) = uVar3;
  }
  if (*(char *)(local_28 + 2) != '\0') {
    uVar3 = *local_28;
    *(undefined8 *)(iVar4 + 0x58) = local_28[1];
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar3 = *(undefined8 *)(iVar4 + 0x50);
      iVar4 = runtime_gcWriteBarrier2();
      *extraout_R11_00 = extraout_RCX_00;
      extraout_R11_00[1] = uVar3;
      uVar3 = extraout_RCX_00;
    }
    *(undefined8 *)(iVar4 + 0x50) = uVar3;
  }
  if ((*(char *)(local_20 + 2) != '\0') &&
     (strings_TrimSpace(*local_20,local_20[1]), iVar4 = local_18, extraout_RBX != 0)) {
    runtime_stringtoslicebyte(0,*local_20,local_20[1]);
    encoding_json_Unmarshal();
    iVar4 = local_18;
  }
  return iVar4;
}

