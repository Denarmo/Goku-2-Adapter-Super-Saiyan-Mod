/*
 * ns36.h - Goku 2 Adapter Super Saiyan Mod - firmware mod SDK (main ARM MCU, firmware V3.4)
 *
 * Everything here was recovered by reverse engineering (see docs/).
 * Items marked [inferred] are best guesses; [confirmed] were checked against
 * several call sites in the decompiled code.
 */
#ifndef NS36_H
#define NS36_H

#include <stdint.h>
#include <stddef.h>

/* ------------------------------------------------------------------------ */
/* Normalized controller state (0x54 bytes).                                 */
/* Every controller driver (Switch Pro/2, PS4/PS5, Xbox, wired-via-MSP)      */
/* fills one of these and passes it to the input pipeline, which then        */
/* encodes it for the currently emulated USB output protocol.                */
/* ------------------------------------------------------------------------ */
typedef struct cntlr_state {
    uint32_t type;        /* +0x00 controller type index 0..7 [confirmed: indexes per-type tables] */
    uint32_t timestamp;   /* +0x04 filled in by the pipeline before mods run [confirmed] */
    uint32_t buttons;     /* +0x08 BTN_* bitmap, Nintendo layout [confirmed for Switch Pro] */
    int16_t  lx, ly;      /* +0x0C left stick,  -32768..32767, calibrated, deadzoned [confirmed] */
    int16_t  rx, ry;      /* +0x10 right stick [confirmed] */
    uint16_t zl, zr;      /* +0x14 analog triggers 0..0x7FFF [confirmed] */
    int16_t  accel[3];    /* +0x18 IMU accelerometer [confirmed for Switch Pro] */
    int16_t  gyro[3];     /* +0x1E IMU gyroscope [confirmed for Switch Pro] */
    uint8_t  _unk24[4];   /* +0x24 byte 0 != 0 suppresses settings hotkeys [inferred] */
    uint8_t  _unk28[0x1C];/* +0x28 */
    uint32_t battery;     /* +0x44 raw battery/connection byte from the controller [inferred] */
    uint8_t  _unk48[0x0C];/* +0x48 */
} cntlr_state_t;

_Static_assert(sizeof(cntlr_state_t) == 0x54, "cntlr_state_t layout");

/* NOTE: cntlr_state_t.buttons is in the *connected controller's native* bit
 * layout (it differs per s->type). Use the logical-button helpers below in mods;
 * the BTN_* bits are only the Switch Pro (type 1) layout. [hardware-confirmed] */

/* Logical buttons, as used by the firmware's own mapping tables. */
enum {
    LB_SOUTH = 0, LB_EAST, LB_WEST, LB_NORTH,    /* Xbox A B X Y / PS Cross Circle Square Triangle */
    LB_L, LB_R, LB_SELECT, LB_START, LB_LSTICK, LB_RSTICK,
    LB_UP, LB_DOWN, LB_LEFT, LB_RIGHT, LB_HOME, LB_CAPTURE,
    LB_PADDLE1, LB_PADDLE2, LB_PADDLE3, LB_PADDLE4,
    LB_COUNT
};

/* Firmware table: per controller type (stride 20), logical button -> native bit (0xFF = none). */
#define NS36_BTN_MAP ((const uint8_t *)0x1001c228)

static inline uint32_t lb_mask(const cntlr_state_t *s, int lb)
{
    uint8_t bit = NS36_BTN_MAP[s->type * LB_COUNT + lb];
    return bit == 0xFF ? 0 : 1u << bit;
}
static inline int lb_get(const cntlr_state_t *s, int lb)
{
    uint32_t m = lb_mask(s, lb);
    return m && (s->buttons & m);
}
static inline void lb_set(cntlr_state_t *s, int lb, int on)
{
    uint32_t m = lb_mask(s, lb);
    if (m) s->buttons = on ? (s->buttons | m) : (s->buttons & ~m);
}

/* Switch Pro (type 1) native bits. */
enum {
    BTN_Y       = 1u << 0,  BTN_X       = 1u << 1,  BTN_B      = 1u << 2,  BTN_A    = 1u << 3,
    BTN_R_SR    = 1u << 4,  BTN_R_SL    = 1u << 5,  BTN_R      = 1u << 6,  BTN_ZR   = 1u << 7,
    BTN_MINUS   = 1u << 8,  BTN_PLUS    = 1u << 9,  BTN_RSTICK = 1u << 10, BTN_LSTICK = 1u << 11,
    BTN_HOME    = 1u << 12, BTN_CAPTURE = 1u << 13,
    BTN_DOWN    = 1u << 16, BTN_UP      = 1u << 17, BTN_RIGHT  = 1u << 18, BTN_LEFT = 1u << 19,
    BTN_L_SR    = 1u << 20, BTN_L_SL    = 1u << 21, BTN_L      = 1u << 22, BTN_ZL   = 1u << 23,
};

/* ------------------------------------------------------------------------ */
/* Firmware functions (addresses provided by build/mods/firmware_syms.ld).   */
/* ------------------------------------------------------------------------ */

/* Debug log over the firmware's log UART [confirmed]. */
/* NOTE: when mods are packed into reclaimed log-string flash (the default), log_printf
 * is a no-op. Mods that need the log set "uses_log": true in mod.json. */
int  log_printf(const char *fmt, ...);
/* Mask-ROM C runtime helpers [inferred from usage]. */
void *rom_memcpy(void *dst, const void *src, size_t n);
int   rom_memcmp(const void *a, const void *b, size_t n);

/* Settings/hotkey/turbo engine, called once per input frame [confirmed].
 * The input_filter hook wraps this call. */
