/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Get.deferwrap1 */

void mv_daemon_provider___TokenStore__Get_deferwrap1(void)

{
  sdword sVar1;
  sdword *psVar2;
  int unaff_RDX;
  int unaff_R14;
  
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_abi0();
  }
  psVar2 = *(sdword **)(unaff_RDX + 8);
  LOCK();
  sVar1 = *psVar2;
  *psVar2 = *psVar2 + -1;
  UNLOCK();
  if (sVar1 != 1) {
    internal_sync___Mutex__unlockSlow();
  }
  return;
}

