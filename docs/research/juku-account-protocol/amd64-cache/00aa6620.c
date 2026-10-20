/* Reconstructed pseudocode, not original Go source: mv-daemon/pkg/proxy.(*ProxyManager).CloseAll */

void mv_daemon_pkg_proxy___ProxyManager__CloseAll(sdword *param_1)

{
  sdword sVar1;
  undefined8 uVar2;
  undefined8 uVar3;
  int unaff_R14;
  undefined8 *in_XMM15_Qa;
  undefined8 *in_XMM15_Qb;
  sdword *psStack0000000000000008;
  undefined8 *local_80;
  undefined8 *puStack_78;
  undefined1 auStack_38 [24];
  code *local_20;
  sdword *local_18;
  code **local_10;
  
  psStack0000000000000008 = param_1;
  while (auStack_38 <= *(undefined1 **)(unaff_R14 + 0x10)) {
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
  local_20 = mv_daemon_pkg_proxy___ProxyManager__CloseAll_deferwrap1;
  local_10 = &local_20;
  local_80 = in_XMM15_Qa;
  puStack_78 = in_XMM15_Qb;
  local_18 = psStack0000000000000008;
  runtime_mapIterStart(&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2));
  while (local_80 != (undefined8 *)0x0) {
    uVar2 = *local_80;
    uVar3 = local_80[1];
    mv_daemon_pkg_proxy___Downloader__Close(*puStack_78);
    runtime_mapdelete_faststr
              (&DAT_00e18f00,*(undefined8 *)(psStack0000000000000008 + 2),uVar2,uVar3);
    runtime_mapIterNext(&local_80);
  }
  psStack0000000000000008[6] = 0;
  psStack0000000000000008[7] = 0;
  (**local_10)();
  return;
}

