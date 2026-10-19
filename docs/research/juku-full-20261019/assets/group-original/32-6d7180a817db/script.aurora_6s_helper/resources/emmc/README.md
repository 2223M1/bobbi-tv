# eMMC backend (1.5.5)

The supported UI prepares a private runtime under `/storage/aurora-emmc-jobs/<id>/runtime`, then directly starts and waits for its worker subprocess in a modal foreground dialog. No systemd-run unit or detached background writer is created. The worker is tied to the Kodi parent process with Linux PDEATHSIG. Status/log files remain for diagnosis; stale process identity is detected using PID, start time and boot ID. The lighting service never starts the writer.

## Scope

CoreELEC NO 22.x and experimental NG 21.x, A4111/A4112 determined from original Android properties, known SC2 MPT layout, reviewed stock cfgload text hashes. NG uses its own Generic_cfgload; neither branch uses the other branch’s boot script. The original Android system partitions are retained, but installation/removal reset userdata. This is not encrypted-userdata shrinking.

## Install / remove

1. Validate external boot/storage by device number, eMMC CID/capacity, Android identity, both physical DTB copies, complete MPT/kernel geometry, known boot environment and storage headroom.
2. No automatic full backup is made. Users can explicitly select manual backup before install/remove/restore.
3. Generate the candidate MPT/DTB using bundled ampart on a sparse **regular file**; independently compare all partition fields and all nonpartition DT properties.
4. Installation copies the live external CE without stopping Kodi or other services, using the official cfgload unchanged plus internal rootopt in config.ini. The user is explicitly reminded to stop playback, library synchronization/scanning and scraping. Per user preference, no live-source stability rejection or SQLite-specific online backup is added; this is not an atomic snapshot of running applications. The frozen destination inventory and final target readback are still verified. DTB and dtb.xml are copied together; no HS400 change is made.
5. Revalidate immediately before writing. Create bounded mappings over only the existing userdata range: loops on NO, dm-linear on NG. Verify the backing device/offset/limit (LOOP_GET_STATUS64 or dmsetup table) and BLKGETSIZE64. Format/copy/readback through those mappings; never use stale partition nodes.
6. Reset only the new userdata header (4096 bytes), commit the two DTB slots and MPT with readback checks, then update only cfgloademmc. Android/USB selection remains intact. Removal restores the stock userdata extent and scanner range; it does not restore old applications.
7. No intermediate reboot is required. On success, shut down, remove the external boot medium, then boot the internal system.

### Selectable capacity (1.5.2)

Installation offers Android **userdata** in whole GiB, at least 8 GiB; this excludes the retained Android system partitions. The default is 16 GiB, or the largest fitting smaller value. CE_FLASH stays 1 GiB. CE_STORAGE receives all remaining bytes after the first 28 partitions, CE_FLASH, and two 8 MiB gaps. The order remains ce_system / ce_storage / userdata; no boot-script change is needed. CE_STORAGE must be at least 4 GiB and have room for the source data plus the greater of 2 GiB or 10% headroom. Options are filtered from current data size and revalidated at submit, execution, and after staging before writing.

The selected integer capacity is pinned in request.json and passed with `--android-gib` to the worker's install probe/submit commands. Layout validation reconstructs exact offsets, sizes, names, flags, gaps and end-of-device boundaries from the observed CE size. Legacy fixed-20-GiB layouts and new variable layouts are accepted for removal/backup/restore. Raw restore always restores the backup geometry; it does not apply an installation capacity choice. Removal reconstructs the original full userdata extent. Changing capacity later requires removal/reinstallation and resets Android; this is not online resizing.

## Backup / restore

Backup inventory is exactly mmcblk0.img, mmcblk0boot0.img, mmcblk0boot1.img plus manifest/probes. Raw images do not contain RPMB, eFuses or hardware configuration. Restore requires full SHA256 verification and a matching recorded CID, Android model and capacity; does not back up the current state automatically. It unmounts Android and removes only eMMC-backed DM mappings before writing. boot-area force_ro is restored after each write; unchanged boot areas are skipped. Every written image is independently read back.

