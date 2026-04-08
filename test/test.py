# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge
import math
import cmath
import logging

N             = 64
STAGES        = 6
OUT_BITS      = 8
MAX_SIGNED    = (1 << (OUT_BITS - 1)) - 1
MIN_SIGNED    = -(1 << (OUT_BITS - 1))
CLK_PERIOD_NS = 10

TRIGGER        = 0xAA
TRIGGER_SIGNED = TRIGGER if TRIGGER < 128 else TRIGGER - 256

SINE_BIN_A  = 10
SINE_BIN_B  = 30
FULL_AMP    = MAX_SIGNED - 1
TONE_AMP    = 55
DC_VALUE    = 32
IMPULSE_AMP = MAX_SIGNED

def bit_reverse(x: int, bits: int) -> int:
    result = 0
    for _ in range(bits):
        result = (result << 1) | (x & 1)
        x >>= 1
    return result

def bit_reverse_order(seq):
    n    = len(seq)
    bits = int(round(math.log2(n)))
    out  = [(0,0)] * n
    for i in range(n):
        out[bit_reverse(i, bits)] = seq[i]
    return out

def to_signed(val: int, bits: int) -> int:
    val = val & ((1 << bits) - 1)
    return val if val < (1 << (bits - 1)) else val - (1 << bits)

def clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))

def to_unsigned8(signed_val: int) -> int:
    return clamp(signed_val, MIN_SIGNED, MAX_SIGNED) & ((1 << OUT_BITS) - 1)

def compute_peak_bin_reference(samples: list) -> int:
    mags = []
    for k in range(N):
        val = sum(
            samples[n] * cmath.exp(-2j * math.pi * k * n / N)
            for n in range(N)
        )
        mags.append(abs(val))
    best_k, best_v = -1, -1.0
    for k, v in enumerate(mags):
        if v > best_v:
            best_k, best_v = k, v
    return best_k

def _with_trigger(data_samples: list) -> list:
    return [TRIGGER] + data_samples[:N - 1]

def make_sine_frame(bin_freq: int, amplitude: int) -> list:
    data = [
        to_unsigned8(int(round(amplitude * math.sin(2.0 * math.pi * bin_freq * n / N))))
        for n in range(1, N)
    ]
    return _with_trigger(data)

def make_two_tone_frame(bin_a: int, bin_b: int, amplitude: int) -> list:
    data = [
        to_unsigned8(int(round(
            amplitude * math.sin(2.0 * math.pi * bin_a * n / N) +
            amplitude * math.sin(2.0 * math.pi * bin_b * n / N)
        )))
        for n in range(1, N)
    ]
    return _with_trigger(data)

def make_dc_frame(value: int) -> list:
    return _with_trigger([to_unsigned8(value)] * (N - 1))

def make_impulse_frame() -> list:
    return [TRIGGER] + [0] * (N - 1)

def magnitudes(results) -> list:
    return [math.sqrt(r * r + i * i) for r, i in results]

def peak_bin(mags: list) -> int:
    best_i, best_v = -1, -1.0
    for i, v in enumerate(mags):
        if v > best_v:
            best_i, best_v = i, v
    return best_i

def top_n_bins(mags: list, n: int) -> list:
    ranked = sorted(
        range(len(mags)),
        key=lambda i: -mags[i]
    )
    return ranked[:n]

async def start_clock(dut):
    dut._log.setLevel(logging.INFO)
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

async def reset_dut(dut):
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value  = 1

async def send_trigger(dut):
    await FallingEdge(dut.clk)
    dut.ui_in.value = TRIGGER
    await RisingEdge(dut.clk)

async def feed_and_collect(dut, samples: list) -> list:
    for idx, s in enumerate(samples):
        await FallingEdge(dut.clk)
        dut.ui_in.value = s

    await FallingEdge(dut.clk)
    dut.ui_in.value = 0

    # Native Hardware Alignment
    timeout = N * 4
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if int(dut.uo_out.value) == 255 and int(dut.uio_out.value) == 255:
            break
    else:
        raise AssertionError("Hardware SYNC (0xFF) timeout.")

    raw_results = [(0, 0)] * N
    for k in range(N):
        await RisingEdge(dut.clk)
        r = to_signed(int(dut.uo_out.value),  OUT_BITS)
        i = to_signed(int(dut.uio_out.value), OUT_BITS)
        raw_results[k] = (r, i)

    return bit_reverse_order(raw_results)

