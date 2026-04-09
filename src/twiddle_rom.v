module twiddle_rom #(
    parameter ADDR_WIDTH = 5
)(
    input  wire [ADDR_WIDTH-1:0]     addr,
    output reg  signed [7:0]         w_r,
    output reg  signed [7:0]         w_i
);

    always @(*) begin
        case (addr)
            5'd0 : begin w_r = 8'h7F; w_i = 8'h00; end
            5'd1 : begin w_r = 8'h7E; w_i = 8'hF4; end
            5'd2 : begin w_r = 8'h7D; w_i = 8'hE7; end
            5'd3 : begin w_r = 8'h79; w_i = 8'hDB; end
            5'd4 : begin w_r = 8'h75; w_i = 8'hCF; end
            5'd5 : begin w_r = 8'h70; w_i = 8'hC4; end
            5'd6 : begin w_r = 8'h6A; w_i = 8'hB9; end
            5'd7 : begin w_r = 8'h62; w_i = 8'hAE; end
            5'd8 : begin w_r = 8'h5A; w_i = 8'hA6; end
            5'd9 : begin w_r = 8'h52; w_i = 8'h9E; end
            5'd10: begin w_r = 8'h47; w_i = 8'h96; end
            5'd11: begin w_r = 8'h3C; w_i = 8'h90; end
            5'd12: begin w_r = 8'h31; w_i = 8'h8B; end
            5'd13: begin w_r = 8'h25; w_i = 8'h87; end
            5'd14: begin w_r = 8'h19; w_i = 8'h83; end
            5'd15: begin w_r = 8'h0C; w_i = 8'h82; end
            5'd16: begin w_r = 8'h00; w_i = 8'h81; end
            5'd17: begin w_r = 8'hF4; w_i = 8'h82; end
            5'd18: begin w_r = 8'hE7; w_i = 8'h83; end
            5'd19: begin w_r = 8'hDB; w_i = 8'h87; end
            5'd20: begin w_r = 8'hCF; w_i = 8'h8B; end
            5'd21: begin w_r = 8'hC4; w_i = 8'h90; end
            5'd22: begin w_r = 8'hB9; w_i = 8'h96; end
            5'd23: begin w_r = 8'hAE; w_i = 8'h9E; end
            5'd24: begin w_r = 8'hA6; w_i = 8'hA6; end
            5'd25: begin w_r = 8'h9E; w_i = 8'hAE; end
            5'd26: begin w_r = 8'h96; w_i = 8'hB9; end
            5'd27: begin w_r = 8'h90; w_i = 8'hC4; end
            5'd28: begin w_r = 8'h8B; w_i = 8'hCF; end
            5'd29: begin w_r = 8'h87; w_i = 8'hDB; end
            5'd30: begin w_r = 8'h83; w_i = 8'hE7; end
            5'd31: begin w_r = 8'h82; w_i = 8'hF4; end
            default: begin w_r = 8'h7F; w_i = 8'h00; end
        endcase
    end
endmodule