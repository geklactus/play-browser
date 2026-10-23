#!/usr/bin/env python3
"""Builds a PS2 ELF that draws a test picture through the GS, for checking Play!'s renderer.

Picture (640x448, 32-bit frame buffer at GS address 0):
  - dark grey background
  - red / green / blue untextured sprites along the top
  - a 256x256 32-bit texture (exactly 256 KB uploaded) with four quadrant colours
  - a 128x128 8-bit CLUT texture
  - a sprite textured from an offscreen framebuffer read as PSMT8H (index = alpha channel),
    through a CLUT in which the index Play! would read from alpha is green, the index it would
    read from red (the WebGL bug) is red
"""
import struct, sys

BASE = 0x00100000

# ---------- GS register numbers (A+D) ----------
PRIM=0x00; RGBAQ=0x01; UV=0x03; XYZ2=0x05; TEX0_1=0x06; TEX1_1=0x14; XYOFFSET_1=0x18; PRMODECONT=0x1A
TEXA=0x3B; TEXFLUSH=0x3F; SCISSOR_1=0x40; DTHE=0x45; COLCLAMP=0x46; TEST_1=0x47; FRAME_1=0x4C; ZBUF_1=0x4E
BITBLTBUF=0x50; TRXPOS=0x51; TRXREG=0x52; TRXDIR=0x53; FINISH=0x61
PSMCT32=0; PSMT8=0x13; PSMT8H=0x1B

# ---------- GS memory layout (bytes) ----------
FB_DISP   = 0x000000   # 640x448x4
ZB        = 0x118000
FB_OFFS   = 0x230000   # offscreen 640-wide 32-bit buffer (page 280)
TEX32     = 0x280000   # 256x256x32
CLUT_8H   = 0x2C0000
TEX8      = 0x2D0000   # 128x128x8
CLUT_8    = 0x2E0000
assert FB_OFFS % 8192 == 0 and ZB % 8192 == 0

def qw(lo, hi): return struct.pack('<QQ', lo & 0xFFFFFFFFFFFFFFFF, hi & 0xFFFFFFFFFFFFFFFF)
def ad(reg, val): return qw(val, reg)
def giftag_ad(nloop, eop): return qw(nloop | (eop << 15) | (1 << 60), 0xE)          # PACKED, NREG=1, A+D
def giftag_image(nloop, eop): return qw(nloop | (eop << 15) | (2 << 58), 0)        # IMAGE
def ad_block(regs, eop=0):
    return giftag_ad(len(regs), eop) + b''.join(ad(r, v) for r, v in regs)

