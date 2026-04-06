/*
 * Copyright (c) 2024 UGRA IIT(BHU)
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module tt_um_fft (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    assign uio_oe = 8'hFF;

    wire valid;
    wire signed [7:0] x_in_r;
    wire signed [7:0] y_out_r, y_out_i;

    assign x_in_r = ui_in;

    reg start_latch;
    always @(posedge clk) begin
        if (!rst_n)
            start_latch <= 1'b0;
        else if (ui_in == 8'b1010_1010)
            start_latch <= 1'b1;
    end

    wire start;
    assign start = start_latch || (ui_in == 8'b1010_1010);

    top #(
        .N(128),
        .STAGES(7)
    ) fft_inst (
        .clk     (clk),
        .reset_n (rst_n),
        .start   (start),
        .x_in_r  (x_in_r),
        .x_in_i  (8'b0),
        .y_out_r (y_out_r),
        .y_out_i (y_out_i),
        .valid   (valid)
    );

    // 2-Stage Slip Buffer for Inline Sync Byte
    reg [7:0] slip_r, slip_i;
    reg [7:0] final_out_r, final_out_i;
    reg sync_flag;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            slip_r      <= 8'd0;
            slip_i      <= 8'd0;
            final_out_r <= 8'd0;
            final_out_i <= 8'd0;
            sync_flag   <= 1'b0;
        end else begin
            slip_r <= y_out_r;
            slip_i <= y_out_i;

            if (valid) begin
                sync_flag   <= 1'b1;
                final_out_r <= 8'hFF;
                final_out_i <= 8'hFF;
            end else if (sync_flag) begin
                sync_flag   <= 1'b0;
                final_out_r <= slip_r; 
                final_out_i <= slip_i;
            end else begin
                final_out_r <= slip_r; 
                final_out_i <= slip_i;
            end
        end
    end

    assign uo_out  = final_out_r;
    assign uio_out = final_out_i;

    wire _unused = &{uio_in, ena, 1'b0};

endmodule