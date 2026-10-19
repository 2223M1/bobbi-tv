/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.NewOfflineCacheStore */

int mv_daemon_provider_NewOfflineCacheStore(undefined8 param_1,undefined8 param_2)

{
  int iVar1;
  int iVar2;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined1 auVar3 [16];
  undefined8 uStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined *local_58;
  undefined8 uStack_50;
  undefined8 local_48;
  undefined8 uStack_40;
  code *local_38;
  undefined *local_30;
  undefined8 local_28;
  undefined **local_20;
  undefined8 local_18;
  undefined8 local_10;
  
  uStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&local_10 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  iVar1 = runtime_newobject(&DAT_00e6a560);
  *(undefined8 *)(iVar1 + 0x18) = uStack0000000000000010;
  if (runtime_writeBarrier._0_4_ != 0) {
    iVar1 = runtime_gcWriteBarrier1();
    *extraout_R11 = uStack0000000000000008;
  }
  *(undefined8 *)(iVar1 + 0x10) = uStack0000000000000008;
  auVar3 = mv_daemon_provider___OfflineCacheStore__init();
  uStack_40 = auVar3._8_8_;
  iVar2 = auVar3._0_8_;
  if (iVar2 != 0) {
    uStack_50 = runtime_convTstring(uStack0000000000000008,uStack0000000000000010);
    local_58 = &DAT_00dd29c0;
    if (iVar2 == 0) {
      local_48 = 0;
    }
    else {
      local_48 = *(undefined8 *)(iVar2 + 8);
    }
    local_38 = mv_daemon_provider_NewOfflineCacheStore_Printf_func1;
    local_28 = 0x3c;
    local_30 = &DAT_00f4e7dc;
    local_18 = 2;
    local_10 = 2;
    local_20 = &local_58;
    log___Logger__output(log_std,0,2,&local_38);
  }
  return iVar1;
}

