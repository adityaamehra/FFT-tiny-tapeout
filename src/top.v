// top.v  –  64-point SDF FFT top-level
//
// CHANGE vs original:
//   Added a STAGES-deep shift register on the `valid` output to compensate
//   for the 1-cycle-per-stage pipeline register added in sdf_stage.v.
//   With 6 stages, real output data arrives 6 cycles after master_cnt wraps,
//   so valid must be delayed by 6 cycles to stay truthful.
//   Everything else is identical to the original.

module top #(parameter N = 64, parameter STAGES = 6)(
    input  wire              clk, reset_n, start,
    input  wire signed [7:0] x_in_r, x_in_i,
    output wire signed [7:0] y_out_r, y_out_i,
    output wire              valid
);
    localparam [STAGES-1:0] CNT_MAX = 6'(N - 1);
    localparam              TADDR_W = STAGES - 1;

    reg [STAGES-1:0] master_cnt;

    // Raw valid: asserted when the counter wraps AND the core is running
    wire valid_raw = (master_cnt == CNT_MAX) && start;

    // ── NEW: delay valid_raw by STAGES cycles ─────────────────────────────
    // Each sdf_stage now has 1 extra register before its butterfly, so the
    // output lags the counter by STAGES cycles. Shift-register the valid
    // signal by the same amount so the upstream consumer sees a correct flag.
    reg [STAGES-1:0] valid_pipe;
    always @(posedge clk) begin
        if (!reset_n)
            valid_pipe <= {STAGES{1'b0}};
        else
            valid_pipe <= {valid_pipe[STAGES-2:0], valid_raw};
    end
    assign valid = valid_pipe[STAGES-1];
    // ─────────────────────────────────────────────────────────────────────

    always @(posedge clk) begin
        if (!reset_n)
            master_cnt <= {STAGES{1'b0}};
        else if (start)
            master_cnt <= (master_cnt == CNT_MAX) ? {STAGES{1'b0}} : master_cnt + 1'b1;
        else
            master_cnt <= {STAGES{1'b0}};
    end

    wire signed [7:0] pipe_r [0:STAGES];
    wire signed [7:0] pipe_i [0:STAGES];
    assign pipe_r[0] = x_in_r;
    assign pipe_i[0] = x_in_i;
    assign y_out_r   = pipe_r[STAGES];
    assign y_out_i   = pipe_i[STAGES];

    genvar k;
    generate
        for (k = 0; k < STAGES; k = k + 1) begin : sdf_pipeline
            wire [TADDR_W-1:0] taddr;
            wire [TADDR_W-1:0] shifted_cnt = master_cnt << k;
            assign taddr = shifted_cnt & CNT_MAX;
            sdf_stage #(
                .STAGE_ID(k),
                .N(N),
                .STAGES(STAGES)
            ) stage_inst (
                .clk         (clk),
                .reset_n     (reset_n),
                .sel         (master_cnt[STAGES-1-k]),
                .twiddle_addr(taddr),
                .x_in_r      (pipe_r[k]),
                .x_in_i      (pipe_i[k]),
                .y_out_r     (pipe_r[k+1]),
                .y_out_i     (pipe_i[k+1])
            );
        end
    endgenerate

endmodule