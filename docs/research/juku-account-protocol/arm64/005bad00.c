/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).load */

void mv_daemon_provider___TokenStore__load(sdword *param_1)

{
  sdword sVar1;
  char cVar2;
  bool bVar3;
  undefined1 *puVar4;
  undefined1 *puVar5;
  undefined1 *puVar6;
  bool bVar7;
  undefined8 extraout_x0;
  uint uVar8;
  undefined8 uVar9;
  undefined8 extraout_x0_00;
  undefined8 extraout_x0_01;
  undefined8 extraout_x1;
  undefined8 uVar10;
  undefined8 extraout_x1_00;
  undefined8 extraout_x1_01;
  undefined8 extraout_x2;
  undefined8 uVar11;
  undefined8 extraout_x2_00;
  undefined8 extraout_x2_01;
  int extraout_x3;
  int extraout_x3_00;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar12 [16];
  undefined8 local_a8 [7];
  undefined1 auStack_69 [8];
  undefined1 local_61 [24];
  undefined1 auStack_49 [57];
  undefined8 local_10 [2];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x20) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(sdword **)((int)register0x00000008 + 8) = param_1;
    in_x30 = 0x5bae9c;
    runtime_morestack_noctxt_abi0();
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
  }
  puVar4 = (undefined1 *)((int)register0x00000008 + -0xa0);
  *(undefined8 *)((int)register0x00000008 + -0xa0) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0xa8) = in_x29;
  *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
  *(undefined1 *)((int)register0x00000008 + -0x69) = 0;
  if ((runtime_arm64HasATOMICS & 1U) == 0) {
    do {
      bVar7 = *param_1 == 0;
      if (!bVar7) break;
      cVar2 = '\x01';
      bVar3 = (bool)ExclusiveMonitorPass(param_1,0x10);
      if (bVar3) {
        *param_1 = 1;
        cVar2 = ExclusiveMonitorsStatus();
      }
    } while (cVar2 != '\0');
  }
  else {
    sVar1 = *param_1;
    if (sVar1 == 0) {
      *param_1 = 1;
    }
    bVar7 = sVar1 == 0;
  }
  *(sdword **)((int)register0x00000008 + 8) = param_1;
  if (!bVar7) {
    internal_sync___Mutex__lockSlow();
    puVar4 = (undefined1 *)((int)register0x00000008 + -0x98);
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
  }
  *(code **)(puVar4 + 0x80) = mv_daemon_provider___TokenStore__load_deferwrap1;
  *(sdword **)(puVar4 + 0x88) = param_1;
  *(undefined1 **)(puVar4 + 0x90) = puVar4 + 0x80;
  puVar4[0x37] = 1;
  os_ReadFile(*(undefined8 *)(param_1 + 2),*(undefined8 *)(param_1 + 4));
  if (extraout_x3 != 0) {
    puVar4[0x3f] = 0;
    (*(code *)**(undefined8 **)(puVar4 + 0x98))();
    return;
  }
  *(undefined8 *)(puVar4 + 0x68) = extraout_x2;
  *(undefined8 *)(puVar4 + 0x60) = extraout_x1;
  *(undefined8 *)(puVar4 + 0x78) = extraout_x0;
  runtime_slicebytetostring(puVar4 + 0x40,extraout_x0,extraout_x1);
  auVar12 = strings_TrimSpace();
  puVar5 = puVar4 + 0x18;
  if (2 < auVar12._8_8_) {
    *(int *)(puVar4 + 0x90) = auVar12._0_8_;
    *(int *)(puVar4 + 0x80) = auVar12._8_8_;
    uVar8 = runtime_memequal(auVar12._0_8_,&DAT_009d2125,3);
    puVar5 = puVar4 + 0x20;
    if ((uVar8 & 1) != 0) {
      mv_daemon_pkg_auth_GetEncryptionKey();
      mv_daemon_pkg_auth_DecryptGCM
                (*(undefined8 *)(puVar4 + 0xa0),*(undefined8 *)(puVar4 + 0x90),extraout_x0_00,
                 extraout_x1_00,extraout_x2_00);
      bVar7 = extraout_x3_00 == 0;
      uVar11 = *(undefined8 *)(puVar4 + 0x90);
      if (bVar7) {
        uVar11 = extraout_x2_01;
      }
      uVar10 = *(undefined8 *)(puVar4 + 0x88);
      if (bVar7) {
        uVar10 = extraout_x1_01;
      }
      uVar9 = *(undefined8 *)(puVar4 + 0xa0);
      puVar6 = puVar4 + 0x30;
      if (bVar7) {
        puVar6 = puVar4 + 0x30;
        uVar9 = extraout_x0_01;
      }
      goto LAB_005bae34;
    }
  }
  uVar11 = *(undefined8 *)(puVar5 + 0x60);
  uVar10 = *(undefined8 *)(puVar5 + 0x58);
  uVar9 = *(undefined8 *)(puVar5 + 0x70);
  puVar6 = puVar5;
LAB_005bae34:
  encoding_json_Unmarshal(uVar9,uVar10,uVar11,&DAT_00892e60,*(int *)(puVar6 + 0xa8) + 0x18);
  puVar6[0x3f] = 0;
  (*(code *)**(undefined8 **)(puVar6 + 0x98))();
  return;
}

