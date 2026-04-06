`timescale 1ns / 1ps

module axi_fft_wrapper #(parameter N = 128)(
    input  wire        aclk, aresetn, s_axis_tvalid, s_axis_tlast, m_axis_tready,
    input  wire [7:0]  s_axis_tdata,
    output wire        s_axis_tready, m_axis_tvalid, m_axis_tlast,
    output wire [15:0] m_axis_tdata
);
    // Latency is exactly the sum of all delay lines (127 for N=128)
    localparam LATENCY = N - 1; 
    assign s_axis_tready = 1'b1;
    
    reg flushing;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) flushing <= 0;
        else if (s_axis_tlast && s_axis_tvalid) flushing <= 1;
        else if (m_axis_tlast && m_axis_tready) flushing <= 0;
    end

    wire start_fft = s_axis_tvalid || flushing;
    wire signed [7:0] y_out_r, y_out_i;

    top #(.N(N)) fft_core (
        .clk(aclk), .reset_n(aresetn), .start(start_fft),
        .x_in_r(s_axis_tvalid ? s_axis_tdata : 8'd0), .x_in_i(8'd0),
        .y_out_r(y_out_r), .y_out_i(y_out_i)
    );

    reg [LATENCY-1:0] tracker;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) tracker <= 0;
        else tracker <= {tracker[LATENCY-2:0], start_fft};
    end

    reg [6:0] out_cnt;
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) out_cnt <= 0;
        else if (m_axis_tvalid && m_axis_tready) out_cnt <= out_cnt + 1;
    end

    assign m_axis_tvalid = tracker[LATENCY-1];
    assign m_axis_tlast  = m_axis_tvalid && (out_cnt == N-1);
    assign m_axis_tdata  = {y_out_i, y_out_r}; // 16 bits: {imag[7:0], real[7:0]}
endmodule