uint32_t cntlr_settings_process(cntlr_state_t *s);
/* Submit a state into the USB output pipeline [confirmed]. */
void     cntlr_submit_input(cntlr_state_t *s);
/* Send an encoded input report to the USB host; the report_filter hook wraps
 * this call [confirmed]. */
int      usb_send_input_report(uint8_t *report, uint32_t len, uint32_t flag, uint32_t zero);
/* ---- USB device side [confirmed from decompiled code] ---------------------- */
/* Transfer buffers for usb_ep_send. */
void    *rom_usb_buf_alloc(uint32_t len, uint32_t one);
void     rom_usb_buf_free(void *buf);
/* Open an endpoint from a 7-byte endpoint descriptor (call from SET_CONFIGURATION). */
int      rom_usb_ep_enable(void *usb_dev, const uint8_t *ep_desc, uint32_t zero);
/* Queue an IN transfer; done_cb(xfer) runs when sent (xfer+4 holds buf). 1 = queued. */
uint32_t usb_ep_send(void *buf, uint32_t len, uint32_t ep_addr, void (*done_cb)(void *xfer));
/* Reply to a control request on EP0: dir_in = 1, data is copied. */
uint32_t usb_ep0_reply(int dir_in, const void *data, uint32_t len);
/* Original handlers, for wrapping. */
void     usb_set_config(void);
/* Vendor control requests (callback table 0x1001C218); setup = 8-byte SETUP
 * packet. Return 0 when handled (after usb_ep0_reply), -1 to stall. */
int      usb_req_vendor(const uint8_t *setup);
extern void *g_usb_dev;                      /* USB device handle */
extern uint8_t g_x360_dev_desc[18];          /* Xbox 360 mode device descriptor (RAM) */
extern uint8_t g_x360_cfg_desc[49];          /* Xbox 360 mode configuration descriptor (RAM) */
extern uint8_t g_x360_str_desc0[4];          /* string descriptors served in Xbox 360 mode */
extern uint8_t g_x360_str_desc1[16];
extern uint8_t g_x360_str_desc2[20];
extern uint8_t g_x360_str_desc3[14];

/* HID class requests (callback table 0x1001C214): same contract as usb_req_vendor. */
int      usb_req_class(const uint8_t *setup);
/* Forward a control request to the USB-host co-processor (PS4/PS5 modes). */
int      msp_forward_request(const uint8_t *setup, const uint8_t *data, uint32_t len);

/* ---- persistent config / flash [confirmed from cntlr_flash_write_config] -- */
/* Vendor config block at flash 0x1007B000: "2NUF", g_config (0x1C), checksum. The
 * rest of the 4 KB sector is free; the vendor erases the whole sector on save. */
#define NS36_CFG_FLASH     0x1007B000
#define NS36_CFG_SECTOR    0x7B000
extern uint8_t g_config[0x1C];
uint8_t  cfg_checksum(const void *buf, uint32_t len);
void     cntlr_flash_write_config(void);   /* runs on timer event 3 */
/* (event, group, delay_ms): event 3 / group 10 = save config later */
void     rom_timer_start(uint32_t event, uint32_t group, uint32_t delay_ms);
void     rom_flash_guard(int on);
void     rom_flash_unlock(void);
void     rom_flash_erase_sector(uint32_t offset);
void     rom_flash_program(uint32_t offset, const void *buf, uint32_t len);
void     rom_flash_lock(void);
void     rom_free(void *p);

/* Raw touch point as stored in cntlr_state_t (+0x31 / +0x35) for PS controllers:
 * byte0 bit7 = 1 when NOT touching, bits 0-6 finger id; then 12-bit X, 12-bit Y. */
#define CNTLR_TOUCH(s, n) ((const uint8_t *)(s) + 0x31 + 4 * (n))

/* Fill len bytes with zero [inferred from usage]. */
void     rom_bzero(void *p, size_t len);

/* USB output protocols (value of NS36_OUTPUT_MODE) [confirmed from encoders]. */
enum {
    OUT_SWITCH_PRO = 1,   /* Switch Pro report 0x30 */
    OUT_XBOX360    = 2,   /* Xbox 360 (XInput) */
    OUT_XBOXONE    = 3,   /* Xbox One GIP 0x20 */
    OUT_PS4        = 4,   /* DualShock 4 report 0x01 */
    OUT_PS5        = 5,   /* DualSense report 0x01 */
    OUT_SWITCH2    = 6,   /* Switch 2 Pro report 0x05 */
};

/* ------------------------------------------------------------------------ */
/* Firmware globals                                                          */
/* ------------------------------------------------------------------------ */
/* Current USB output protocol (1..6) selected for the host console/PC [confirmed]. */
#define NS36_OUTPUT_MODE   (*(volatile uint32_t *)0x2000d318)
/* Last state submitted to the pipeline [confirmed]. */
#define NS36_LAST_STATE    (*(volatile cntlr_state_t *)0x2000d478)
/* Persistent user config: turbo per button A,B,X,Y,R1,R2 [confirmed via log text]. */
#define NS36_CFG_TURBO     ((volatile uint8_t *)0x2000d5b8)
#define NS36_CFG_MODE_MASK (*(volatile uint8_t  *)0x2000d5c3)
/* Warm-boot mailbox: AA mode ~mode 55 survives reset [confirmed]. */
#define NS36_BOOT_MAILBOX  ((volatile uint8_t *)0x2000fffc)

/* Put in front of functions/data that must be kept even if unreferenced. */
#define MOD_KEEP __attribute__((used))

#endif /* NS36_H */
