/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ClearAll115DirCache.func1 */

undefined8 mv_daemon_provider_ClearAll115DirCache_func1(undefined8 param_1,undefined8 param_2)

{
  int unaff_R14;
  undefined8 uStack0000000000000008;
  undefined8 uStack0000000000000010;
  
  uStack0000000000000008 = param_1;
  uStack0000000000000010 = param_2;
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  internal_sync___HashTrieMap_go_shape_interface____go_shape_interface______LoadAndDelete
            (&mv_daemon_provider_lifeAncestorCache,
             internal_sync__dict_HashTrieMap_interface____interface____,uStack0000000000000008,
             uStack0000000000000010);
  return 1;
}

