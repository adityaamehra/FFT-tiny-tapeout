`timescale 1ns / 1ps

module Butterfly (
    input  wire  signed [7:0]    x0_r, x0_i,
    input  wire  signed [7:0]    x1_r, x1_i,
    input  wire  signed [7:0]    w_r,  w_i,
    output wire  signed [7:0]    y0_r, y0_i,
    output wire  signed [7:0]    y1_r, y1_i
);
    wire signed [8:0] sum_r  = {x0_r[7], x0_r} + {x1_r[7], x1_r};
    wire signed [8:0] sum_i  = {x0_i[7], x0_i} + {x1_i[7], x1_i};
    wire signed [8:0] diff_r = {x0_r[7], x0_r} - {x1_r[7], x1_r};
    wire signed [8:0] diff_i = {x0_i[7], x0_i} - {x1_i[7], x1_i};

    wire signed [7:0] d_r = diff_r[8:1];
    wire signed [7:0] d_i = diff_i[8:1];

    wire signed [15:0] mul_r = d_r * w_r - d_i * w_i;
    wire signed [15:0] mul_i = d_r * w_i + d_i * w_r;

    // Convergent Rounding (+0.5 LSB)
    wire signed [15:0] rnd_r = mul_r + 16'sh0040;
    wire signed [15:0] rnd_i = mul_i + 16'sh0040;

    assign y0_r = sum_r[8:1];
    assign y0_i = sum_i[8:1];
    assign y1_r = rnd_r[14:7];
    assign y1_i = rnd_i[14:7];
endmodule