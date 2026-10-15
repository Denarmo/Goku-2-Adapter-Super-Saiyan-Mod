// Ghidra headless PRE-script for the NS36 main firmware (ARM Cortex-M).
//
// Expects the whole update file imported raw at 0x10003000 (the address the
// bootloader writes it to; vector table/code start at 0x10004000).
// Builds the runtime memory map before auto-analysis:
//   0x00000000 +0x60000  mask ROM (contents unknown; filled with "bx lr" stubs
//                        so calls through veneers appear as rom_XXXXX())
//   0x10003000           flash image (read-only => literal pools fold)
//   0x2000C000 +0x1308   .data, reconstructed exactly like ARMCC __scatterload:
//                        plain copy of 0xD70 bytes + LZ-decompressed 0x598 bytes
//                        (contains RAM-resident functions)
//   0x2000D308 +0xC1C    .bss, then free RAM / stack up to 0x20010000
//   0x20000000..0x2000BFFF  RAM owned by the mask ROM / BT controller
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import java.io.*;

public class SetupMemoryArm extends GhidraScript {
  Memory m;
  AddressSpace sp;
  Address A(long v) { return sp.getAddress(v); }
  int u32(long a) throws Exception { return m.getInt(A(a)); }

  // ARMCC RW-data decompressor (__decompress1), mirrors flash code at 0x10004220.
  static byte[] decompress(byte[] src, int outLen) {
    byte[] out = new byte[outLen];
    int i = 0, o = 0;
    while (o < outLen) {
      int tok = src[i++] & 0xff;
      int lit = tok & 7;   if (lit == 0) lit = src[i++] & 0xff;
      int len = tok >> 4;  if (len == 0) len = src[i++] & 0xff;
      for (int k = 1; k < lit; k++) out[o++] = src[i++];
      if ((tok & 8) != 0) {
        int from = o - (src[i++] & 0xff);
        for (int k = 0; k < len + 2 && o < outLen; k++) out[o++] = out[from++];
      } else {
        for (int k = 0; k < len && o < outLen; k++) out[o++] = 0;
      }
    }
    return out;
  }

  public void run() throws Exception {
    m = currentProgram.getMemory();
    sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
    MemoryBlock flash = m.getBlocks()[0];
    long base = flash.getStart().getOffset();
    flash.setWrite(false); flash.setExecute(true); flash.setName("flash");

    // --- mask ROM stubs
    byte[] stub = new byte[0x60000];
    for (int k = 0; k < stub.length; k += 2) { stub[k] = 0x70; stub[k + 1] = 0x47; }
    MemoryBlock rom = m.createInitializedBlock("maskrom", A(0), new ByteArrayInputStream(stub), stub.length, monitor, false);
    rom.setWrite(false); rom.setExecute(true);

    // --- RAM: reconstruct .data from the scatter-load table
    // __scatterload: adr r0, tbl ; ldm r0, {r10, r11} ; add r10, r0 ; add r11, r0
    long tblRef = base + 0x1218;
    long tbl = tblRef + (u32(tblRef) & 0xffffffffL), tblEnd = tblRef + (u32(tblRef + 4) & 0xffffffffL);
    final long DATA = 0x2000C000L;
    long dataEnd = DATA;
    byte[] ram = new byte[0x4000];
    for (long e = tbl; e < tblEnd; e += 16) {
      long src = u32(e) & 0xffffffffL, dst = u32(e + 4) & 0xffffffffL;
      int size = u32(e + 8);
      long fn = u32(e + 12) & 0xffffffffL;
      String kind;
      if (fn == base + 0x1220) {                        // compressed
        byte[] in = new byte[0x2000];
        m.getBytes(A(src), in);
        System.arraycopy(decompress(in, size), 0, ram, (int) (dst - DATA), size);
        kind = "decompress";
      } else if (src >= base && src + size <= flash.getEnd().getOffset() && e + 16 < tblEnd) {
        byte[] in = new byte[size];                     // plain copy
        m.getBytes(A(src), in);
        System.arraycopy(in, 0, ram, (int) (dst - DATA), size);
        kind = "copy";
      } else {
        kind = "zero";                                  // .bss (last entry)
      }
      printf("scatter: %08x -> %08x size %x (%s)\n", src, dst, size, kind);
      if (!kind.equals("zero")) dataEnd = Math.max(dataEnd, dst + size);
    }
    byte[] init = java.util.Arrays.copyOf(ram, (int) (dataEnd - DATA));
    m.createUninitializedBlock("ram_rom", A(0x20000000L), DATA - 0x20000000L, false).setWrite(true);
    MemoryBlock rd = m.createInitializedBlock("ram_data", A(DATA), new ByteArrayInputStream(init), init.length, monitor, false);
    rd.setWrite(true); rd.setExecute(true);
    m.createUninitializedBlock("ram_bss", A(dataEnd), 0x20010000L - dataEnd, false).setWrite(true);

    // --- peripherals
    for (long[] p : new long[][] { {0x40000000L, 0x100000}, {0x50000000L, 0x100000}, {0xE000E000L, 0x1000} }) {
      MemoryBlock b = m.createUninitializedBlock(String.format("periph_%08x", p[0]), A(p[0]), p[1], false);
      b.setVolatile(true); b.setWrite(true);
    }
  }
}
