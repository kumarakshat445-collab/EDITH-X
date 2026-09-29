`timescale 1ns/1ps
// @hexa-spec {"kind":"uart_tx","clks_per_bit":16}
module uart_tx #(
    parameter int CLKS_PER_BIT = 16
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       tx_start,
    input  logic [7:0] tx_data,
    output logic       tx,
    output logic       tx_busy,
    output logic       tx_done
);
    typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;
    state_t state;
    logic [15:0] clk_count;
    logic [2:0]  bit_idx;
    logic [7:0]  shifter;

    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= IDLE;
            tx        <= 1'b1;
            tx_busy   <= 1'b0;
            tx_done   <= 1'b0;
            clk_count <= '0;
            bit_idx   <= '0;
            shifter   <= '0;
        end else begin
            tx_done <= 1'b0;
            case (state)
                IDLE: begin
                    tx      <= 1'b1;
                    tx_busy <= 1'b0;
                    if (tx_start) begin
                        shifter   <= tx_data;
                        state     <= START;
                        clk_count <= '0;
                        tx_busy   <= 1'b1;
                    end
                end
                START: begin
                    tx <= 1'b0;
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= '0;
                        bit_idx   <= '0;
                        state     <= DATA;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                DATA: begin
                    tx <= shifter[bit_idx];
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= '0;
                        if (bit_idx == 3'd7) begin
                            state <= STOP;
                        end else begin
                            bit_idx <= bit_idx + 1'b1;
                        end
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                STOP: begin
                    tx <= 1'b1;
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        state     <= IDLE;
                        tx_busy   <= 1'b0;
                        tx_done   <= 1'b1;
                        clk_count <= '0;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
