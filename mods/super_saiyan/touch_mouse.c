/*
 * DualShock 4 / DualSense touchpad as a PC mouse while the adapter runs in Xbox 360
 * mode (output mode 2). Tunable from the companion app (ss.tm_*):
 *  - one finger moves the cursor, two fingers scroll
 *  - a short press is a left click, holding it is a right click, pressing and then
 *    moving drags with the left button; the click is hidden from the gamepad
 *  - the cursor stays still until the finger leaves a small "slop" circle around
 *    where it landed / pressed / released, so clicking doesn't nudge it
 */
#include "ss.h"

/* DS4 path: the vendor parser drops touch coordinates; copy them into the
 * same state slots the DualSense parser uses (+0x31 / +0x35). */
int ps_parse_state(void *dev, const uint8_t *report, uint32_t len, cntlr_state_t *s);

int ss_ps_parse(void *dev, const uint8_t *report, uint32_t len, cntlr_state_t *s)
{
    int ok = ps_parse_state(dev, report, len, s);
    if (ok) {
        uint32_t bt = report[0] == 0x11 ? 2 : 0;    /* BT report 0x11 has 2 extra bytes */
        if (len >= bt + 0x2B) {
            uint8_t *dst = (uint8_t *)s + 0x31;
            for (int i = 0; i < 8; i++) dst[i] = report[bt + 0x23 + i];
        }
    }
    return ok;
}

static __attribute__((noinline)) int8_t clamp8(int32_t v) { return v > 127 ? 127 : v < -127 ? -127 : (int8_t)v; }
static int32_t iabs(int32_t v) { return v < 0 ? -v : v; }

enum { C_IDLE, C_PENDING, C_DRAG, C_RIGHT, C_TAP };   /* click state */
static const uint8_t click_buttons[] = { 0, 0, 1, 2, 1 };

static struct {
    int32_t  last_x, last_y, acc_x, acc_y, acc_wheel, anchor_x, anchor_y;
    uint32_t press_t;
    uint8_t  last_id, click, last_sent_btn, moving;
} tm = { .last_id = 0xFF };

#define NOINLINE __attribute__((noinline))

/* Click gestures and the slop that keeps the cursor still around clicks. */
static NOINLINE void tm_click(cntlr_state_t *s, int pressed, int same, int32_t x, int32_t y)
{
    int32_t dist = iabs(x - tm.anchor_x) + iabs(y - tm.anchor_y);
    int rearm = !same;                                /* restart the slop around here */
    if (pressed) {
        if (tm.click == C_IDLE || tm.click == C_TAP) {   /* press: decide later */
            tm.click = C_PENDING;
            tm.press_t = s->timestamp;
            rearm = 1;
        } else if (tm.click == C_PENDING) {
            if (same && dist > ss.tm_drag_slop)
                tm.click = C_DRAG, tm.moving = 1;     /* moved while pressed: drag */
            else if (((s->timestamp - tm.press_t) & 0x0FFFFFFF) * 5 >= (uint32_t)ss.tm_hold_ms * 16)
                tm.click = C_RIGHT;                   /* BT clock: 16 ticks = 5 ms */
        }
    } else if (tm.click == C_PENDING) {
        tm.click = C_TAP, rearm = 1;                  /* short press: left click */
    } else if (tm.click == C_DRAG || tm.click == C_RIGHT) {
        tm.click = C_IDLE, rearm = 1;
    }
    if (rearm) {
        tm.moving = 0;
        tm.anchor_x = x;
        tm.anchor_y = y;
    } else if (!tm.moving && tm.click == C_IDLE) {
        tm.moving = dist > ss.tm_slop;
    }
    if (tm.click != C_IDLE && tm.click != C_DRAG) tm.moving = 0;   /* still while clicking */

}

/* Accumulate motion / scroll and send a report when something changed. */
#define PS_TOUCH_CLICK (1u << 17)   /* LB_CAPTURE native bit on DS4 and DualSense (types 5-7) */

/* Send the accumulated motion when something changed. */
static NOINLINE void tm_send(int div)
{
    int8_t mx = clamp8(tm.acc_x / 8), my = clamp8(tm.acc_y / 8), mw = clamp8(tm.acc_wheel / div);
    uint8_t btn = click_buttons[tm.click];
    if (!ss_mouse_ready() || (!mx && !my && !mw && btn == tm.last_sent_btn))
        return;
    if (ss_mouse_send(btn, mx, my, mw)) {
        tm.acc_x -= mx * 8;
        tm.acc_y -= my * 8;
        tm.acc_wheel -= mw * div;
        tm.last_sent_btn = btn;
        if (tm.click == C_TAP) tm.click = C_IDLE;    /* tap: button up next report */
    }
}

/* Accumulate cursor motion, or wheel motion with two fingers. */
static NOINLINE void tm_motion(int32_t dx, int32_t dy, int down1)
{
    if (down1) {                                      /* two fingers: scroll */
        tm.acc_wheel += (ss.tm_flags & TMF_INVERT_SCROLL) ? dy : -dy;
    } else if (tm.moving) {
        tm.acc_x += dx * ss.tm_speed;
        tm.acc_y += dy * ss.tm_speed;
    }
    tm_send(ss.tm_scroll_div ? ss.tm_scroll_div : 1);
}

/* Decode touch point 0: finger id (0xFF = none), 12-bit X and Y. */
static NOINLINE int tm_point(const uint8_t *t, int32_t *x, int32_t *y)
{
    *x = t[1] | (t[2] & 0x0F) << 8;
    *y = t[2] >> 4 | t[3] << 4;
    return t[0] & 0x80 ? 0xFF : t[0] & 0x7F;
}

void ss_touch_mouse(cntlr_state_t *s)
{
    if (!ss.tm_enable || NS36_OUTPUT_MODE != OUT_XBOX360 || s->type < 5 || s->type > 7)
        return;                                       /* PlayStation controllers only */
    int32_t x, y;
    int id = tm_point(CNTLR_TOUCH(s, 0), &x, &y);
    int same = id != 0xFF && id == tm.last_id;
    int32_t dx = x - tm.last_x, dy = y - tm.last_y;
    tm.last_id = id;
    tm.last_x = x;
    tm.last_y = y;
    tm_click(s, (s->buttons & PS_TOUCH_CLICK) != 0, same, x, y);
    s->buttons &= ~PS_TOUCH_CLICK;                    /* touchpad click, hidden from the pad */
    if (same) tm_motion(dx, dy, !(CNTLR_TOUCH(s, 1)[0] & 0x80));
    else tm_send(ss.tm_scroll_div ? ss.tm_scroll_div : 1);
}

/* input_filter: touchpad first (it consumes the touchpad click), then the features */
void ss_input(cntlr_state_t *s)
{
    ss_touch_mouse(s);
    ss_features(s);
}
