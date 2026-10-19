/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*OfflineCacheStore).Set */

undefined1  [16] mv_daemon_provider___OfflineCacheStore__Set(dword *param_1,undefined8 *param_2)

{
  dword dVar1;
  undefined1 uVar2;
  int iVar3;
  int iVar4;
  undefined **ppuVar5;
  uint uVar6;
  undefined8 uVar7;
  undefined8 *puVar8;
  undefined **ppuVar9;
  undefined8 extraout_RCX;
  sdword sVar10;
  int iVar11;
  int extraout_RDI;
  undefined8 extraout_RDI_00;
  int unaff_R14;
  undefined *in_XMM15_Qa;
  undefined *in_XMM15_Qb;
  undefined1 auVar12 [16];
  undefined1 auVar13 [16];
  undefined1 auVar14 [16];
  undefined1 auVar15 [16];
  dword *pdStack0000000000000008;
  undefined8 *puStack0000000000000010;
  undefined8 local_110;
  undefined *local_108;
  undefined8 uStack_100;
  undefined *local_f8;
  undefined8 uStack_f0;
  undefined *local_e8;
  undefined8 uStack_e0;
  undefined *local_d8;
  undefined8 uStack_d0;
  undefined *local_c8;
  undefined8 local_c0;
  undefined *local_b8;
  undefined8 local_b0;
  undefined *local_a8;
  undefined8 local_a0;
  undefined *local_98;
  undefined8 local_90;
  undefined *local_88;
  undefined8 uStack_80;
  undefined *local_78;
  undefined8 uStack_70;
  undefined *local_68;
  undefined8 uStack_60;
  undefined *local_58;
  undefined8 local_50;
  undefined *local_48;
  undefined8 local_40;
  undefined *local_38;
  undefined8 local_30;
  undefined *local_28;
  undefined8 local_20;
  undefined8 local_18;
  undefined8 local_10;
  
  pdStack0000000000000008 = param_1;
  puStack0000000000000010 = param_2;
  while (&local_110 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  if (puStack0000000000000010 == (undefined8 *)0x0) {
    return ZEXT816(0);
  }
  strings_TrimSpace(puStack0000000000000010[4],puStack0000000000000010[5]);
  auVar12 = strings_ToLower();
  local_110 = auVar12._0_8_;
  strings_TrimSpace(*puStack0000000000000010,puStack0000000000000010[1]);
  auVar13 = strings_ToLower();
  local_10 = auVar13._0_8_;
  strings_TrimSpace(puStack0000000000000010[2],puStack0000000000000010[3]);
  auVar14 = strings_ToLower();
  uVar7 = local_110;
  iVar4 = auVar12._8_8_;
  if (auVar12._8_8_ == 0) {
    uVar7 = local_10;
    iVar4 = auVar13._8_8_;
  }
  auVar12._8_8_ = iVar4;
  auVar12._0_8_ = uVar7;
  if (iVar4 == 0) {
    auVar12 = auVar14;
  }
  iVar4 = auVar12._8_8_;
  local_18 = auVar12._0_8_;
  if (iVar4 != 0) {
    uVar6 = 0;
    LOCK();
    dVar1 = *pdStack0000000000000008;
    if (dVar1 == 0) {
      *pdStack0000000000000008 = 1;
    }
    else {
      uVar6 = (uint)dVar1;
    }
    UNLOCK();
    local_110 = auVar14._0_8_;
    if (dVar1 != 0) {
      uVar6 = internal_sync___Mutex__lockSlow(pdStack0000000000000008);
    }
    iVar3 = *(int *)(pdStack0000000000000008 + 2);
    LOCK();
    dVar1 = *pdStack0000000000000008;
    *pdStack0000000000000008 = *pdStack0000000000000008 - 1;
    UNLOCK();
    if ((dword)(dVar1 - 1) != 0) {
      uVar6 = internal_sync___Mutex__unlockSlow
                        (pdStack0000000000000008,dVar1 - 1,iVar4,local_10,local_18,local_110);
    }
    if (iVar3 != 0) {
      auVar12 = time_Now(uVar6);
      iVar11 = auVar12._8_8_;
      if ((int)auVar12._0_8_ < 0) {
        iVar11 = ((auVar12._0_8_ & 0x7fffffffffffffff) >> 0x1e) + 0xdd7b17f80;
      }
      if (puStack0000000000000010[0x18] == 0) {
        puStack0000000000000010[0x18] = iVar11 + -0xe7791f700;
      }
      uVar2 = *(undefined1 *)(puStack0000000000000010 + 0x13);
      if (puStack0000000000000010[0x15] == 0) {
        auVar12 = ZEXT816(0);
      }
      else {
        uVar7 = runtime_convTslice(puStack0000000000000010[0x14],puStack0000000000000010[0x15],
                                   puStack0000000000000010[0x16]);
        auVar12 = encoding_json_Marshal(&DAT_00dc15a0,uVar7);
        if (extraout_RDI == 0) {
          auVar12 = runtime_slicebytetostring(0,auVar12._0_8_,auVar12._8_8_);
        }
        else {
          auVar12 = ZEXT816(0);
        }
      }
      sVar10 = 3;
      ppuVar5 = &local_108;
      do {
        ppuVar9 = ppuVar5;
        *ppuVar9 = in_XMM15_Qa;
        ppuVar9[1] = in_XMM15_Qb;
        ppuVar9[2] = in_XMM15_Qa;
        ppuVar9[3] = in_XMM15_Qb;
        ppuVar9[4] = in_XMM15_Qa;
        ppuVar9[5] = in_XMM15_Qb;
        ppuVar9[6] = in_XMM15_Qa;
        ppuVar9[7] = in_XMM15_Qb;
        sVar10 = sVar10 + -1;
        ppuVar5 = ppuVar9 + 8;
      } while (sVar10 != 0);
      ppuVar9[8] = in_XMM15_Qa;
      ppuVar9[9] = in_XMM15_Qb;
      ppuVar9[10] = in_XMM15_Qa;
      ppuVar9[0xb] = in_XMM15_Qb;
      ppuVar9[0xc] = in_XMM15_Qa;
      ppuVar9[0xd] = in_XMM15_Qb;
      uStack_100 = runtime_convTstring(local_18,iVar4);
      local_108 = &DAT_00dd29c0;
      uStack_f0 = runtime_convTstring(local_10,auVar13._8_8_);
      local_f8 = &DAT_00dd29c0;
      uStack_e0 = runtime_convTstring(local_110,auVar14._8_8_);
      local_e8 = &DAT_00dd29c0;
      uStack_d0 = runtime_convTstring(puStack0000000000000010[6],puStack0000000000000010[7]);
      local_d8 = &DAT_00dd29c0;
      local_c0 = runtime_convTstring(puStack0000000000000010[8],puStack0000000000000010[9]);
      local_c8 = &DAT_00dd29c0;
      local_b0 = runtime_convTstring(puStack0000000000000010[10],puStack0000000000000010[0xb]);
      local_b8 = &DAT_00dd29c0;
      local_a0 = runtime_convTstring(puStack0000000000000010[0xc],puStack0000000000000010[0xd]);
      local_a8 = &DAT_00dd29c0;
      local_90 = runtime_convTstring(puStack0000000000000010[0xe],puStack0000000000000010[0xf]);
      local_98 = &DAT_00dd29c0;
      uStack_80 = runtime_convTstring(puStack0000000000000010[0x10],puStack0000000000000010[0x11]);
      local_88 = &DAT_00dd29c0;
      uStack_70 = runtime_convT64(puStack0000000000000010[0x12]);
      local_78 = &DAT_00dd2b80;
      uStack_60 = runtime_convT64(uVar2);
      local_68 = &DAT_00dd2c00;
      local_50 = runtime_convTstring(auVar12._0_8_,auVar12._8_8_);
      local_58 = &DAT_00dd29c0;
      local_40 = runtime_convT64(puStack0000000000000010[0x17]);
      local_48 = &DAT_00dd2c00;
      local_30 = runtime_convT64(iVar11 + -0xe7791f700);
      local_38 = &DAT_00dd2b80;
      local_20 = runtime_convT64(puStack0000000000000010[0x18]);
      local_28 = &DAT_00dd2b80;
      database_sql___DB__ExecContext
                (iVar3,go_itab_context_backgroundCtx_context_Context,&runtime_zerobase,&DAT_00f6db6e
                 ,0x2fe,&local_108,0xf,0xf);
      auVar15._8_8_ = extraout_RDI_00;
      auVar15._0_8_ = extraout_RCX;
      return auVar15;
    }
    puVar8 = (undefined8 *)
             runtime_newobject(&DAT_00e21740,auVar14._8_8_,iVar4,local_10,local_18,local_110);
    puVar8[1] = 0x22;
    *puVar8 = &DAT_00f33ff4;
    auVar14._8_8_ = puVar8;
    auVar14._0_8_ = go_itab__errors_errorString_error;
    return auVar14;
  }
  puVar8 = (undefined8 *)runtime_newobject(&DAT_00e21740);
  puVar8[1] = 0x2a;
  *puVar8 = &DAT_00f3e009;
  auVar13._8_8_ = puVar8;
  auVar13._0_8_ = go_itab__errors_errorString_error;
  return auVar13;
}

