/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*OfflineCacheStore).GetValid */

undefined1  [24]
mv_daemon_provider___OfflineCacheStore__GetValid
          (undefined8 param_1,undefined8 param_2,undefined8 param_3,int param_4,undefined8 param_5,
          int param_6)

{
  char cVar1;
  uint uVar2;
  undefined1 auVar3 [24];
  undefined1 auVar4 [24];
  int extraout_RBX;
  int unaff_R14;
  undefined8 uStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined8 uStack0000000000000018;
  int iStack0000000000000020;
  undefined8 uStack0000000000000028;
  int iStack0000000000000030;
  
  uStack0000000000000008 = param_1;
  uStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  uStack0000000000000028 = param_5;
  iStack0000000000000020 = param_4;
  iStack0000000000000030 = param_6;
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar2 = mv_daemon_provider___OfflineCacheStore__Get();
  if (uVar2 == 0) {
    auVar4._0_16_ = ZEXT816(0);
    auVar4._16_8_ = 0;
    return auVar4;
  }
  if (((*(int *)(uVar2 + 0xb8) == 2) &&
      (((*(int *)(uVar2 + 0x68) != 0 || (*(int *)(uVar2 + 0x78) != 0)) &&
       (iStack0000000000000030 != 0)))) &&
     (((iStack0000000000000020 != 0 &&
       (cVar1 = mv_daemon_provider___Cloud115Provider__Check115FileExists
                          (iStack0000000000000020,*(undefined8 *)(uVar2 + 0x60),
                           *(int *)(uVar2 + 0x68),*(undefined8 *)(uVar2 + 0x70),
                           *(undefined8 *)(uVar2 + 0x78),uStack0000000000000028), extraout_RBX == 0)
       ) && (cVar1 == '\0')))) {
    mv_daemon_provider___OfflineCacheStore__Delete
              (uStack0000000000000008,uStack0000000000000010,uStack0000000000000018);
    if (*(int *)(uVar2 + 0x28) != 0) {
      mv_daemon_provider___OfflineCacheStore__Delete
                (uStack0000000000000008,*(undefined8 *)(uVar2 + 0x20));
    }
    if (*(int *)(uVar2 + 0x18) != 0) {
      mv_daemon_provider___OfflineCacheStore__Delete
                (uStack0000000000000008,*(undefined8 *)(uVar2 + 0x10));
    }
    auVar3._0_16_ = ZEXT816(0);
    auVar3._16_8_ = 0;
    return auVar3;
  }
  return ZEXT824(uVar2);
}