def rgbaq(r, g, b, a, q=1.0): return r | (g << 8) | (b << 16) | (a << 24) | (struct.unpack('<I', struct.pack('<f', q))[0] << 32)
def xyz(x, y, z=0): return ((x * 16) & 0xFFFF) | (((y * 16) & 0xFFFF) << 16) | (z << 32)
def uv(u, v): return ((u * 16) & 0x3FFF) | (((v * 16) & 0x3FFF) << 16)
def tex0(tbp, tbw_px, psm, w_log, h_log, tfx=1, cbp=0, cpsm=0, cld=0):
    return ((tbp // 256) | ((tbw_px // 64) << 14) | (psm << 20) | (w_log << 26) | (h_log << 30) | (1 << 34) | (tfx << 35)
            | ((cbp // 256) << 37) | (cpsm << 51) | (cld << 61))
def frame(fbp_bytes, fbw_px, psm=PSMCT32): return (fbp_bytes // 8192) | ((fbw_px // 64) << 16) | (psm << 24)
def bitbltbuf(dbp_bytes, dbw_px, dpsm): return ((dbp_bytes // 256) << 32) | ((dbw_px // 64) << 48) | (dpsm << 56)
def trxreg(w, h): return w | (h << 32)

def upload(dst, dbw_px, dpsm, w, h, data):
    assert len(data) % 16 == 0 and len(data) // 16 <= 32767
    return (ad_block([(BITBLTBUF, bitbltbuf(dst, dbw_px, dpsm)), (TRXPOS, 0), (TRXREG, trxreg(w, h)), (TRXDIR, 0)])
            + giftag_image(len(data) // 16, 0) + data)

def sprite(x0, y0, x1, y1, textured=False, u0=0, v0=0, u1=0, v1=0):
    regs = []
    if textured:
        regs += [(UV, uv(u0, v0)), (XYZ2, xyz(x0, y0)), (UV, uv(u1, v1)), (XYZ2, xyz(x1, y1))]
    else:
        regs += [(XYZ2, xyz(x0, y0)), (XYZ2, xyz(x1, y1))]
    return regs

# CSM1 CLUT storage for 8-bit textures: the 256 entries live in a 16x16 32-bit image in which
# bits 3 and 4 of the index are swapped.
def csm1_pos(i): return (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)
def make_clut(color_of_index):
    buf = bytearray(256 * 4)
    for i in range(256):
        r, g, b, a = color_of_index(i)
        struct.pack_into('<BBBB', buf, csm1_pos(i) * 4, r, g, b, a)
    return bytes(buf)

# ---------- texture contents ----------
tex32 = bytearray()
for y in range(256):
    for x in range(256):
        if y < 128: c = (0x20, 0x40, 0xFF, 0x80) if x < 128 else (0xFF, 0xFF, 0x00, 0x80)
        else:       c = (0x00, 0xFF, 0xFF, 0x80) if x < 128 else (0xFF, 0x00, 0xFF, 0x80)
        tex32 += bytes(c)
assert len(tex32) == 256 * 1024

tex8 = bytearray()
for y in range(128):
    for x in range(128):
        tex8.append((x // 16) + 8 * (y // 16))          # 64 distinct indices, 16x16 cells
clut8 = make_clut(lambda i: (((i * 37) & 0xFF), ((i * 91) & 0xFF), ((i * 53) & 0xFF), 0x80) if i < 64 else (0, 0, 0, 0x80))

def clut8h_color(i):
    if i == 0x40: return (0x00, 0xFF, 0x00, 0x80)   # alpha 0x20 written, stored doubled by Play!'s shader
    if i == 0x20: return (0x00, 0x00, 0xFF, 0x80)   # alpha stored as written
    if i == 0x10: return (0xFF, 0x00, 0x00, 0x80)   # red channel read as the index (the WebGL bug)
    return (0x80, 0x80, 0x80, 0x80)
clut8h = make_clut(clut8h_color)

# ---------- the GIF packet ----------
pkt = b''
pkt += ad_block([
    (FRAME_1, frame(FB_DISP, 640)), (ZBUF_1, (ZB // 8192) | (1 << 32)), (XYOFFSET_1, 0),
    (SCISSOR_1, (639 << 16) | (447 << 48)), (PRMODECONT, 1), (TEST_1, (1 << 16) | (1 << 17)),
    (COLCLAMP, 1), (DTHE, 0), (TEXA, 0x80 | (0x80 << 32)), (TEX1_1, 0),
    (PRIM, 6), (RGBAQ, rgbaq(0x20, 0x20, 0x20, 0x80)), *sprite(0, 0, 640, 448),
    (RGBAQ, rgbaq(0xFF, 0x00, 0x00, 0x80)), *sprite(16, 16, 144, 144),
    (RGBAQ, rgbaq(0x00, 0xFF, 0x00, 0x80)), *sprite(160, 16, 288, 144),
    (RGBAQ, rgbaq(0x00, 0x00, 0xFF, 0x80)), *sprite(304, 16, 432, 144),
])
pkt += upload(TEX32, 256, PSMCT32, 256, 256, bytes(tex32))
pkt += upload(CLUT_8H, 64, PSMCT32, 16, 16, clut8h)
pkt += upload(TEX8, 128, PSMT8, 128, 128, bytes(tex8))
pkt += upload(CLUT_8, 64, PSMCT32, 16, 16, clut8)
pkt += ad_block([
    (TEXFLUSH, 0),
    (PRIM, 6 | (1 << 4) | (1 << 8)), (RGBAQ, rgbaq(0x80, 0x80, 0x80, 0x80)),
    (TEX0_1, tex0(TEX32, 256, PSMCT32, 8, 8)), *sprite(16, 160, 272, 416, True, 0, 0, 256, 256),
    (TEX0_1, tex0(TEX8, 128, PSMT8, 7, 7, cbp=CLUT_8, cld=1)), (TEXFLUSH, 0), *sprite(288, 160, 416, 288, True, 0, 0, 128, 128),
    # offscreen: one sprite whose alpha is the index we want to read back
    (FRAME_1, frame(FB_OFFS, 640)), (PRIM, 6), (RGBAQ, rgbaq(0x10, 0x60, 0x30, 0x20)), *sprite(0, 0, 64, 64),
    (FRAME_1, frame(FB_DISP, 640)), (TEXFLUSH, 0),
    (PRIM, 6 | (1 << 4) | (1 << 8)), (RGBAQ, rgbaq(0x80, 0x80, 0x80, 0x80)),
    (TEX0_1, tex0(FB_OFFS, 640, PSMT8H, 6, 6, cbp=CLUT_8H, cld=1)), *sprite(448, 160, 512, 224, True, 0, 0, 64, 64),
    (FINISH, 0),
], eop=1)
assert len(pkt) % 16 == 0
QWC = len(pkt) // 16
assert QWC < 0xFFFF

# ---------- code ----------
def lui(rt, imm): return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)
def ori(rt, rs, imm): return 0x34000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, off, base): return 0xAC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def sd(rt, off, base): return 0xFC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def lw(rt, off, base): return 0x8C000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def ld(rt, off, base): return 0xDC000000 | (base << 21) | (rt << 16) | (off & 0xFFFF)
def andi(rt, rs, imm): return 0x30000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def bne(rs, rt, words): return 0x14000000 | (rs << 21) | (rt << 16) | (words & 0xFFFF)
def j(target): return 0x08000000 | ((target >> 2) & 0x3FFFFFF)
NOP = 0
ZERO, T0, T1, T2, T3, T4, T5, T6, T7, T8, T9 = 0, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25

CODE_SIZE = 0x100
DATA_OFF = CODE_SIZE                 # 64-bit display register values
PKT_OFF = CODE_SIZE + 0x100          # GIF packet (16-byte aligned)
data_addr = BASE + DATA_OFF
pkt_addr = BASE + PKT_OFF

# PMODE: EN1, CRTMD=1, MMOD=1, ALP=0xFF ; SMODE2: progressive ; DISPFB1: FBW=10 ; DISPLAY1: 640x448 at (636,50) MAGH=3
PMODE_V = 1 | (1 << 2) | (1 << 5) | (0xFF << 8)
DISPFB1_V = (640 // 64) << 9
DISPLAY1_V = 636 | (50 << 12) | (3 << 23) | ((640 * 4 - 1) << 32) | (447 << 44)
disp_regs = [(0x00, PMODE_V), (0x20, 0), (0x70, DISPFB1_V), (0x80, DISPLAY1_V), (0xE0, 0)]

code = []
code += [lui(T0, 0x1200), lui(T1, data_addr >> 16), ori(T1, T1, data_addr & 0xFFFF)]
for i, (off, _) in enumerate(disp_regs):
    code += [ld(T2, i * 8, T1), sd(T2, off, T0)]
code += [lui(T5, 0x1000), ori(T5, T5, 0xE000), ori(T4, ZERO, 1), sw(T4, 0, T5)]          # D_CTRL = 1
code += [lui(T5, 0x1000), ori(T5, T5, 0xA000)]                                           # D2 regs
code += [lui(T6, pkt_addr >> 16), ori(T6, T6, pkt_addr & 0xFFFF), sw(T6, 0x10, T5)]      # MADR
code += [ori(T7, ZERO, QWC), sw(T7, 0x20, T5)]                                           # QWC
code += [ori(T8, ZERO, 0x101), sw(T8, 0, T5)]                                            # CHCR: DIR, STR
wait_idx = len(code)
code += [lw(T9, 0, T5), andi(T9, T9, 0x100)]
code += [bne(T9, ZERO, wait_idx - (len(code) + 1)), NOP]
LOOP = len(sys.argv) > 2 and sys.argv[2] == '--loop'
loop_idx = len(code)
code += [ld(T2, 2 * 8, T1), sd(T2, 0x70, T0)]                                            # keep the GS presenting
if LOOP:
    # Redraw the whole picture once per vertical blank: clear CSR.VSINT, wait for it, restart the DMA.
    code += [ori(T4, ZERO, 8), sd(T4, 0x1000, T0)]                                       # CSR: clear VSINT
    vwait = len(code)
    code += [ld(T9, 0x1000, T0), andi(T9, T9, 8)]
    code += [0x10000000 | (T9 << 21) | (ZERO << 16) | ((vwait - (len(code) + 1)) & 0xFFFF), NOP]   # beq t9, zero, vwait
    code += [sw(T6, 0x10, T5), sw(T7, 0x20, T5), sw(T8, 0, T5)]                          # MADR, QWC, CHCR
    dwait = len(code)
    code += [lw(T9, 0, T5), andi(T9, T9, 0x100)]
    code += [bne(T9, ZERO, dwait - (len(code) + 1)), NOP]
code += [j(BASE + loop_idx * 4), NOP]
assert len(code) * 4 <= CODE_SIZE
text = b''.join(struct.pack('<I', c) for c in code).ljust(CODE_SIZE, b'\0')
data = b''.join(struct.pack('<Q', v) for _, v in disp_regs).ljust(PKT_OFF - DATA_OFF, b'\0')
image = text + data + pkt

# ---------- ELF ----------
EH = 52; PH = 32; SH = 40
load_off = 0x80
shstr = b'\0.text\0.shstrtab\0'
sh_off = load_off + len(image)
sh_off += (-sh_off) % 4
ehdr = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01' + b'\0' * 9, 2, 8, 1, BASE, EH, sh_off, 0x20924001,
                   EH, PH, 1, SH, 3, 2)
phdr = struct.pack('<IIIIIIII', 1, load_off, BASE, BASE, len(image), len(image), 7, 16)
shdrs = struct.pack('<IIIIIIIIII', *[0] * 10)
shdrs += struct.pack('<IIIIIIIIII', 1, 1, 6, BASE, load_off, len(image), 0, 0, 16, 0)
shdrs += struct.pack('<IIIIIIIIII', 7, 3, 0, 0, sh_off + 3 * SH, len(shstr), 0, 0, 1, 0)
out = bytearray(ehdr + phdr)
out += b'\0' * (load_off - len(out))
out += image
out += b'\0' * (sh_off - len(out))
out += shdrs + shstr
open(sys.argv[1], 'wb').write(out)
print(f"wrote {sys.argv[1]}: {len(out)} bytes, packet {QWC} qwords, code {len(code)} instructions")
