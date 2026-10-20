/* Reconstructed pseudocode, not original Go source: main.handleQrCode.Printf.func1 */

void main_handleQrCode_Printf_func1(undefined8 param_1,undefined8 param_2,undefined8 param_3)

{
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 local_58 [11];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    in_x30 = 0x75c388;
    runtime_morestack_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
  }
  *(undefined8 *)((int)register0x00000008 + -0x50) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x58) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 8) = param_1;
  fmt_Appendf();
  return;
}

