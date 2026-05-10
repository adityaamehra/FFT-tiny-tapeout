# ── Clock ─────────────────────────────────────────────────────────
create_clock -name clk -period 100.000 [get_ports clk]

set_clock_uncertainty -setup 0.5 [get_clocks clk]
set_clock_uncertainty -hold  0.2 [get_clocks clk]

# ── Input / Output Delays ─────────────────────────────────────────
# cause we will we driving this with an FPGA we have to give more input delays so that things can be driven easier
set_input_delay  -max 20.0 -clock clk [get_ports {ui_in[*]}] 
set_input_delay  -min 0.5 -clock clk [get_ports {ui_in[*]}]
set_output_delay -max 20.0 -clock clk [get_ports {uo_out[*]}]
set_output_delay -min 0.5 -clock clk [get_ports {uo_out[*]}]

# ── Bidir pins ────────────────────────────────────────────────────
set_input_delay  -max 20.0 -clock clk [get_ports {uio_in[*]}]
set_output_delay -max 20.0 -clock clk [get_ports {uio_out[*]}]