module twiddle_rom #(
    parameter ADDR_WIDTH = 6
)(
    input  wire [ADDR_WIDTH-1:0]     addr,
    output reg  signed [7:0]         w_r,
    output reg  signed [7:0]         w_i
);
    wire [4:0]  base_addr   = addr[4:0];
    wire        phase_shift = addr[4];
    reg signed [7:0] lut_r, lut_i;

    always @(*) begin
        case (base_addr)
            5'd0 : begin lut_r = 8'h7F; lut_i = 8'h00; end
            5'd1 : begin lut_r = 8'h7F; lut_i = 8'hFA; end
            5'd2 : begin lut_r = 8'h7E; lut_i = 8'hF4; end
            5'd3 : begin lut_r = 8'h7E; lut_i = 8'hED; end
            5'd4 : begin lut_r = 8'h7D; lut_i = 8'hE7; end
            5'd5 : begin lut_r = 8'h7B; lut_i = 8'hE1; end
            5'd6 : begin lut_r = 8'h7A; lut_i = 8'hDB; end
            5'd7 : begin lut_r = 8'h78; lut_i = 8'hD5; end
            5'd8 : begin lut_r = 8'h75; lut_i = 8'hCF; end
            5'd9 : begin lut_r = 8'h73; lut_i = 8'hCA; end
            5'd10: begin lut_r = 8'h70; lut_i = 8'hC4; end
            5'd11: begin lut_r = 8'h6D; lut_i = 8'hBF; end
            5'd12: begin lut_r = 8'h6A; lut_i = 8'hB9; end
            5'd13: begin lut_r = 8'h66; lut_i = 8'hB4; end
            5'd14: begin lut_r = 8'h62; lut_i = 8'hAF; end
            5'd15: begin lut_r = 8'h5E; lut_i = 8'hAB; end
            5'd16: begin lut_r = 8'h5A; lut_i = 8'hA6; end
            5'd17: begin lut_r = 8'h55; lut_i = 8'hA2; end
            5'd18: begin lut_r = 8'h51; lut_i = 8'h9E; end
            5'd19: begin lut_r = 8'h4C; lut_i = 8'h9A; end
            5'd20: begin lut_r = 8'h47; lut_i = 8'h96; end
            5'd21: begin lut_r = 8'h41; lut_i = 8'h93; end
            5'd22: begin lut_r = 8'h3C; lut_i = 8'h90; end
            5'd23: begin lut_r = 8'h36; lut_i = 8'h8D; end
            5'd24: begin lut_r = 8'h31; lut_i = 8'h8B; end
            5'd25: begin lut_r = 8'h2B; lut_i = 8'h88; end
            5'd26: begin lut_r = 8'h25; lut_i = 8'h86; end
            5'd27: begin lut_r = 8'h1F; lut_i = 8'h85; end
            5'd28: begin lut_r = 8'h19; lut_i = 8'h83; end
            5'd29: begin lut_r = 8'h13; lut_i = 8'h82; end
            5'd30: begin lut_r = 8'h0C; lut_i = 8'h82; end
            5'd31: begin lut_r = 8'h06; lut_i = 8'h81; end
            default: begin lut_r = 8'h7F; lut_i = 8'h00; end
        endcase
    end

    always @(*) begin
        if (!phase_shift) begin
            w_r = lut_r; w_i = lut_i;
        end else begin
            w_r = lut_i; w_i = -lut_r;
        end
    end
endmodule