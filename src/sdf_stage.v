module sdf_stage #(
    parameter STAGE_ID = 0, parameter N = 128, parameter STAGES = 7,
    parameter DELAY = N >> (STAGE_ID + 1)
)(
    input  wire              clk, reset_n, sel,
    input  wire [STAGES-2:0] twiddle_addr,
    input  wire signed [7:0] x_in_r, x_in_i,
    output wire signed [7:0] y_out_r, y_out_i
);
    wire signed [7:0] w_r, w_i;
    twiddle_rom #(.N(N), .ADDR_WIDTH(STAGES-1)) rom_inst (
        .addr(twiddle_addr), .w_r(w_r), .w_i(w_i)
    );

    wire signed [7:0] sr_out_r, sr_out_i, sr_in_r, sr_in_i;
    delay_line #(.DEPTH(DELAY)) dl (
        .clk(clk), .reset_n(reset_n),
        .in_r(sr_in_r), .in_i(sr_in_i),
        .out_r(sr_out_r), .out_i(sr_out_i)
    );

    wire signed [7:0] bf_y0_r, bf_y0_i, bf_y1_r, bf_y1_i;
    Butterfly bf (
        .x0_r(sr_out_r), .x0_i(sr_out_i),
        .x1_r(x_in_r),   .x1_i(x_in_i),
        .w_r(w_r),       .w_i(w_i),
        .y0_r(bf_y0_r),  .y0_i(bf_y0_i),
        .y1_r(bf_y1_r),  .y1_i(bf_y1_i)
    );

    assign sr_in_r = sel ? bf_y1_r : x_in_r;
    assign sr_in_i = sel ? bf_y1_i : x_in_i;
    assign y_out_r = sel ? bf_y0_r : sr_out_r;
    assign y_out_i = sel ? bf_y0_i : sr_out_i;
endmodule