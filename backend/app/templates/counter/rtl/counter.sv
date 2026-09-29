`timescale 1ns/1ps
// @hexa-spec {"kind":"counter","width":8,"increment":1}
module counter #(
    parameter int WIDTH = 8
) (
    input  logic             clk,
    input  logic             reset,
    output logic [WIDTH-1:0] count
);
    always_ff @(posedge clk) begin
        if (reset)
            count <= '0;
        else
            count <= count + 8'd2;
    end
endmodule
