/*
 * super_saiyan - firmware side of the companion app.
 *
 * Settings live in one packed struct that the app reads and writes byte-for-byte
 * over a HID feature report (see config.c), and that is saved to flash next to the
 * vendor config. Keep the layout in sync with app/lib/protocol.dart.
 */
#ifndef SS_H
#define SS_H

#include "ns36.h"

#define SS_PROTO_VERSION   2       /* 2: INFO reports the battery */
#define SS_FW_VERSION      0x0110      /* mod firmware 1.1 */
#define SS_SETTINGS_VER    1

/* stick_flags */
#define SF_INV_LX          0x01
#define SF_INV_LY          0x02
#define SF_INV_RX          0x04
#define SF_INV_RY          0x08
#define SF_SWAP_STICKS     0x10
#define SF_DPAD_TO_LSTICK  0x20        /* D-pad drives the left stick */
#define SF_LSTICK_TO_DPAD  0x40        /* left stick drives the D-pad */
/* trig_flags */
#define TF_HAIR_L          0x01
#define TF_HAIR_R          0x02
/* tm_flags */
#define TMF_INVERT_SCROLL  0x01
/* socd */
enum { SOCD_OFF, SOCD_NEUTRAL, SOCD_LAST_WINS, SOCD_UP_PRIORITY };

typedef struct __attribute__((packed)) {
    uint8_t  version;            /* SS_SETTINGS_VER */
    uint8_t  size;               /* sizeof(ss_settings_t) */
    /* touchpad mouse (PS4/PS5 controller, Xbox 360 output mode) */
    uint8_t  tm_enable;
    uint8_t  tm_speed;           /* cursor speed in 1/8: 6 = 0.75x */
    uint8_t  tm_scroll_div;      /* touch units per wheel notch */
    uint8_t  tm_flags;           /* TMF_* */
    uint16_t tm_slop;            /* travel before the cursor moves (touch units) */
    uint16_t tm_drag_slop;       /* travel while pressed before a left-drag starts */
    uint16_t tm_hold_ms;         /* hold this long for a right click */
    /* buttons (logical indices, LB_*) */
    uint8_t  remap[LB_COUNT];    /* output button for each physical button; 0xFF = disabled */
    uint32_t turbo_mask;         /* buttons with turbo */
    uint8_t  turbo_rate;         /* presses per second */
    uint32_t toggle_mask;        /* buttons that latch (tap on, tap off) */
    uint8_t  socd;               /* SOCD_* for the D-pad */
    /* sticks: [0] left, [1] right */
    uint8_t  stick_dz[2];        /* deadzone, % of full deflection */
    uint8_t  stick_anti_dz[2];   /* smallest non-zero output, % */
    uint8_t  stick_curve[2];     /* 0 = linear .. 100 = quadratic response */
    uint8_t  stick_flags;        /* SF_* */
    /* triggers: [0] left, [1] right */
    uint8_t  trig_dz[2];         /* % */
    uint8_t  trig_flags;         /* TF_* */
} ss_settings_t;

extern ss_settings_t ss;

void ss_defaults(void);
void ss_load(void);
void ss_request_save(void);
void ss_touch_mouse(cntlr_state_t *s);
void ss_features(cntlr_state_t *s);
int  ss_mouse_ready(void);
int  ss_mouse_send(uint8_t btn, int8_t x, int8_t y, int8_t wheel);   /* 1 = queued */
/* feature report 2 (config channel), called from usb.c */
uint32_t ss_config_get(uint8_t *out);           /* GET_REPORT -> length */
void     ss_config_set(const uint8_t *in, uint32_t len);   /* SET_REPORT data */

#endif
