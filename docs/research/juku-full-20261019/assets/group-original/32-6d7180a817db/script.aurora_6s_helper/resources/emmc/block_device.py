"""Linux block ioctl ABI follows userspace word size, not kernel bitness."""
import struct

# BLKGETSIZE64 is _IOR(0x12, 114, size_t); returned capacity is always uint64.
# NG has 32-bit Python on an ARM64 kernel; NO has 64-bit Python.
BLKGETSIZE64 = 0x80001272 | (struct.calcsize('P') << 16)
