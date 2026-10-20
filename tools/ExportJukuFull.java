// All identified functions, with no business-name filter. Static analysis only.
// @category bobbi.Audit
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Symbol;
import ghidra.util.task.TaskMonitor;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.io.BufferedWriter;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ExportJukuFull extends GhidraScript {
    private static String clean(Object value) {
        return String.valueOf(value).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ');
    }

    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) throw new IllegalArgumentException("output [workers=4] [timeout=60] [retryFailures=false]");
        Path output = Path.of(args[0]);
        int workers = args.length > 1 ? Integer.parseInt(args[1]) : 4;
        int timeout = args.length > 2 ? Integer.parseInt(args[2]) : 60;
        boolean retryFailures = args.length > 3 && Boolean.parseBoolean(args[3]);
        Files.createDirectories(output.resolve("functions"));
        Files.createDirectories(output.resolve("journals"));
        List<Function> functions = new ArrayList<>();
        for (Function function : currentProgram.getFunctionManager().getFunctions(true)) functions.add(function);
        for (Function function : currentProgram.getFunctionManager().getExternalFunctions()) functions.add(function);
        try (BufferedWriter index = Files.newBufferedWriter(output.resolve("functions.tsv"), StandardCharsets.UTF_8)) {
            index.write("ordinal\taddress\tname\tbody_bytes\texternal\tthunk\n");
            int ordinal = 0;
            for (Function function : functions) index.write((ordinal++) + "\t" + function.getEntryPoint() + "\t"
                + clean(function.getName(true)) + "\t" + function.getBody().getNumAddresses() + "\t"
                + function.isExternal() + "\t" + function.isThunk() + "\n");
        }
        try (BufferedWriter ranges = Files.newBufferedWriter(output.resolve("function-body-ranges.tsv"), StandardCharsets.UTF_8)) {
            ranges.write("function_address\tstart\tend_inclusive\n");
            for (Function function : functions) {
                for (var range : function.getBody().getAddressRanges()) ranges.write(function.getEntryPoint() + "\t"
                    + range.getMinAddress() + "\t" + range.getMaxAddress() + "\n");
            }
        }
        int symbolCount = 0;
        try (BufferedWriter symbols = Files.newBufferedWriter(output.resolve("symbols.tsv"), StandardCharsets.UTF_8)) {
            symbols.write("address\tname\ttype\tsource\tprimary\n");
            for (Symbol symbol : currentProgram.getSymbolTable().getAllSymbols(true)) {
                symbols.write(symbol.getAddress() + "\t" + clean(symbol.getName(true)) + "\t"
                    + symbol.getSymbolType() + "\t" + symbol.getSource() + "\t" + symbol.isPrimary() + "\n");
                symbolCount++;
            }
        }
        Files.writeString(output.resolve("program.txt"), "program=" + currentProgram.getName()
            + "\nexecutable_path=" + currentProgram.getExecutablePath()
            + "\nexecutable_sha256=" + currentProgram.getExecutableSHA256()
            + "\nlanguage=" + currentProgram.getLanguageID() + "\ncompiler=" + currentProgram.getCompilerSpec().getCompilerSpecID()
            + "\nfunction_count=" + functions.size() + "\nsymbol_count=" + symbolCount
            + "\nworkers=" + workers + "\ntimeout_seconds=" + timeout + "\nstarted_utc=" + Instant.now()
            + "\nAll identified functions are included. Decompiled C is not original Go source.\n", StandardCharsets.UTF_8);
        println("JUKU_FULL_INVENTORY program=" + currentProgram.getName() + " functions=" + functions.size() + " symbols=" + symbolCount);
        Map<String, String> completed = new HashMap<>();
        try (var journals = Files.list(output.resolve("journals"))) {
            for (Path journal : journals.filter(p -> p.toString().endsWith(".tsv")).sorted().toList()) {
                for (String row : Files.readAllLines(journal, StandardCharsets.UTF_8)) {
                    String[] cells = row.split("\t", -1);
                    if (cells.length >= 7 && !cells[0].equals("address")) completed.put(cells[0], cells[2]);
                }
            }
        }
        List<Function> pending = new ArrayList<>();
        for (Function function : functions) {
            String address = function.getEntryPoint().toString();
            Path directory = output.resolve("functions").resolve(address.substring(0, Math.min(4, address.length())));
            String status = completed.get(address);
            boolean existing = status != null && Files.exists(directory.resolve(address + ".asm"))
                && Files.exists(directory.resolve(address + ".calls.tsv"))
                && (!status.equals("OK") || Files.exists(directory.resolve(address + ".c")));
            if (!existing || (retryFailures && !"OK".equals(status))) pending.add(function);
        }
        AtomicInteger next = new AtomicInteger();
        AtomicInteger done = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();
        var pool = Executors.newFixedThreadPool(workers);
        List<Future<?>> futures = new ArrayList<>();
        long runId = System.currentTimeMillis();
        for (int worker = 0; worker < workers; worker++) {
            final int workerId = worker;
            futures.add(pool.submit(() -> {
                DecompInterface decompiler = new DecompInterface();
                decompiler.toggleCCode(true);
                decompiler.toggleSyntaxTree(true);
                try (BufferedWriter journal = Files.newBufferedWriter(output.resolve("journals").resolve(runId + "-" + workerId + ".tsv"), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
                    if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("Cannot open decompiler");
                    journal.write("address\tname\tstatus\tbody_bytes\telapsed_ms\tcompleted_utc\terror\n");
                    int position;
                    while (!monitor.isCancelled() && (position = next.getAndIncrement()) < pending.size()) {
                        Function function = pending.get(position);
                        String address = function.getEntryPoint().toString();
                        String name = function.getName(true);
                        Path directory = output.resolve("functions").resolve(address.substring(0, Math.min(4, address.length())));
                        Files.createDirectories(directory);
                        long start = System.nanoTime();
                        String status = "ERROR", error = "";
                        try {
                            try (BufferedWriter assembly = Files.newBufferedWriter(directory.resolve(address + ".asm"), StandardCharsets.UTF_8)) {
                                assembly.write("; " + clean(name) + "\n");
                                for (Instruction instruction : currentProgram.getListing().getInstructions(function.getBody(), true))
                                    assembly.write(instruction.getAddress() + "  " + instruction + "\n");
                            }
                            try (BufferedWriter calls = Files.newBufferedWriter(directory.resolve(address + ".calls.tsv"), StandardCharsets.UTF_8)) {
                                calls.write("caller_address\tcaller_name\tcallee_address\tcallee_name\n");
                                for (Function called : function.getCalledFunctions(TaskMonitor.DUMMY)) calls.write(address + "\t" + clean(name)
                                    + "\t" + called.getEntryPoint() + "\t" + clean(called.getName(true)) + "\n");
                            }
                            var result = decompiler.decompileFunction(function, timeout, TaskMonitor.DUMMY);
                            boolean ok = result.decompileCompleted() && result.getDecompiledFunction() != null;
                            status = ok ? "OK" : (result.isTimedOut() ? "TIMEOUT" : "FAILED");
                            error = result.getErrorMessage();
                            String pseudocode = "/* Ghidra reconstructed pseudocode, NOT original Go source.\n * " + clean(name)
                                + "\n * " + address + "\n */\n";
                            pseudocode += ok ? result.getDecompiledFunction().getC() : "/* " + status + ": " + clean(error).replace("*/", "* /") + " */\n";
                            Files.writeString(directory.resolve(address + ".c"), pseudocode, StandardCharsets.UTF_8);
                        } catch (Exception failure) {
                            error = failure.getClass().getName() + ": " + failure.getMessage();
                        }
                        journal.write(address + "\t" + clean(name) + "\t" + status + "\t" + function.getBody().getNumAddresses()
                            + "\t" + ((System.nanoTime() - start) / 1000000) + "\t" + Instant.now() + "\t" + clean(error) + "\n");
                        journal.flush();
                        if (!status.equals("OK")) failed.incrementAndGet();
                        int total = done.incrementAndGet();
                        if (total % 250 == 0) println("JUKU_FULL_PROGRESS " + total + "/" + pending.size() + " failed=" + failed.get());
                    }
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                } finally { decompiler.dispose(); }
            }));
        }
        pool.shutdown();
        for (Future<?> future : futures) future.get();
        Files.writeString(output.resolve("run-complete.txt"), "finished_utc=" + Instant.now() + "\nidentified=" + functions.size()
            + "\nprevious_records=" + completed.size() + "\nattempted_this_run=" + done.get() + "\nfailed_this_run=" + failed.get()
            + "\ncancelled=" + monitor.isCancelled() + "\n", StandardCharsets.UTF_8);
        println("JUKU_FULL_DONE identified=" + functions.size() + " attempted=" + done.get() + " failed=" + failed.get());
    }
}
