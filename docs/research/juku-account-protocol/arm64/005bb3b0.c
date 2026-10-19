/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Get.deferwrap1 */

void mv_daemon_provider___TokenStore__Get_deferwrap1(void)

{
  char cVar1;
  bool bVar2;
  dword dVar3;
  dword *pdVar4;
  undefined8 in_x3;
  int iVar5;
  undefined8 extraout_x3;
  int in_x26;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 local_28 [5];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    in_x30 = 0x5bb420;
    runtime_morestack_abi0();
    in_x3 = extraout_x3;
  }
  *(undefined8 *)((int)register0x00000008 + -0x20) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x28) = in_x29;
  pdVar4 = *(dword **)(in_x26 + 8);
  if ((runtime_arm64HasATOMICS & 1U) == 0) {
    do {
      iVar5 = *pdVar4 - 1;
      cVar1 = '\x01';
      bVar2 = (bool)ExclusiveMonitorPass(pdVar4,0x10);
      if (bVar2) {
        *pdVar4 = (dword)iVar5;
        cVar1 = ExclusiveMonitorsStatus();
      }
    } while (cVar1 != '\0');
  }
  else {
    LOAcquire();
    dVar3 = *pdVar4;
    *pdVar4 = dVar3 - 1;
    LORelease();
    iVar5 = CONCAT44((sdword)((uint)in_x3 >> 0x20),dVar3) + -1;
  }
  if ((sdword)iVar5 != 0) {
    internal_sync___Mutex__unlockSlow(pdVar4,iVar5);
  }
  return;
}

