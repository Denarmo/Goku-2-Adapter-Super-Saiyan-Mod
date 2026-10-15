// Writes a one-line summary per unnamed function (for batch naming):
// addr|size|nparams|callers|callees|globals|consts
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;
public class Summarize extends GhidraScript {
  public void run() throws Exception {
    PrintWriter pw = new PrintWriter(new FileWriter(getScriptArgs()[0]));
    for (Function f : currentProgram.getListing().getFunctions(true)) {
      if (!f.getName().startsWith("FUN_")) continue;
      Set<String> callers = new TreeSet<>(), callees = new TreeSet<>(), globs = new TreeSet<>(), cons = new TreeSet<>();
      for (Function c : f.getCallingFunctions(monitor)) callers.add(c.getName());
      for (Function c : f.getCalledFunctions(monitor)) callees.add(c.isThunk() ? c.getThunkedFunction(true).getName() : c.getName());
      for (Instruction i : currentProgram.getListing().getInstructions(f.getBody(), true)) {
        for (Reference r : i.getReferencesFrom()) {
          long t = r.getToAddress().getOffset();
          if (t >= 0x20000000L && t < 0x30000000L || t >= 0x40000000L) { Symbol s = getSymbolAt(r.getToAddress()); globs.add(s != null ? s.getName() : String.format("%08x", t)); }
          Data d = getDataAt(r.getToAddress());
          if (d != null && d.isPointer() && d.getValue() instanceof ghidra.program.model.address.Address) {
            long v = ((ghidra.program.model.address.Address) d.getValue()).getOffset();
            if (v >= 0x20000000L) globs.add(String.format("%08x", v));
          }
        }
        for (int k = 0; k < i.getNumOperands(); k++) for (Object o : i.getOpObjects(k))
          if (o instanceof Scalar) { long v = ((Scalar) o).getUnsignedValue(); if (v > 8 && v < 0x10000 && cons.size() < 6) cons.add(Long.toHexString(v)); }
      }
      pw.println(String.format("%s|%d|%d|%s|%s|%s|%s", f.getEntryPoint(), f.getBody().getNumAddresses(), f.getParameterCount(),
        trim(callers), trim(callees), trim(globs), String.join(" ", cons)));
    }
    pw.close();
  }
  static String trim(Set<String> s) { List<String> l = new ArrayList<>(s); return String.join(" ", l.size() > 6 ? l.subList(0, 6) : l) + (l.size() > 6 ? " +" + (l.size() - 6) : ""); }
}