Restore performs one full pre-write SHA256 pass over each of the three source images, followed by the copy and one target readback pass. All source images must pass before unmounting Android or writing any target. Verified source descriptors stay open through the operation; file identity, size and modification timestamps are rechecked, and a streaming hash while copying detects source-content changes without another source read pass. This is not a filesystem snapshot; modifying backup files during restore remains unsupported. Metadata and the destination identity are rechecked after the potentially long initial verification. The worker no longer repeats full hashing.

Progress distinguishes `verifying`, `restoring` and `readback`, showing per-image bytes about every ten seconds. The foreground dialog sums planned copy/hash/readback passes into processed/total bytes (not physical disk throughput), caps percentage at 99 until all finalization succeeds, and counts only the small written metadata regions for removal. Metadata checks and filesystem formatting have no invented byte progress. Backup and restore count their two and three main passes respectively. Installation totals are refined from the frozen inventory; excluded backup/job/staging trees are not migrated. Cancellation is cooperative and accepted only before a target write; the frontend remains attached after writes start. `device_writes_started` becomes true immediately before the first target write, not before source verification; pre-write failures remain `failed`, whereas failures once writing may have begun require recovery. These are same-device raw backups, not USB-burning images and not a guarantee about hardware-bound encryption keys.

Old research backups without recorded CID are refused unless an audited legacy identity supplement is present. The supplement pins hashes of all three original JSON records and a historical layout ticket linking the backup, original MPT and CID. It does not modify the acquisition records, automatically trust the currently connected device, or bypass full image hash checks. This is provenance checking, not a cryptographic signature. Arbitrary/corrupt MPT layouts are currently refused by preflight; interruption of the metadata write may require manual recovery using a previously created manual full backup or a tested factory USB image. No automatic partial-table repair or metadata-only rollback is attempted after userdata has been overwritten. Failed jobs never automatically replay on reboot.

Before unmounting Android for restore, stop the previously active `opentee_linuxdriver.service`, whose tee-supplicant/linker maps Android system/vendor files. Re-enumerate mounts after its ExecStop cleanup. If anything fails before a target write, restart that service through CoreELEC’s loader so its mappings and mounts are recreated. Do not start a previously inactive service. Once writing has begun, leave the service stopped until reboot to avoid loading Android through stale partition mappings. The service is never disabled for future boots.

## Validation boundary

- Unit tests cover identity, unsupported geometry, consent, internal-boot rejection, scan environment transformations, write bounds, corrupt/truncated backup refusal, transfer/readback and repeated-job rejection.
- Real box read-only inspection recognizes the current A4111 and internal CE, and verifies a read-only bounded loop against the raw eMMC offset.
- Native aarch64 ampart simulation: current 31 partitions -> stock 29 -> target 31; independently checked.
- Native temporary-file loop rehearsal: ext4 format, mount, copy/readback and outside-range guard bytes passed. No real eMMC write during these integration tests.
- The add-on removal was device-tested on A4111: stock 29-partition MPT and physical DTB copies verified, first 28 partition geometries unchanged. Android first boot after removal remains a separate check. The 1.5.1 foreground version was deployed; the previously running private 1.4.5 restore completed with target readback verified. The 1.5.2 capacity version has passed 55 local tests but has not been deployed. Local sparse-file ampart simulations using captured A4111 metadata verified install and removal for Android userdata sizes 8, 16, 32 and 50 GiB; MPT/DTB geometry and nonpartition DT properties passed independent checks. These simulations used a native build of the bundled ampart source and did not write a physical device. The previous 1.4.5 restore pipeline passed 39 local tests. A no-write device rehearsal successfully stopped the Android-backed TEE service, unmounted Android, released eMMC DM mappings, and restored the service/mounts on a simulated pre-write failure; physical MPT/DTB hashes were unchanged. The new foreground flow and variable-capacity installation still require end-to-end device testing. Existing phased 4 Pro installation and Android/CE boots were previously tested. No claim of new A4112 install testing.

