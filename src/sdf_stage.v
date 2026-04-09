// sdf_stage.v  –  Single-path Delay-Feedback FFT stage
//
// CHANGE vs original:
//   Added one pipeline register bank BEFORE the Butterfly.
//   Every signal entering the multiply tree (w_r, w_i, sr_out, x_in, sel)
//   is now a flip-flop output, not a combinational ROM/mux output.
//
//   This breaks the long combinational path:
//     twiddle_addr → 32-entry case → w_r/w_i → 8×8 multiply → subtract → truncate
//   into two shorter paths:
//     path 1:  twiddle_addr → 32-entry case → [FF]
//     path 2:  [FF] → 8×8 multiply → subtract → truncate
//
//   Net effect: eliminates the primary source of max-slew violations.
//   Trade-off:  each stage adds 1 cycle of output latency (6 cycles total
//               for a 6-stage design). top.v compensates with a valid delay.

module sdf_stage #(
    parameter STAGE_ID = 0,
    parameter N        = 64,
    parameter STAGES   = 6,
    parameter DELAY    = N >> (STAGE_ID + 1)
)(
    input  wire              clk, reset_n, sel,
    input  wire [STAGES-2:0] twiddle_addr,
    input  wire signed [7:0] x_in_r, x_in_i,
    output wire signed [7:0] y_out_r, y_out_i
);

    // ── twiddle ROM (unchanged, still combinational) ──────────────────────
    wire signed [7:0] w_r, w_i;
    twiddle_rom #(.ADDR_WIDTH(STAGES-1)) rom_inst (
        .addr(twiddle_addr), .w_r(w_r), .w_i(w_i)
    );

    // ── delay line (unchanged) ────────────────────────────────────────────
    wire signed [7:0] sr_out_r, sr_out_i, sr_in_r, sr_in_i;
    delay_line #(.DEPTH(DELAY)) dl (
        .clk(clk), .reset_n(reset_n),
        .in_r(sr_in_r), .in_i(sr_in_i),
        .out_r(sr_out_r), .out_i(sr_out_i)
    );

    // ── PIPELINE REGISTER — new, inserted before butterfly ────────────────
    // Captures w_r/w_i (ROM outputs), sr_out (delay-line output),
    // x_in (stage input), and sel (control mux select) all on the same edge.
    // The butterfly now sees only flip-flop outputs, never raw combinational.
    reg signed [7:0] w_r_q,      w_i_q;
    reg signed [7:0] sr_out_r_q, sr_out_i_q;
    reg signed [7:0] x_in_r_q,   x_in_i_q;
    reg              sel_q;

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            w_r_q      <= 8'h7F;   // identity twiddle (W^0 real part)
            w_i_q      <= 8'h00;
            sr_out_r_q <= 8'h00;
            sr_out_i_q <= 8'h00;
            x_in_r_q   <= 8'h00;
            x_in_i_q   <= 8'h00;
            sel_q      <= 1'b0;
        end else begin
            w_r_q      <= w_r;
            w_i_q      <= w_i;
            sr_out_r_q <= sr_out_r;
            sr_out_i_q <= sr_out_i;
            x_in_r_q   <= x_in_r;
            x_in_i_q   <= x_in_i;
            sel_q      <= sel;
        end
    end

    // ── butterfly (combinational, unchanged logic) ────────────────────────
    // Now driven entirely by registered signals — clean, low-slew FF outputs.
    wire signed [7:0] bf_y0_r, bf_y0_i, bf_y1_r, bf_y1_i;
    Butterfly bf (
        .x0_r(sr_out_r_q), .x0_i(sr_out_i_q),   // registered delay-line out
        .x1_r(x_in_r_q),   .x1_i(x_in_i_q),     // registered stage input
        .w_r (w_r_q),      .w_i (w_i_q),         // registered ROM output
        .y0_r(bf_y0_r),    .y0_i(bf_y0_i),
        .y1_r(bf_y1_r),    .y1_i(bf_y1_i)
    );

    // ── feedback and output muxes ──────────────────────────────────────────
    // sel_q is delayed 1 cycle to stay aligned with the registered butterfly
    // inputs: at cycle N the mux routes data that was latched at cycle N-1.
    assign sr_in_r = sel_q ? bf_y1_r : x_in_r_q;
    assign sr_in_i = sel_q ? bf_y1_i : x_in_i_q;
    assign y_out_r = sel_q ? bf_y0_r : sr_out_r_q;
    assign y_out_i = sel_q ? bf_y0_i : sr_out_i_q;

endmodule