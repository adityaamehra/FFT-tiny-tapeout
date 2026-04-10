module top #(parameter N = 64, parameter STAGES = 6)(
    input  wire              clk, reset_n, start,
    input  wire signed [7:0] x_in_r, x_in_i,
    output wire signed [7:0] y_out_r, y_out_i,
    output wire valid
);
    localparam [STAGES-1:0] CNT_MAX  = 6'(N - 1);
    localparam              TADDR_W  = STAGES - 1;

    reg [STAGES-1:0] master_cnt;

    assign valid = (master_cnt == CNT_MAX) && start;

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
    assign y_out_r = pipe_r[STAGES];
    assign y_out_i = pipe_i[STAGES];

    genvar k;
    generate
        for (k = 0; k < STAGES; k = k + 1) begin : sdf_pipeline
            wire [TADDR_W-1:0] taddr;
            wire [STAGES-2:0] shifted_cnt = master_cnt << k;
            assign taddr = shifted_cnt[TADDR_W-1:0] & CNT_MAX[TADDR_W-1:0];
            sdf_stage #(
                .STAGE_ID(k),
                .N(N),
                .STAGES(STAGES)
            ) stage_inst (
                .clk        (clk),
                .reset_n    (reset_n),
                .sel        (master_cnt[STAGES-1-k]),
                .twiddle_addr(taddr),
                .x_in_r     (pipe_r[k]),
                .x_in_i     (pipe_i[k]),
                .y_out_r    (pipe_r[k+1]),
                .y_out_i    (pipe_i[k+1])
            );
        end
    endgenerate
endmodule