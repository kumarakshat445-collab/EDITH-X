# UART Controller

8N1 transmitter and receiver in a loopback top. `CLKS_PER_BIT` is the number of clocks per bit (default 16).

The receiver's DATA state compares `clk_count` with `CLKS_PER_BIT`. The transmitter advances a bit when `clk_count == CLKS_PER_BIT - 1`. That one-cycle skew is intentional in this demo project. HEXA-R should discover it from simulation output and the two compares, then propose a one-line edit. Applying the edit is left to you.

Generate `tb/uart_tb.sv`, run VERIFY RTL, review the diff, apply it, and verify again.
