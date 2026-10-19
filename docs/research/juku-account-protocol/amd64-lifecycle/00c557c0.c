/* Reconstructed pseudocode, not original Go source: main.handle115OfflineTasks */

void main_handle115OfflineTasks(int param_1,undefined8 param_2,int param_3)

{
  undefined8 uVar1;
  int *piVar2;
  int iVar3;
  int *extraout_RAX;
  undefined8 *puVar4;
  int iVar5;
  undefined8 extraout_RCX;
  undefined8 uVar6;
  undefined8 extraout_RCX_00;
  undefined8 extraout_RCX_01;
  undefined8 extraout_RCX_02;
  undefined8 extraout_RCX_03;
  undefined8 extraout_RCX_04;
  undefined8 extraout_RCX_05;
  int iVar7;
  int extraout_RCX_06;
  undefined8 extraout_RCX_07;
  uint uVar8;
  char extraout_BL;
  int extraout_RBX;
  undefined8 extraout_RSI;
  int extraout_RDI;
  int extraout_RDI_00;
  int extraout_R8;
  int extraout_R8_00;
  int iVar9;
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
  undefined8 in_XMM15_Qa;
  undefined1 auVar10 [16];
  undefined1 auVar11 [16];
  int iStack0000000000000008;
  undefined8 uStack0000000000000010;
  int iStack0000000000000018;
  undefined8 local_90;
  undefined8 uStack_88;
  undefined1 local_80 [16];
  undefined1 local_70;
  undefined7 uStack_6f;
  int local_30;
  undefined8 local_28;
  undefined8 local_20;
  undefined8 *local_18;
  undefined8 local_10;
  
  iStack0000000000000008 = param_1;
  iStack0000000000000018 = param_3;
  uStack0000000000000010 = param_2;
  while (local_80 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  uVar1 = (**(code **)(iStack0000000000000008 + 0x18))(uStack0000000000000010);
  auVar10 = net_textproto_CanonicalMIMEHeaderKey(&DAT_00f10b4b,0xc);
  local_10 = auVar10._0_8_;
  local_18 = (undefined8 *)runtime_newobject(&DAT_00ddc380);
  local_18[1] = 0x10;
  *local_18 = &DAT_00f195fc;
  auVar10 = runtime_mapassign_faststr(&DAT_00e91b20,uVar1,local_10,auVar10._8_8_);
  puVar4 = auVar10._0_8_;
  puVar4[1] = 1;
  puVar4[2] = 1;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,*puVar4);
    *extraout_R11 = local_18;
    extraout_R11[1] = extraout_RCX;
  }
  *puVar4 = local_18;
  uVar1 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar2 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar1,&DAT_00efc947,5);
  if (piVar2[1] == 0) {
    iVar7 = 0;
    uVar1 = 0;
  }
  else {
    iVar7 = ((undefined8 *)*piVar2)[1];
    uVar1 = *(undefined8 *)*piVar2;
  }
  auVar11._8_8_ = iVar7;
  auVar11._0_8_ = uVar1;
  auVar10._8_8_ = iVar7;
  auVar10._0_8_ = uVar1;
  if ((iVar7 == 0) && (auVar10 = auVar11, main_tokenStore != (mv_daemon_provider_TokenStore *)0x0))
  {
    auVar10 = mv_daemon_provider___TokenStore__Get(main_tokenStore,&DAT_00f02951,8);
  }
  if (auVar10._8_8_ == 0) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3daf3,0x2a,0x191);
    return;
  }
  piVar2 = (int *)runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,&DAT_00f02951,8);
  iVar7 = piVar2[1];
  if (extraout_BL == '\0') {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f2d163,0x1d,500);
    return;
  }
  if ((undefined1 *)*piVar2 !=
      go_itab__mv_daemon_provider_Cloud115Provider_mv_daemon_provider_CloudProvider) {
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,&DAT_00f3a315,0x27,500);
    return;
  }
  uVar1 = net_url___URL__Query(*(undefined8 *)(iStack0000000000000018 + 0x10));
  piVar2 = (int *)runtime_mapaccess1_faststr(&DAT_00e9bd40,uVar1,&DAT_00efb5af,4);
  if (piVar2[1] == 0) {
    uVar1 = 0;
    uVar6 = 0;
  }
  else {
    uVar1 = ((undefined8 *)*piVar2)[1];
    uVar6 = *(undefined8 *)*piVar2;
  }
  auVar11 = strconv_Atoi(uVar6,uVar1);
  iVar3 = auVar11._0_8_;
  if ((auVar11._8_8_ != 0) || (iVar3 < 1)) {
    iVar3 = 1;
  }
  mv_daemon_provider___Cloud115Provider__List115OfflineTasks
            (iVar7,iVar3,auVar10._0_8_,auVar10._8_8_);
  if (extraout_RBX != 0) {
    auVar10 = (**(code **)(extraout_RBX + 0x18))(extraout_RCX_00);
    main_writeJsonError(iStack0000000000000008,uStack0000000000000010,auVar10._0_8_,auVar10._8_8_,
                        500);
    return;
  }
  if (mv_daemon_provider_GlobalOfflineCacheStore != (mv_daemon_provider_OfflineCacheStore *)0x0) {
    iVar7 = extraout_RAX[1];
    for (uVar8 = 0; (int)uVar8 < iVar7; uVar8 = uVar8 + 1) {
      if ((uint)extraout_RAX[1] <= uVar8) {
                    /* WARNING: Subroutine does not return */
        runtime_panicBounds();
      }
      local_30 = *extraout_RAX;
      iVar3 = uVar8 * 0xe0;
      auVar10 = strings_TrimSpace(*(undefined8 *)(local_30 + iVar3),
                                  *(undefined8 *)(local_30 + 8 + iVar3));
      if (auVar10._8_8_ == 0) {
        iVar5 = 0;
      }
      else {
        iVar5 = mv_daemon_provider___OfflineCacheStore__Get
                          (mv_daemon_provider_GlobalOfflineCacheStore,auVar10._0_8_,auVar10._8_8_);
      }
      auVar10 = strings_TrimSpace(*(undefined8 *)(local_30 + 0x88 + iVar3),
                                  *(undefined8 *)(local_30 + 0x90 + iVar3));
      if ((iVar5 == 0) && (auVar10._8_8_ != 0)) {
        iVar5 = mv_daemon_provider___OfflineCacheStore__Get
                          (mv_daemon_provider_GlobalOfflineCacheStore,auVar10._0_8_,auVar10._8_8_);
      }
      if (iVar5 != 0) {
        iVar9 = local_30;
        if (*(int *)(iVar5 + 0x48) != 0) {
          uVar1 = *(undefined8 *)(iVar5 + 0x40);
          *(int *)(local_30 + 0xb8 + iVar3) = *(int *)(iVar5 + 0x48);
          if (runtime_writeBarrier._0_4_ != 0) {
            uVar1 = *(undefined8 *)(local_30 + 0xb0 + iVar3);
            runtime_gcWriteBarrier2();
            *extraout_R11_07 = extraout_RSI;
            extraout_R11_07[1] = uVar1;
            iVar5 = extraout_RCX_06;
            uVar1 = extraout_RSI;
            iVar3 = extraout_RDI;
            iVar9 = extraout_R8;
          }
          *(undefined8 *)(iVar9 + 0xb0 + iVar3) = uVar1;
        }
        if (*(int *)(iVar5 + 0x58) != 0) {
          uVar1 = *(undefined8 *)(iVar5 + 0x50);
          *(int *)(iVar9 + 200 + iVar3) = *(int *)(iVar5 + 0x58);
          if (runtime_writeBarrier._0_4_ != 0) {
            uVar1 = *(undefined8 *)(iVar9 + 0xc0 + iVar3);
            runtime_gcWriteBarrier2();
            *extraout_R11_08 = extraout_RCX_07;
            extraout_R11_08[1] = uVar1;
            uVar1 = extraout_RCX_07;
            iVar3 = extraout_RDI_00;
            iVar9 = extraout_R8_00;
          }
          *(undefined8 *)(iVar9 + 0xc0 + iVar3) = uVar1;
        }
      }
    }
  }
  local_90 = 0;
  if (iStack0000000000000008 != 0) {
    uVar8 = (uint)*(dword *)(iStack0000000000000008 + 0x10);
    do {
      iVar7 = (uVar8 & *(uint *)main__typeAssert_56) * 0x10;
      if (*(int *)(main__typeAssert_56 + iVar7 + 8) == *(int *)(iStack0000000000000008 + 8)) {
        local_90 = *(undefined8 *)(main__typeAssert_56 + iVar7 + 0x10);
        goto LAB_00c55af1;
      }
      uVar8 = uVar8 + 1;
    } while (*(int *)(main__typeAssert_56 + iVar7 + 8) != 0);
    local_90 = runtime_typeAssert(&main__typeAssert_56);
  }
