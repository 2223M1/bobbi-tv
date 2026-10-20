/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*OfflineCacheStore).Delete */

undefined1  [16]
mv_daemon_provider___OfflineCacheStore__Delete
          (sdword *param_1,undefined8 param_2,undefined8 param_3)

{
  sdword sVar1;
  int iVar2;
  undefined8 uVar3;
  undefined8 *puVar4;
  undefined8 extraout_RCX;
  undefined8 extraout_RDI;
  int unaff_R14;
  undefined1 auVar6 [16];
  undefined1 auVar7 [16];
  sdword *psStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined *local_38;
  undefined8 uStack_30;
  undefined *local_28;
  undefined8 uStack_20;
  undefined *local_18;
  undefined8 uStack_10;
  int iVar5;
  
  psStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&uStack_10 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  strings_TrimSpace(uStack0000000000000010,param_3);
  auVar6 = strings_ToLower();
  iVar5 = auVar6._8_8_;
  uVar3 = auVar6._0_8_;
  if (iVar5 == 0) {
    return ZEXT816(0);
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
    puVar4 = (undefined8 *)runtime_newobject(&DAT_00e21740,iVar5);
    puVar4[1] = 0x22;
    *puVar4 = &DAT_00f33ff4;
    auVar7._8_8_ = puVar4;
    auVar7._0_8_ = go_itab__errors_errorString_error;
    return auVar7;
  }
  uStack_30 = runtime_convTstring(uVar3);
  local_38 = &DAT_00dd29c0;
  uStack_20 = runtime_convTstring(uVar3,iVar5);
  local_28 = &DAT_00dd29c0;
  uStack_10 = runtime_convTstring(uVar3,iVar5);
  local_18 = &DAT_00dd29c0;
  database_sql___DB__ExecContext
            (iVar2,go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_00f54f1f,
             0x47,&local_38,3,3);
  auVar6._8_8_ = extraout_RDI;
  auVar6._0_8_ = extraout_RCX;
  return auVar6;
}

