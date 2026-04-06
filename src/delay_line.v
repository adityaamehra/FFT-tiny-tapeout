module delay_line #(parameter DEPTH = 1)(
    input  wire clk, reset_n,
    input  wire signed [7:0] in_r, in_i,
    output wire signed [7:0] out_r, out_i
);
    generate
        if (DEPTH == 0) begin : bypass
            assign {out_r, out_i} = {in_r, in_i};
        end else begin : shift_reg
            reg [15:0] mem [0:DEPTH-1];
            integer idx;
            always @(posedge clk) begin
                if (!reset_n) begin
                    for (idx = 0; idx < DEPTH; idx = idx + 1) mem[idx] <= 16'd0;
                end else begin
                    for (idx = DEPTH-1; idx > 0; idx = idx - 1) mem[idx] <= mem[idx-1];
                    mem[0] <= {in_r, in_i};
                end
            end
            assign {out_r, out_i} = mem[DEPTH-1];
        end
    endgenerate
endmodule