LAB_00c55af1:
  uStack_88 = uStack0000000000000010;
  _local_70 = CONCAT71((int7)((uint)in_XMM15_Qa >> 8),1);
  local_20 = runtime_makemap_small();
  puVar4 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00effdf5,7);
  *puVar4 = &DAT_00dd2dc0;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar1 = puVar4[1];
    puVar4 = (undefined8 *)runtime_gcWriteBarrier1();
    *extraout_R11_00 = uVar1;
  }
  puVar4[1] = 0x115e2c8;
  local_28 = runtime_convTslice(*extraout_RAX,extraout_RAX[1],extraout_RAX[2]);
  auVar10 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00efc979,5);
  puVar4 = auVar10._0_8_;
  *puVar4 = &DAT_00dc15e0;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,puVar4[1]);
    *extraout_R11_01 = local_28;
    extraout_R11_01[1] = extraout_RCX_01;
  }
  puVar4[1] = local_28;
  local_28 = runtime_convT64(extraout_RAX[3]);
  auVar10 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00efc97e,5);
  puVar4 = auVar10._0_8_;
  *puVar4 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,puVar4[1]);
    *extraout_R11_02 = local_28;
    extraout_R11_02[1] = extraout_RCX_02;
  }
  puVar4[1] = local_28;
  local_28 = runtime_convT64(extraout_RAX[4]);
  auVar10 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00efb5af,4);
  puVar4 = auVar10._0_8_;
  *puVar4 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,puVar4[1]);
    *extraout_R11_03 = local_28;
    extraout_R11_03[1] = extraout_RCX_03;
  }
  puVar4[1] = local_28;
  local_28 = runtime_convT64(extraout_RAX[5]);
  auVar10 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f0a1cb,10);
  puVar4 = auVar10._0_8_;
  *puVar4 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,puVar4[1]);
    *extraout_R11_04 = local_28;
    extraout_R11_04[1] = extraout_RCX_04;
  }
  puVar4[1] = local_28;
  local_28 = runtime_convT64(extraout_RAX[6]);
  auVar10 = runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00efc983,5);
  puVar4 = auVar10._0_8_;
  *puVar4 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2(puVar4,auVar10._8_8_,puVar4[1]);
    *extraout_R11_05 = local_28;
    extraout_R11_05[1] = extraout_RCX_05;
  }
  puVar4[1] = local_28;
  local_28 = runtime_convT64(extraout_RAX[7]);
  puVar4 = (undefined8 *)runtime_mapassign_faststr(&DAT_00e16300,local_20,&DAT_00f0cdb0,0xb);
  *puVar4 = &DAT_00dd2c00;
  if (runtime_writeBarrier._0_4_ != 0) {
    uVar1 = puVar4[1];
    puVar4 = (undefined8 *)runtime_gcWriteBarrier2();
    *extraout_R11_06 = local_28;
    extraout_R11_06[1] = uVar1;
  }
  puVar4[1] = local_28;
  encoding_json___Encoder__Encode(&local_90,&DAT_00e16300,local_20);
  return;
}

