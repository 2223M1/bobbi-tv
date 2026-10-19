/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ClearAll115DirCache.func1 */

undefined8
mv_daemon_provider_ClearAll115DirCache_func1
          (undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4)

{
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 local_38 [7];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    *(undefined8 *)((int)register0x00000008 + 8) = param_1;
    *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
    *(undefined8 *)((int)register0x00000008 + 0x18) = param_3;
    *(undefined8 *)((int)register0x00000008 + 0x20) = param_4;
    in_x30 = 0x5dafc8;
    runtime_morestack_noctxt_abi0();
    param_1 = *(undefined8 *)((int)register0x00000008 + 0x10);
    param_2 = *(undefined8 *)((int)register0x00000008 + 0x18);
    param_3 = *(undefined8 *)((int)register0x00000008 + 0x20);
    param_4 = *(undefined8 *)((int)register0x00000008 + 0x28);
  }
  *(undefined8 *)((int)register0x00000008 + -0x30) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x38) = in_x29;
  *(undefined8 *)((int)register0x00000008 + 8) = param_1;
  *(undefined8 *)((int)register0x00000008 + 0x10) = param_2;
  internal_sync___HashTrieMap_go_shape_interface____go_shape_interface______LoadAndDelete
            (&mv_daemon_provider_lifeAncestorCache,
             internal_sync__dict_HashTrieMap_interface____interface____,param_1,param_2);
  return 1;
}

