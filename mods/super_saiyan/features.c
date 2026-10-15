/*
 * Table-driven input features, configured by the companion app. Runs on every input
 * frame (any controller, any output mode), after the touchpad mouse.
 *
 * Buttons are handled as a 20-bit logical bitmap (LB_*), so every setting works the
 * same on every controller: SOCD -> toggle (latch) -> turbo -> remap.
 */
#include "ss.h"

#define DPAD_BITS  (1u << LB_UP | 1u << LB_DOWN | 1u << LB_LEFT | 1u << LB_RIGHT)
#define FULL       32767

static int16_t clamp16(int32_t v) { return v > FULL ? FULL : v < -FULL ? -FULL : (int16_t)v; }

static uint32_t isqrt(uint32_t v)
{
    uint32_t r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= r + bit) { v -= r + bit; r = (r >> 1) + bit; }
        else r >>= 1;
        bit >>= 2;
    }
    return r;
}

/* Radial deadzone + anti-deadzone + response curve for one stick. */
static void stick(int16_t *px, int16_t *py, int i)
{
    int32_t x = *px, y = *py;
    uint32_t mag = isqrt((uint32_t)(x * x) + (uint32_t)(y * y));
    uint32_t dz = ss.stick_dz[i] * 327u, anti = ss.stick_anti_dz[i] * 327u;
    if (mag <= dz) { *px = *py = 0; return; }
    if (!dz && !anti && !ss.stick_curve[i]) return;
    uint32_t m = mag > FULL ? FULL : mag;
    uint32_t out = (m - dz) * FULL / (FULL - dz);                 /* 0..FULL */
    out += (int32_t)ss.stick_curve[i] * ((int32_t)(out * out / FULL) - (int32_t)out) / 100;
    out = anti + out * (FULL - anti) / FULL;
    *px = clamp16(x * (int32_t)out / (int32_t)mag);
    *py = clamp16(y * (int32_t)out / (int32_t)mag);
}

static uint16_t trigger(uint16_t v, int i)
{
    uint32_t d = ss.trig_dz[i] * 327u;
    if (v <= d) return 0;
    if (ss.trig_flags & (TF_HAIR_L << i)) return FULL;
    return (uint16_t)((v - d) * FULL / (FULL - d));
}

#define NOINLINE __attribute__((noinline))

static uint32_t prev_in, latch, last_lr, last_ud;

static NOINLINE void axis_flags(cntlr_state_t *s)
{
    uint8_t f = ss.stick_flags;
    int16_t *axis = &s->lx;                           /* lx, ly, rx, ry; SF_INV_* bits 0-3 */
    for (int i = 0; i < 4; i++)
        if (f >> i & 1) axis[i] = ~axis[i];           /* -x-1: no overflow at -32768 */
    if (f & SF_SWAP_STICKS) {
        int16_t t = s->lx; s->lx = s->rx; s->rx = t;
        t = s->ly; s->ly = s->ry; s->ry = t;
    }
}

static NOINLINE void sticks_triggers(cntlr_state_t *s)
{
    stick(&s->lx, &s->ly, 0);
    stick(&s->rx, &s->ry, 1);
    axis_flags(s);
    s->zl = trigger(s->zl, 0);
    s->zr = trigger(s->zr, 1);
}

/* native button bits -> logical bitmap; *native = every bit the table maps */
static NOINLINE uint32_t buttons_in(const cntlr_state_t *s, uint32_t *native)
{
    uint32_t in = 0, all = 0;
    for (int i = 0; i < LB_COUNT; i++) {
        uint32_t m = lb_mask(s, i);
        all |= m;
        if (s->buttons & m) in |= 1u << i;
    }
    *native = all;
    return in;
}

/* SOCD cleaning: opposite D-pad directions held together */
static NOINLINE uint32_t socd(uint32_t in)
{
    uint32_t lr = in & (1u << LB_LEFT | 1u << LB_RIGHT), ud = in & (1u << LB_UP | 1u << LB_DOWN);
    uint32_t new_lr = lr & ~last_lr, new_ud = ud & ~last_ud;
    last_lr = lr;
    last_ud = ud;
    if (lr == (1u << LB_LEFT | 1u << LB_RIGHT))
        in &= ~(ss.socd == SOCD_NEUTRAL ? lr : lr & ~new_lr);    /* neutral or last wins */
    if (ud == (1u << LB_UP | 1u << LB_DOWN))
        in &= ~(ss.socd == SOCD_NEUTRAL ? ud
              : ss.socd == SOCD_UP_PRIORITY ? 1u << LB_DOWN : ud & ~new_ud);
    return in;
}

/* remap the logical bitmap and write it back as native bits */
static NOINLINE void buttons_out(cntlr_state_t *s, uint32_t in, uint32_t native)
{
    uint32_t out = 0;
    for (int i = 0; i < LB_COUNT; i++)
        if (in >> i & 1 && ss.remap[i] < LB_COUNT) out |= 1u << ss.remap[i];
    s->buttons &= ~native;
    for (int i = 0; i < LB_COUNT; i++)
        if (out >> i & 1) s->buttons |= lb_mask(s, i);
}

/* D-pad <-> left stick (stick Y: positive = up [inferred]) */
static NOINLINE uint32_t lstick_to_dpad(cntlr_state_t *s, uint32_t in)
{
    if (s->lx > FULL / 2) in |= 1u << LB_RIGHT;
    if (s->lx < -FULL / 2) in |= 1u << LB_LEFT;
    if (s->ly > FULL / 2) in |= 1u << LB_UP;
    if (s->ly < -FULL / 2) in |= 1u << LB_DOWN;
    s->lx = s->ly = 0;
    return in;
}

static NOINLINE uint32_t dpad_to_lstick(cntlr_state_t *s, uint32_t in)
{
    if (in & DPAD_BITS) {
        s->lx = (in >> LB_RIGHT & 1) ? FULL : (in >> LB_LEFT & 1) ? -FULL : 0;
        s->ly = (in >> LB_UP & 1) ? FULL : (in >> LB_DOWN & 1) ? -FULL : 0;
    }
    return in & ~DPAD_BITS;
}

void ss_features(cntlr_state_t *s)
{
    uint32_t native;
    sticks_triggers(s);
    uint32_t in = buttons_in(s, &native);
    if (ss.stick_flags & SF_LSTICK_TO_DPAD) in = lstick_to_dpad(s, in);
    if (ss.stick_flags & SF_DPAD_TO_LSTICK) in = dpad_to_lstick(s, in);
    if (ss.socd) in = socd(in);

    /* toggle: each press flips a latched state */
    latch ^= in & ~prev_in & ss.toggle_mask;
    prev_in = in;
    in = (in & ~ss.toggle_mask) | (latch & ss.toggle_mask);

    /* turbo: held buttons pulse at turbo_rate presses per second (BT clock 3200 Hz) */
    if (ss.turbo_rate && (s->timestamp / (1600u / ss.turbo_rate)) & 1)
        in &= ~ss.turbo_mask;

    buttons_out(s, in, native);
}
