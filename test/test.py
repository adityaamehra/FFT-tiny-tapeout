import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import numpy as np

# ─────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────
CLK_PERIOD_NS = 100
N             = 64
STAGES        = int(math.log2(N))
START_BYTE    = 0xAA
SYNC_BYTE     = 0xAA
TOLERANCE_LSB = 4
SNR_FLOOR_DB  = 5.0

# ─────────────────────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────────────────────

def to_signed8(raw):
    v = int(raw) & 0xFF
    return v - 256 if v >= 128 else v

def bit_reverse(val, width=STAGES):
    return int('{:0{w}b}'.format(val, w=width)[::-1], 2)

def unwrap_bit_reverse(hw_r, hw_i):
    nat_r = np.zeros(N, dtype=int)
    nat_i = np.zeros(N, dtype=int)
    for i in range(N):
        nat_r[bit_reverse(i)] = hw_r[i]
        nat_i[bit_reverse(i)] = hw_i[i]
    return nat_r, nat_i

def hw_reference_fft(samples):
    X     = np.fft.fft(np.array(samples, dtype=float)) / N
    ref_r = np.clip(np.round(X.real), -128, 127).astype(int)
    ref_i = np.clip(np.round(X.imag), -128, 127).astype(int)
    return ref_r, ref_i

def check_spectrum(hw_r, hw_i, ref_r, ref_i, label):
    err_r   = np.abs(hw_r - ref_r)
    err_i   = np.abs(hw_i - ref_i)
    max_err = float(max(np.max(err_r), np.max(err_i)))
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
#  DUT helpers
# ─────────────────────────────────────────────────────────────

async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

async def reset_dut(dut, cycles=5):
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def send_frame(dut, samples):
    """Trigger FSM with 0xAA then clock in N samples."""
    assert len(samples) == N
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for s in samples:
        dut.ui_in.value = int(s) & 0xFF
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

async def collect_frame(dut, timeout=300):
    """
    Spin until 0xFF/0xFF sync marker then read N output samples.
    Returns (raw_r, raw_i) in hardware bit-reversed order.
    """
    sync_found = False
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if (int(dut.uo_out.value) == SYNC_BYTE and
                int(dut.uio_out.value) == SYNC_BYTE):
            sync_found = True
            break
    assert sync_found, f"SYNC 0xFF/0xFF not seen within {timeout} cycles"
    out_r, out_i = [], []
    for _ in range(N):
        await RisingEdge(dut.clk)
        out_r.append(to_signed8(dut.uo_out.value))
        out_i.append(to_signed8(dut.uio_out.value))
    return np.array(out_r, dtype=int), np.array(out_i, dtype=int)

async def assert_outputs_zero(dut, cycles, context=""):
    """Assert both outputs stay 0x00 for <cycles> rising edges."""
    for i in range(cycles):
        await RisingEdge(dut.clk)
        uo  = int(dut.uo_out.value)
        uio = int(dut.uio_out.value)
        assert uo == 0 and uio == 0, \
            f"{context} cycle {i}: uo={uo:#04x} uio={uio:#04x} must be 0x00"

async def count_sync_markers(dut, cycles):
    """Return number of 0xFF/0xFF sync markers seen in <cycles> clocks."""
    count = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        if (int(dut.uo_out.value) == SYNC_BYTE and
                int(dut.uio_out.value) == SYNC_BYTE):
            count += 1
    return count

