/* Reconstructed pseudocode, not original Go source: main.getRealProvider */

undefined1  [16] main_getRealProvider(undefined8 param_1,undefined8 param_2)

{
  uint extraout_x1;
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined1 auVar2 [16];
  undefined1 auVar3 [16];
  undefined8 local_48 [7];
  int local_10 [2];
  int iVar1;
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    in_x30 = 0x75b29c;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
  }
  *(undefined8 *)((int)register0x00000008 + -0x40) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x48) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 8) = param_1;
  auVar2 = strings_TrimSpace();
  iVar1 = auVar2._8_8_;
  if (iVar1 == 0) {
    return ZEXT816(0);
  }
  *(int *)((int)register0x00000008 + -8) = auVar2._0_8_;
  *(int *)((int)register0x00000008 + -0x10) = iVar1;
  runtime_mapaccess2_faststr(&DAT_008edb60,main_providers,auVar2._0_8_,iVar1);
  if ((extraout_x1 & 1) != 0) {
    auVar2._0_8_ = *(undefined8 *)register0x00000008;
    auVar2._8_8_ = *(undefined8 *)((int)register0x00000008 + -8);
    return auVar2;
  }
  auVar2 = strings_ToLower(*(undefined8 *)register0x00000008,
                           *(undefined8 *)((int)register0x00000008 + -8));
  auVar2 = runtime_mapaccess2_faststr(&DAT_008ecae0,main_providerAlias,auVar2._0_8_,auVar2._8_8_);
  if ((auVar2._8_8_ & 1) != 0) {
    return *auVar2._0_8_;
  }
  auVar3._0_8_ = *(undefined8 *)((int)register0x00000008 + 0x10);
  auVar3._8_8_ = *(undefined8 *)((int)register0x00000008 + 8);
  return auVar3;
}

