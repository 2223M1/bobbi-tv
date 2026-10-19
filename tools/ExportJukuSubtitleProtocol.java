// Targeted, read-only static export. Never executes the analysed daemon.
// @category bobbi.Audit
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExportJukuSubtitleProtocol extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Path output = Path.of(args[0]);
        Files.createDirectories(output);
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (var index = Files.newBufferedWriter(output.resolve("index.tsv"), StandardCharsets.UTF_8)) {
            for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
                String name = function.getName(true);
                if (!name.contains("ExtractSubFidsFromUrl") && !name.contains("resolve115Subtitles")) continue;
                String address = function.getEntryPoint().toString();
                var result = decompiler.decompileFunction(function, 45, monitor);
                if (!result.decompileCompleted()) throw new RuntimeException(result.getErrorMessage());
                Files.writeString(output.resolve(address + ".c"),
                    "/* Reconstructed pseudocode, not original Go source: " + name + " */\n"
                    + result.getDecompiledFunction().getC(), StandardCharsets.UTF_8);
                StringBuilder assembly = new StringBuilder("; " + name + "\n");
                for (Instruction instruction : currentProgram.getListing().getInstructions(function.getBody(), true)) {
                    assembly.append(instruction.getAddress()).append("  ").append(instruction).append("\n");
                }
                Files.writeString(output.resolve(address + ".asm"), assembly, StandardCharsets.UTF_8);
                index.write(address + "\t" + name + "\t" + function.getBody().getNumAddresses() + "\n");
                println("SUBTITLE_PROTOCOL " + address + " " + name);
            }
            for (int i = 1; i < args.length; i++) {
                String[] pair = args[i].split(":");
                byte[] bytes = new byte[Integer.parseInt(pair[1])];
                currentProgram.getMemory().getBytes(toAddr(pair[0]), bytes);
                Files.write(output.resolve(pair[0] + "-" + pair[1] + ".bin"), bytes);
                println("EXACT_LITERAL " + args[i] + " = " + new String(bytes, StandardCharsets.UTF_8));
            }
        } finally { decompiler.dispose(); }
    }
}
