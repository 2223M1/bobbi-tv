/* Reconstructed pseudocode, not original Go source: mv-daemon/provider.ClearAll115DirCache */

void mv_daemon_provider_ClearAll115DirCache(void)

{
  int unaff_R14;
  
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  internal_sync___HashTrieMap_go_shape_interface____go_shape_interface______Range
            (&mv_daemon_provider_lifeAncestorCache,
             internal_sync__dict_HashTrieMap_interface____interface____,
             &PTR_mv_daemon_provider_ClearAll115DirCache_func1_0112fa50);
  return;
}

