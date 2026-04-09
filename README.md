![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# 64-Point Radix-2 SDF FFT (Tiny Tapeout)

## Overview
This repository contains a hardware implementation of a 64-point Fast Fourier Transform (FFT). It utilizes a Radix-2 Single Delay Feedback (SDF) Decimation-In-Frequency (DIF) architecture. The design is tailored for the Tiny Tapeout physical specification.

## Architectural Specifications
* **Transform Size (N):** 64 points.
* **Pipeline Stages:** 6 ($\log_2(64)$).
* **Data Format:** 8-bit signed two's complement integer.
* **Arithmetic:** Fixed-point with convergent rounding. Each butterfly stage applies an arithmetic right-shift (division by 2) to prevent overflow, resulting in a total pipeline gain of $1/64$.
* **Output Order:** Bit-reversed sequence (inherent to Radix-2 DIF).

## Pin Mapping
| Port | Width | Direction | Function |
| :--- | :--- | :--- | :--- |
| `ui_in` | 8 | Input | Signed real input data ($x_n$). |
| `uio_in` | 8 | Input | Unused. Tied low internally. |
| `uo_out` | 8 | Output | Signed real output data ($X_k$). |
| `uio_out` | 8 | Output | Signed imaginary output data ($X_k$). |
| `uio_oe` | 8 | Output | Output enable mask. Hardwired to `0xFF`. |
| `ena` | 1 | Input | Output gate. Must be `1` to propagate data to `uo_out`/`uio_out`. |
| `clk` | 1 | Input | System clock (Target: 10 MHz / 100 ns period). |
| `rst_n` | 1 | Input | Active-low asynchronous reset. |

## Execution Protocol
The pipeline is governed by a 128-cycle state machine, separating ingestion from computation flushing to prevent cross-frame memory contamination.

1.  **Arming:** The idle system detects the trigger byte `0xAA` on `ui_in`. The internal `running` state goes high on the next clock edge.
2.  **Ingest Phase (Cycles 0–63):** 64 consecutive data samples are read from `ui_in`. 
3.  **Sync Emission (Cycle 63):** A 2-stage slip buffer emits the synchronization marker `0xFF` on both `uo_out` and `uio_out`.
4.  **Flush Phase (Cycles 64–127):** The hardware forces the input to `0x00` internally. The 64 FFT bins stream out simultaneously on `uo_out` (real) and `uio_out` (imaginary) in bit-reversed order.
5.  **Halt:** At cycle 128, `running` deasserts. The system awaits the next `0xAA` trigger.

## Module Hierarchy
* `project.v` (`tt_um_fft`): Top-level wrapper. Contains the 128-cycle control state machine, zero-forcing logic during the flush phase, and the slip-buffer for sync marker emission.
* `top.v`: Iteratively generates the 6 `sdf_stage` modules and manages the master control counter for stage synchronization.
* `sdf_stage.v`: The core structural unit. Instantiates the twiddle ROM, delay line, and butterfly unit. Routes data through the delay line or butterfly based on the stage-specific timing bit derived from the master counter.
* `delay_line.v`: Shift register matrix. Depth varies per stage ($32, 16, 8, 4, 2, 1$).
* `Butterfly.v`: Radix-2 DIF arithmetic core. Computes sum $A+B$ and product $(A-B) \cdot W$. Contains intermediate bit-growth registers (16-bit) and applies $+0.5$ LSB convergent rounding prior to final 8-bit truncation.
* `twiddle_rom.v`: Asynchronous lookup table storing 32 pre-computed phase factors ($W_{64}^{0...31}$). Maps 5-bit input addresses to 8-bit signed real/imaginary coefficients.

## Testbench Metrics (CocoTB)
The `test.py` suite validates the physical design against an unquantized `numpy.fft.fft` floating-point reference.

* **Inputs Tested:** DC, unit impulse, single-tone sine, single-tone cosine, Nyquist frequency, pseudo-random noise.
* **Verification Logic:** Extracts the bit-reversed hardware output array, remaps it to natural order, and executes a point-by-point LSB deviation check against the reference array.
* **Tolerance:** Hardware output must deviate by $\leq 4$ LSBs per bin (typical observed maximum is $\sim 2.0$ LSBs due to cascaded truncation).