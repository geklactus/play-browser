#!/usr/bin/env python3
"""A minimal ISO9660 image (what Play!'s reader looks at) holding SYSTEM.CNF and TEST.ELF."""
import struct, sys
SECTOR = 2048
def both32(v): return struct.pack('<I', v) + struct.pack('>I', v)
def both16(v): return struct.pack('<H', v) + struct.pack('>H', v)
def dirrec(ident, lba, size, flags):
    body = bytes([0]) + both32(lba) + both32(size) + bytes(7) + bytes([flags, 0, 0]) + both16(1) + bytes([len(ident)]) + ident
    if len(ident) % 2 == 0: body += b'\0'
    return bytes([1 + len(body)]) + body
elf = open(sys.argv[1], 'rb').read()
cnf = b"BOOT2 = cdrom0:\\TEST.ELF;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
LBA_LPATH, LBA_MPATH, LBA_ROOT, LBA_CNF, LBA_ELF = 18, 19, 20, 22, 23
elf_sectors = (len(elf) + SECTOR - 1) // SECTOR
total = LBA_ELF + elf_sectors
lpath = bytes([1, 0]) + struct.pack('<I', LBA_ROOT) + struct.pack('<H', 1) + b'\0\0'
mpath = bytes([1, 0]) + struct.pack('>I', LBA_ROOT) + struct.pack('>H', 1) + b'\0\0'
root = dirrec(b'\0', LBA_ROOT, SECTOR, 2) + dirrec(b'\x01', LBA_ROOT, SECTOR, 2) \
     + dirrec(b'SYSTEM.CNF;1', LBA_CNF, len(cnf), 0) + dirrec(b'TEST.ELF;1', LBA_ELF, len(elf), 0)
pvd = bytearray(SECTOR)
pvd[0] = 1; pvd[1:6] = b'CD001'; pvd[6] = 1
pvd[8:40] = b' ' * 32; pvd[40:72] = b'PLAYTEST'.ljust(32)
pvd[80:88] = both32(total)
pvd[120:124] = both16(1); pvd[124:128] = both16(1); pvd[128:132] = both16(SECTOR)
pvd[132:140] = both32(len(lpath) - 2)
pvd[140:144] = struct.pack('<I', LBA_LPATH); pvd[148:152] = struct.pack('>I', LBA_MPATH)
pvd[156:190] = dirrec(b'\0', LBA_ROOT, SECTOR, 2)
term = bytearray(SECTOR); term[0] = 255; term[1:6] = b'CD001'; term[6] = 1
img = bytearray(total * SECTOR)
img[16 * SECTOR:17 * SECTOR] = pvd
img[17 * SECTOR:18 * SECTOR] = term
img[LBA_LPATH * SECTOR:LBA_LPATH * SECTOR + len(lpath)] = lpath
img[LBA_MPATH * SECTOR:LBA_MPATH * SECTOR + len(mpath)] = mpath
img[LBA_ROOT * SECTOR:LBA_ROOT * SECTOR + len(root)] = root
img[LBA_CNF * SECTOR:LBA_CNF * SECTOR + len(cnf)] = cnf
img[LBA_ELF * SECTOR:LBA_ELF * SECTOR + len(elf)] = elf
open(sys.argv[2], 'wb').write(img)
print(f"wrote {sys.argv[2]}: {len(img)} bytes, {total} sectors")
