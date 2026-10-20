/* Reconstructed pseudocode, not original Go source: main.handleUserPlay.func1 */

undefined1  [40] main_handleUserPlay_func1(void)

{
  int iVar1;
  undefined8 uVar2;
  undefined8 uVar3;
  undefined8 uVar4;
  undefined8 uVar5;
  undefined8 uVar6;
  undefined1 (*extraout_RAX) [24];
  undefined8 extraout_RCX;
  int unaff_RDX;
  int extraout_RBX;
  undefined1 auVar7 [40];
  int unaff_R14;
  undefined1 auVar8 [16];
  
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_abi0();
  }
  iVar1 = *(int *)(unaff_RDX + 0x18);
  uVar2 = *(undefined8 *)(unaff_RDX + 0x20);
  uVar3 = *(undefined8 *)(unaff_RDX + 0x28);
  uVar4 = *(undefined8 *)(unaff_RDX + 0x30);
  uVar5 = *(undefined8 *)(unaff_RDX + 0x38);
  uVar6 = *(undefined8 *)(unaff_RDX + 0x40);
  auVar8 = *(undefined1 (*) [16])(unaff_RDX + 8);
  if ((*(int *)(unaff_RDX + 0x10) == 0) &&
     (auVar8 = *(undefined1 (*) [16])(unaff_RDX + 8),
     main_tokenStore != (mv_daemon_provider_TokenStore *)0x0)) {
    auVar8 = (**(code **)(iVar1 + 0x28))();
    auVar8 = mv_daemon_provider___TokenStore__Get(main_tokenStore,auVar8._0_8_,auVar8._8_8_);
  }
  (**(code **)(iVar1 + 0x40))(uVar2,uVar3,uVar4,auVar8._0_8_,auVar8._8_8_,uVar5,uVar6);
  if (extraout_RBX != 0) {
    auVar7._0_16_ = ZEXT816(0);
    auVar7._16_8_ = 0;
    auVar7._24_8_ = extraout_RBX;
    auVar7._32_8_ = extraout_RCX;
    return auVar7;
  }
  return ZEXT2440(*extraout_RAX);
}

