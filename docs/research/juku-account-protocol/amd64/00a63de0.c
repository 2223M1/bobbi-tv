/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Get */

/* WARNING: Restarted to delay deadcode elimination for space: stack */

undefined1  [16]
mv_daemon_provider___TokenStore__Get(sdword *param_1,undefined8 param_2,undefined8 param_3)

{
  sdword sVar1;
  undefined1 auVar2 [16];
  undefined1 (*pauVar3) [16];
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  code *local_28;
  sdword *local_20;
  sdword *local_18;
  code **local_10;
  
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  LOCK();
  sVar1 = *param_1;
  if (sVar1 == 0) {
    *param_1 = 1;
  }
  UNLOCK();
  if (sVar1 != 0) {
    local_18 = param_1;
    internal_sync___Mutex__lockSlow(param_1);
    param_1 = local_18;
  }
  local_28 = mv_daemon_provider___TokenStore__Get_deferwrap1;
  local_10 = &local_28;
  local_20 = param_1;
  if (*(int *)(param_1 + 6) == 0) {
    mv_daemon_provider___TokenStore__Get_deferwrap1(mv_daemon_provider___TokenStore__Get_deferwrap1)
    ;
    auVar2._8_8_ = in_XMM15_Qb;
    auVar2._0_8_ = in_XMM15_Qa;
    return auVar2;
  }
  pauVar3 = (undefined1 (*) [16])
            runtime_mapaccess1_faststr(&DAT_00e16200,*(int *)(param_1 + 6),param_2,param_3);
  auVar2 = *pauVar3;
  (**local_10)();
  return auVar2;
}

