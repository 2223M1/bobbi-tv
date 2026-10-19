/* Reconstructed pseudocode, not original Go source: main.handlePanStatus */

void main_handlePanStatus(int param_1,undefined8 param_2)

{
  int *piVar1;
  undefined8 uVar2;
  int iVar3;
  undefined8 uVar4;
  int iVar5;
  undefined8 uVar6;
  undefined8 *puVar7;
  undefined8 extraout_RCX;
  undefined1 *extraout_RCX_00;
  undefined1 *puVar8;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  byte bVar9;
  uint uVar10;
  int iVar11;
  undefined8 uVar12;
  undefined8 extraout_RSI;
  byte bVar13;
  undefined8 *extraout_R11;
  undefined8 *extraout_R11_00;
  undefined8 *extraout_R11_01;
  undefined8 *extraout_R11_02;
  undefined8 *extraout_R11_03;
  undefined8 *extraout_R11_04;
  undefined8 *extraout_R11_05;
  undefined8 *extraout_R11_06;
  undefined8 *extraout_R11_07;
  undefined8 *extraout_R11_08;
  int unaff_R14;
  undefined8 *in_XMM15_Qa;
  undefined1 auVar14 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  undefined1 *local_108;
  undefined1 *local_100;
  undefined8 *local_f8;
  undefined1 *local_f0;
  undefined8 local_e8;
  undefined8 uStack_e0;
  undefined1 local_c8;
  undefined7 uStack_c7;
  undefined8 *local_88 [12];
  undefined8 local_28;
  byte *local_20;
  byte *local_18;
  byte *local_10;
  
  iStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&local_108 <= *(undefined1 ***)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar2 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar14 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_f0 = auVar14._0_8_;
  local_f8 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_f8[1] = 0x10;
  *local_f8 = &DAT_00f195fc;
  auVar14 = runtime_mapassign_faststr(&DAT_00e91b20,uVar2,local_f0,auVar14._8_8_);
  puVar7 = auVar14._0_8_;
  puVar7[1] = 1;
  puVar7[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar7 = (undefined8 *)runtime_gcWriteBarrier2(puVar7,auVar14._8_8_,*puVar7);
    *extraout_R11 = local_f8;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar7 = local_f8;
  uVar2 = runtime_makemap_small();
  local_88[0] = in_XMM15_Qa;
  runtime_mapIterStart(&DAT_00e17280,main_providers);
  while (local_88[0] != (undefined8 *)0x0) {
    piVar1 = (int *)*local_88[0];
    iVar11 = local_88[0][1];
    if (main_tokenStore == (mv_daemon_provider_TokenStore *)0x0) {
      auVar14 = ZEXT816(0);
    }
    else {
      auVar14 = mv_daemon_provider___TokenStore__Get();
    }
    iVar3 = auVar14._8_8_;
    uVar6 = auVar14._0_8_;
    if (iVar11 == 6) {
      if (((sdword)*piVar1 == 0x59494c41) && (*(short *)((int)piVar1 + 4) == 0x4e55)) {
        uVar12 = 0x20;
      }
      else {
        if (((sdword)*piVar1 != 0x4c4e5558) || (*(short *)((int)piVar1 + 4) != 0x4945))
        goto LAB_00c58882;
        uVar12 = 0x10;
      }
    }
    else {
LAB_00c58882:
      uVar12 = 8;
    }
    if (main_concurrencyStore != (mv_daemon_provider_ConcurrencyStore *)0x0) {
      uVar12 = mv_daemon_provider___ConcurrencyStore__Get(main_concurrencyStore);
    }
    if (mv_daemon_provider_GlobalChunkSizeStore == (mv_daemon_provider_ChunkSizeStore *)0x0) {
      uVar4 = 0;
    }
    else {
      uVar4 = mv_daemon_provider___ChunkSizeStore__Get(mv_daemon_provider_GlobalChunkSizeStore);
    }
    if (iVar3 == 0) {
      bVar9 = 0;
    }
    else if (((iVar11 == 6) && ((sdword)*piVar1 == 0x59494c41)) &&
            (*(short *)((int)piVar1 + 4) == 0x4e55)) {
      local_10 = (byte *)runtime_newobject(&DAT_00e0d840);
      runtime_stringtoslicebyte(0,uVar6,iVar3);
      encoding_json_Unmarshal();
      bVar9 = *local_10;
    }
    else if (((iVar11 == 5) && ((sdword)*piVar1 == 0x52415551)) &&
            (*(char *)((int)piVar1 + 4) == 'K')) {
      auVar14 = strings_TrimSpace(uVar6,iVar3,5,uVar4,uVar12);
      if (auVar14._8_8_ == 0) {
        bVar9 = 0;
      }
      else if (*auVar14._0_8_ == '{') {
        local_18 = (byte *)runtime_newobject(&DAT_00e0d840);
        runtime_stringtoslicebyte(0,uVar6,iVar3);
        encoding_json_Unmarshal();
        bVar9 = *local_18;
      }
      else {
        bVar9 = 0;
      }
    }
    else if (iVar11 == 2) {
      if ((short)*piVar1 == 0x4355) {
        auVar14 = strings_TrimSpace(uVar6,iVar3,2,uVar4,uVar12);
        if (auVar14._8_8_ == 0) {
          bVar9 = 0;
        }
        else if (*auVar14._0_8_ == '{') {
          local_20 = (byte *)runtime_newobject(&DAT_00e0d840);
          runtime_stringtoslicebyte(0,uVar6,iVar3);
          encoding_json_Unmarshal();
          bVar9 = *local_20;
        }
        else {
          bVar9 = 0;
        }
      }
      else {
        bVar9 = 0;
      }
    }
    else {
      bVar9 = 0;
    }
    if (mv_daemon_provider_GlobalAutoDeleteStore == (mv_daemon_provider_AutoDeleteStore *)0x0) {
      bVar13 = 1;
      iVar5 = iVar3;
    }
    else {
      iVar5 = mv_daemon_provider___AutoDeleteStore__Get
                        (mv_daemon_provider_GlobalAutoDeleteStore,piVar1,iVar11,uVar4,uVar12);
      bVar13 = (byte)iVar5;
    }
    uVar6 = runtime_makemap_small(iVar5);
    puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f05a59,9);
    *puVar7 = &DAT_00dd2dc0;
    puVar8 = runtime_staticuint64s + (uint)(iVar3 != 0) * 8;
    local_f0 = runtime_staticuint64s + (uint)bVar13 * 8;
    local_100 = runtime_staticuint64s + (uint)bVar9 * 8;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar7 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_00 = extraout_RSI;
      puVar8 = extraout_RCX_00;
    }
    puVar7[1] = puVar8;
    local_108 = puVar8;
    auVar14 = runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f10c17,0xc);
    puVar7 = auVar14._0_8_;
    *puVar7 = &DAT_00dd2dc0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar7 = (undefined8 *)runtime_gcWriteBarrier1(puVar7,auVar14._8_8_,puVar7[1]);
      *extraout_R11_01 = extraout_RCX_01;
    }
    puVar7[1] = local_108;
    local_28 = runtime_convT64(uVar12);
    auVar14 = runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f0cdbb,0xb);
    puVar7 = auVar14._0_8_;
    *puVar7 = &DAT_00dd2c00;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar7 = (undefined8 *)runtime_gcWriteBarrier2(puVar7,auVar14._8_8_,puVar7[1]);
      *extraout_R11_02 = local_28;
      extraout_R11_02[1] = extraout_RCX_02;
    }
    puVar7[1] = local_28;
    local_28 = runtime_convT64(uVar4);
    puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f0a1d5,10);
    *puVar7 = &DAT_00dd2c00;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar12 = puVar7[1];
      puVar7 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_03 = local_28;
      extraout_R11_03[1] = uVar12;
    }
    puVar7[1] = local_28;
    puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f0cdc6,0xb);
    *puVar7 = &DAT_00dd2dc0;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar12 = puVar7[1];
      puVar7 = (undefined8 *)runtime_gcWriteBarrier1();
      *extraout_R11_04 = uVar12;
    }
    puVar7[1] = local_f0;
    auVar14 = runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00efe2cf,6);
    puVar7 = auVar14._0_8_;
    *puVar7 = &DAT_00dd2dc0;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar7 = (undefined8 *)runtime_gcWriteBarrier1(puVar7,auVar14._8_8_,puVar7[1]);
      *extraout_R11_05 = extraout_RCX_03;
    }
    puVar7[1] = local_100;
    uVar12 = mv_daemon_provider_GetPanQPS(piVar1,iVar11);
    local_28 = runtime_convT64(uVar12);
    puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00efabbe,3);
    *puVar7 = &DAT_00dd2d80;
    if (runtime_writeBarrier._0_4_ != 0) {
      uVar12 = puVar7[1];
      puVar7 = (undefined8 *)runtime_gcWriteBarrier2();
      *extraout_R11_06 = local_28;
      extraout_R11_06[1] = uVar12;
    }
    puVar7[1] = local_28;
    if ((iVar11 == 8) && (*piVar1 == 0x35313144554f4c43)) {
      if (main_global115DirStore == (main_Pan115DirStore *)0x0) {
        auVar14._8_8_ = 9;
        auVar14._0_8_ = &DAT_00f05a62;
      }
      else {
        auVar14 = main___Pan115DirStore__Get();
      }
      local_28 = runtime_convTstring(auVar14._0_8_,auVar14._8_8_);
      puVar7 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,uVar6,&DAT_00f02a81,8);
      *puVar7 = &DAT_00dd29c0;
      if (runtime_writeBarrier._0_4_ != 0) {
        uVar12 = puVar7[1];
        puVar7 = (undefined8 *)runtime_gcWriteBarrier2();
        *extraout_R11_07 = local_28;
        extraout_R11_07[1] = uVar12;
      }
      puVar7[1] = local_28;
    }
    auVar14 = runtime_mapassign_faststr(&DAT_00e17200,uVar2,piVar1,iVar11);
    puVar7 = auVar14._0_8_;
    if (runtime_writeBarrier._0_4_ != 0) {
      puVar7 = (undefined8 *)runtime_gcWriteBarrier2(puVar7,auVar14._8_8_,*puVar7);
      *extraout_R11_08 = uVar6;
      extraout_R11_08[1] = extraout_RCX_04;
    }
    *puVar7 = uVar6;
    runtime_mapIterNext(local_88);
  }
  local_e8 = 0;
  if (iStack0000000000000008 != 0) {
    uVar10 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar11 = (uVar10 & *(uint *)main__typeAssert_60) * 0x10;
      if (*(int *)(main__typeAssert_60 + iVar11 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_e8 = *(undefined8 *)(main__typeAssert_60 + iVar11 + 0x10);
        goto LAB_00c58ede;
      }
      uVar10 = uVar10 + 1;
    } while (*(int *)(main__typeAssert_60 + iVar11 + 8) != 0);
    local_e8 = runtime_typeAssert(&main__typeAssert_60);
  }
LAB_00c58ede:
  uStack_e0 = uStack0000000000000010;
  _local_c8 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  encoding_json___Encoder__Encode(&local_e8,&DAT_00e17200,uVar2);
  return;
}