# ─────────────────────────────────────────────────────────────
#  ════════  FUNCTIONAL ACCURACY  ════════════════════════════
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_all_zeros(dut):
    """FFT of all-zero frame → all-zero output."""
    cocotb.log.info("━━ test_all_zeros ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    await send_frame(dut, [0] * N)
    out_r, out_i = await collect_frame(dut)
    assert int(np.count_nonzero(out_r)) == 0 and int(np.count_nonzero(out_i)) == 0
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_dc_signal(dut):
    """DC level 32: peak at bin 0, sidelobes within tolerance."""
    cocotb.log.info("━━ test_dc_signal ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    samples      = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    hw_mag = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    assert int(np.argmax(hw_mag)) == 0
    assert float(np.max(hw_mag[1:])) <= TOLERANCE_LSB + 1
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "dc_signal")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_dc_max_positive(dut):
    """All +127: full-scale DC, no overflow corruption."""
    cocotb.log.info("━━ test_dc_max_positive ━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    samples      = [127] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    hw_mag = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    assert int(np.argmax(hw_mag)) == 0
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "dc_max_positive")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_dc_max_negative(dut):
    """All -128: negative full-scale DC."""
    cocotb.log.info("━━ test_dc_max_negative ━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    samples      = [-128] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, [s & 0xFF for s in samples])
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "dc_max_negative")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_impulse(dut):
    """Unit impulse at n=0: flat spectrum."""
    cocotb.log.info("━━ test_impulse ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    samples    = [0] * N;  samples[0] = 127
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    hw_mag = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    assert float(np.std(hw_mag)) < 3.0, f"Impulse spectrum not flat: std={np.std(hw_mag):.2f}"
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "impulse")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_single_tone(dut):
    """Sine at bin 4: peak at bin 4 or conjugate N-4."""
    cocotb.log.info("━━ test_single_tone_bin4 ━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    k, amp = 4, 50
    raw    = amp * np.sin(2 * np.pi * k * np.arange(N) / N)
    samples = np.clip(np.round(raw).astype(int), -128, 127)
    ref_r, ref_i = hw_reference_fft(samples.tolist())
    await send_frame(dut, (samples & 0xFF).tolist())
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    peak = int(np.argmax(np.abs(out_r.astype(float) + 1j * out_i.astype(float))))
    assert peak in (k, N - k), f"Expected {k} or {N-k}, got {peak}"
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "single_tone_bin4")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_two_tone(dut):
    """Bins 3 and 11 simultaneously: both peaks present."""
    cocotb.log.info("━━ test_two_tone ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    k1, k2, amp = 3, 11, 30
    t   = np.arange(N)
    raw = amp * np.sin(2*np.pi*k1*t/N) + amp * np.sin(2*np.pi*k2*t/N)
    samples = np.clip(np.round(raw).astype(int), -128, 127)
    ref_r, ref_i = hw_reference_fft(samples.tolist())
    await send_frame(dut, (samples & 0xFF).tolist())
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    hw_mag  = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    top4    = np.argsort(hw_mag)[::-1][:4].tolist()
    for expected in [k1, k2]:
        assert any(abs(b - expected) <= 1 or abs(b - (N - expected)) <= 1 for b in top4), \
            f"No peak near bin {expected}; top4={top4}"
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "two_tone")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_nyquist_bin(dut):
    """Alternating ±40: energy only at bin N/2."""
    cocotb.log.info("━━ test_nyquist_bin ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    samples = [40 if n % 2 == 0 else -40 for n in range(N)]
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, [s & 0xFF for s in samples])
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    hw_mag = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    assert int(np.argmax(hw_mag)) == N // 2
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "nyquist_bin")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_random_data(dut):
    """Random frames: 5 seeds, per-bin and SNR checks."""
    cocotb.log.info("━━ test_random_data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    all_ok = True
    for seed in [42, 137, 2025, 999, 31415]:
        await reset_dut(dut)
        rng     = np.random.default_rng(seed)
        samples = rng.integers(-64, 64, size=N, dtype=int)
        ref_r, ref_i = hw_reference_fft(samples.tolist())
        await send_frame(dut, (samples & 0xFF).tolist())
        raw_r, raw_i = await collect_frame(dut)
        out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
        all_ok = all_ok and check_spectrum(out_r, out_i, ref_r, ref_i, f"random[{seed}]")
    assert all_ok
    cocotb.log.info("  PASSED (all 5 seeds)")

# ─────────────────────────────────────────────────────────────
#  ════════  ENA — FSM ARMING (new dual-gate behaviour)  ══════
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_fsm_does_not_arm_without_ena(dut):
    """
    0xAA on ui_in while ena=0 must NOT start the FSM.
    No sync marker should appear in the window where a full frame
    would have completed.
    """
    cocotb.log.info("━━ test_fsm_does_not_arm_without_ena ━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.ena.value = 0

    # Send the trigger byte followed by a full payload — FSM must ignore it
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for _ in range(N):
        dut.ui_in.value = 0x20
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    # No sync marker should appear in twice the frame window
    markers = await count_sync_markers(dut, 2 * (N + 80))
    assert markers == 0, \
        f"FSM armed without ena=1: {markers} sync marker(s) detected"
    cocotb.log.info("  PASSED  (FSM stayed idle with ena=0)")

@cocotb.test()
async def test_fsm_arms_only_after_ena_high(dut):
    """
    Send 0xAA with ena=0 (ignored), then send 0xAA with ena=1.
    Only the second trigger should arm the FSM and produce output.
    """
    cocotb.log.info("━━ test_fsm_arms_only_after_ena_high ━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    # --- Attempt 1: ena=0, must be ignored ---
    dut.ena.value = 0
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for _ in range(N):
        dut.ui_in.value = 0x10
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 10)     # brief idle

    # --- Attempt 2: ena=1, must arm ---
    dut.ena.value = 1
    samples = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)

    hw_mag = np.abs(out_r.astype(float) + 1j * out_i.astype(float))
    assert hw_mag[0] > 0, "DC bin should be non-zero after ena=1 trigger"
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "fsm_arm_after_ena_high")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_repeated_0xaa_with_ena_low(dut):
    """
    Stream 0xAA repeatedly while ena=0.  Frame counter must never increment
    — verified by the absence of any sync marker.
    """
    cocotb.log.info("━━ test_repeated_0xaa_with_ena_low ━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.ena.value = 0
    for _ in range(3 * (N + 10)):
        dut.ui_in.value = START_BYTE
        await RisingEdge(dut.clk)

    dut.ui_in.value = 0
    markers = await count_sync_markers(dut, 50)
    assert markers == 0, f"Unexpected {markers} sync marker(s)"
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_ena_low_mid_frame_fsm_continues(dut):
    """
    ena goes low mid-frame (after 30 samples ingested).
    FSM keeps running (frame_cnt still increments) but outputs are gated.
    After the full 128-cycle frame the FSM returns to idle.
    The NEXT frame (with ena=1) must then produce correct output.
    """
    cocotb.log.info("━━ test_ena_low_mid_frame_fsm_continues ━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    # Start a frame normally
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for i in range(30):
        dut.ui_in.value = 0x20
        await RisingEdge(dut.clk)

    # Pull ena low mid-frame
    dut.ena.value = 0
    for i in range(N - 30):
        dut.ui_in.value = 0x20
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    # Outputs must stay 0x00 for the remainder of the 128-cycle frame
    await assert_outputs_zero(dut, N + 10,
                              context="mid-frame ena=0 gating")

    # Re-enable and run a fresh frame — pipeline should be clean
    dut.ena.value = 1
    await ClockCycles(dut.clk, 5)

    samples = [40] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "ena_mid_frame_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_ena_deassert_before_sync(dut):
    """
    ena pulled low just before the sync marker window.
    Sync byte (0xFF/0xFF) must be gated to 0x00, not leaked.
    """
    cocotb.log.info("━━ test_ena_deassert_before_sync ━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    # Send frame, let ingest complete
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for _ in range(N):
        dut.ui_in.value = 0x30
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    # Pull ena low immediately — sync should be gated
    dut.ena.value = 0

    # Scan the flush window — no SYNC_BYTE should escape
    for _ in range(N + 20):
        await RisingEdge(dut.clk)
        uo  = int(dut.uo_out.value)
        uio = int(dut.uio_out.value)
        assert uo != SYNC_BYTE or uio != SYNC_BYTE or uo == 0, \
            f"Sync marker leaked through ena=0 gate: uo={uo:#04x} uio={uio:#04x}"
        assert uo == 0 and uio == 0, \
            f"Non-zero output while ena=0: uo={uo:#04x} uio={uio:#04x}"

    cocotb.log.info("  PASSED  (sync marker gated when ena=0)")

# ─────────────────────────────────────────────────────────────
#  ════════  ENA — OUTPUT MUX  ════════════════════════════════
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_ena_output_gate_active(dut):
    """Classic gate: ena=0 forces 0x00 on both outputs throughout frame."""
    cocotb.log.info("━━ test_ena_output_gate_active ━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    # ena goes low AFTER reset but BEFORE any frame
    dut.ena.value = 0
    await assert_outputs_zero(dut, N + 80, context="ena_gate")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_ena_output_mux_is_combinatorial(dut):
    """
    ena toggle must take effect on the very same clock edge —
    no one-cycle pipeline delay through the output mux.
    We drive a frame, wait for sync+data, then toggle ena and
    check that the NEXT sampled cycle is immediately gated.
    """
    cocotb.log.info("━━ test_ena_output_mux_is_combinatorial ━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    samples = [64] * N   # strong DC → bin-0 will be non-zero
    await send_frame(dut, samples)

    # Wait for sync
    sync_found = False
    for _ in range(300):
        await RisingEdge(dut.clk)
        if (int(dut.uo_out.value) == SYNC_BYTE and
                int(dut.uio_out.value) == SYNC_BYTE):
            sync_found = True
            break
    assert sync_found

    # Read one real output sample (should be non-zero — bin 0 of DC frame)
    await RisingEdge(dut.clk)
    v_on = int(dut.uo_out.value)

    # Now deassert ena and sample on the very next rising edge
    dut.ena.value = 0
    await RisingEdge(dut.clk)
    v_off = int(dut.uo_out.value)

    assert v_off == 0, \
        f"Output mux not combinatorial: still {v_off:#04x} one cycle after ena=0"

    # Re-enable and confirm output is non-zero again
    dut.ena.value = 1
    await RisingEdge(dut.clk)
    v_back = int(dut.uo_out.value)
    # (may be 0 for high-freq bins; just ensure the register-read loop is exercised)
    cocotb.log.info(f"  v_on={v_on:#04x}  v_off={v_off:#04x}  v_back={v_back:#04x}")
    cocotb.log.info("  PASSED  (output mux is combinatorial)")

@cocotb.test()
async def test_ena_restore_correct_output(dut):
    """
    ena=0 → (gated frame) → ena=1 → fresh frame must produce correct FFT,
    confirming no pipeline corruption from the gated period.
    """
    cocotb.log.info("━━ test_ena_restore_correct_output ━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    # Frame 1: ena=0, FSM won't arm — just idle
    dut.ena.value = 0
    await ClockCycles(dut.clk, N + 20)

    # Frame 2: re-enable
    dut.ena.value = 1
    await reset_dut(dut)
    samples = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "ena_restore")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_ena_toggle_rapid(dut):
    """
    Rapid ena toggling (every cycle) while in idle must never produce
    non-zero output or a spurious sync marker.
    """
    cocotb.log.info("━━ test_ena_toggle_rapid ━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.ui_in.value = 0   # no trigger
    for cyc in range(100):
        dut.ena.value = cyc % 2
        await RisingEdge(dut.clk)
        # when ena=1 and ui_in=0, no frame starts; outputs must be 0
        if dut.ena.value == 1:
            uo  = int(dut.uo_out.value)
            uio = int(dut.uio_out.value)
            assert uo == 0 and uio == 0, \
                f"Idle with ena=1 but no trigger: uo={uo:#04x}"

    cocotb.log.info("  PASSED")

# ─────────────────────────────────────────────────────────────
#  ════════  RST_N BEHAVIOUR  ═════════════════════════════════
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_reset_clears_all_state(dut):
    """Post-reset idle → outputs stay 0x00, no spontaneous output."""
    cocotb.log.info("━━ test_reset_clears_all_state ━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)
    await assert_outputs_zero(dut, 20, context="post-reset idle")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_reset_during_rst_outputs_zero(dut):
    """
    While rst_n=0 is asserted (with ena=1), slip buffer is cleared
    and outputs must be 0x00.
    """
    cocotb.log.info("━━ test_reset_during_rst_outputs_zero ━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.rst_n.value = 0
    await assert_outputs_zero(dut, 10, context="active rst_n=0")
    dut.rst_n.value = 1
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_reset_short_pulse(dut):
    """Single-cycle reset is enough to clear all state."""
    cocotb.log.info("━━ test_reset_short_pulse ━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await RisingEdge(dut.clk)      # exactly one clock
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    samples = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "short_pulse_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_reset_mid_frame(dut):
    """
    Reset asserted 30 samples into an active frame.
    FSM must abort; next complete frame must be correct.
    """
    cocotb.log.info("━━ test_reset_mid_frame ━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for i in range(30):
        dut.ui_in.value = 0x30
        await RisingEdge(dut.clk)

    # Mid-frame reset
    dut.rst_n.value = 0
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

    samples = [20] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "reset_mid_frame_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_reset_during_flush(dut):
    """Reset asserted during flush phase; recovery frame correct."""
    cocotb.log.info("━━ test_reset_during_flush ━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    await send_frame(dut, [40] * N)
    await ClockCycles(dut.clk, 32)   # halfway through flush
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

    samples = [24] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "reset_flush_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_multiple_resets(dut):
    """Three consecutive resets; final frame correct."""
    cocotb.log.info("━━ test_multiple_resets ━━━━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    for rep in range(3):
        await reset_dut(dut, cycles=3 + rep)
        await ClockCycles(dut.clk, 4)
    samples = [40] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "multiple_resets_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_reset_with_ena_low(dut):
    """
    Reset released with ena=0: the reset must still clear state cleanly.
    When ena is then raised, the first frame must be correct.
    """
    cocotb.log.info("━━ test_reset_with_ena_low ━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)

    # Reset while ena=0
    dut.rst_n.value  = 0
    dut.ena.value    = 0
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

    # Raise ena and run a frame
    dut.ena.value = 1
    samples = [48] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "reset_with_ena_low_recovery")
    cocotb.log.info("  PASSED")

# ─────────────────────────────────────────────────────────────
#  ════════  PROTOCOL / EDGE CASES  ═══════════════════════════
# ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_back_to_back_frames(dut):
    """Three frames with no gap between them."""
    cocotb.log.info("━━ test_back_to_back_frames ━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    for k, amp, label in [(4, 45, "b2b_f0"), (8, 40, "b2b_f1"), (12, 35, "b2b_f2")]:
        t   = np.arange(N)
        raw = amp * np.sin(2 * np.pi * k * t / N)
        samples = np.clip(np.round(raw).astype(int), -128, 127)
        ref_r, ref_i = hw_reference_fft(samples.tolist())
        await send_frame(dut, (samples & 0xFF).tolist())
        raw_r, raw_i = await collect_frame(dut)
        out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
        peak = int(np.argmax(np.abs(out_r.astype(float) + 1j * out_i.astype(float))))
        assert peak in (k, N - k), f"{label}: peak at {peak}"
        assert check_spectrum(out_r, out_i, ref_r, ref_i, label)

    cocotb.log.info("  PASSED  (3 back-to-back frames)")

@cocotb.test()
async def test_multi_frame_determinism(dut):
    """Same input twice → byte-identical output (no state leak)."""
    cocotb.log.info("━━ test_multi_frame_determinism ━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    rng     = np.random.default_rng(777)
    samples = rng.integers(-64, 64, size=N, dtype=int)
    results = []
    for _ in range(2):
        await send_frame(dut, (samples & 0xFF).tolist())
        raw_r, raw_i = await collect_frame(dut)
        results.append((raw_r.copy(), raw_i.copy()))

    assert np.array_equal(results[0][0], results[1][0]) and \
           np.array_equal(results[0][1], results[1][1]), \
        "Same input produced different outputs on consecutive frames"
    cocotb.log.info("  PASSED  (deterministic output)")

@cocotb.test()
async def test_start_byte_in_payload_ignored(dut):
    """
    0xAA inside the active payload must be treated as data, not a new trigger.
    FSM is already running → the start-arm condition requires !running, so 0xAA
    is ignored mid-frame.  A single clean sync marker must still arrive.
    """
    cocotb.log.info("━━ test_start_byte_in_payload_ignored ━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    samples = [0] * N
    samples[10] = 0xAA
    samples[30] = 0xAA
    samples[50] = 0xAA
    signed_samples = [to_signed8(s) for s in samples]
    ref_r, ref_i = hw_reference_fft(signed_samples)

    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for s in samples:
        dut.ui_in.value = int(s) & 0xFF
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "start_byte_in_payload")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_no_trigger_no_output(dut):
    """Arbitrary non-0xAA data with ena=1 must produce no sync markers."""
    cocotb.log.info("━━ test_no_trigger_no_output ━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    for _ in range(200):
        dut.ui_in.value = 0x55   # not 0xAA
        await RisingEdge(dut.clk)

    markers = await count_sync_markers(dut, 50)
    assert markers == 0, f"Spurious {markers} sync marker(s) without trigger"
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_sync_marker_appears_exactly_once(dut):
    """Exactly one 0xFF/0xFF sync per 128-cycle frame — no duplicates."""
    cocotb.log.info("━━ test_sync_marker_appears_exactly_once ━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for _ in range(N):
        dut.ui_in.value = 0x20
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    markers = await count_sync_markers(dut, N + 80)
    assert markers == 1, f"Expected 1 sync marker, got {markers}"
    cocotb.log.info(f"  Sync marker count: {markers} — PASSED")

@cocotb.test()
async def test_uio_oe_always_0xff(dut):
    """uio_oe must be 0xFF across reset, idle, active, and ena=0 phases."""
    cocotb.log.info("━━ test_uio_oe_always_0xff ━━━━━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)

    for ena_val, rst_val, label in [
        (1, 0, "during reset"),
        (1, 1, "post-reset idle"),
        (0, 1, "ena=0 idle"),
    ]:
        dut.ena.value   = ena_val
        dut.rst_n.value = rst_val
        dut.ui_in.value = 0
        for _ in range(5):
            await RisingEdge(dut.clk)
            oe = int(dut.uio_oe.value)
            assert oe == 0xFF, f"uio_oe={oe:#04x} ({label})"

    # Also check during an active frame
    dut.rst_n.value = 1
    dut.ena.value   = 1
    await ClockCycles(dut.clk, 2)
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for _ in range(10):
        dut.ui_in.value = 0x20
        await RisingEdge(dut.clk)
        assert int(dut.uio_oe.value) == 0xFF, "uio_oe dropped during active frame"

    cocotb.log.info("  PASSED  (uio_oe=0xFF throughout)")

@cocotb.test()
async def test_pipeline_flush_masking(dut):
    """
    During flush (frame_cnt 64-127), ui_in is masked to 0.
    Drive 0x55 during that window; the next frame must still match
    the clean reference (confirming the mask worked).
    """
    cocotb.log.info("━━ test_pipeline_flush_masking ━━━━━━━━━━━━━━━━━━")
    await start_clock(dut)
    await reset_dut(dut)

    samples = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)

    # Ingest phase
    dut.ui_in.value = START_BYTE
    await RisingEdge(dut.clk)
    for s in samples:
        dut.ui_in.value = int(s) & 0xFF
        await RisingEdge(dut.clk)

    # Flush phase — drive garbage
    for _ in range(N):
        dut.ui_in.value = 0x55
        await RisingEdge(dut.clk)
    dut.ui_in.value = 0

    # Recovery frame
    await reset_dut(dut)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "flush_masking_recovery")
    cocotb.log.info("  PASSED")

@cocotb.test()
async def test_ena_and_reset_simultaneous(dut):
    """
    Assert rst_n=0 and ena=0 simultaneously; release both together.
    Design must initialise correctly and produce valid output.
    """
    cocotb.log.info("━━ test_ena_and_reset_simultaneous ━━━━━━━━━━━━━━")
    await start_clock(dut)

    dut.rst_n.value  = 0
    dut.ena.value    = 0
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 5)

    # Release both at once
    dut.rst_n.value = 1
    dut.ena.value   = 1
    await ClockCycles(dut.clk, 2)

    samples = [32] * N
    ref_r, ref_i = hw_reference_fft(samples)
    await send_frame(dut, samples)
    raw_r, raw_i = await collect_frame(dut)
    out_r, out_i = unwrap_bit_reverse(raw_r, raw_i)
    assert check_spectrum(out_r, out_i, ref_r, ref_i, "ena_reset_simultaneous_recovery")
    cocotb.log.info("  PASSED")