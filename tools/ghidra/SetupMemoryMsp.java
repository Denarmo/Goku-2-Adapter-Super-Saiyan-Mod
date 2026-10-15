// Ghidra headless PRE-script for the MSP (WCH RISC-V) co-processor image.
// Reproduces the startup copy done by _start: flash[0x4..0x75c) -> RAM 0x1fffc000
// (RAM-resident code), flash[0x3920..) -> RAM 0x1fffc75c (.data), then .bss.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import java.io.*;

public class SetupMemoryMsp extends GhidraScript {
  public void run() throws Exception {
    Memory m = currentProgram.getMemory();
    AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
    for (MemoryBlock b : m.getBlocks()) { b.setWrite(false); b.setExecute(true); b.setName("flash"); }
    byte[] ram = new byte[0x804];
    m.getBytes(sp.getAddress(0x4), ram, 0, 0x75c);
    m.getBytes(sp.getAddress(0x3920), ram, 0x75c, 0x804 - 0x75c);
    MemoryBlock r = m.createInitializedBlock("ramcode", sp.getAddress(0x1fffc000L), new ByteArrayInputStream(ram), ram.length, monitor, false);
    r.setWrite(true); r.setExecute(true);
    m.createUninitializedBlock("bss", sp.getAddress(0x1fffc804L), 0x20000000L - 0x1fffc804L, false).setWrite(true);
    MemoryBlock p = m.createUninitializedBlock("periph", sp.getAddress(0x40000000L), 0x10000, false);
    p.setVolatile(true); p.setWrite(true);
    MemoryBlock c = m.createUninitializedBlock("pfic", sp.getAddress(0xE000E000L), 0x2000, false);
    c.setVolatile(true); c.setWrite(true);

    // Register names from WCH CH58x/CH57x SDK headers (CH583SFR.h). The chip is
    // identified by register map only - see docs/hardware.md.
    Object[][] regs = {
      {0x40001008L, "R8_CLK_SYS_CFG"}, {0x4000100AL, "R8_HFCK_PWR_CTRL"},
      {0x40001018L, "R32_RTC_TRIG"},   {0x40001024L, "R8_RST_WDOG_CTRL"},
      {0x40001025L, "R8_GLOB_RESET_KEEP"}, {0x40001040L, "R8_SAFE_ACCESS_SIG"},
      {0x40001041L, "R8_CHIP_ID"},     {0x40001044L, "R8_GLOB_ROM_CFG"},
      {0x40001045L, "R8_GLOB_CFG_INFO"}, {0x40001046L, "R8_RST_WDOG_CTRL2"},
      {0x4000104EL, "R8_FLASH_CTRL"},  {0x400010B8L, "R32_PB_DIR"},
      {0x40003400L, "R8_UART1_MCR"},   {0x40003401L, "R8_UART1_IER"},
      {0x40003402L, "R8_UART1_FCR"},   {0x40003403L, "R8_UART1_LCR"},
      {0x40003404L, "R8_UART1_IIR"},   {0x40003405L, "R8_UART1_LSR"},
      {0x40003408L, "R8_UART1_RBR_THR"}, {0x4000340AL, "R8_UART1_RFC"},
      {0x4000340BL, "R8_UART1_TFC"},   {0x4000340CL, "R16_UART1_DL"},
      {0x4000340EL, "R8_UART1_DIV"},
      {0x40008000L, "R8_USB_CTRL"},    {0x40008001L, "R8_UHOST_CTRL"},
      {0x40008002L, "R8_USB_INT_EN"},  {0x40008003L, "R8_USB_DEV_AD"},
      {0x40008005L, "R8_USB_MIS_ST"},  {0x40008006L, "R8_USB_INT_FG"},
      {0x40008007L, "R8_USB_INT_ST"},  {0x40008008L, "R8_USB_RX_LEN"},
      {0x4000800DL, "R8_UH_EP_MOD"},   {0x40008018L, "R16_UH_RX_DMA"},
      {0x4000801CL, "R16_UH_TX_DMA"},  {0x40008026L, "R8_UH_SETUP"},
      {0x40008028L, "R8_UH_EP_PID"},   {0x4000802AL, "R8_UH_RX_CTRL"},
      {0x4000802CL, "R8_UH_TX_LEN"},   {0x4000802EL, "R8_UH_TX_CTRL"},
    };
    ghidra.program.model.symbol.SymbolTable st = currentProgram.getSymbolTable();
    for (Object[] reg : regs)
      st.createLabel(sp.getAddress((Long) reg[0]), (String) reg[1], ghidra.program.model.symbol.SourceType.IMPORTED);

    // _start sets gp = 0x1fffcfc0; tell the analyzer so gp-relative globals resolve.
    ghidra.program.model.listing.ProgramContext ctx = currentProgram.getProgramContext();
    ghidra.program.model.lang.Register gp = ctx.getRegister("gp");
    java.math.BigInteger gpv = java.math.BigInteger.valueOf(0x1fffcfc0L);
    for (MemoryBlock b : m.getBlocks())
      if (b.isInitialized() && b.isExecute() || b.getName().equals("flash"))
        ctx.setValue(gp, b.getStart(), b.getEnd(), gpv);
  }
}