## Sources

Project backend adapted from CE_android/tools. ampart source and build files are bundled under vendor/ampart (GPL-3.0), alongside bin/ampart, LICENSE.ampart and provenance.json; source commit 1539ff2f6fa73ef78dfde3ac585fb9c93244e85e: https://github.com/7Ji/ampart . Static aarch64 executable is the previously CE-tested build; build provenance is recorded in provenance.json. Its only execution target is a fresh simulation image.

AM9 comparison: https://github.com/dangerouslaser/ugoos-am9-pro-coreelec-emmc/blob/581ca4f7a441461b957d814cc9beb1a1cca6cfe5/ce-emmc-install.sh#L361-L393 . That installer tries partprobe and constructs nodes from sysfs; it can still require reboot if the kernel does not register them. This backend uses bounded mappings and retains MPT instead of copying its GPT/MPT-clearing strategy.

Main user-area force_ro does not imply a hardware boot partition. Only mmcblk0boot0/1 receive the small pre-write content comparison for skip-unchanged handling; mmcblk0 never receives an extra full-target comparison. This fixes the 1.4.5 silent preparing-stage delay on the vendor kernel.

## NG 21.x adaptation (1.5.3)

Release aliases (DISTRO_DEVICE, COREELEC_DEVICE and architecture fields) must agree; NG 21.x / NO 22.x are accepted. On NG without Android mounts, the probe validates super against live MPT/sysfs, verifies the LP geometry/header/table SHA-256 checksums, and requires an unambiguous vendor partition on one super device. It creates a temporary read-only dm-linear mapping of its bounded linear extents and mounts ext4 with ro,noload to read vendor build.prop. The mount and mapping are removed after each probe. Unknown/disabled/multiple vendor layouts are refused; no manual model override is used. LP layout reference: https://github.com/tchebb/parse-android-dynparts/blob/master/liblp/include/liblp/metadata_format.h (AOSP liblp format).

The block-size ioctl uses the actual userspace pointer size: NG arm userspace requires 0x80041272 even though its kernel is ARM64; NO aarch64 uses 0x80081272. The existing static aarch64 ampart was verified executable on the NG kernel. Only pure memory zram is allowed to remain as swap; disk swaps and zram with backing storage remain blocked. No kernel, firmware or Wi-Fi service changes accompany this adaptation.

62 local tests passed. On NG 21.3 / 4.9.269, original A4111 identity, current dual layout, remove preflight, read-only bounded loop and actual ampart regular-file metadata simulation passed. Temporary identity mappings were removed. No eMMC writes or automatic removal/installation were performed. Full NG internal installation/boot and restore still require user testing. The installed firmware's NG cfgload text SHA-256 is 5bbb58b16e3c41081fb1b3e2abd9ddfdf0d8b0e4116e985e0500013028c39dc8; config.ini import follows default rootopt and precedes bootargs construction. update.sh preserves existing config.ini.

## NG partition-view loss fix (1.5.4)

During the first NG removal, the requested 4 KiB header reset completed but the subsequent probe failed because the kernel MPT partition nodes had disappeared. Raw MPT/DTB still matched the original saved bytes. A reboot restored the nodes. dm-linear write/readback of the already-zeroed header preserved all 31 nodes, but later raw metadata writing also led to missing /dev/env. Therefore the fix does not assume loop replacement alone solves every case; the underlying kernel invalidation trigger has not been fully isolated.

NG formatting/header operations now use verified bounded dm-linear mappings. NG's post-write metadata checkpoint reads CID/capacity, validates the whole block device and unchanged external mounts, rejects remaining mappings, and retains write_regions' exact expected-before and readback checks, without re-reading Android through disappearing partition nodes. The final environment operation uses a bounded mapping over the independently validated, unchanged 8 MiB env partition and a private fw_env.config matching the reviewed 64 KiB Amlogic format. All tracked environment keys are compared before/after; only cfgloademmc may change. Temporary mapper removal uses --retry for transient udev opens. NO's loop and normal environment access remain supported.

