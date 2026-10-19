/* Reconstructed pseudocode, not original Go source: main.getRealProvider */

undefined1  [16] main_getRealProvider(undefined8 param_1)

{
  undefined1 (*pauVar1) [16];
  char extraout_BL;
  char extraout_BL_00;
  int iVar2;
  int unaff_R14;
  undefined1 auVar3 [16];
  undefined1 auVar4 [16];
  undefined8 uStack0000000000000008;
  
  uStack0000000000000008 = param_1;
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  auVar3 = strings_TrimSpace();
  iVar2 = auVar3._8_8_;
  if (iVar2 == 0) {
    return ZEXT816(0);
  }
  runtime_mapaccess2_faststr(&DAT_00e17280,main_providers,auVar3._0_8_,iVar2);
  if (extraout_BL != '\0') {
    return auVar3;
  }
  auVar4 = strings_ToLower(auVar3._0_8_,iVar2);
  pauVar1 = (undefined1 (*) [16])
            runtime_mapaccess2_faststr(&DAT_00e16200,main_providerAlias,auVar4._0_8_,auVar4._8_8_);
  if (extraout_BL_00 != '\0') {
    return *pauVar1;
  }
  return auVar3;
}

