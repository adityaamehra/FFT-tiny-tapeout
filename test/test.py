"""
test.py  —  CocoTB testbench for tt_um_fft
64-point, 6-stage SDF FFT on Tiny Tapeout (8-bit I/O)
"""

import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import numpy as np

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
CLK_PERIOD_NS = 100
N             = 64
STAGES        = int(math.log2(N))
START_BYTE    = 0xAA
SYNC_BYTE     = 0xFF
TOLERANCE_LSB = 4
SNR_FLOOR_DB  = 5.0

# ─────────────────────────────────────────────────────────────
#  Utility helpers
# ─────────────────────────────────────────────────────────────

def to_signed8(raw):
    v = int(raw) & 0xFF
    return v - 256 if v >= 128 else v

def bit_reverse(val, width=STAGES):
    return int('{:0{width}b}'.format(val, width=width)[::-1], 2)

def unwrap_bit_reverse(hw_r, hw_i):
    """Reorders Radix-2 DIF bit-reversed hardware output to natural order."""
    nat_r = np.zeros(N, dtype=int)
    nat_i = np.zeros(N, dtype=int)
    for i in range(N):
        rev = bit_reverse(i)
        nat_r[rev] = hw_r[i]
        nat_i[rev] = hw_i[i]
    return nat_r, nat_i

def hw_reference_fft(samples):
    x   = np.array(samples, dtype=float)
    X   = np.fft.fft(x) / N
    ref_r = np.clip(np.round(X.real), -128, 127).astype(int)
    ref_i = np.clip(np.round(X.imag), -128, 127).astype(int)
    return ref_r, ref_i

def check_spectrum(hw_r, hw_i, ref_r, ref_i, label):
    """Validates aligned arrays point-by-point for strict error mapping."""
    # hardware arrays must be unwrapped prior to calling this
    err_r = np.abs(hw_r - ref_r)
    err_i = np.abs(hw_i - ref_i)
    
    max_err  = float(max(np.max(err_r), np.max(err_i)))
    
    sig_pwr = np.mean(ref_r.astype(float)**2 + ref_i.astype(float)**2) + 1e-12
    nse_pwr = np.mean(err_r.astype(float)**2 + err_i.astype(float)**2) + 1e-12
    snr_db  = 10.0 * math.log10(sig_pwr / nse_pwr)

    per_bin_ok = bool(max_err <= TOLERANCE_LSB)
    snr_ok     = snr_db >= SNR_FLOOR_DB

    cocotb.log.info(
        f"  [{label}]  max_err={max_err:.1f} LSB  "
        f"SNR={snr_db:.1f} dB  "
        f"per-bin={'PASS' if per_bin_ok else 'FAIL'}  "
        f"SNR={'PASS' if snr_ok else 'FAIL'}"
    )
    return per_bin_ok and snr_ok

# ─────────────────────────────────────────────────────────────
#  DUT control helpers
# ─────────────────────────────────────────────────────────────

async def reset_dut(dut):
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def send_frame(dut, samples):
    assert len(samples) == N
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)

    for s in samples:
        dut.ui_in.value = int(s) & 0xFF
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

async def collect_frame(dut, timeout=300):
    sync_found = False
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if (int(dut.uo_out.value) == SYNC_BYTE and
                int(dut.uio_out.value) == SYNC_BYTE):
            sync_found = True
            break

    assert sync_found, f"collect_frame: SYNC marker 0xFF/0xFF not seen within {timeout} cycles."

    out_r, out_i = [], []
    for _ in range(N):
        await RisingEdge(dut.clk)
        out_r.append(to_signed8(dut.uo_out.value))
        out_i.append(to_signed8(dut.uio_out.value))

    return np.array(out_r, dtype=int), np.array(out_i, dtype=int)

# ─────────────────────────────────────────────────────────────
#  Test cases
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_all_zeros(dut):
    cocotb.log.info("━━ test_all_zeros ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    await send_frame(dut, [0] * N)
    out_r, out_i = await collect_frame(dut)

    nonzero_r = int(np.count_nonzero(out_r))
    nonzero_i = int(np.count_nonzero(out_i))

    assert nonzero_r == 0 and nonzero_i == 0
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_dc_signal(dut):
    cocotb.log.info("━━ test_dc_signal ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    level   = 32
    samples = [level] * N
    ref_r, ref_i = hw_reference_fft(samples)

    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

    hw_mag   = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    peak_bin = int(np.argmax(hw_mag))
    sidelobes = float(np.max(hw_mag[1:]))

    assert peak_bin == 0
    assert sidelobes <= TOLERANCE_LSB + 1

    ok = check_spectrum(out_r, out_i, ref_r, ref_i, "dc_signal")
    assert ok
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_impulse(dut):
    cocotb.log.info("━━ test_impulse ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    samples    = [0] * N
    samples[0] = 127
    ref_r, ref_i = hw_reference_fft(samples)

    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

    hw_mag  = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    mag_std = float(np.std(hw_mag))
    
    assert mag_std < 3.0
    ok = check_spectrum(out_r, out_i, ref_r, ref_i, "impulse")
    assert ok
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_single_tone_sine(dut):
    cocotb.log.info("━━ test_single_tone_sine ━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    k, amp = 4, 50
    t      = np.arange(N)
    raw    = amp * np.sin(2 * np.pi * k * t / N)
    samples = np.clip(np.round(raw).astype(int), -128, 127)

    ref_r, ref_i = hw_reference_fft(samples.tolist())

    await send_frame(dut, (samples & 0xFF).tolist())
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

    hw_mag   = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    peak_bin = int(np.argmax(hw_mag))

    assert peak_bin in (k, N - k)
    ok = check_spectrum(out_r, out_i, ref_r, ref_i, "single_tone_sine")
    assert ok
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_nyquist_bin(dut):
    cocotb.log.info("━━ test_nyquist_bin ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    amp     = 40
    samples = [amp if n % 2 == 0 else -amp for n in range(N)]
    ref_r, ref_i = hw_reference_fft(samples)

    await send_frame(dut, [s & 0xFF for s in samples])
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

    hw_mag   = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    peak_bin = int(np.argmax(hw_mag))

    assert peak_bin == N // 2
    ok = check_spectrum(out_r, out_i, ref_r, ref_i, "nyquist_bin")
    assert ok
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_random_data(dut):
    cocotb.log.info("━━ test_random_data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())

    seeds = [42, 137, 2025]
    all_ok = True

    for seed in seeds:
        await reset_dut(dut)

        rng     = np.random.default_rng(seed)
        samples = rng.integers(-64, 64, size=N, dtype=int)

        ref_r, ref_i = hw_reference_fft(samples.tolist())

        await send_frame(dut, (samples & 0xFF).tolist())
        raw_r, raw_i = await collect_frame(dut)
        out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

        ok = check_spectrum(out_r, out_i, ref_r, ref_i, f"random_data[seed={seed}]")
        all_ok = all_ok and ok

    assert all_ok
    cocotb.log.info("  PASSED  (all 3 seeds)")

@cocotb.test()
async def test_ena_gate(dut):
    cocotb.log.info("━━ test_ena_gate ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)

    dut.ena.value = 0
    await send_frame(dut, [64] * N)

    for _ in range(N + 70):
        await RisingEdge(dut.clk)
        uo  = int(dut.uo_out.value)
        uio = int(dut.uio_out.value)
        assert uo == 0 and uio == 0

    cocotb.log.info("  PASSED  (outputs gated to 0x00 while ena=0)")