The interrupted user-requested removal was completed after matching its CID, original/candidate metadata and saved environment: the final physical MPT/DTB contain the stock 29-partition layout, first 28 boundaries are unchanged, and the Android scanner setting passed readback. The original failure status is retained as recovery-original-status.json with a separate recovery-result.json. No full restore or NG installation was initiated. 67 local tests passed; fresh full NG installation remains untested.

## rsync without xattrs/ACLs (1.5.5)

The NG install attempt f01989ed92464c84ac1deffcb706e062 failed during snapshot capability checking with “Source has extended attributes but rsync cannot preserve them”. Its status was failed/device_writes_started=false; no eMMC installation writes had begun.

The copy pipeline now allows rsync builds without -A/-X and separately preserves extended attributes (including POSIX ACL xattrs) through Python's no-follow xattr APIs. It walks only copied destination objects, so excluded backup/log/staging trees remain excluded; it also handles root-directory attributes. Extra destination attributes are removed, source values copied and immediately read back. The frozen manifest records per-object attributes and root attributes, and validates them again after final filesystem remount/readback. Legacy manifests without the new marker retain their original validation semantics. Errors preserving attributes still stop the operation; metadata is not silently discarded. Source stability behavior remains the previously agreed live-copy behavior.

70 local tests passed, including actual rsync without -A/-X followed by xattr copy, root/directory/hardlink attributes, stale attribute removal, exclusion preservation and detection of attribute-only modifications. After the user rebooted the stalled box, actual NG live snapshot validation passed. A second device rehearsal formatted temporary regular-file FAT/ext4 images, copied the current CE, remounted read-only and verified 10 boot files and 1,989 storage entries including extended attributes. eMMC was not written. The actual observed attribute was user.crtime_usec.

### Separate platform backends

`no_backend.py` owns NO loop mapping, live partition-view checkpoint and native CE environment access. `ng_backend.py` owns NG dm-linear mapping, whole-device post-write identity checks and bounded env access. The common operations module dispatches through a validated release identity. UI, explicit consent, size planning, fixed-system-partition validation, metadata generation/readback, raw backup/restore and file-copy verification remain shared to avoid diverging protection rules. Compatibility wrappers remain for recorded recovery scripts; they delegate to NG implementations. Both backends are included in the 1.5.5 package.


## OTA layout recovery (1.5.13, NO 22.x only)

The explicit `repair` action uses `ota_repair.py` / `ota_repair_core.py`, adapted from standalone 0.1.2, validated on an A4111 box through internal CE and Android boot. It reconstructs the known helper layout from live CE FAT32/ext4 headers, without consulting installation records. Preview rejects NG, healthy dual layouts, missing filesystems, unknown geometry or boot scripts. Full read-only filesystem and boot payload checks run in the foreground worker; no snapshot copy, formatting, userdata reset, environment update, full backup or automatic reboot is invoked.

Only the Android DTB pair and MPT are written. All environment variables and misc remain unchanged; full env/misc hashes are checked before/after. Small original metadata artifacts and a schema-2 layout-only plan are retained in the job's `layout-repair` subdirectory. Existing worker locks and lifecycle apply, cancellation is allowed only before the first write, and interrupted writes require manual recovery review. Old standalone plans cannot be submitted via the UI. Reboot to external CE before any further disk operation, then separately test internal CE and Android. This does not establish Android OTA compatibility.

The UI displays filesystem check phases without invented byte progress; boot-file hashing and metadata write/readback have byte accounting. The standalone hardware validation does not replace end-to-end testing of the integrated plugin flow.


## Slot-independent boot/layout repair (1.6.13)

Only `probe --action repair` uses identity-only reads of both vendor metadata slots.
Each usable vendor must pass existing LP checksums, bounds and ext4-size checks;
readable model properties must agree on A4111 or A4112. A structurally invalid or
unreadable vendor is recorded, never enlarged; conflicting/unknown models and
mapping-cleanup failures stop the operation. This does not select Android's boot
slot. Install, remove, backup and restore retain their existing identity path.

