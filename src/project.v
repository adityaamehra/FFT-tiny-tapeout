/*
 * Copyright (c) 2024 UGRA IIT(BHU)
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none
`include "top.v"
`include "Butterfly.v"
`include "delay_line.v"
`include "sdf_stage.v"
`include "twiddle_rom.v"

module tt_um_fft_adityaamehra (
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

    wire signed [7:0] y_out_r, y_out_i;
    wire top_valid;

    // 128-Cycle State Machine (64 Ingest + 64 Flush)
    reg [6:0] frame_cnt;
    reg running;

    always @(posedge clk) begin
        if (!rst_n) begin
            running   <= 1'b0;
            frame_cnt <= 7'd0;
        end else begin
            if (!running && ui_in == 8'hAA) begin
                running   <= 1'b1;
                frame_cnt <= 7'd0;
            end else if (running) begin
                if (frame_cnt == 7'd127) begin
                    running   <= 1'b0;
                    frame_cnt <= 7'd0;
                end else begin
                    frame_cnt <= frame_cnt + 1'b1;
                end
            end
        end
    end

    // Force inputs to zero during flush phase (cycles 64-127)
    wire signed [7:0] x_in_r = (running && frame_cnt < 7'd64) ? ui_in : 8'd0;

    top #(
        .N(64),
        .STAGES(6)
    ) fft_inst (
        .clk     (clk),
        .reset_n (rst_n),
        .start   (running),
        .x_in_r  (x_in_r),
        .x_in_i  (8'b0),
        .y_out_r (y_out_r),
        .y_out_i (y_out_i),
        .valid   (top_valid)
    );

    // Mask valid signal to trigger sync marker ONLY at the end of the input phase (cycle 63)
    // Prevents double-triggering when master_cnt wraps at cycle 127
    wire sync_trigger = top_valid && (frame_cnt == 7'd63);

    // 2-Stage Slip Buffer for Inline Sync Byte
    reg [7:0] slip_r, slip_i;
    reg [7:0] final_out_r, final_out_i;
    reg sync_flag;

    always @(posedge clk) begin
        if (!rst_n) begin
            slip_r      <= 8'd0;
            slip_i      <= 8'd0;
            final_out_r <= 8'd0;
            final_out_i <= 8'd0;
            sync_flag   <= 1'b0;
        end else begin
            slip_r <= y_out_r;
            slip_i <= y_out_i;

            if (sync_trigger) begin
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

    assign uo_out  = ena ? final_out_r : 8'h00;
    assign uio_out = ena ? final_out_i : 8'h00;

    wire _unused = &{uio_in, 1'b0};

endmodule