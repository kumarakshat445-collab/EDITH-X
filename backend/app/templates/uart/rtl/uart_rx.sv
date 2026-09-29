`timescale 1ns/1ps
// @hexa-spec {"kind":"uart_rx","clks_per_bit":16}
module uart_rx #(
    parameter int CLKS_PER_BIT = 16
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       rx,
    output logic [7:0] rx_data,
    output logic       rx_valid
);
    typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;
    state_t state;
    logic [15:0] clk_count;
    logic [2:0]  bit_idx;
    logic [7:0]  shift;

    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= IDLE;
            rx_data   <= '0;
            rx_valid  <= 1'b0;
            clk_count <= '0;
            bit_idx   <= '0;
            shift     <= '0;
        end else begin
            rx_valid <= 1'b0;
            case (state)
                IDLE: begin
                    if (rx == 1'b0) begin
                        state     <= START;
                        clk_count <= '0;
                    end
                end
                START: begin
                    if (clk_count == (CLKS_PER_BIT/2) - 1) begin
                        if (rx == 1'b0) begin
                            clk_count <= '0;
                            bit_idx   <= '0;
                            state     <= DATA;
                        end else begin
                            state <= IDLE;
                        end
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                DATA: begin
                    if (clk_count == CLKS_PER_BIT) begin
                        clk_count      <= '0;
                        shift[bit_idx] <= rx;
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
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        rx_data   <= shift;
                        rx_valid  <= 1'b1;
                        state     <= IDLE;
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
