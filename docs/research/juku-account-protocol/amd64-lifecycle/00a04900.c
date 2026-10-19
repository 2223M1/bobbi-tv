/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*LifeSyncManager).handleEventForDir */

undefined8
mv_daemon_provider___LifeSyncManager__handleEventForDir
          (undefined8 param_1,undefined8 param_2,undefined8 param_3,int param_4,undefined8 param_5,
          undefined8 param_6)

{
  byte *pbVar1;
  undefined8 uVar2;
  int iVar3;
  int iVar4;
  undefined8 extraout_R10;
  undefined8 extraout_R11;
  int unaff_R14;
  undefined1 auVar5 [16];
  undefined8 in_stack_00000008;
  undefined8 in_stack_00000010;
  undefined8 in_stack_00000018;
  undefined8 in_stack_00000020;
  undefined8 in_stack_00000028;
  undefined8 in_stack_00000030;
  int in_stack_00000038;
  int in_stack_00000040;
  undefined8 in_stack_00000048;
  undefined8 in_stack_00000050;
  undefined8 in_stack_00000058;
  undefined8 in_stack_00000060;
  undefined8 in_stack_00000068;
  int in_stack_00000070;
  undefined8 in_stack_00000078;
  undefined8 in_stack_00000080;
  undefined8 uStack0000000000000088;
  undefined8 uStack0000000000000090;
  undefined8 uStack0000000000000098;
  int iStack00000000000000a0;
  undefined8 uStack00000000000000a8;
  undefined8 uStack00000000000000b0;
  undefined1 local_110 [55];
  byte local_d9;
  undefined *local_d8;
  undefined8 uStack_d0;
  undefined *local_c8;
  undefined8 uStack_c0;
  undefined *local_b8;
  undefined8 uStack_b0;
  undefined *local_a8;
  undefined8 uStack_a0;
  undefined *local_98;
  undefined8 uStack_90;
  undefined *local_88;
  undefined8 uStack_80;
  undefined *local_78;
  undefined8 uStack_70;
  undefined1 local_68 [16];
  undefined8 local_58;
  undefined8 uStack_50;
  undefined8 local_48;
  undefined8 uStack_40;
  code *local_38;
  undefined *local_30;
  undefined8 local_28;
  undefined **local_20;
  undefined8 local_18;
  undefined8 local_10;
  
  uStack0000000000000088 = param_1;
  uStack0000000000000098 = param_3;
  uStack0000000000000090 = param_2;
  uStack00000000000000a8 = param_5;
  iStack00000000000000a0 = param_4;
  uStack00000000000000b0 = param_6;
  while (iVar4 = in_stack_00000040, local_110 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  while ((iVar4 = iVar4 + -1, -1 < iVar4 && (*(char *)(in_stack_00000038 + iVar4) != '/'))) {
    if (*(char *)(in_stack_00000038 + iVar4) == '.') {
      iVar3 = in_stack_00000038 + iVar4;
      iVar4 = in_stack_00000040 - iVar4;
LAB_00a04989:
      strings_ToLower(iVar3,iVar4);
      if (in_stack_00000070 == 0) {
        auVar5 = mv_daemon_provider_CleanExt();
        pbVar1 = (byte *)runtime_mapaccess1_faststr
                                   (&DAT_00e16280,mv_daemon_provider_videoExtsMap,auVar5._0_8_,
                                    auVar5._8_8_);
        local_d9 = *pbVar1 ^ 1;
      }
      else {
        local_d9 = 0;
      }
      switch(in_stack_00000018) {
      case 1:
      case 2:
      case 0xe:
      case 0x11:
      case 0x12:
      case 0x17:
        if (local_d9 != 0) {
          uStack_90 = runtime_convTstring(in_stack_00000038,in_stack_00000040);
          local_98 = &DAT_00dd29c0;
          uStack_80 = runtime_convTstring(in_stack_00000028,in_stack_00000030);
          local_88 = &DAT_00dd29c0;
          uStack_70 = runtime_convTstring(*(undefined8 *)(iStack00000000000000a0 + 0x40),
                                          *(undefined8 *)(iStack00000000000000a0 + 0x48));
          local_78 = &DAT_00dd29c0;
          local_38 = mv_daemon_provider___LifeSyncManager__handleEventForDir_Printf_func1;
          local_28 = 0x57;
          local_30 = &DAT_00f5c50a;
          local_18 = 3;
          local_10 = 3;
          local_20 = &local_98;
          log___Logger__output(log_std,0,2,&local_38);
          uVar2 = mv_daemon_provider___LifeSyncManager__handleFolderSync
                            (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                             iStack00000000000000a0,uStack00000000000000a8,uStack00000000000000b0);
          return uVar2;
        }
        uVar2 = mv_daemon_provider___LifeSyncManager__handleCreateEvent
                          (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                           iStack00000000000000a0,uStack00000000000000a8,uStack00000000000000b0);
        return uVar2;
      default:
        return 0;
      case 5:
      case 6:
        goto switchD_00a04a18_caseD_5;
      case 0x14:
      case 0x18:
        uStack_50 = in_stack_00000030;
        local_58 = in_stack_00000028;
        uStack_40 = in_stack_00000050;
        local_48 = in_stack_00000048;
        mv_daemon_provider_Invalidate115DirCache(&local_58,2,2);
        if (local_d9 != 0) {
          mv_daemon_provider_ClearAll115DirCache();
        }
        uVar2 = mv_daemon_provider___LifeSyncManager__handleRenameOrMoveEvent
                          (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                           iStack00000000000000a0);
        return uVar2;
      case 0x16:
        uStack_50 = in_stack_00000030;
        local_58 = in_stack_00000028;
        uStack_40 = in_stack_00000050;
        local_48 = in_stack_00000048;
        mv_daemon_provider_Invalidate115DirCache(&local_58,2,2);
        if (local_d9 != 0) {
          mv_daemon_provider_ClearAll115DirCache();
          uVar2 = mv_daemon_provider___LifeSyncManager__handleDeleteFolderEvent
                            (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                             iStack00000000000000a0);
          return uVar2;
        }
        uVar2 = mv_daemon_provider___LifeSyncManager__handleDeleteEvent
                          (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                           iStack00000000000000a0);
        return uVar2;
      }
    }
  }
  iVar4 = 0;
  iVar3 = 0;
  goto LAB_00a04989;
switchD_00a04a18_caseD_5:
  uStack_50 = in_stack_00000030;
  local_58 = in_stack_00000028;
  uStack_40 = in_stack_00000050;
  local_48 = in_stack_00000048;
  mv_daemon_provider_Invalidate115DirCache(&local_58,2,2);
  if (local_d9 != 0) {
    mv_daemon_provider_ClearAll115DirCache();
  }
  local_68 = mv_daemon_provider___LifeSyncManager__resolveEventPickCode
                       (uStack0000000000000088,&stack0x00000008,uStack00000000000000a8,
                        uStack00000000000000b0);
  auVar5 = mv_daemon_provider___PrivateLibStore__FindLinkByFileIDAndLib
                     (mv_daemon_provider_GlobalPrivateLibStore,
                      *(undefined8 *)(iStack00000000000000a0 + 0x10),
                      *(undefined8 *)(iStack00000000000000a0 + 0x18),&DAT_00f02951,8,
                      in_stack_00000028,in_stack_00000030,extraout_R10,extraout_R11,local_68,1,1);
  if ((auVar5._8_8_ != 0) && (auVar5._0_8_ != 0)) {
    uVar2 = mv_daemon_provider___LifeSyncManager__handleRenameOrMoveEvent
                      (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                       iStack00000000000000a0);
    return uVar2;
  }
  uStack_d0 = runtime_convTstring(in_stack_00000038,in_stack_00000040);
  local_d8 = &DAT_00dd29c0;
  uStack_c0 = runtime_convTstring(in_stack_00000028,in_stack_00000030);
  local_c8 = &DAT_00dd29c0;
  uStack_b0 = runtime_convT64(in_stack_00000070);
  local_b8 = &DAT_00dd2c00;
  uStack_a0 = runtime_convTstring(*(undefined8 *)(iStack00000000000000a0 + 0x40),
                                  *(undefined8 *)(iStack00000000000000a0 + 0x48));
  local_a8 = &DAT_00dd29c0;
  local_38 = mv_daemon_provider___LifeSyncManager__handleEventForDir_Printf_func2;
  local_28 = 0x65;
  local_30 = &DAT_00f5fd86;
  local_18 = 4;
  local_10 = 4;
  local_20 = &local_d8;
  log___Logger__output(log_std,0,2,&local_38);
  if (local_d9 != 0) {
    uVar2 = mv_daemon_provider___LifeSyncManager__handleFolderSync
                      (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                       iStack00000000000000a0,uStack00000000000000a8,uStack00000000000000b0);
    return uVar2;
  }
  uVar2 = mv_daemon_provider___LifeSyncManager__handleCreateEvent
                    (uStack0000000000000088,uStack0000000000000090,uStack0000000000000098,
                     iStack00000000000000a0,uStack00000000000000a8,uStack00000000000000b0);
  return uVar2;
}

