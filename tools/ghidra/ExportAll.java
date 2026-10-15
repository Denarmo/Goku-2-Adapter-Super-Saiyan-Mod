// Ghidra headless post-script for the NS36 main (ARM Cortex-M) firmware.
//
// Expects the full update file imported raw at 0x10003000 (ARM:LE:32:Cortex)
// with SetupMemoryArm.java as pre-script.
// Args: <output .c path> [names.csv]
//   names.csv: "address,name[,comment]" rows (hex addresses) that override
//   automatic names - this is where human RE knowledge is recorded.
// Writes <out>, <out>.functions.csv, <out>.strings.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.app.cmd.disassemble.ArmDisassembleCommand;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class ExportAll extends GhidraScript {
  AddressSpace sp;
  Address A(long v) { return sp.getAddress(v); }

  void applyTypes(String typesPath, String protoPath, String globalsPath) throws Exception {
    ghidra.program.model.data.DataTypeManager dtm = currentProgram.getDataTypeManager();
    ghidra.app.util.cparser.C.CParser parser = new ghidra.app.util.cparser.C.CParser(dtm, true, null);
    String hdr = new String(java.nio.file.Files.readAllBytes(new File(typesPath).toPath()));
    parser.parse(hdr);
    int nProto = 0, nGlob = 0;
    for (String line : java.nio.file.Files.readAllLines(new File(protoPath).toPath())) {
      line = line.trim();
      if (line.isEmpty() || line.startsWith("#")) continue;
      String[] f = line.split("\\|", 2);
      Address a = A(Long.decode(f[0].trim()));
      parser.parse(f[1].trim() + ";");
      String fname = f[1].replaceAll("\\(.*", "").trim().replaceAll(".*[\\s*]", "");
      ghidra.program.model.data.DataType dt = parser.getFunctions().get(fname);
      if (!(dt instanceof ghidra.program.model.data.FunctionDefinition)) {
        println("prototype not a function: " + line); continue;
      }
      Function fn = getFunctionAt(a);
      if (fn == null) { println("no function at " + a); continue; }
      new ghidra.app.cmd.function.ApplyFunctionSignatureCmd(a,
          (ghidra.program.model.data.FunctionDefinition) dt, SourceType.USER_DEFINED)
          .applyTo(currentProgram, monitor);
      fn.setCallingConvention("__stdcall");   // AAPCS
      nProto++;
    }
    for (String line : java.nio.file.Files.readAllLines(new File(globalsPath).toPath())) {
      line = line.trim();
      if (line.isEmpty() || line.startsWith("#") || line.startsWith("address")) continue;
      String[] f = line.split(",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)");
      Address a = A(Long.decode(f[0].trim()));
      createLabel(a, f[1].trim(), true, SourceType.USER_DEFINED);
      if (f.length > 3 && !f[3].isBlank()) {
        List<ghidra.program.model.data.DataType> found = new ArrayList<>();
        dtm.findDataTypes(f[3].trim(), found);
        if (found.isEmpty()) { println("unknown type " + f[3]); continue; }
        ghidra.program.model.data.DataType dt = found.get(0);
        try {
          clearListing(a, a.add(dt.getLength() - 1));
          createData(a, dt);
          nGlob++;
        } catch (Exception e) { println("cannot type " + f[1] + ": " + e.getMessage()); }
      }
    }
    println("applied prototypes: " + nProto + ", typed globals: " + nGlob);
  }

  /** NUL-terminated printable string of >= 5 chars at a, or null. */
  static String cstring(Memory m, Address a) {
    StringBuilder sb = new StringBuilder();
    try {
      for (int i = 0; i < 160; i++) {
        int c = m.getByte(a.add(i)) & 0xff;
        if (c == 0) return sb.length() >= 5 ? sb.toString() : null;
        if (c == '\r' || c == '\n' || c == '\t') { sb.append(' '); continue; }
        if (c < 0x20 || c > 0x7e) return null;
        sb.append((char) c);
      }
    } catch (Exception e) { }
    return null;
  }

  /** "  cntlr trigger save config %d" -> "cntlr_trigger_save_config" (max 5 words). */
  static String snake(String s) {
    List<String> words = new ArrayList<>();
    for (String w : s.split("[^A-Za-z0-9]+")) {
      if (w.isEmpty()) continue;
      if (w.matches("[0-9].*") || w.matches("0?[xX]?[0-9A-Fa-f]{0,2}") && w.length() <= 2 && words.isEmpty()) continue;
      if (w.equals("d") || w.equals("x") || w.equals("s") || w.equals("X") || w.equals("p") || w.equals("lx")) continue;
      words.add(w.toLowerCase());
      if (words.size() == 5) break;
    }
    if (words.size() < 2) return null;
    return String.join("_", words);
  }

  public void run() throws Exception {
    String[] args = getScriptArgs();
    String out = args[0];
    Memory m = currentProgram.getMemory();
    sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
    Listing L = currentProgram.getListing();
    final long BASE = m.getBlock("flash").getStart().getOffset();
    final long codeStart = BASE + 0x1000;
    final long imageEnd = codeStart + (m.getInt(A(BASE + 0x20)) & 0xffffffffL);
    // The tail of the image [first scatter-load source, imageEnd) is the load
    // image of .data (it runs from RAM, which SetupMemoryArm reconstructs), so
    // code discovery stops at its start.
    final long tblRef = BASE + 0x1218;
    final long codeEnd = m.getInt(A(tblRef + (m.getInt(A(tblRef)) & 0xffffffffL))) & 0xffffffffL;
    println(String.format("code+rodata: %08x-%08x, .data load image: %08x-%08x", codeStart, codeEnd, codeEnd, imageEnd));

    // ---- code discovery -----------------------------------------------------
    for (int i = 1; i < 48; i++) {               // vector table
      long v = m.getInt(A(codeStart + 4 * i)) & 0xffffffffL;
      if ((v & 1) == 1 && v >= codeStart && v < codeEnd) {
        new ArmDisassembleCommand(A(v & ~1L), null, true).applyTo(currentProgram, monitor);
        createFunction(A(v & ~1L), i == 16 ? "IRQ0_Handler" : "vector_" + i);
      }
    }
    // __main (ARMCC C runtime entry) sits right after the app header
    new ArmDisassembleCommand(A(codeStart + 0x1e4), null, true).applyTo(currentProgram, monitor);
    createFunction(A(codeStart + 0x1e4), "__main");
    // ARMCC long-branch veneers: movw r12,#lo ; movt r12,#hi ; bx r12
    // Targets are mask-ROM (0x0000xxxx) or RAM-resident (.data) functions.
    int veneers = 0;
    for (long o = codeStart; o + 10 <= codeEnd; o += 2) {
      int h0 = m.getShort(A(o)) & 0xffff, h1 = m.getShort(A(o + 2)) & 0xffff;
      int h2 = m.getShort(A(o + 4)) & 0xffff, h3 = m.getShort(A(o + 6)) & 0xffff;
      int h4 = m.getShort(A(o + 8)) & 0xffff;
      if ((h0 & 0xfbf0) != 0xf240 || (h1 & 0x0f00) != 0x0c00 || (h2 & 0xfbf0) != 0xf2c0
          || (h3 & 0x0f00) != 0x0c00 || h4 != 0x4760) continue;
      long lo = ((h0 & 0xf) << 12) | (((h0 >> 10) & 1) << 11) | (((h1 >> 12) & 7) << 8) | (h1 & 0xff);
      long hi = ((h2 & 0xf) << 12) | (((h2 >> 10) & 1) << 11) | (((h3 >> 12) & 7) << 8) | (h3 & 0xff);
      long t = (lo | (hi << 16)) & ~1L;
      Address ta = A(t);
      if (m.getBlock(ta) == null || !m.getBlock(ta).isInitialized()) continue;
      String nm = t < 0x00100000L ? String.format("rom_%05x", t)
                : t >= 0x20000000L ? String.format("ramfn_%08x", t) : null;
      new ArmDisassembleCommand(ta, null, true).applyTo(currentProgram, monitor);
      Function tf = getFunctionAt(ta);
      if (tf == null) tf = createFunction(ta, nm);
      else if (nm != null && tf.getName().startsWith("FUN_")) tf.setName(nm, SourceType.ANALYSIS);
      new ArmDisassembleCommand(A(o), null, true).applyTo(currentProgram, monitor);
      if (getFunctionAt(A(o)) == null) createFunction(A(o), null);
      veneers++;
    }
    println("veneers: " + veneers);
    // function pointers stored anywhere in code/rodata (callbacks, tables)
    for (long o = codeStart; o + 4 <= codeEnd; o += 4) {
      long v = m.getInt(A(o)) & 0xffffffffL;
      if ((v & 1) == 1 && v > codeStart + 0x200 && v < codeEnd && (v & 0xffff) != 0xffff) {
        int hw = m.getShort(A(v & ~1L)) & 0xffff;
        if ((hw & 0xff00) == 0xb500 || hw == 0xe92d || (hw & 0xfe00) == 0xb400) {
          new ArmDisassembleCommand(A(v & ~1L), null, true).applyTo(currentProgram, monitor);
          if (getFunctionAt(A(v & ~1L)) == null) createFunction(A(v & ~1L), null);
        }
      }
    }
    analyzeAll(currentProgram);
    for (long o = codeStart; o < codeEnd; o += 2) {   // PUSH {.., lr} prologues
      Address a = A(o);
      if (L.getInstructionContaining(a) != null || L.getDefinedDataContaining(a) != null) continue;
      int hw = m.getShort(a) & 0xffff;
      if ((hw & 0xff00) == 0xb500 || hw == 0xe92d) {
        new ArmDisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
        if (getFunctionAt(a) == null) createFunction(a, null);
      }
    }
    analyzeAll(currentProgram);

    // ---- type literal-pool words as pointers so the decompiler folds them ----
    int ptrs = 0;
    for (Instruction ins : L.getInstructions(A(codeStart), true)) {
      if (ins.getAddress().getOffset() >= codeEnd) break;
      for (Reference r : ins.getReferencesFrom()) {
        Address t = r.getToAddress();
        if (!r.getReferenceType().isRead() || t.getOffset() < codeStart || t.getOffset() + 4 > codeEnd) continue;
        if ((t.getOffset() & 3) != 0 || L.getInstructionContaining(t) != null) continue;
        Data d0 = getDataAt(t);
        if (d0 != null && d0.isDefined() && !d0.getDataType().getName().startsWith("undefined")) continue;
        long v = m.getInt(t) & 0xffffffffL;
        boolean isPtr = (v >= 0x200L && v < 0x60000L && (v & 1) == 1) || (v >= 0x20000000L && v < 0x20010000L) || (v >= 0x40000000L && v < 0x40100000L)
            || (v >= 0x50000000L && v < 0x50100000L) || (v >= 0xE000E000L && v < 0xE000F000L)
            || (v >= BASE && v < codeEnd);
        if (!isPtr) continue;
        try {
          clearListing(t, t.add(3));
          createData(t, ghidra.program.model.data.PointerDataType.dataType);
          ptrs++;
        } catch (Exception e) {}
      }
    }
    println("typed literal pointers: " + ptrs);
    analyzeAll(currentProgram);

    // Drop code that auto-analysis found inside the .data load image: those bytes
    // only execute from their RAM copy (decompiled at 0x2000xxxx instead).
    int dropped = 0;
    for (Function f : currentProgram.getFunctionManager().getFunctions(A(codeEnd), true)) {
      if (f.getEntryPoint().getOffset() >= imageEnd) break;
      currentProgram.getFunctionManager().removeFunction(f.getEntryPoint());
      dropped++;
    }
    clearListing(A(codeEnd), A(imageEnd - 1));
    createLabel(A(codeEnd), "__data_load_image", true);
    println("dropped functions in .data load image: " + dropped);

    // Known data regions (reference/data_arm.csv, passed as args[5]).
    if (args.length > 5 && new File(args[5]).exists()) {
      for (String line : java.nio.file.Files.readAllLines(new File(args[5]).toPath())) {
        line = line.trim();
        if (line.isEmpty() || line.startsWith("#") || line.startsWith("address")) continue;
        String[] f = line.split(",", 4);
        Address a = A(Long.decode(f[0].trim()));
        int len = Integer.decode(f[1].trim());
        Address e = a.add(len - 1);
        Iterator<Function> it = currentProgram.getFunctionManager().getFunctionsOverlapping(new AddressSet(a, e));
        List<Address> doomed = new ArrayList<>();
        while (it.hasNext()) doomed.add(it.next().getEntryPoint());
        for (Address d : doomed) currentProgram.getFunctionManager().removeFunction(d);
        clearListing(a, e);
        createData(a, new ghidra.program.model.data.ArrayDataType(
            ghidra.program.model.data.ByteDataType.dataType, len, 1));
        createLabel(a, f[2].trim(), true, SourceType.USER_DEFINED);
        if (f.length > 3) setPlateComment(a, f[3].replace("\"", "").trim());
      }
    }

    // ---- naming ----------------------------------------------------------------
    Map<Long, String[]> manual = new HashMap<>();
    if (args.length > 1 && new File(args[1]).exists()) {
      for (String line : java.nio.file.Files.readAllLines(new File(args[1]).toPath())) {
        line = line.trim();
        if (line.isEmpty() || line.startsWith("#") || line.startsWith("address")) continue;
        String[] f = line.split(",", 3);
        manual.put(Long.decode(f[0].trim()), f);
      }
    }
    Pattern idp = Pattern.compile("^[\\s\\[\\]+*-]*([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]{2,})");
    Set<String> used = new HashSet<>();
    for (String[] f : manual.values()) used.add(f[1].trim());
    PrintWriter idx = new PrintWriter(new FileWriter(out + ".functions.csv"));
    idx.println("address,name,source");
    for (Function f : L.getFunctions(true)) {
      long ep = f.getEntryPoint().getOffset();
      String why = "";
      String[] man = manual.get(ep);
      if (man != null) {
        f.setName(man[1].trim(), SourceType.USER_DEFINED);
        if (man.length > 2 && !man[2].isBlank()) f.setComment(man[2].trim());
        why = "manual";
      } else if (f.getName().startsWith("FUN_")) {
        // Gather every C string this function references (directly or via a
        // literal-pool pointer). Prefer an identifier-like token
        // ("usb_set_config ..."), else snake_case the first words of a
        // descriptive message ("cntlr trigger save config").
        List<String> strs = new ArrayList<>();
        for (Address a : f.getBody().getAddresses(true)) {
          for (Reference r : getReferencesFrom(a)) {
            Address t = r.getToAddress();
            Data dd = getDataAt(t);
            if (dd != null && dd.isPointer() && dd.getValue() instanceof Address) t = (Address) dd.getValue();
            String s = cstring(m, t);
            if (s != null) strs.add(s);
          }
        }
        String best = null;
        for (String s : strs) {
          Matcher mm = idp.matcher(s);
          if (mm.find()) { best = mm.group(1); break; }
        }
        if (best == null) for (String s : strs) { best = snake(s); if (best != null) break; }
        if (best != null) {
          String nm = best; int k = 2; while (used.contains(nm)) nm = best + "_" + (k++);
          used.add(nm);
          try { f.setName(nm, SourceType.ANALYSIS); why = "log-string"; } catch (Exception e) {}
        }
      }
      if (f.isThunk()) idx.println(String.format("0x%08x,thunk_%s,thunk", ep, f.getName()));
      else idx.println(String.format("0x%08x,%s,%s", ep, f.getName(), why));
    }
    idx.close();

    PrintWriter sw = new PrintWriter(new FileWriter(out + ".strings.txt"));
    for (Data dd : L.getDefinedData(true))
      if (dd.getValue() instanceof String) sw.println(dd.getAddress() + "\t" + ((String) dd.getValue()).replace("\n", "\\n"));
    sw.close();

    // ---- subsystem tags for everything still unnamed (args[6] modules csv) --------
    if (args.length > 6 && new File(args[6]).exists()) {
      List<long[]> ranges = new ArrayList<>(); List<String> prefixes = new ArrayList<>();
      for (String line : java.nio.file.Files.readAllLines(new File(args[6]).toPath())) {
        line = line.trim();
        if (line.isEmpty() || line.startsWith("#") || line.startsWith("start")) continue;
        String[] f = line.split(",", 4);
        ranges.add(new long[] { Long.decode(f[0].trim()), Long.decode(f[1].trim()) });
        prefixes.add(f[2].trim());
      }
      int tagged = 0;
      Map<Long, String> retag = new HashMap<>();
      for (Function f : L.getFunctions(true)) {
        if (!f.getName().startsWith("FUN_")) continue;
        long ep = f.getEntryPoint().getOffset();
        String pre = ep < 0x00100000L ? "rom" : null;
        for (int k = 0; k < ranges.size() && pre == null; k++)
          if (ep >= ranges.get(k)[0] && ep < ranges.get(k)[1]) pre = prefixes.get(k);
        if (pre == null) continue;
        Set<String> callees = new HashSet<>();
        for (Function c : f.getCalledFunctions(monitor))
          callees.add(c.isThunk() ? c.getThunkedFunction(true).getName() : c.getName());
        String role = "";
        if (callees.contains("pkt_alloc_payload")) role = "_pdu";
        else if (callees.contains("hci_send")) role = "_hcicmd";
        else if (callees.contains("rom_sched_post") && callees.contains("rom_irq_save")) role = "_post";
        else if (callees.contains("log_printf")) role = "_log";
        String nm = ep < 0x00100000L ? String.format("rom_%05x", ep) : String.format("%s%s_%08x", pre, role, ep);
        try { f.setName(nm, SourceType.ANALYSIS); tagged++; retag.put(ep, nm); } catch (Exception e) { }
      }
      println("subsystem-tagged functions: " + tagged);
      // patch the already-written index
      File idxFile = new File(out + ".functions.csv");
      List<String> rows = new ArrayList<>();
      for (String row : java.nio.file.Files.readAllLines(idxFile.toPath())) {
        String[] c = row.split(",", 3);
        if (!row.startsWith("address") && c.length == 3) {
          String nm = retag.get(Long.decode(c[0]));
          if (nm != null) row = c[0] + "," + nm + "," + (nm.startsWith("rom_") ? "rom" : "module");
        }
        rows.add(row);
      }
      java.nio.file.Files.write(idxFile.toPath(), rows);
    }

    // ---- recovered types, prototypes and typed globals ----------------------------
    // args: [2] types header, [3] prototypes csv ("addr|proto"), [4] globals csv
    if (args.length > 4) applyTypes(args[2], args[3], args[4]);

    // ---- decompile -------------------------------------------------------------
    DecompInterface di = new DecompInterface();
    DecompileOptions dopt = new DecompileOptions();
    dopt.grabFromProgram(currentProgram);
    dopt.setRespectReadOnly(true);
    di.setOptions(dopt);
    di.openProgram(currentProgram);
    PrintWriter pw = new PrintWriter(new FileWriter(out));
    int n = 0, ok = 0;
    for (Function f : L.getFunctions(true)) {
      if (f.getEntryPoint().getOffset() < 0x00100000L) continue;   // mask ROM stubs
      DecompileResults r = di.decompileFunction(f, 60, monitor);
      pw.println("/* ==== " + f.getName() + " @ " + f.getEntryPoint() + " ==== */");
      if (r != null && r.decompileCompleted()) { pw.println(r.getDecompiledFunction().getC()); ok++; }
      else pw.println("/* decompile failed */\n");
      n++;
    }
    pw.close();
    println("functions: " + n + " decompiled: " + ok + "");
  }
}