The combined NG/NO repair records misc (including pending BCB and Virtual A/B) as
opaque state to preserve. It does not require an idle Android OTA or overwrite
active_slot, boot_part, recovery_part, misc or userdata. Warnings are shown before
confirmation. Full read-only CE filesystem/payload checks still precede writes.
The strict legacy layout-only entry point retains its earlier slot checks; only
the explicit combined repair context enables this preservation policy.

NG accesses the unchanged env range through a bounded raw dm-linear mapping,
read-only for reads, so post-write partition-node invalidation does not require a
reboot before checking/updating cfgloademmc. NO retains named env access. Both
paths compare the entire decoded environment; cfgloademmc is the only permitted
changed key. Raw DTB/MPT and full misc are checked after the write. Original
DTB/MPT/env/misc are saved in the external job, without making a full backup.
Reboot to external CE to verify layout, then test internal CE before Android.
Pending Android recovery may still request a wipe; this repair does not authorize
that action or guarantee Android can finish its OTA.


## Guarded pending OTA target retry (1.6.14)

The combined repair action now calls `ota_resume.py`. Its pure parsers in
`ota_resume_core.py` validate Android 11 protobuf records, LP geometry/header/table
checksums and extents, source/target agreement, A/B CRC and a successful source.
`ota_snapshot.py` reads Linux persistent snapshot v1 exception tables in userspace;
no kernel snapshot target or userdata mount/decryption is used. Only full coverage
(no fallback to old origin blocks) for the five known dynamic partitions qualifies.
All virtual bytes are read in the foreground before any repair write. Their hashes
are change/evidence fingerprints, not an assertion of official image authenticity.

The tested default Amlogic records (source successful 7/7; target unverified 7/7)
can be promoted to target priority 15 / tries 6 / unsuccessful. The source record,
recorded suffix, Virtual A/B message and snapshot state are preserved. Unknown or
already-attempted target states are not replenished. This supports either direction
when all evidence agrees; hardware validation so far is A-to-B on A4111/NG.
Only the exact known init_user0_failed BCB command is clearable; other requests
remain untouched. Writes cover the command sector and/or A/B sector with unchanged
surrounding bytes, fsync and full 2 MiB misc readback. No success bit is forged.

If geometry needs recovery, the first invocation only restores DTB/MPT/scanner and
clears the eligible BCB command. The kernel partition view must match the repaired
layout after reboot to external CE before a new invocation can activate the target.
UI confirmation is bound by a digest to the submitted plan. Existing pinned runtime,
boot-ID checks, task locks, rereads and cancellation rules remain in force. No new
service or automatic reboot is installed. Other repair cases retain the original
preserve-only policy. Install/remove/backup/restore paths do not call OTA retry.

Original metadata is retained privately in the external job's `ota-resume` folder.
It is not sufficient to undo a subsequent Android snapshot merge. NO uses the same
validated on-disk formats and raw byte writes as NG, with the preexisting branch
specific environment mapping. NO recovery has now been hardware tested on A4111: UI repair, target B boot,
MergeCompleted, and a subsequent internal CE boot all passed.


## Completed repair instructions (1.6.17)

When the Android target is already marked successful, no second activation step is
needed: shut down, remove external USB/SD, and verify internal CE boots normally
without pressing AV reset. Then use CE's internal-storage boot action to start
Android and finish snapshot merging. Ordinary completed boot/layout repairs use
the same internal CE boot check. A layout-first repair with an unconfirmed target
still requires rebooting external CE and a second guarded invocation.


## FAT32 filename migration (1.8.1)

