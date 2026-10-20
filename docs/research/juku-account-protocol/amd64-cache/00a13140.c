/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*OfflineCacheStore).init */

undefined1  [16] mv_daemon_provider___OfflineCacheStore__init(sdword *param_1)

{
  sdword sVar1;
  undefined8 uVar2;
  undefined1 auVar3 [16];
  undefined8 *puVar4;
  undefined8 extraout_RAX;
  undefined8 extraout_RCX;
  int extraout_RCX_00;
  sdword *extraout_RCX_01;
  sdword *psVar5;
  int extraout_RBX;
  undefined8 extraout_RDI;
  undefined8 *extraout_R11;
  int unaff_R14;
  undefined8 in_XMM15_Qa;
  undefined8 in_XMM15_Qb;
  undefined1 auVar6 [16];
  undefined1 auVar7 [16];
  undefined1 auVar8 [16];
  sdword *psStack0000000000000008;
  undefined *local_a0;
  undefined8 uStack_98;
  undefined8 local_90;
  undefined8 uStack_88;
  undefined8 local_80;
  undefined8 uStack_78;
  undefined8 local_70;
  undefined8 uStack_68;
  code *local_60;
  sdword *local_58;
  code *local_50;
  undefined *local_48;
  undefined8 local_40;
  undefined **local_38;
  undefined8 local_30;
  undefined8 local_28;
  undefined *local_20;
  undefined8 uStack_18;
  code **local_10;
  
  psStack0000000000000008 = param_1;
  while (&local_90 <= *(undefined8 **)(unaff_R14 + 0x10)) {
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
  local_60 = mv_daemon_provider___OfflineCacheStore__init_deferwrap1;
  local_10 = &local_60;
  local_58 = psStack0000000000000008;
  auVar6 = internal_filepathlite_Dir
                     (*(undefined8 *)(psStack0000000000000008 + 4),
                      *(undefined8 *)(psStack0000000000000008 + 6));
  auVar6 = os_MkdirAll(auVar6._0_8_,auVar6._8_8_,0x1ed);
  uStack_68 = auVar6._8_8_;
  if (auVar6._0_8_ != 0) {
    local_70 = *(undefined8 *)(auVar6._0_8_ + 8);
    auVar6 = fmt_errorf(&DAT_00f2fedd,0x1f,&local_70,1,1);
    if (auVar6._0_8_ == 0) {
      puVar4 = (undefined8 *)runtime_newobject(&DAT_00e21740);
      puVar4[1] = 0x1f;
      *puVar4 = &DAT_00f2fedd;
      auVar6._8_8_ = puVar4;
      auVar6._0_8_ = go_itab__errors_errorString_error;
    }
    (**local_10)();
    return auVar6;
  }
  uStack_18 = runtime_convTstring(*(undefined8 *)(psStack0000000000000008 + 4),
                                  *(undefined8 *)(psStack0000000000000008 + 6));
  local_20 = &DAT_00dd29c0;
  auVar6 = fmt_Sprintf(&DAT_00f5ab3c,0x53,&local_20,1,1);
  database_sql_Open(&DAT_00efe359,6,auVar6._0_8_,auVar6._8_8_);
  if (extraout_RBX != 0) {
    local_80 = *(undefined8 *)(extraout_RBX + 8);
    uStack_78 = extraout_RCX;
    auVar7 = fmt_errorf(&DAT_00f3287b,0x21,&local_80,1,1);
    if (auVar7._0_8_ == 0) {
      puVar4 = (undefined8 *)runtime_newobject(&DAT_00e21740);
      puVar4[1] = 0x21;
      *puVar4 = &DAT_00f3287b;
      auVar7._8_8_ = puVar4;
      auVar7._0_8_ = go_itab__errors_errorString_error;
    }
    (**local_10)();
    return auVar7;
  }
  database_sql___DB__SetMaxOpenConns(extraout_RAX,1);
  database_sql___DB__SetMaxIdleConns(extraout_RAX,1);
  database_sql___DB__ExecContext
            (extraout_RAX,go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,
             &DAT_00f6d87e,0x2f0,0,0,0);
  if (extraout_RCX_00 != 0) {
    database_sql___DB__Close(extraout_RAX);
    local_90 = 0;
    if (extraout_RCX_00 != 0) {
      local_90 = *(undefined8 *)(extraout_RCX_00 + 8);
    }
    uStack_88 = extraout_RDI;
    auVar8 = fmt_errorf(&DAT_00f3bcff,0x28,&local_90,1,1);
    if (auVar8._0_8_ == 0) {
      puVar4 = (undefined8 *)runtime_newobject(&DAT_00e21740);
      puVar4[1] = 0x28;
      *puVar4 = &DAT_00f3bcff;
      auVar8._8_8_ = puVar4;
      auVar8._0_8_ = go_itab__errors_errorString_error;
    }
    (**local_10)();
    return auVar8;
  }
  psVar5 = psStack0000000000000008;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar2 = *(undefined8 *)(psStack0000000000000008 + 2);
    runtime_gcWriteBarrier2();
    *extraout_R11 = extraout_RAX;
    extraout_R11[1] = uVar2;
    psVar5 = extraout_RCX_01;
  }
  *(undefined8 *)(psVar5 + 2) = extraout_RAX;
  uStack_98 = runtime_convTstring(*(undefined8 *)(psVar5 + 4),*(undefined8 *)(psVar5 + 6));
  local_a0 = &DAT_00dd29c0;
  local_50 = mv_daemon_provider___OfflineCacheStore__init_Printf_func1;
  local_40 = 0x37;
  local_48 = &DAT_00f4aa9a;
  local_30 = 1;
  local_28 = 1;
  local_38 = &local_a0;
  log___Logger__output(log_std,0,2,&local_50);
  (**local_10)();
  auVar3._8_8_ = in_XMM15_Qb;
  auVar3._0_8_ = in_XMM15_Qa;
  return auVar3;
}

