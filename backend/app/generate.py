"""Deterministic RTL and testbench generation.

Open-ended prose is refused when no template matches. Generated RTL carries an
@hexa-spec header so the testbench checks the same contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .sv import Module, active_low_reset, is_clock, is_reset, parse_modules, read_spec


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class Generation:
    ok: bool
    backend: str
    title: str
    message: str
    assumptions: list[str] = field(default_factory=list)
    interface: list[str] = field(default_factory=list)
    files: list[GeneratedFile] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "title": self.title,
            "message": self.message,
            "assumptions": self.assumptions,
            "interface": self.interface,
            "files": [{"path": f.path, "content": f.content} for f in self.files],
        }


def _width(prompt: str, default: int = 8) -> int:
    match = re.search(r"(\d+)\s*-?\s*bit", prompt, re.I)
    if match:
        return max(1, min(int(match.group(1)), 128))
    return default


def _depth(prompt: str) -> int:
    match = re.search(r"depth\s*(?:of|=)?\s*(\d+)|(\d+)\s*-?\s*deep|(\d+)\s+entries", prompt, re.I)
    if not match:
        return 16
    raw = next(g for g in match.groups() if g)
    depth = int(raw)
    if depth < 2:
        depth = 2
    if depth & (depth - 1):
        depth = 1 << (depth - 1).bit_length()
    return min(depth, 256)


def generate_rtl(prompt: str) -> Generation:
    text = prompt.strip()
    lowered = text.lower()
    if not text:
        return Generation(False, "rule-engine", "Generate RTL", "Describe the module you want.")
    if "fifo" in lowered:
        return _fifo(text)
    if re.search(r"\balu\b", lowered):
        return _alu(text)
    if "counter" in lowered:
        return _counter(text)
    if "shift" in lowered:
        return _shift(text)
    if "mux" in lowered or "multiplex" in lowered:
        return _mux(text)
    if "uart" in lowered:
        return _uart_clean()
    return Generation(
        False,
        "rule-engine",
        "Generate RTL",
        "Local language model is not installed, so open-ended RTL generation is unavailable. "
        "The rule engine can build a synchronous FIFO, counter, ALU, shift register, mux, or UART. "
        "Rephrase the request around one of those.",
    )


def _fifo(prompt: str) -> Generation:
    width = _width(prompt, 32)
    depth = _depth(prompt)
    spec = {"kind": "sync_fifo", "width": width, "depth": depth}
    code = f'''`timescale 1ns/1ps
// @hexa-spec {json.dumps(spec)}
// Synchronous FIFO. Single clock. Count-based full and empty flags.
module sync_fifo #(
    parameter int WIDTH = {width},
    parameter int DEPTH = {depth}
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             wr_en,
    input  logic             rd_en,
    input  logic [WIDTH-1:0] din,
    output logic [WIDTH-1:0] dout,
    output logic             full,
    output logic             empty
);
    localparam int AW = $clog2(DEPTH);
    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [AW:0] wr_ptr;
    logic [AW:0] rd_ptr;
    logic [AW:0] count;

    assign full  = (count == DEPTH[AW:0]);
    assign empty = (count == '0);
    assign dout  = mem[rd_ptr[AW-1:0]];

    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr[AW-1:0]] <= din;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
            unique case ({{wr_en && !full, rd_en && !empty}})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a synchronous FIFO from the FIFO template. No language model was called.",
        [
            "One clock domain. rst is synchronous and active-high.",
            "DEPTH is forced to a power of two so pointer wrap is a bit increment.",
            "full and empty come from a count, not from pointer comparison alone.",
            "Read data is show-ahead: dout reflects mem[rd_ptr] combinationally.",
            "A write while full, or a read while empty, is ignored.",
        ],
        [
            f"clk, rst — control",
            f"wr_en, din[{width-1}:0] — write port",
            f"rd_en, dout[{width-1}:0] — read port",
            "full, empty — status",
        ],
        [GeneratedFile("rtl/sync_fifo.sv", code)],
    )


def _counter(prompt: str) -> Generation:
    width = _width(prompt, 8)
    spec = {"kind": "counter", "width": width, "increment": 1}
    code = f'''`timescale 1ns/1ps
// @hexa-spec {json.dumps(spec)}
module counter #(
    parameter int WIDTH = {width}
) (
    input  logic             clk,
    input  logic             reset,
    output logic [WIDTH-1:0] count
);
    always_ff @(posedge clk) begin
        if (reset)
            count <= '0;
        else
            count <= count + 1'b1;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a free-running counter. No language model was called.",
        [
            "Synchronous active-high reset clears count.",
            "Each rising clock outside reset adds 1.",
            "The counter wraps naturally at the WIDTH boundary.",
        ],
        ["clk", "reset", f"count[{width-1}:0]"],
        [GeneratedFile("rtl/counter.sv", code)],
    )


def _alu(prompt: str) -> Generation:
    width = _width(prompt, 32)
    spec = {"kind": "alu", "width": width}
    code = f'''`timescale 1ns/1ps
// @hexa-spec {json.dumps(spec)}
// op: 0 add, 1 sub, 2 and, 3 or, 4 xor, 5 logical left shift
module alu #(
    parameter int WIDTH = {width}
) (
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic [2:0]       op,
    output logic [WIDTH-1:0] result
);
    always_comb begin
        case (op)
            3'd0: result = a + b;
            3'd1: result = a - b;
            3'd2: result = a & b;
            3'd3: result = a | b;
            3'd4: result = a ^ b;
            3'd5: result = a << b[2:0];
            default: result = '0;
        endcase
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a combinational ALU. No language model was called.",
        [
            "Purely combinational. No clock and no stored flags.",
            "Shift distance uses only b[2:0] so the shift is bounded.",
            "Unknown opcodes drive result to zero.",
        ],
        ["a, b — operands", "op[2:0] — operation select", "result"],
        [GeneratedFile("rtl/alu.sv", code)],
    )


def _shift(prompt: str) -> Generation:
    width = _width(prompt, 8)
    spec = {"kind": "shift_reg", "width": width}
    code = f'''`timescale 1ns/1ps
// @hexa-spec {json.dumps(spec)}
module shift_reg #(
    parameter int WIDTH = {width}
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             sin,
    output logic             sout,
    output logic [WIDTH-1:0] q
);
    always_ff @(posedge clk) begin
        if (rst)
            q <= '0;
        else
            q <= {{q[WIDTH-2:0], sin}};
    end
    assign sout = q[WIDTH-1];
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a left-shifting register. No language model was called.",
        ["sin enters at bit 0.", "sout is the bit shifted out of the MSB.", "Reset clears the register."],
        ["clk, rst, sin", "sout", f"q[{width-1}:0]"],
        [GeneratedFile("rtl/shift_reg.sv", code)],
    )


def _mux(prompt: str) -> Generation:
    width = _width(prompt, 8)
    spec = {"kind": "mux4", "width": width}
    code = f'''`timescale 1ns/1ps
// @hexa-spec {json.dumps(spec)}
module mux4 #(
    parameter int WIDTH = {width}
) (
    input  logic [WIDTH-1:0] d0,
    input  logic [WIDTH-1:0] d1,
    input  logic [WIDTH-1:0] d2,
    input  logic [WIDTH-1:0] d3,
    input  logic [1:0]       sel,
    output logic [WIDTH-1:0] y
);
    always_comb begin
        case (sel)
            2'd0: y = d0;
            2'd1: y = d1;
            2'd2: y = d2;
            default: y = d3;
        endcase
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a 4-to-1 mux. No language model was called.",
        ["Combinational.", "sel == 3 selects d3, which is also the default."],
        ["d0, d1, d2, d3", "sel[1:0]", "y"],
        [GeneratedFile("rtl/mux4.sv", code)],
    )


def _uart_clean() -> Generation:
    from pathlib import Path

    root = Path(__file__).resolve().parent / "templates" / "uart_good"
    files = []
    for path in sorted(root.rglob("*.sv")):
        rel = path.relative_to(root).as_posix()
        files.append(GeneratedFile(rel, path.read_text(encoding="utf-8")))
    return Generation(
        True,
        "rule-engine",
        "AI Generated RTL",
        "Built a loopback UART (transmitter, receiver, top). The receiver samples on the bit period. No language model was called.",
        [
            "8N1 framing.",
            "CLKS_PER_BIT is clocks per bit and defaults to 16.",
            "The receiver confirms the start bit at its midpoint, then samples each data bit one bit-period later.",
            "This copy does not include the demo sampling defect.",
        ],
        ["clk, rst", "tx_start, tx_data[7:0]", "rx_data[7:0], rx_valid, tx, tx_busy"],
        files,
    )


def generate_testbench(files: dict[str, str], focus: str | None = None) -> Generation:
    modules: list[tuple[str, Module]] = []
    for path, src in files.items():
        if not path.endswith((".sv", ".v")):
            continue
        for module in parse_modules(src):
            modules.append((path, module))
    if not modules:
        return Generation(False, "rule-engine", "Testbench", "No module was found to test.")

    by_name = {module.name: (path, module, src) for path, src in files.items() for module in parse_modules(src)}
    chosen = None
    if focus:
        focus_name = PathName(focus)
        for path, module in modules:
            if path == focus or module.name == focus_name:
                chosen = (path, module)
                break
    if chosen is None:
        for path, module in modules:
            if module.name.endswith("_tb"):
                continue
            chosen = (path, module)
            break
    if chosen is None:
        return Generation(False, "rule-engine", "Testbench", "No design module was found.")

    path, module = chosen
    src = files[path]
    spec = read_spec(src) or module.spec
    kind = str(spec.get("kind") or module.name)

    if kind in {"uart_rx", "uart_tx", "uart_top"} or (
        "uart_tx" in by_name and "uart_rx" in by_name
    ):
        return _tb_uart(by_name)
    if kind == "counter" or module.name == "counter":
        return _tb_counter(module, spec)
    if kind == "sync_fifo" or module.name == "sync_fifo":
        return _tb_fifo(module, spec)
    if kind == "alu" or module.name == "alu":
        return _tb_alu(module, spec)
    if kind == "shift_reg" or module.name == "shift_reg":
        return _tb_shift(module)
    if kind == "mux4" or module.name == "mux4":
        return _tb_mux(module)
    return _tb_generic(module)


def PathName(focus: str) -> str:
    return focus.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _header(spec: dict, note: str) -> str:
    return f"`timescale 1ns/1ps\n// @hexa-spec {json.dumps(spec)}\n// {note}\n"


def _tb_counter(module: Module, spec: dict) -> Generation:
    width = int(spec.get("width") or 8)
    inc = int(spec.get("increment") or 1)
    code = _header({"kind": "counter_tb", "width": width, "increment": inc}, "Checks reset and a +1 count.")
    instance = "counter dut"
    if any(name == "WIDTH" for name, _ in module.parameters):
        instance = f"counter #(.WIDTH({width})) dut"
    code += f'''
module counter_tb;
    logic clk = 0;
    logic reset = 1;
    logic [{width - 1}:0] count;
    int unsigned tests = 0;
    int unsigned passed = 0;
    int unsigned failed = 0;

    {instance} (.clk(clk), .reset(reset), .count(count));
    always #5 clk = ~clk;

    task automatic check(input [{width - 1}:0] expected, input string label);
        begin
            tests++;
            if (count !== expected) begin
                failed++;
                $display("FAIL %s expected %0d got %0d", label, expected, count);
            end else begin
                passed++;
                $display("PASS %s expected %0d got %0d", label, expected, count);
            end
        end
    endtask

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(1, counter_tb);
        repeat (3) @(posedge clk);
        #1 check({width}'d0, "reset");
        reset = 0;
        for (int i = 1; i <= 8; i++) begin
            @(posedge clk);
            #1 check(i * {inc}, $sformatf("cycle %0d", i));
        end
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0) $display("VERIFICATION PASSED");
        else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "Clock, synchronous reset, then eight increments checked against the counter contract.",
        ["Reset is held for three clocks.", "Count is sampled 1ns after the rising edge.", "The expected step is the @hexa-spec increment (default 1)."],
        ["Clock", "Reset", "Basic increment", "Pass/fail report"],
        [GeneratedFile("tb/counter_tb.sv", code)],
    )


def _tb_fifo(module: Module, spec: dict) -> Generation:
    width = int(spec.get("width") or 32)
    depth = int(spec.get("depth") or 16)
    code = _header({"kind": "sync_fifo_tb"}, "Writes a burst, checks empty/full, then reads it back.")
    code += f'''
module sync_fifo_tb;
    logic clk = 0;
    logic rst = 1;
    logic wr_en = 0;
    logic rd_en = 0;
    logic [{width - 1}:0] din = '0;
    logic [{width - 1}:0] dout;
    logic full, empty;
    int unsigned tests = 0, passed = 0, failed = 0;

    sync_fifo #(.WIDTH({width}), .DEPTH({depth})) dut (
        .clk(clk), .rst(rst), .wr_en(wr_en), .rd_en(rd_en),
        .din(din), .dout(dout), .full(full), .empty(empty)
    );
    always #5 clk = ~clk;

    task automatic check(input int cond, input string label);
        begin
            tests++;
            if (!cond) begin failed++; $display("FAIL %s", label); end
            else begin passed++; $display("PASS %s", label); end
        end
    endtask

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(1, sync_fifo_tb);
        repeat (3) @(posedge clk);
        rst = 0;
        @(posedge clk); #1;
        check(empty === 1'b1, "empty after reset");
        check(full === 1'b0, "not full after reset");
        din = {width}'h11; wr_en = 1; rd_en = 0;
        @(posedge clk); #1; wr_en = 0;
        check(empty === 1'b0, "not empty after one write");
        check(dout === {width}'h11, "show-ahead data is 0x11");
        din = {width}'h22; wr_en = 1;
        @(posedge clk); #1;
        din = {width}'h33;
        @(posedge clk); #1; wr_en = 0;
        check(dout === {width}'h11, "oldest value stays at the output");
        rd_en = 1; wr_en = 0;
        @(posedge clk); #1;
        check(dout === {width}'h22, "second value after one read");
        @(posedge clk); #1;
        check(dout === {width}'h33, "third value");
        @(posedge clk); #1; rd_en = 0;
        check(empty === 1'b1, "empty after draining three writes");
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0) $display("VERIFICATION PASSED");
        else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "Reset, a three-word write, show-ahead checks, then an ordered read.",
        ["Does not fill the FIFO to capacity.", "Simultaneous read and write is not exercised."],
        ["Clock", "Reset", "Basic writes", "Ordered reads", "Empty flag"],
        [GeneratedFile("tb/sync_fifo_tb.sv", code)],
    )


def _tb_alu(module: Module, spec: dict) -> Generation:
    width = int(spec.get("width") or 32)
    code = _header({"kind": "alu_tb"}, "Directed vectors for add, sub, and, or, xor, and shift.")
    code += f'''
module alu_tb;
    logic [{width - 1}:0] a, b, result;
    logic [2:0] op;
    int unsigned tests = 0, passed = 0, failed = 0;
    alu #(.WIDTH({width})) dut (.a(a), .b(b), .op(op), .result(result));

    task automatic check(input [{width - 1}:0] expected, input string label);
        begin
            tests++;
            #1;
            if (result !== expected) begin
                failed++;
                $display("FAIL %s expected %0d got %0d", label, expected, result);
            end else begin
                passed++;
                $display("PASS %s", label);
            end
        end
    endtask

    initial begin
        a = {width}'h10; b = {width}'h03;
        op = 3'd0; check({width}'h13, "add");
        op = 3'd1; check({width}'h0d, "sub");
        op = 3'd2; check({width}'h00, "and");
        op = 3'd3; check({width}'h13, "or");
        op = 3'd4; check({width}'h13, "xor");
        b = {width}'h1; op = 3'd5; check({width}'h20, "shift");
        op = 3'd7; check({width}'h0, "default");
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0) $display("VERIFICATION PASSED");
        else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "One directed vector per opcode, including the default arm.",
        ["Vectors use a=0x10 and b=0x3 except the shift.", "No clock is required."],
        ["Add", "Sub", "Bitwise", "Shift", "Default"],
        [GeneratedFile("tb/alu_tb.sv", code)],
    )


def _tb_shift(module: Module) -> Generation:
    code = '''`timescale 1ns/1ps
module shift_reg_tb;
    logic clk = 0, rst = 1, sin = 0, sout;
    logic [7:0] q;
    int unsigned tests = 0, passed = 0, failed = 0;
    shift_reg #(.WIDTH(8)) dut (.clk(clk), .rst(rst), .sin(sin), .sout(sout), .q(q));
    always #5 clk = ~clk;
    task automatic check(input [7:0] expected, input string label);
        begin
            tests++;
            if (q !== expected) begin failed++; $display("FAIL %s expected %0d got %0d", label, expected, q); end
            else begin passed++; $display("PASS %s", label); end
        end
    endtask
    initial begin
        repeat (2) @(posedge clk);
        #1 check(8'h00, "reset");
        rst = 0; sin = 1;
        @(posedge clk); #1 check(8'h01, "first 1");
        sin = 0;
        @(posedge clk); #1 check(8'h02, "shift left");
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0) $display("VERIFICATION PASSED"); else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "Reset, then a single 1 shifted left by one position.",
        ["WIDTH is 8 to match the default generator."],
        ["Reset", "Shift"],
        [GeneratedFile("tb/shift_reg_tb.sv", code)],
    )


def _tb_mux(module: Module) -> Generation:
    code = '''`timescale 1ns/1ps
module mux4_tb;
    logic [7:0] d0, d1, d2, d3, y;
    logic [1:0] sel;
    int unsigned tests = 0, passed = 0, failed = 0;
    mux4 #(.WIDTH(8)) dut (.d0(d0), .d1(d1), .d2(d2), .d3(d3), .sel(sel), .y(y));
    task automatic check(input [1:0] which, input [7:0] expected);
        begin
            sel = which; #1; tests++;
            if (y !== expected) begin failed++; $display("FAIL sel %0d expected %0d got %0d", which, expected, y); end
            else begin passed++; $display("PASS sel %0d", which); end
        end
    endtask
    initial begin
        d0 = 8'h1; d1 = 8'h2; d2 = 8'h3; d3 = 8'h4;
        check(2'd0, 8'h1); check(2'd1, 8'h2); check(2'd2, 8'h3); check(2'd3, 8'h4);
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0) $display("VERIFICATION PASSED"); else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "Each select value is checked against its data input.",
        ["Combinational, sampled after #1."],
        ["sel 0", "sel 1", "sel 2", "sel 3"],
        [GeneratedFile("tb/mux4_tb.sv", code)],
    )


def _tb_uart(by_name: dict) -> Generation:
    clks = 16
    for key in ("uart_rx", "uart_tx", "uart_top"):
        if key in by_name:
            spec = read_spec(by_name[key][2])
            if spec.get("clks_per_bit"):
                clks = int(spec["clks_per_bit"])
                break
    code = f'''`timescale 1ns/1ps
// Loopback: uart_tx drives uart_rx. Each byte must arrive unchanged.
module uart_tb;
    localparam int CLKS_PER_BIT = {clks};
    logic clk = 0;
    logic rst = 1;
    logic tx_start = 0;
    logic [7:0] tx_data = '0;
    logic tx, tx_busy, tx_done;
    logic [7:0] rx_data;
    logic rx_valid;
    int unsigned tests = 0, passed = 0, failed = 0;

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) dut_tx (
        .clk(clk), .rst(rst), .tx_start(tx_start), .tx_data(tx_data),
        .tx(tx), .tx_busy(tx_busy), .tx_done(tx_done)
    );
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) dut_rx (
        .clk(clk), .rst(rst), .rx(tx), .rx_data(rx_data), .rx_valid(rx_valid)
    );

    always #5 clk = ~clk;

    task automatic send_and_check(input logic [7:0] value);
        int guard;
        begin
            tests++;
            @(posedge clk);
            tx_data <= value;
            tx_start <= 1'b1;
            @(posedge clk);
            tx_start <= 1'b0;
            guard = 0;
            while (!rx_valid && guard < (CLKS_PER_BIT * 20)) begin
                @(posedge clk);
                guard++;
            end
            if (!rx_valid) begin
                failed++;
                $display("FAIL byte 0x%02h expected 0x%02h got timeout", value, value);
            end else if (rx_data !== value) begin
                failed++;
                $display("FAIL byte 0x%02h expected 0x%02h got 0x%02h", value, value, rx_data);
            end else begin
                passed++;
                $display("PASS byte 0x%02h expected 0x%02h got 0x%02h", value, value, rx_data);
            end
            repeat (CLKS_PER_BIT + 2) @(posedge clk);
        end
    endtask

    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(1, uart_tb);
        repeat (4) @(posedge clk);
        rst = 0;
        repeat (4) @(posedge clk);
        send_and_check(8'h55);
        send_and_check(8'hA3);
        send_and_check(8'h00);
        send_and_check(8'hFF);
        send_and_check(8'h01);
        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);
        if (failed == 0 && passed == tests) $display("VERIFICATION PASSED");
        else $display("VERIFICATION FAILED");
        $finish;
    end
endmodule
'''
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        "Loopback testbench. The transmitter shifts each byte and the receiver must return the same byte.",
        [
            "Bytes 0x55, 0xA3, 0x00, 0xFF, and 0x01 cover alternating, sparse, and solid patterns.",
            "A missing rx_valid is a timeout failure, not a pass.",
            "Clock, reset, stimulus, and the pass/fail count are all in this file.",
        ],
        ["Clock", "Reset", "Directed bytes", "Timeout", "Pass/fail"],
        [GeneratedFile("tb/uart_tb.sv", code)],
    )


def _tb_generic(module: Module) -> Generation:
    clk = next((p for p in module.ports if is_clock(p.name)), None)
    rst = next((p for p in module.ports if is_reset(p.name)), None)
    inputs = [p for p in module.ports if p.direction == "input" and p is not clk and p is not rst]
    outputs = [p for p in module.ports if p.direction != "input"]
    lines = ["`timescale 1ns/1ps", f"module {module.name}_tb;"]
    if clk:
        lines.append(f"    logic {clk.name} = 0;")
    if rst:
        low = active_low_reset(rst.name)
        lines.append(f"    logic {rst.name} = {'0' if low else '1'};")
    for port in inputs + outputs:
        width = port.width or ""
        lines.append(f"    logic {width} {port.name};")
    lines.append("    int unsigned tests = 0, passed = 0, failed = 0;")
    conns = ", ".join(f".{p.name}({p.name})" for p in module.ports)
    params = ""
    if module.parameters:
        params = " #(" + ", ".join(f".{name}({value})" for name, value in module.parameters) + ")"
    lines.append(f"    {module.name}{params} dut ({conns});")
    if clk:
        lines.append(f"    always #5 {clk.name} = ~{clk.name};")
    lines.append("    task automatic check_known(input string label);")
    lines.append("        begin")
    lines.append("            tests++;")
    conds = [f"!$isunknown({p.name})" for p in outputs] or ["1"]
    lines.append(f"            if ({' && '.join(conds)}) begin passed++; $display(\"PASS %s\", label); end")
    lines.append("            else begin failed++; $display(\"FAIL %s unknown output\", label); end")
    lines.append("        end")
    lines.append("    endtask")
    lines.append("    initial begin")
    lines.append(f'        $dumpfile("dump.vcd"); $dumpvars(1, {module.name}_tb);')
    for port in inputs:
        lines.append(f"        {port.name} = '0;")
    if clk:
        lines.append("        repeat (2) @(posedge clk);")
    if rst:
        release = "1" if active_low_reset(rst.name) else "0"
        lines.append(f"        {rst.name} = {release};")
        if clk:
            lines.append("        repeat (2) @(posedge clk); #1;")
    lines.append('        check_known("inputs held at 0");')
    for index, port in enumerate(inputs):
        lines.append(f"        {port.name} = '1;")
        if clk:
            lines.append("        @(posedge clk); #1;")
        else:
            lines.append("        #1;")
        lines.append(f'        check_known("driven {port.name}");')
        lines.append(f"        {port.name} = '0;")
    lines.append('        $display("RESULT tests=%0d passed=%0d failed=%0d", tests, passed, failed);')
    lines.append('        if (failed == 0) $display("VERIFICATION PASSED"); else $display("VERIFICATION FAILED");')
    lines.append("        $finish;")
    lines.append("    end")
    lines.append("endmodule")
    code = "\n".join(lines) + "\n"
    return Generation(
        True,
        "rule-engine",
        "Testbench",
        f"Structural testbench for {module.name}. It resets the design, drives each input, and fails if an output is X. "
        "It does not invent a functional specification that was not in the source.",
        [
            "No expected numeric behavior was inferred beyond 'outputs must be defined'.",
            "Add an @hexa-spec header or use a known template for functional checks.",
        ],
        ["Clock" if clk else "No clock", "Reset" if rst else "No reset", "Drive inputs", "Unknown-output checks"],
        [GeneratedFile(f"tb/{module.name}_tb.sv", code)],
    )
