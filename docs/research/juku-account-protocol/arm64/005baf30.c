/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*TokenStore).Save */

undefined1  [16]
mv_daemon_provider___TokenStore__Save
          (sdword *param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,
          undefined8 param_5)

{
  sdword sVar1;
  char cVar2;
  bool bVar3;
  undefined1 *puVar4;
  undefined1 *puVar5;
  undefined1 *puVar6;
  bool bVar7;
  undefined8 uVar8;
  undefined8 *puVar9;
  undefined8 extraout_x0;
  undefined8 extraout_x0_00;
  undefined8 extraout_x0_01;
  undefined8 extraout_x0_02;
  int extraout_x1;
  undefined8 extraout_x1_00;
  undefined8 extraout_x1_01;
  undefined8 extraout_x1_02;
  undefined8 extraout_x1_03;
  int iVar10;
  int extraout_x2;
  undefined8 extraout_x2_00;
  undefined8 extraout_x2_01;
  undefined8 extraout_x2_02;
  int extraout_x2_03;
  undefined8 extraout_x2_04;
  undefined8 extraout_x3;
  int extraout_x3_00;
  undefined8 extraout_x3_01;
  undefined8 extraout_x4;
  undefined8 *in_x25;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar11 [16];
  undefined8 local_b8 [9];
  undefined1 local_69 [24];
  undefined1 auStack_51 [16];
  undefined1 local_41 [9];
  undefined8 local_38;
  undefined8 auStack_30 [4];
  undefined8 local_10 [2];
  
  for (; (undefined1 *)((int)register0x00000008 + -0x30) <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(sdword **)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
    *(undefined8 *)((int)register0x00000008 + 0x28) = param_5;
    in_x30 = 0x5bb1cc;
    runtime_morestack_noctxt_abi0();
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
    param_4 = *(undefined8 *)((int)register0x00000008 + 0x28);
    param_5 = *(undefined8 *)((int)register0x00000008 + 0x30);
  }
  puVar4 = (undefined1 *)((int)register0x00000008 + -0xb0);
  *(undefined8 *)((int)register0x00000008 + -0xb0) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0xb8) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
  *(undefined8 *)((int)register0x00000008 + -0x10) = 0;
  *(undefined1 *)((int)register0x00000008 + -0x69) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x38) = 0;
  *(undefined8 *)((int)register0x00000008 + -0x30) = 0;
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
  *(undefined8 *)((int)register0x00000008 + 0x28) = param_5;
  *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
  if (!bVar7) {
    internal_sync___Mutex__lockSlow();
    puVar4 = (undefined1 *)((int)register0x00000008 + -0xa8);
    param_1 = *(sdword **)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
    param_4 = *(undefined8 *)((int)register0x00000008 + 0x28);
    param_5 = *(undefined8 *)((int)register0x00000008 + 0x30);
  }
  *(code **)(puVar4 + 0x90) = mv_daemon_provider___TokenStore__Save_deferwrap1;
  *(sdword **)(puVar4 + 0x98) = param_1;
  *(undefined1 **)(puVar4 + 0xa0) = puVar4 + 0x90;
  puVar4[0x47] = 1;
  puVar5 = puVar4;
  if (*(int *)(param_1 + 6) == 0) {
    uVar8 = runtime_makemap_small(param_1,param_2,param_3);
    puVar5 = puVar4 + 8;
    if (runtime_writeBarrier._0_4_ == 0) {
      iVar10 = *(int *)(puVar4 + 0xc0);
    }
    else {
      uVar8 = runtime_gcWriteBarrier2();
      puVar5 = puVar4 + 0x10;
      *in_x25 = uVar8;
      in_x25[1] = extraout_x3;
      iVar10 = extraout_x2;
    }
    *(undefined8 *)(iVar10 + 0x18) = uVar8;
    param_4 = *(undefined8 *)(puVar5 + 0xd0);
    param_5 = *(undefined8 *)(puVar5 + 0xd8);
  }
  strings_TrimSpace(param_4,param_5);
  if (extraout_x1 == 0) {
    runtime_mapdelete_faststr
              (&DAT_008ecae0,*(undefined8 *)(*(int *)(puVar5 + 0xc0) + 0x18),
               *(undefined8 *)(puVar5 + 200),*(undefined8 *)(puVar5 + 0xd0));
    puVar6 = puVar5 + 0x10;
  }
  else {
    auVar11 = runtime_mapassign_faststr
                        (&DAT_008ecae0,*(undefined8 *)(*(int *)(puVar5 + 0xc0) + 0x18),
                         *(undefined8 *)(puVar5 + 200),*(undefined8 *)(puVar5 + 0xd0));
    puVar9 = auVar11._0_8_;
    puVar6 = puVar5 + 0x10;
    puVar9[1] = *(undefined8 *)(puVar5 + 0xe8);
    if (runtime_writeBarrier._0_4_ == 0) {
      uVar8 = *(undefined8 *)(puVar5 + 0xe0);
    }
    else {
      puVar9 = (undefined8 *)runtime_gcWriteBarrier2(puVar9,auVar11._8_8_,*puVar9);
      puVar6 = puVar5 + 0x18;
      uVar8 = *(undefined8 *)(puVar5 + 0xe8);
      *in_x25 = uVar8;
      in_x25[1] = extraout_x2_00;
    }
    *puVar9 = uVar8;
  }
  encoding_json_Marshal(&DAT_008ecae0,*(undefined8 *)(*(int *)(puVar6 + 0xb8) + 0x18));
  if (extraout_x3_00 != 0) {
    *(int *)(puVar6 + 0x80) = extraout_x3_00;
    *(undefined8 *)(puVar6 + 0x88) = extraout_x4;
    puVar6[0x4f] = 0;
    (*(code *)**(undefined8 **)(puVar6 + 0xa8))();
    return *(undefined1 (*) [16])(puVar6 + 0x88);
  }
  *(undefined8 *)(puVar6 + 0x70) = extraout_x1_00;
  *(undefined8 *)(puVar6 + 0x90) = extraout_x0;
  *(undefined8 *)(puVar6 + 0x78) = extraout_x2_01;
  mv_daemon_pkg_auth_GetEncryptionKey();
  mv_daemon_pkg_auth_EncryptGCM
            (*(undefined8 *)(puVar6 + 0x98),*(undefined8 *)(puVar6 + 0x78),
             *(undefined8 *)(puVar6 + 0x80),extraout_x0_00,extraout_x1_01,extraout_x2_02);
  if (extraout_x2_03 == 0) {
    runtime_stringtoslicebyte(puVar6 + 0x60,extraout_x0_01,extraout_x1_02);
    auVar11 = os_WriteFile(*(undefined8 *)(*(int *)(puVar6 + 0xd8) + 8),
                           *(undefined8 *)(*(int *)(puVar6 + 0xd8) + 0x10),extraout_x0_02,
                           extraout_x1_03,extraout_x2_04,0x180);
    *(undefined1 (*) [16])(puVar6 + 0xa0) = auVar11;
    puVar6[0x6f] = 0;
    (*(code *)**(undefined8 **)(puVar6 + 200))();
    return *(undefined1 (*) [16])(puVar6 + 0xa8);
  }
  *(int *)(puVar6 + 0x90) = extraout_x2_03;
  *(undefined8 *)(puVar6 + 0x98) = extraout_x3_01;
  puVar6[0x5f] = 0;
  (*(code *)**(undefined8 **)(puVar6 + 0xb8))();
  return *(undefined1 (*) [16])(puVar6 + 0x98);
}

