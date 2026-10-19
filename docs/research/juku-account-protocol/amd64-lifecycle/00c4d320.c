/* Reconstructed pseudocode, not original Go source: main.handlePlay.func1 */

undefined1  [40] main_handlePlay_func1(void)

{
  int iVar1;
  undefined8 uVar2;
  undefined8 uVar3;
  undefined8 uVar4;
  undefined8 uVar5;
  undefined1 (*extraout_RAX) [24];
  undefined8 extraout_RCX;
  int unaff_RDX;
  int extraout_RBX;
  undefined1 auVar6 [40];
  int unaff_R14;
  undefined1 auVar7 [16];
  undefined8 local_68;
  undefined8 local_60;
  undefined8 local_58;
  undefined8 local_50;
  undefined *local_48;
  undefined8 uStack_40;
  code *local_38;
  undefined *puStack_30;
  undefined8 local_28;
  undefined **ppuStack_20;
  undefined8 local_18;
  undefined8 uStack_10;
  
  while (&local_68 <= *(undefined8 **)(unaff_R14 + 0x10)) {
    runtime_morestack_abi0();
  }
  iVar1 = *(int *)(unaff_RDX + 0x18);
  local_68 = *(undefined8 *)(unaff_RDX + 0x20);
  auVar7 = *(undefined1 (*) [16])(unaff_RDX + 8);
  uVar2 = *(undefined8 *)(unaff_RDX + 0x28);
  uVar3 = *(undefined8 *)(unaff_RDX + 0x30);
  local_50 = *(undefined8 *)(unaff_RDX + 0x38);
  uVar4 = *(undefined8 *)(unaff_RDX + 0x40);
  local_60 = *(undefined8 *)(unaff_RDX + 0x48);
  uVar5 = *(undefined8 *)(unaff_RDX + 0x50);
  if (*(int *)(unaff_RDX + 0x10) == 0) {
    auVar7 = (**(code **)(iVar1 + 0x28))();
    auVar7 = mv_daemon_provider___TokenStore__Get(main_tokenStore,auVar7._0_8_,auVar7._8_8_);
  }
  local_58 = auVar7._0_8_;
  (**(code **)(iVar1 + 0x28))(local_68);
  uStack_40 = runtime_convTstring();
  local_48 = &DAT_00dd29c0;
  local_38 = main_handlePlay_func1_Printf_1;
  local_28 = 0x35;
  puStack_30 = &DAT_00f48bc6;
  local_18 = 1;
  uStack_10 = 1;
  ppuStack_20 = &local_48;
  log___Logger__output(log_std,0,2,&local_38);
  (**(code **)(iVar1 + 0x38))
            (local_68,uVar2,uVar3,local_50,uVar4,local_60,uVar5,local_58,auVar7._8_8_);
  if (extraout_RBX != 0) {
    auVar6._0_16_ = ZEXT816(0);
    auVar6._16_8_ = 0;
    auVar6._24_8_ = extraout_RBX;
    auVar6._32_8_ = extraout_RCX;
    return auVar6;
  }
  local_38 = main_handlePlay_func1_Printf_2;
  local_28 = 0x35;
  puStack_30 = &DAT_00f48bfb;
  log___Logger__output(log_std,0,2);
  return ZEXT2440(*extraout_RAX);
}

