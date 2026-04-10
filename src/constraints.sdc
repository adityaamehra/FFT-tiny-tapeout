# ── Clock ─────────────────────────────────────────────────────────
create_clock -name clk -period 20.000 [get_ports clk]

set_clock_uncertainty -setup 0.5 [get_clocks clk]
set_clock_uncertainty -hold  0.2 [get_clocks clk]

# ── Input / Output Delays ─────────────────────────────────────────
set_input_delay  -max 2.0 -clock clk [get_ports {ui_in[*]}]
set_input_delay  -min 0.5 -clock clk [get_ports {ui_in[*]}]
set_output_delay -max 2.0 -clock clk [get_ports {uo_out[*]}]
set_output_delay -min 0.5 -clock clk [get_ports {uo_out[*]}]

# ── Bidir pins ────────────────────────────────────────────────────
set_input_delay  -max 2.0 -clock clk [get_ports {uio_in[*]}]
set_output_delay -max 2.0 -clock clk [get_ports {uio_out[*]}]

# ── Reset and enable are async → false paths ──────────────────────
set_false_path -from [get_ports rst_n]
set_false_path -from [get_ports ena]