/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ClearAll115DirCache */

void mv_daemon_provider_ClearAll115DirCache(void)

{
  int in_x28;
  undefined8 in_x29;
  undefined8 in_x30;
  undefined8 local_38 [7];
  
  for (; register0x00000008 <= *(undefined1 **)(in_x28 + 0x10);
      register0x00000008 = (BADSPACEBASE *)((int)register0x00000008 + 8)) {
    in_x30 = 0x570b6c;
    runtime_morestack_noctxt_abi0();
  }
  *(undefined8 *)((int)register0x00000008 + -0x30) = in_x30;
  *(undefined8 *)((int)register0x00000008 + -0x38) = in_x29;
  internal_sync___HashTrieMap_go_shape_interface____go_shape_interface______Range
            (&mv_daemon_provider_lifeAncestorCache,
             internal_sync__dict_HashTrieMap_interface____interface____,
             &PTR_mv_daemon_provider_ClearAll115DirCache_func1_00c06e70);
  return;
}

