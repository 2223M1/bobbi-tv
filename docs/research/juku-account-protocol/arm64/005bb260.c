/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Get */

undefined1  [16]
mv_daemon_provider___TokenStore__Get(sdword *param_1,undefined8 param_2,undefined8 param_3)

{
  sdword sVar1;
  undefined8 uVar2;
  char cVar3;
  bool bVar4;
  undefined1 *puVar5;
  bool bVar6;
  undefined8 *puVar7;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 local_68 [6];
  undefined1 local_31;
  undefined8 local_30;
  undefined8 local_28 [5];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(sdword **)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x5bb3a0;
    runtime_morestack_noctxt_abi0();
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  puVar5 = (undefined1 *)((int)register0x00000008 + -0x60);
  *(undefined8 *)((int)register0x00000008 + -0x60) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x68) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
  *(undefined1 *)((int)register0x00000008 + -0x31) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x30) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x28) = 0;
  if ((runtime_arm64HasATOMICS & 1U) == 0) {
    do {
      bVar6 = *param_1 == 0;
      if (!bVar6) break;
      cVar3 = '\x01';
      bVar4 = (bool)ExclusiveMonitorPass(param_1,0x10);
      if (bVar4) {
        *param_1 = 1;
        cVar3 = ExclusiveMonitorsStatus();
      }
    } while (cVar3 != '\0');
  }
  else {
    sVar1 = *param_1;
    if (sVar1 == 0) {
      *param_1 = 1;
    }
    bVar6 = sVar1 == 0;
  }
  if (!bVar6) {
    *(sdword **)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    internal_sync___Mutex__lockSlow();
    puVar5 = (undefined1 *)((int)register0x00000008 + -0x58);
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(code **)(puVar5 + 0x40) = mv_daemon_provider___TokenStore__Get_deferwrap1;
  *(sdword **)(puVar5 + 0x48) = param_1;
  *(undefined1 **)(puVar5 + 0x50) = puVar5 + 0x40;
  puVar5[0x2f] = 1;
  if (*(int *)(param_1 + 6) == 0) {
    *(undefined8 *)(puVar5 + 0x30) = 0;
    *(undefined8 *)(puVar5 + 0x38) = 0;
    puVar5[0x2f] = 0;
    (*(code *)**(undefined8 **)(puVar5 + 0x50))();
    return *(undefined1 (*) [16])(puVar5 + 0x38);
  }
  puVar7 = (undefined8 *)
           runtime_mapaccess1_faststr(&DAT_008ecae0,*(int *)(param_1 + 6),param_2,param_3);
  uVar2 = puVar7[1];
  *(undefined8 *)(puVar5 + 0x38) = *puVar7;
  *(undefined8 *)(puVar5 + 0x40) = uVar2;
  puVar5[0x37] = 0;
  (*(code *)**(undefined8 **)(puVar5 + 0x58))();
  return *(undefined1 (*) [16])(puVar5 + 0x40);
}

