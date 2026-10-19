// Read-only static account-lifecycle export. Never executes the analysed daemon.
// @category bobbi.Audit
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class ExportJukuAccountProtocol extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Path output = Path.of(args[0]);
        Files.createDirectories(output);
        List<String> filters = new ArrayList<>();
        List<String> addresses = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            if (args[i].startsWith("fn:")) filters.add(args[i].substring(3));
            if (args[i].startsWith("at:")) addresses.add(args[i].substring(3));
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (var symbols = Files.newBufferedWriter(output.resolve("symbols.tsv"), StandardCharsets.UTF_8);
             var index = Files.newBufferedWriter(output.resolve("index.tsv"), StandardCharsets.UTF_8);
             var calls = Files.newBufferedWriter(output.resolve("calls.tsv"), StandardCharsets.UTF_8);
             var callers = Files.newBufferedWriter(output.resolve("callers.tsv"), StandardCharsets.UTF_8)) {
            for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                String name = function.getName(true);
                String address = function.getEntryPoint().toString();
                if (name.contains("mv-daemon") || name.startsWith("main.")) {
                    symbols.write(address + "\t" + name + "\n");
                }
                if (!addresses.contains(address) && !filters.stream().anyMatch(name::contains)) continue;
                var result = decompiler.decompileFunction(function, 45, monitor);
                boolean complete = result.decompileCompleted() && result.getDecompiledFunction() != null;
                Files.writeString(output.resolve(address + ".c"),
                    "/* Reconstructed pseudocode, not original Go source: " + name + " */\n"
                    + (complete ? result.getDecompiledFunction().getC() : result.getErrorMessage()), StandardCharsets.UTF_8);
                StringBuilder assembly = new StringBuilder("; " + name + "\n");
                for (Instruction instruction : currentProgram.getListing().getInstructions(function.getBody(), true)) {
                    assembly.append(instruction.getAddress()).append("  ").append(instruction).append("\n");
                }
                Files.writeString(output.resolve(address + ".asm"), assembly, StandardCharsets.UTF_8);
                index.write(address + "\t" + name + "\t" + complete + "\t" + function.getBody().getNumAddresses() + "\n");
                for (Function called : function.getCalledFunctions(monitor)) {
                    calls.write(address + "\t" + name + "\t" + called.getEntryPoint() + "\t" + called.getName(true) + "\n");
                }
                for (Function caller : function.getCallingFunctions(monitor)) {
                    callers.write(address + "\t" + name + "\t" + caller.getEntryPoint() + "\t" + caller.getName(true) + "\n");
                }
                index.flush();
                calls.flush();
                callers.flush();
                println("ACCOUNT_PROTOCOL " + address + " " + name + " " + complete);
            }
            for (int i = 1; i < args.length; i++) {
                if (!args[i].startsWith("bytes:")) continue;
                String[] pair = args[i].substring(6).split(":");
                byte[] bytes = new byte[Integer.parseInt(pair[1])];
                currentProgram.getMemory().getBytes(toAddr(pair[0]), bytes);
                Files.write(output.resolve(pair[0] + "-" + pair[1] + ".bin"), bytes);
                println("EXACT_LITERAL " + args[i] + " = " + new String(bytes, StandardCharsets.UTF_8));
            }
        } finally { decompiler.dispose(); }
    }
}