The source FAT may be mounted with `iocharset=iso8859-1`. Chinese long filenames
then appear as literal question marks, causing rsync EINVAL on the target. Setting
UTF-8 on the destination alone cannot recover names already lost at the source.
`fat_boot.boot_source` creates an independent read-only loop-backed UTF-8 mount
for source inventory, staging and source revalidation; it checks the source block
identity and read-only state and leaves the live `/flash` mount unchanged.
Both target copy and target readback mount vfat with `utf8=1`. ext4 is unchanged.
Preflight checks FAT-invalid names, UTF-16 component length and case collisions.
The existing device_trees/aml_autoscript exclusions and config.ini/cfgload handling
are unchanged. New jobs freeze the shared module with the other runtime files;
existing failed jobs are not rewritten or automatically retried.

Validation: 241 local tests passed with 4 skips. On 192.168.50.80 running NO
22.0-Piers_nightly_20260924, disposable FAT32/ext4 loop images reproduced default
question-mark names and passed production staging, source revalidation, copy and
readback with Chinese filenames/directories and ext4 content. The real `/flash`
read-only UTF-8 view was also checked; its original mount stayed unchanged.
No physical eMMC format/write was performed. This run did not repeat on NG.


## Persisted normal boot environment (1.8.2)

NG identity probing previously required `active_slot=_a/_b`, and install/remove
also rejected `normal` even though the supported vendor storeboot resolves the
slot through `get_valid_slot` at boot. For the exact persisted value `normal`,
NG now reads both bounded, read-only vendor identities using the same identity
checks as repair. One unreadable slot may be ignored only if the readable model
is unambiguously A4111/A4112; conflicting/unknown models and mapping cleanup
failures stop the operation. Explicit `_a/_b` still reads only that slot and does
not fall back. Unknown/missing environment values remain refused. The normal
probe stores this evidence in `android_identity`; repair keeps `repair_identity`.

Install/remove accept `normal` with the existing boot-script checks. They still
write only cfgloademmc in the environment, preserve active_slot, and do not copy
misc's recorded suffix into an environment variable or choose an Android slot.
Partition, model, external-boot and write-boundary validation remain in force.

The supplied A4111/NG report has a stock 29-partition layout, verified B vendor,
B marked successful, idle Virtual A/B status and no pending boot message. Its A
vendor mapping is shorter than the ext4 filesystem and is not expanded. Local
regressions cover this identity case, ambiguous identities, cleanup failures,
unknown slots, and install/remove environment write/readback preservation.

### 1.8.3：硬件修复兼容 normal

硬件修复的原厂机型读取入口复用同一套只读识别：`active_slot=normal` 时分别检查 A/B vendor，要求可读取的原厂机型唯一；明确为 `_a`/`_b` 时只读取指定槽。不会修改环境变量或选择 Android 启动槽。已有 Android 属性可直接读取时，仍优先使用这些属性。

### 1.8.4：保留内核文件名大小写

安装时忽略 `kernel.img` 的大小写识别必需内核文件；复制、清单和读回验证保留源文件实际名称（例如 `KERNEL.img`），不把 `KERNELce.img` 当成标准内核。源目录及清单中的大小写冲突仍拒绝。缺少启动文件时明确列出缺少的名称。`config.ini`、`cfgload` 的特殊处理及其他复制规则不变。

### 2026-10-04：兼容蓝牙唤醒配置的运行时挂载

安装预检、storage 暂存和复制预演共用嵌套挂载检查。仅允许已验证的
`/storage/.config/aurora6s-wake/rtl8852bs_config.wake` 到
`/storage/.config/firmware/rtlbt/rtl8852bs_config` 的同文件系统普通文件绑定：
检查挂载来源、文件身份和心跳配置哈希，不按文件名直接放行。

有此挂载时，通过 `/run` 下非递归、私有、只读的 storage 绑定视图复制底层文件，
并验证基础配置哈希。保留基础配置（0x18），同时迁移唤醒服务和独立心跳配置（0x1a），
由新系统启动时重新建立覆盖。不会卸载当前蓝牙配置、停止心跳或重置控制器。
视图在正常完成或异常退出时卸载；卸载失败会报错并停止流程。
其他嵌套挂载仍拒绝，后端日志和中文提示均显示解码后的具体路径。
