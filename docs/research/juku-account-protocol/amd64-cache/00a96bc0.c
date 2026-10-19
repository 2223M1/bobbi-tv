/* Reconstructed pseudocode, not original Go source: type:.eq.mv-daemon/provider.OfflineCacheStore */

undefined8 type__eq_mv_daemon_provider_OfflineCacheStore(sdword *param_1,sdword *param_2)

{
  undefined8 uVar1;
  int unaff_R14;
  
  while (&stack0x00000000 <= *(undefined1 **)(unaff_R14 + 0x10)) {
    runtime_morestack_noctxt_abi0();
  }
  if ((((*param_2 == *param_1) && (param_2[1] == param_1[1])) &&
      (*(int *)(param_2 + 2) == *(int *)(param_1 + 2))) &&
     (*(int *)(param_2 + 6) == *(int *)(param_1 + 6))) {
    uVar1 = runtime_memequal(*(undefined8 *)(param_1 + 4),*(undefined8 *)(param_2 + 4));
  }
  else {
    uVar1 = 0;
  }
  return uVar1;
}

