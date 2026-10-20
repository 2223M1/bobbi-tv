# Aurora boot Logo

`stock-logo.img.gz` is a deterministic gzip of the complete 8 MiB `logo`
partition read from an original Aurora 6S/A4112 on 2026-09-26. The displayed
image is “腾讯极光 / 互联八方”. Uncompressed SHA-256:

`77499f3c323e5697207efd26d612e8ad1821cbb4bb232d00fd6b8ed7d12127dd`

The compressed asset is 80,910 bytes and is verified against that fixed hash
before use. It is a firmware resource, not the user's Android data. The
current test 4 Pro uses the identical resource package; this does not claim
all 4 Pro factory firmware revisions ship identical artwork.

- `codec.py` validates AML_RES! v2 framing, CRC, alignment and resource bounds.
- Custom PNG/JPEG/BMP images use Pillow, are limited to 32 MiB / 24 MP,
  proportionally fitted to 1920×1080 against black, and encoded as bottom-up
  RGB565 BMP with BI_BITFIELDS. Only `bootup` changes; other resources remain.
- The package uses standard-library gzip; decompression is bounded.
- `backend.py` checks Android model A4111/A4112 and supported CE NG21/NO22,
  the actual mmcblk0/logo sysfs/MPT geometry, CID and block-device capacity.
- Only `/dev/logo` is opened for writing. No environment, bootloader, DTB,
  partition table, user data, or persistent service is modified.
- Each prepared task has a compressed original partition, manifest and
  preview in `/storage/.config/aurora-logo/`. Cancelling a prepared task
  removes its temporary files; completed/failed writes retain their backup.
- UI confirmation plus the preview's expected hash is required. eMMC locks
  exclude concurrent install/restore/backup operations. Writes are followed
  by fsync and a full readback. There is no automatic reboot.
- The first screen is shared by Android/CE and is separate from either OS's
  animation. It is changed once, with no startup script required.

Format reference (not vendored/executed):
https://github.com/dangerouslaser/ugoos-am9-pro-coreelec-emmc/blob/main/img-tools/aml-logo-tool.py

Pillow must be available to the CE `/usr/bin/python3` interpreter. A missing
library causes a clear error before any write. Tests cover image conversion
and disk writing on ordinary temporary files; reboot display of a custom
image still needs physical validation on each supported branch.
