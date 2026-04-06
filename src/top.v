`timescale 1ns / 1ps
`include "sdf_stage.v"
`include "Butterfly.v"
`include "twiddle_rom.v"
`include "delay_line.v"
`include "axi_fft_wrapper.v"

module top #(parameter N = 128, parameter STAGES = 7)(
    input  wire              clk, reset_n, start,
    input  wire signed [7:0] x_in_r, x_in_i,
    output wire signed [7:0] y_out_r, y_out_i,
    output wire valid        // wire, driven combinatorially
);
    reg [STAGES-1:0] master_cnt;
    assign valid = (master_cnt == N-1) && start;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin 
            master_cnt <= 0; 
        end
        else if (start)
            master_cnt <= (master_cnt == N-1) ? 0 : master_cnt + 1;
        else
            master_cnt <= 0;
    end

    wire signed [7:0] pipe_r [0:STAGES], pipe_i [0:STAGES];
    assign pipe_r[0] = x_in_r;
    assign pipe_i[0] = x_in_i;
    assign y_out_r = pipe_r[STAGES];
    assign y_out_i = pipe_i[STAGES];

    genvar k;
    generate
        for (k = 0; k < STAGES; k = k + 1) begin : sdf_pipeline
            sdf_stage #(.STAGE_ID(k), .N(N), .STAGES(STAGES)) stage_inst (
                .clk(clk), .reset_n(reset_n),
                .sel(master_cnt[STAGES-1-k]),
                .twiddle_addr(((master_cnt << k) & ((N/2)-1))[STAGES-1:0]),
                .x_in_r(pipe_r[k]), .x_in_i(pipe_i[k]),
                .y_out_r(pipe_r[k+1]), .y_out_i(pipe_i[k+1])
            );
        end
    endgenerate
endmodule