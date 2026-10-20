/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.(*Cloud115Provider).Check115FileExists */

undefined1  [24]
mv_daemon_provider___Cloud115Provider__Check115FileExists
          (undefined8 param_1,undefined8 param_2,int param_3,undefined8 param_4,int param_5,
          undefined8 param_6,int param_7,undefined8 param_8,undefined8 param_9)

{
  undefined1 auVar1 [24];
  int iVar2;
  undefined8 *puVar3;
  int extraout_RCX;
  undefined1 auVar4 [24];
  undefined1 auVar5 [24];
  undefined1 auVar6 [24];
  undefined1 auVar7 [24];
  undefined1 auVar8 [24];
  undefined8 uVar9;
  undefined8 uVar10;
  undefined8 extraout_RDI;
  undefined8 extraout_R11;
  int unaff_R14;
  bool bVar11;
  undefined1 auVar12 [16];
  undefined8 uStack0000000000000010;
  undefined8 uStack0000000000000020;
  undefined8 uStack0000000000000030;
  
  uStack0000000000000010 = param_2;
  uStack0000000000000020 = param_4;
  uStack0000000000000030 = param_6;
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
    param_9 = extraout_R11;
  }
  if (param_7 == 0) {
    puVar3 = (undefined8 *)runtime_newobject(&DAT_00e21740);
    puVar3[1] = 0xd;
    *puVar3 = &DAT_00f13592;
    auVar8._0_16_ = ZEXT816(0x1139800) << 0x40;
    auVar8._16_8_ = puVar3;
    return auVar8;
  }
  uVar10 = uStack0000000000000020;
  if (param_5 == 0) {
    uVar10 = uStack0000000000000010;
    param_5 = param_3;
  }
  if (param_5 == 0) {
    puVar3 = (undefined8 *)runtime_newobject(&DAT_00e21740);
    puVar3[1] = 0x18;
    *puVar3 = &DAT_00f26bfa;
    auVar7._0_16_ = ZEXT816(0x1139800) << 0x40;
    auVar7._16_8_ = puVar3;
    return auVar7;
  }
  mv_daemon_provider_get115ChromeDownurl
            (uVar10,param_5,0,0,0,0,uStack0000000000000030,param_7,param_9,&DAT_00f62b17,0x72);
  if (extraout_RCX == 0) {
    auVar6._0_16_ = ZEXT816(1);
    auVar6._16_8_ = 0;
    return auVar6;
  }
  (**(code **)(extraout_RCX + 0x18))(extraout_RDI);
  auVar12 = strings_ToLower();
  uVar9 = auVar12._8_8_;
  uVar10 = auVar12._0_8_;
  iVar2 = internal_stringslite_Index(uVar10,uVar9,&DAT_00f05aaa,9);
  if (iVar2 < 0) {
    iVar2 = internal_stringslite_Index(uVar10,uVar9,&DAT_00f05f7b,9);
    if (iVar2 < 0) {
      iVar2 = internal_stringslite_Index(uVar10,uVar9,&DAT_00f05ebe,9);
      bVar11 = -1 < iVar2;
    }
    else {
      bVar11 = true;
    }
  }
  else {
    bVar11 = true;
  }
  if ((!bVar11) && (iVar2 = internal_stringslite_Index(uVar10,uVar9,&DAT_00efacdb,3), iVar2 < 0)) {
    auVar12 = mv_daemon_provider___Cloud115Provider__ListUserFiles
                        (param_1,uStack0000000000000010,param_3,uStack0000000000000030,param_7);
    if ((auVar12._8_8_ == 0) && (auVar12._0_8_ != 0)) {
      auVar5._0_16_ = ZEXT816(1);
      auVar5._16_8_ = 0;
      return auVar5;
    }
    auVar1._8_8_ = extraout_RDI;
    auVar1._0_8_ = extraout_RCX;
    auVar1._16_8_ = 0;
    return auVar1 << 0x40;
  }
  auVar4._0_16_ = ZEXT816(0);
  auVar4._16_8_ = 0;
  return auVar4;
}