async def run_fft(dut, samples: list) -> list:
    await reset_dut(dut)
    return await feed_and_collect(dut, samples)

@cocotb.test()
async def test_fft_single_tone(dut):
    await start_clock(dut)
    samples = make_sine_frame(SINE_BIN_A, FULL_AMP)
    signed_samples = [to_signed(s, OUT_BITS) for s in samples]
    ref_peak = compute_peak_bin_reference(signed_samples)

    results = await run_fft(dut, samples)
    mags    = magnitudes(results)
    pb      = peak_bin(mags)

    valid_peaks = {ref_peak, N - ref_peak}
    assert pb in valid_peaks, f"Peak bin mismatch: expected one of {valid_peaks}, got {pb}."

@cocotb.test()
async def test_fft_all_zeros(dut):
    await start_clock(dut)
    await reset_dut(dut)

    for _ in range(2 * N):
        await FallingEdge(dut.clk)
        dut.ui_in.value = 0

    nonzero = []
    for k in range(N):
        await RisingEdge(dut.clk)
        uo  = to_signed(int(dut.uo_out.value),  OUT_BITS)
        uio = to_signed(int(dut.uio_out.value), OUT_BITS)
        if uo != 0 or uio != 0:
            nonzero.append((k, uo, uio))

    assert len(nonzero) == 0, f"Expected all-zero outputs, got {len(nonzero)} non-zero sample(s)."

@cocotb.test()
async def test_fft_dc_input(dut):
    await start_clock(dut)
    samples = make_dc_frame(DC_VALUE)
    signed_samples = [to_signed(s, OUT_BITS) for s in samples]
    ref_peak = compute_peak_bin_reference(signed_samples)

    results = await run_fft(dut, samples)
    mags    = magnitudes(results)
    pb      = peak_bin(mags)

    assert pb == ref_peak, f"DC test: expected peak at bin {ref_peak}, got bin {pb}."

@cocotb.test()
async def test_fft_multi_tone(dut):
    await start_clock(dut)
    samples = make_two_tone_frame(SINE_BIN_A, SINE_BIN_B, TONE_AMP)
    signed_samples = [to_signed(s, OUT_BITS) for s in samples]

    mags_ref = [
        abs(sum(signed_samples[n] * cmath.exp(-2j * math.pi * k * n / N) for n in range(N)))
        for k in range(N)
    ]
    ref_top4 = set(sorted(range(N), key=lambda k: -mags_ref[k])[:4])

    results = await run_fft(dut, samples)
    mags    = magnitudes(results)
    top2    = set(top_n_bins(mags, 2))

    assert top2.issubset(ref_top4), f"Top-2 output bins {top2} not in reference top-4 {ref_top4}."

@cocotb.test()
async def test_fft_impulse(dut):
    await start_clock(dut)
    samples = make_impulse_frame()
    results = await run_fft(dut, samples)
    mags    = magnitudes(results)

    total_energy = sum(mags)
    assert total_energy > 0, "Impulse test: total output energy is zero."

    mean_mag = total_energy / N
    max_mag  = max(mags)
    assert max_mag <= 4.0 * mean_mag + 1.0, "Impulse spectrum not flat."

@cocotb.test()
async def test_fft_reset_during_op(dut):
    await start_clock(dut)
    await reset_dut(dut)

    await send_trigger(dut)
    garbage = make_sine_frame(SINE_BIN_A, FULL_AMP)[1: N // 2]
    for s in garbage:
        await FallingEdge(dut.clk)
        dut.ui_in.value = s

    dut.rst_n.value = 0
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1

    await ClockCycles(dut.clk, N)

    samples = make_sine_frame(SINE_BIN_A, FULL_AMP)
    signed_samples = [to_signed(s, OUT_BITS) for s in samples]
    ref_peak = compute_peak_bin_reference(signed_samples)

    results = await feed_and_collect(dut, samples)
    mags    = magnitudes(results)
    pb      = peak_bin(mags)

    valid_peaks = {ref_peak, N - ref_peak}
    assert pb in valid_peaks, f"Post-reset FFT peak mismatch: expected one of {valid_peaks}, got {pb}."