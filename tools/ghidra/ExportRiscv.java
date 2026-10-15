// Ghidra headless post-script for the MSP (RISC-V RV32IMC) co-processor image.
// Args: <output .c path>. Writes <out>, <out>.functions.csv, <out>.strings.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;
import java.util.regex.*;
public class ExportRiscv extends GhidraScript {
  public void run() throws Exception {
    String out = getScriptArgs()[0];
    Memory m = currentProgram.getMemory();
    AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
    Listing L = currentProgram.getListing();
    Address start = sp.getAddress(0);
        new DisassembleCommand(start, null, true).applyTo(currentProgram, monitor);
    createFunction(start, "_start");
    analyzeAll(currentProgram);
    // prologue scan over flash and RAM-resident code:
    // c.addi sp,-N / c.addi16sp sp,-N
    for (MemoryBlock blk : m.getBlocks()) {
      if (!blk.isInitialized()) continue;
      for (long o = blk.getStart().getOffset(); o + 2 <= blk.getEnd().getOffset(); o += 2) {
        Address a = sp.getAddress(o);
        if (L.getInstructionContaining(a) != null || L.getDefinedDataContaining(a) != null) continue;
        int hw;
        try { hw = m.getShort(a) & 0xffff; } catch (MemoryAccessException e) { continue; }
        boolean caddi16sp = (hw & 0xef83) == 0x6101 && (hw & 0x1000) != 0;
        boolean caddi = (hw & 0xef83) == 0x0101 && (hw & 0x1000) != 0;
        if (caddi16sp || caddi) {
          new DisassembleCommand(a, null, true).applyTo(currentProgram, monitor);
          if (getFunctionAt(a) == null) createFunction(a, null);
        }
      }
    }
    analyzeAll(currentProgram);
    Pattern idp = Pattern.compile("^[\\s\\[\\]+*-]*([A-Za-z][A-Za-z0-9_]{3,})");
    Map<Long, String[]> manual = new HashMap<>();
    String[] args = getScriptArgs();
    if (args.length > 1 && new File(args[1]).exists()) {
      for (String line : java.nio.file.Files.readAllLines(new File(args[1]).toPath())) {
        line = line.trim();
        if (line.isEmpty() || line.startsWith("#") || line.startsWith("address")) continue;
        String[] f = line.split(",", 3);
        manual.put(Long.decode(f[0].trim()), f);
      }
    }
    Set<String> used = new HashSet<>();
    for (String[] f : manual.values()) used.add(f[1].trim());
    PrintWriter idx = new PrintWriter(new FileWriter(out + ".functions.csv"));
    idx.println("address,name,source");
    for (Function f : L.getFunctions(true)) {
      String why = "";
      String[] man = manual.get(f.getEntryPoint().getOffset());
      if (man != null) {
        f.setName(man[1].trim(), SourceType.USER_DEFINED);
        if (man.length > 2 && !man[2].isBlank()) f.setComment(man[2].trim());
        why = "manual";
      } else if (f.getName().startsWith("FUN_")) {
        String best = null;
        for (Address a : f.getBody().getAddresses(true)) {
          for (Reference r : getReferencesFrom(a)) {
            Data dd = getDataAt(r.getToAddress());
            if (dd == null || !(dd.getValue() instanceof String)) continue;
            Matcher mm = idp.matcher((String) dd.getValue());
            if (mm.find()) { best = mm.group(1); break; }
          }
          if (best != null) break;
        }
        if (best != null) {
          String nm = best; int k = 2; while (used.contains(nm)) nm = best + "_" + (k++);
          used.add(nm);
          try { f.setName(nm, SourceType.ANALYSIS); why = "log-string"; } catch (Exception e) {}
        }
      }
      if (f.getName().startsWith("FUN_")) {
        // tag by the peripheral the function touches (WCH register labels)
        String role = null;
        for (Instruction ins : L.getInstructions(f.getBody(), true)) {
          for (Reference r : ins.getReferencesFrom()) {
            Symbol s = getSymbolAt(r.getToAddress());
            if (s == null) continue;
            String n = s.getName();
            if (n.startsWith("R8_U") && !n.startsWith("R8_UART") || n.startsWith("R16_UH") || n.startsWith("R8_USB")) role = "usbh";
            else if (n.startsWith("R8_UART") || n.startsWith("R16_UART")) role = role == null ? "uart" : role;
            else if (n.startsWith("R8_") || n.startsWith("R32_")) role = role == null ? "sys" : role;
          }
        }
        boolean ram = f.getEntryPoint().getOffset() >= 0x1fffc000L;
        String nm = String.format("msp_%s%s_%x", ram ? "ram_" : "", role == null ? "fn" : role, f.getEntryPoint().getOffset());
        try { f.setName(nm, SourceType.ANALYSIS); why = "module"; } catch (Exception e) { }
      }
      idx.println(String.format("0x%08x,%s,%s", f.getEntryPoint().getOffset(), f.getName(), why));
    }
    idx.close();
    DecompInterface di = new DecompInterface();
    DecompileOptions dopt = new DecompileOptions();
    dopt.grabFromProgram(currentProgram);
    dopt.setRespectReadOnly(true);
    di.setOptions(dopt); di.openProgram(currentProgram);
    PrintWriter pw = new PrintWriter(new FileWriter(out));
    int n = 0;
    for (Function f : L.getFunctions(true)) {
      DecompileResults r = di.decompileFunction(f, 60, monitor);
      pw.println("/* ==== " + f.getName() + " @ " + f.getEntryPoint() + " ==== */");
      pw.println(r != null && r.decompileCompleted() ? r.getDecompiledFunction().getC() : "/* decompile failed */\n");
      n++;
    }
    pw.close();
    println("functions: " + n);
  }
}
